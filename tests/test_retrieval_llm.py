import math

import pytest

from src.common.config import Settings
from src.common.llm import FakeLLM, Usage, UsageLedger, get_llm, hash_embed
from src.payer_mock.crd import CrdRequest, check
from src.policies.loader import load_policies
from src.policies.retriever import InMemoryHybridRetriever, chunk_policy, rrf, tokens
from src.priorauth.models import NoteFindings
from src.priorauth.pipeline import retrieve_policy

POLICIES = load_policies()
CHUNKS = [c for p in POLICIES.values() for c in chunk_policy(p)]
RET = InMemoryHybridRetriever(CHUNKS, lambda ts: [hash_embed(t) for t in ts])


def test_hash_embed_deterministic_unit_norm():
    a, b = hash_embed("knee pain"), hash_embed("knee pain")
    assert a == b and math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)


def test_rrf_math():
    s = rrf([["a", "b"], ["b", "c"]], k=60)
    assert s["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert max(s, key=s.get) == "b"


def test_one_chunk_per_section_with_breadcrumb():
    p = POLICIES["ACME-POL-LSMRI"]
    chunks = chunk_policy(p)
    assert {c.section_id for c in chunks} == set(p.sections)
    c = next(c for c in chunks if c.section_id == "LSMRI-2.2")
    assert "LSMRI-2 Coverage criteria > LSMRI-2.2" in c.content


def test_search_filters_by_policy_and_is_deterministic():
    h1 = RET.search("conservative therapy weeks", "ACME-POL-KMRI", k=5)
    h2 = RET.search("conservative therapy weeks", "ACME-POL-KMRI", k=5)
    assert [h.chunk.chunk_id for h in h1] == [h.chunk.chunk_id for h in h2]
    assert all(h.chunk.policy_id == "ACME-POL-KMRI" for h in h1)
    assert h1[0].chunk.section_id == "KMRI-2.2"


def test_lexical_ignores_stopwords():
    assert tokens("The MRI of the knee") == ["mri", "knee"]


@pytest.mark.parametrize("pid", sorted(POLICIES))
def test_retrieve_policy_finds_every_criterion(pid):
    p = POLICIES[pid]
    crd = check(CrdRequest(service_code=p.services[0].code, plan_type="HMO"))
    docs = [d.document for d in crd.documents_required]
    crit, sections, missing = retrieve_policy(RET, p, p.services[0].display, docs)
    assert missing == [] and [c.id for c in crit] == [c.id for c in p.criteria]
    assert sections  # section ids are kept for citations


def test_fake_llm_records_usage():
    llm = FakeLLM(lambda step, ctx, schema: {"findings": []})
    out = llm.complete_json(step="s", system="x", user="y", schema=NoteFindings)
    assert out.findings == [] and llm.ledger.totals()["calls"] == 1
    assert llm.ledger.totals(since=1)["calls"] == 0


def test_cost_unknown_without_prices(monkeypatch):
    monkeypatch.delenv("LLM_PRICE_INPUT_PER_1M", raising=False)
    led = UsageLedger()
    led.add(Usage("openai", "m", "s", 10, 5, 0.1, None))
    assert led.totals()["cost_usd"] is None


def test_cost_from_env_prices(monkeypatch):
    from src.common.llm import _price

    monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "2")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "8")
    assert _price(1_000_000, 500_000) == pytest.approx(6.0)


def test_get_llm_defaults_to_fake():
    assert get_llm(Settings(_env_file=None)).name == "fake"


def test_strict_schema_has_no_extras():
    schema = NoteFindings.model_json_schema()
    item = schema["$defs"]["NoteFinding"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"criterion_id", "note_id", "stance", "quote"}
