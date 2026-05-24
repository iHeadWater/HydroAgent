"""Compile Experiment III (paper §4.3) result tables from run outputs.

Reads:
  results/paper/exp3/exp3_results.json   -> Table 4.4 (workflow + efficiency)
  experiment/_annot/llm_scores.csv       -> Table 4.5 (DiagScore), if present

Emits both tables as markdown, aggregated per knowledge condition (K0..K4)
averaged across tasks T1-T6, ready to paste into the paper.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/compile_exp3_tables.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS = Path("results/paper/exp3/exp3_results.json")
DIAG_CSV = Path("experiment/_annot/llm_scores.csv")
DIMENSIONS = ["D1", "D2", "D3", "D4", "D5"]
COND_ORDER = ["K0", "K1", "K2", "K3"]
COND_LABEL = {
    "K0": "tools only", "K1": "+procedural",
    "K2": "+domain", "K3": "+full",
}


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return sum(xs) / len(xs) if xs else float("nan")


def _load():
    d = json.load(open(RESULTS, encoding="utf-8"))
    by_cond = defaultdict(list)
    for r in d["results"]:
        by_cond[r["condition_id"]].append(r)
    return by_cond


def main_table():
    """Threshold + diminishing-returns view: success rate & cost vs knowledge level."""
    if not RESULTS.exists():
        print(f"[skip] {RESULTS} not found")
        return
    by_cond = _load()
    print("## Table 4.4 — Task success rate, result quality and cost vs knowledge level\n")
    print("| Cond | level | n | Task success | mean test-NSE | Reasoning turns "
          "| Tokens (mean) | Cached % | Wall (s) |")
    print("|------|-------|---|------|------|------|------|------|------|")
    for c in COND_ORDER:
        rs = by_cond.get(c)
        if not rs:
            continue
        n = len(rs)
        succ = sum(1 for r in rs if r.get("task_success")) / n * 100
        nse = _mean([r.get("test_nse") for r in rs])
        turns = _mean([r["efficiency"]["llm_calls"] for r in rs])
        tok = _mean([r["efficiency"]["tokens"]["total"] for r in rs])
        cp = sum(r["efficiency"]["tokens"]["cached"] for r in rs)
        pp = sum(r["efficiency"]["tokens"]["prompt"] for r in rs)
        cached_pct = 100 * cp / pp if pp else float("nan")
        wall = _mean([r["wall_clock_total_s"] for r in rs])
        print(f"| {c} | {COND_LABEL.get(c,'')} | {n} | {succ:.0f}% | {nse:.3f} | "
              f"{turns:.1f} | {tok:,.0f} | {cached_pct:.0f}% | {wall:.0f} |")
    print()


def success_matrix():
    """Per (condition x task) task_success — locates exactly where each level flips."""
    if not RESULTS.exists():
        return
    by_cond = _load()
    tasks = sorted({r["task_id"] for rs in by_cond.values() for r in rs})
    print("## Success matrix (task_success per condition × task)\n")
    print("| Cond | " + " | ".join(tasks) + " |")
    print("|------|" + "|".join("---" for _ in tasks) + "|")
    for c in COND_ORDER:
        rs = {r["task_id"]: r for r in by_cond.get(c, [])}
        cells = []
        for t in tasks:
            r = rs.get(t)
            if not r:
                cells.append("-")
            else:
                mark = "PASS" if r.get("task_success") else "FAIL"
                cap = " (cap)" if r.get("hit_cap") else ""
                cells.append(f"{mark}{cap}")
        print(f"| {c} | " + " | ".join(cells) + " |")
    print()


def table_4_5():
    if not DIAG_CSV.exists():
        print(f"## Table 4.5 — DiagScore\n\n[pending] {DIAG_CSV} not found; "
              "run llm_rater.py first.\n")
        return
    rows = list(csv.DictReader(open(DIAG_CSV, encoding="utf-8")))
    by_cond = defaultdict(list)
    for row in rows:
        try:
            scores = {dm: int(row[dm]) for dm in DIMENSIONS}
        except (ValueError, KeyError):
            continue
        by_cond[row["condition"]].append(scores)

    print("## Table 4.5 — Rubric-based diagnostic reasoning score (per condition)\n")
    print("| Cond | n | D1 problem | D2 evidence | D3 causality | D4 action "
          "| D5 limits | DiagScore (0-1) |")
    print("|------|---|------|------|------|------|------|------|")
    for c in COND_ORDER:
        items = by_cond.get(c)
        if not items:
            continue
        n = len(items)
        dim_means = {dm: _mean([it[dm] for it in items]) for dm in DIMENSIONS}
        diag = _mean([sum(it.values()) / 10 for it in items])
        print(f"| {c} | {n} | " + " | ".join(f"{dim_means[dm]:.2f}" for dm in DIMENSIONS)
              + f" | {diag:.3f} |")
    print()


if __name__ == "__main__":
    main_table()
    success_matrix()
    table_4_5()
