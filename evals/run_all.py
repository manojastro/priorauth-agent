"""Run every eval that exists so far and write evals/reports/summary_<date>.md + .json.

Usage: uv run python -m evals.run_all [--live]
Runs intake, criteria (full pipeline) and criteria baseline (no retrieval, no verification).
"""

from __future__ import annotations

import argparse

from evals.common import SPLITS, meta_block, run_metadata, write_report
from evals.runners import criteria_eval, intake_eval


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    live = ap.parse_args().live
    intake = intake_eval.run(live)
    crit = criteria_eval.run(live)
    base = criteria_eval.run(live, baseline=True)
    meta = run_metadata(intake["meta"]["data_source"])
    meta["extractor"] = crit["meta"]["extractor"]
    summary = {
        "meta": meta,
        "intake": intake["metrics"],
        "criteria": crit["metrics"],
        "baseline": base["metrics"],
    }
    lines = [
        "# Eval summary\n",
        meta_block(meta),
        "",
        "| Metric | dev | holdout |",
        "|---|---|---|",
    ]
    for k, label in (("eligible", "Eligibility accuracy"), ("pa_required", "PA-required accuracy")):
        cells = [
            f"{intake['metrics'][s][k]['accuracy']:.2%} (n={intake['metrics'][s][k]['n']})"
            for s in SPLITS
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    for k, label in criteria_eval.NAMES.items():
        for suffix, res in (("", crit), (" (baseline)", base)):
            cells = [
                "n/a" if res["metrics"][s][k] is None else str(res["metrics"][s][k]) for s in SPLITS
            ]
            lines.append(f"| {label}{suffix} | " + " | ".join(cells) + " |")
    lines += ["", f"Extractor: {meta['extractor']}"]
    j, m = write_report("summary", summary, "\n".join(lines) + "\n")
    print(f"wrote {j} and {m}")


if __name__ == "__main__":
    main()
