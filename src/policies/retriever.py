"""Policy chunking and hybrid retrieval (vector cosine + lexical, merged by reciprocal rank fusion).

Two backends with the same interface:
- InMemoryHybridRetriever: BM25 + cosine in Python. Used offline and in tests.
- PgHybridRetriever: pgvector cosine + Postgres full-text search. Needs the docker stack.
Chunks are one policy section each, so section IDs survive into citations.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable

from pydantic import BaseModel

from src.policies.loader import Policy

RRF_K = 60
_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("a an and or the of to in for on with by is are be at as from this that".split())

Embedder = Callable[[list[str]], list[list[float]]]


class Chunk(BaseModel):
    chunk_id: str
    policy_id: str
    policy_version: str
    section_id: str
    title: str
    content: str


class Hit(BaseModel):
    chunk: Chunk
    score: float
    vector_rank: int | None
    lexical_rank: int | None


def _breadcrumb(p: Policy, section_id: str) -> str:
    """'Policy title > LSMRI-2 Coverage criteria > LSMRI-2.1 Qualifying diagnosis'."""
    parts = [p.title]
    if "." in section_id:
        parent = p.sections.get(section_id.split(".")[0])
        if parent:
            parts.append(f"{parent.id} {parent.title}")
    s = p.sections[section_id]
    parts.append(f"{s.id} {s.title}")
    return " > ".join(parts)


def chunk_policy(p: Policy) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"{p.policy_id}:{s.id}",
            policy_id=p.policy_id,
            policy_version=p.version,
            section_id=s.id,
            title=s.title,
            content=f"{_breadcrumb(p, s.id)}. {s.text}",
        )
        for s in p.sections.values()
    ]


def tokens(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if t not in _STOP]


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


class InMemoryHybridRetriever:
    def __init__(self, chunks: list[Chunk], embed: Embedder):
        self.chunks = {c.chunk_id: c for c in chunks}
        self.embed = embed
        ids = list(self.chunks)
        self._vecs = dict(zip(ids, embed([self.chunks[i].content for i in ids]), strict=True))
        self._toks = {i: tokens(self.chunks[i].content) for i in ids}
        n = len(ids)
        df = Counter(t for i in ids for t in set(self._toks[i]))
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avgdl = sum(len(v) for v in self._toks.values()) / max(n, 1)

    def _bm25(self, q: list[str], cid: str, k1: float = 1.5, b: float = 0.75) -> float:
        tf = Counter(self._toks[cid])
        dl = len(self._toks[cid])
        s = 0.0
        for t in q:
            if t in tf:
                f = tf[t]
                s += self._idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self._avgdl))
        return s

    def search(self, query: str, policy_id: str | None = None, k: int = 10) -> list[Hit]:
        cands = [c for c in self.chunks.values() if policy_id in (None, c.policy_id)]
        qv = self.embed([query])[0]
        q = tokens(query)
        vec = sorted(cands, key=lambda c: (-_cos(qv, self._vecs[c.chunk_id]), c.chunk_id))
        lex_scored = [(self._bm25(q, c.chunk_id), c.chunk_id) for c in cands]
        lex = [cid for s, cid in sorted(lex_scored, key=lambda x: (-x[0], x[1])) if s > 0]
        vr = [c.chunk_id for c in vec]
        fused = rrf([vr, lex])
        order = sorted(fused, key=lambda cid: (-fused[cid], cid))[:k]
        return [
            Hit(
                chunk=self.chunks[cid],
                score=round(fused[cid], 6),
                vector_rank=vr.index(cid) + 1,
                lexical_rank=lex.index(cid) + 1 if cid in lex else None,
            )
            for cid in order
        ]


DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS policy_chunks (
  chunk_id text PRIMARY KEY,
  policy_id text NOT NULL,
  policy_version text NOT NULL,
  section_id text NOT NULL,
  title text NOT NULL,
  content text NOT NULL,
  embedding vector({dim}) NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX IF NOT EXISTS policy_chunks_tsv ON policy_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS policy_chunks_policy ON policy_chunks (policy_id);
"""

SEARCH_SQL = """
WITH v AS (
  SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> %(qv)s::vector, chunk_id) AS r
  FROM policy_chunks WHERE (%(pid)s::text IS NULL OR policy_id = %(pid)s)
  ORDER BY embedding <=> %(qv)s::vector, chunk_id LIMIT 50
), l AS (
  SELECT chunk_id,
         row_number() OVER (ORDER BY ts_rank_cd(tsv, to_tsquery('english', %(tq)s)) DESC, chunk_id)
           AS r
  FROM policy_chunks
  WHERE (%(pid)s::text IS NULL OR policy_id = %(pid)s) AND tsv @@ to_tsquery('english', %(tq)s)
  LIMIT 50
)
SELECT c.chunk_id, c.policy_id, c.policy_version, c.section_id, c.title, c.content,
       v.r AS vr, l.r AS lr,
       COALESCE(1.0 / (%(k)s + v.r), 0) + COALESCE(1.0 / (%(k)s + l.r), 0) AS score
FROM policy_chunks c
LEFT JOIN v USING (chunk_id) LEFT JOIN l USING (chunk_id)
WHERE v.r IS NOT NULL OR l.r IS NOT NULL
ORDER BY score DESC, c.chunk_id
LIMIT %(lim)s
"""


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


class PgHybridRetriever:
    """pgvector + Postgres FTS. Status: built, not run (needs the docker stack)."""

    def __init__(self, conn, embed: Embedder):
        self.conn = conn
        self.embed = embed

    def index(self, chunks: list[Chunk], dim: int) -> None:
        self.conn.execute(DDL.format(dim=int(dim)))
        vecs = self.embed([c.content for c in chunks])
        for c, v in zip(chunks, vecs, strict=True):
            self.conn.execute(
                """INSERT INTO policy_chunks
                   (chunk_id, policy_id, policy_version, section_id, title, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                   ON CONFLICT (chunk_id) DO UPDATE SET content = EXCLUDED.content,
                     embedding = EXCLUDED.embedding, policy_version = EXCLUDED.policy_version""",
                (c.chunk_id, c.policy_id, c.policy_version, c.section_id, c.title, c.content,
                 _vec_literal(v)),
            )  # fmt: skip
        self.conn.commit()

    def search(self, query: str, policy_id: str | None = None, k: int = 10) -> list[Hit]:
        tq = " | ".join(sorted(set(tokens(query)))) or "x"
        rows = self.conn.execute(
            SEARCH_SQL,
            {"qv": _vec_literal(self.embed([query])[0]), "pid": policy_id, "tq": tq,
             "k": RRF_K, "lim": k},
        ).fetchall()  # fmt: skip
        return [
            Hit(
                chunk=Chunk(
                    chunk_id=r[0],
                    policy_id=r[1],
                    policy_version=r[2],
                    section_id=r[3],
                    title=r[4],
                    content=r[5],
                ),
                score=float(r[8]),
                vector_rank=r[6],
                lexical_rank=r[7],
            )  # fmt: skip
            for r in rows
        ]
