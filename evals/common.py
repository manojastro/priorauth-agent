"""Shared eval helpers: ground truth, git provenance, report writing."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.common.config import SYNTHETIC_BANNER

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH = ROOT / "data" / "cases" / "ground_truth.json"
REPORTS = ROOT / "evals" / "reports"
SPLITS = ("dev", "holdout")


def load_ground_truth(path: Path = GROUND_TRUTH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_provenance() -> dict:
    def run(*args: str) -> str:
        try:
            out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else ""
        except OSError:
            return ""

    commit = run("rev-parse", "HEAD")
    dirty = bool(run("status", "--porcelain"))
    return {"commit": commit or "uncommitted", "dirty_worktree": dirty}


def run_metadata(source: str) -> dict:
    return {
        "banner": SYNTHETIC_BANNER,
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_source": source,
        **git_provenance(),
    }


def accuracy(pairs: list[tuple[object, object]]) -> dict:
    n = len(pairs)
    correct = sum(1 for got, want in pairs if got == want)
    return {"n": n, "correct": correct, "accuracy": round(correct / n, 4) if n else None}


def write_report(name: str, payload: dict, markdown: str) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = payload["meta"]["run_at_utc"][:10]
    j = REPORTS / f"{name}_{day}.json"
    m = REPORTS / f"{name}_{day}.md"
    j.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    m.write_text(markdown, encoding="utf-8")
    return j, m


def meta_block(meta: dict) -> str:
    return (
        f"> **{SYNTHETIC_BANNER}**\n\n"
        f"- Run at (UTC): {meta['run_at_utc']}\n"
        f"- Commit: `{meta['commit']}` (dirty worktree: {meta['dirty_worktree']})\n"
        f"- Data source: {meta['data_source']}\n"
    )
