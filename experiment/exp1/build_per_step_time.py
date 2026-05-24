"""Emit experiment/exp1/tables/table_exp1_per_step_time.csv.

Per-trial decision-time comparison in the same unit:
  - M0 default_script:    no decision step (default menu hardcoded), 0 s
  - M1 human_runner:      active_seconds (input-prompt-to-input-prompt interval)
  - M2 hydroagent_menu:   llm_tokens.decision_elapsed_s (LLM call latency)
  - M3 random_menu:       0 s (no decision step, just sample)

Plus per-trial token cost (only LLM pays) and outcome NSE for cross-referencing.

This is the table to read when discussing "token replaces time" — both columns
are directly comparable across methods because they represent the same act
(choosing one menu entry given the previous trial's feedback).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP1 = ROOT / "results" / "paper" / "exp1_v2"
TABLES = Path(__file__).resolve().parent / "tables"

METHODS = {
    "M0": "default_script",
    "M1": "human_script",
    "M2": "hydroagent_menu",
    "M3": "random_menu",
}


def _metric(r: dict, period: str, name: str):
    m = r.get(f"{period}_metrics") or {}
    v = m.get(name)
    return v if isinstance(v, (int, float)) else None


def _dec_time(r: dict, method: str) -> float:
    """Decision time in seconds for a single trial, by method semantics."""
    if method == "M1":
        return r.get("active_seconds") or 0
    if method == "M2":
        return (r.get("llm_tokens") or {}).get("decision_elapsed_s") or 0
    return 0  # M0, M3 have no decision step


def main() -> None:
    rows = []
    for label, sub in METHODS.items():
        path = EXP1 / sub / "trials.jsonl"
        if not path.exists():
            continue
        records = [json.loads(l) for l in open(path, encoding="utf-8")]
        for ord_idx, r in enumerate(records, start=1):
            dec = r.get("decision") or {}
            tok = r.get("llm_tokens") or {}
            rows.append({
                "method": label,
                "basin_id": r.get("basin_id"),
                "trial_idx": r.get("trial_idx") or ord_idx,
                "decision_time_s": round(_dec_time(r, label), 2),
                "decision_time_kind": (
                    "human_active" if label == "M1"
                    else "llm_decision_elapsed" if label == "M2"
                    else "none"
                ),
                "prompt_tokens":     tok.get("prompt_tokens") or 0,
                "completion_tokens": tok.get("completion_tokens") or 0,
                "cached_tokens":     tok.get("cached_tokens") or 0,
                "total_tokens":      tok.get("total_tokens") or 0,
                "wall_time_s":       round(r.get("wall_time_s") or 0, 1),
                "test_NSE":          _metric(r, "test", "NSE"),
                "test_KGE":          _metric(r, "test", "KGE"),
                "objective":         dec.get("objective"),
                "budget_level":      dec.get("budget_level"),
                "range_policy":      dec.get("range_policy"),
                "stop_flag":         dec.get("stop"),
            })
    if not rows:
        print("No exp1 trials.")
        return
    rows.sort(key=lambda r: (r["method"], r["basin_id"], r["trial_idx"]))
    TABLES.mkdir(parents=True, exist_ok=True)
    out = TABLES / "table_exp1_per_step_time.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")

    # per-method aggregate
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "dec_sum": 0.0, "tok_sum": 0, "wall_sum": 0.0})
    for r in rows:
        a = agg[r["method"]]
        a["n"] += 1
        a["dec_sum"] += r["decision_time_s"]
        a["tok_sum"] += r["total_tokens"]
        a["wall_sum"] += r["wall_time_s"]
    print()
    print(f"{'M':3} {'n':>3} {'mean_dec_s':>10} {'total_dec_s':>11} {'total_tokens':>12} {'total_wall_s':>12}")
    for m, a in sorted(agg.items()):
        mean_dec = a["dec_sum"] / a["n"] if a["n"] else 0
        print(f"{m:3} {a['n']:>3} {mean_dec:>10.2f} {a['dec_sum']:>11.1f} {a['tok_sum']:>12} {a['wall_sum']:>12.0f}")


if __name__ == "__main__":
    main()
