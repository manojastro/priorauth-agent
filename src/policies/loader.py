"""Load synthetic payer policies (markdown + YAML front matter) with stable section IDs."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
PLAN_TYPES = ("HMO", "PPO", "EPO")

_FRONT = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
_HEADING = re.compile(r"^(#{2,4})\s+([A-Z]+-\d+(?:\.\d+)?)\s+(.+)$", re.M)

CriterionKind = Literal[
    "condition",
    "procedure_duration",
    "procedure_count",
    "procedure_done",
    "medication_trial",
    "observation_threshold",
    "observation_result",
    "note",
]


class Coding(BaseModel):
    code: str
    display: str


class Criterion(BaseModel):
    id: str
    kind: CriterionKind
    window_days: int
    codes: list[str] = []
    non_qualifying_codes: list[str] = []
    code: str | None = None
    system: str | None = None
    display: str | None = None
    min_days: int | None = None
    min_count: int | None = None
    rxnorm: list[Coding] = []
    value_type: Literal["integer", "quantity"] | None = None
    unit: str | None = None
    op: Literal[">=", "<"] | None = None
    value: float | None = None
    met_value: str | None = None
    not_met_value: str | None = None
    text: str = ""


class Service(BaseModel):
    code: str
    display: str
    hcpcs: str | None = None


class Section(BaseModel):
    id: str
    level: int
    title: str
    text: str


class Policy(BaseModel):
    policy_id: str
    version: str
    title: str
    services: list[Service]
    pa_required: dict[str, bool]
    criteria: list[Criterion]
    sections: dict[str, Section]
    source_file: str


def parse_policy(raw: str, source_file: str = "") -> Policy:
    raw = raw.replace("\r\n", "\n")
    m = _FRONT.match(raw)
    if not m:
        raise ValueError(f"{source_file}: missing YAML front matter")
    meta = yaml.safe_load(m.group(1))
    body = m.group(2)
    heads = list(_HEADING.finditer(body))
    sections: dict[str, Section] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        sid = h.group(2)
        if sid in sections:
            raise ValueError(f"{source_file}: duplicate section id {sid}")
        sections[sid] = Section(
            id=sid,
            level=len(h.group(1)),
            title=h.group(3).strip(),
            text=body[h.end() : end].strip(),
        )
    criteria = []
    for c in meta["criteria"]:
        if c["id"] not in sections:
            raise ValueError(f"{source_file}: criterion {c['id']} has no section heading")
        s = sections[c["id"]]
        criteria.append(Criterion(**c, text=f"{s.title}. {s.text}"))
    return Policy(
        policy_id=meta["policy_id"],
        version=str(meta["version"]),
        title=meta["title"],
        services=meta["services"],
        pa_required=meta["pa_required"],
        criteria=criteria,
        sections=sections,
        source_file=source_file,
    )


@lru_cache
def load_policies(policy_dir: Path = POLICY_DIR) -> dict[str, Policy]:
    out: dict[str, Policy] = {}
    for f in sorted(policy_dir.glob("*.md")):
        p = parse_policy(f.read_text(encoding="utf-8"), f.name)
        out[p.policy_id] = p
    return out


def policy_for_service(service_code: str) -> Policy | None:
    for p in load_policies().values():
        if any(s.code == service_code for s in p.services):
            return p
    return None
