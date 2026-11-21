"""verify_citations: deterministic. Re-fetch every cited resource and confirm the cited value or
quote/span really exists there, and that the resource belongs to this patient."""

from __future__ import annotations

import re

from src.common.fhir_source import FhirSource, NotFound
from src.priorauth.models import EvidenceItem
from src.priorauth.notes import is_instruction_like, note_text

_SEG = re.compile(r"([A-Za-z_]+)(?:\[(\d+)\])?")


def get_path(res: dict, path: str):
    cur = res
    for part in path.split("."):
        m = _SEG.fullmatch(part)
        if not m or not isinstance(cur, dict) or m.group(1) not in cur:
            return None
        cur = cur[m.group(1)]
        if m.group(2) is not None:
            i = int(m.group(2))
            if not isinstance(cur, list) or i >= len(cur):
                return None
            cur = cur[i]
    return cur


def _same(actual, expected: str) -> bool:
    if actual is None:
        return False
    if isinstance(actual, str) and len(expected) == 10 and actual[:10] == expected:
        return True  # date or dateTime compared at day precision
    return str(actual) == expected


def _patient_ref(res: dict) -> str | None:
    for f in ("subject", "beneficiary", "patient"):
        if isinstance(res.get(f), dict):
            return res[f].get("reference")
    return None


def verify_item(src: FhirSource, item: EvidenceItem, patient_ref: str) -> EvidenceItem:
    it = item.model_copy()
    try:
        res = src.read(it.resource_type, it.resource_id)
    except NotFound:
        it.verified, it.verify_note = False, "cited resource not found"
        return it
    if _patient_ref(res) != patient_ref:
        it.verified, it.verify_note = False, "resource belongs to a different patient"
        return it
    if it.source == "note":
        text = note_text(res)
        if not it.quote or it.span is None:
            it.verified, it.verify_note = False, "quote not found verbatim in note"
            return it
        a, b = it.span
        if text[a:b] != it.quote:
            it.verified, it.verify_note = False, "span does not match quote"
            return it
        if is_instruction_like(it.quote):
            it.verified, it.verify_note = False, "quote is an instruction-like line, not evidence"
            return it
        it.verified, it.verify_note = True, "quote found at span"
        return it
    for path, expected in it.checks.items():
        if not _same(get_path(res, path), expected):
            it.verified, it.verify_note = False, f"value mismatch at {path}"
            return it
    it.verified, it.verify_note = bool(it.checks), "all cited values present"
    return it


def verify_citations(
    src: FhirSource, items: list[EvidenceItem], patient_ref: str
) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    checked = [verify_item(src, i, patient_ref) for i in items]
    return [i for i in checked if i.verified], [i for i in checked if not i.verified]
