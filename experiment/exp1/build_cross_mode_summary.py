"""Emit experiment/exp1/tables/table_exp1_cross_mode_summary.csv.

One row per (basin, method) with best-of-N test NSE/KGE + total cost.
Methods cover M0 budget ablation (min/default/max), M1 (human, Mode A/B),
M2 (LLM, Mode A/B). This is THE table the exp1 paper draws its 5 findings
from.

Also emits the per-method panel mean as a separate header summary.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP1_A    = ROOT / "results" / "paper" / "exp1_v2"
EXP1_B    = ROOT / "results" / "paper" / "exp1_v2_modeb"
EXP1_B_V6 = ROOT / "results" / "paper" / "exp1_v2_modeb_m2_v6"
TABLES = Path(__file__).resolve().parent / "tables"


def _pick_m2b_root() -> Path:
    live = EXP1_B / "hydroagent_menu" / "trials.jsonl"
    if live.exists():
        n = sum(1 for _ in open(live, encoding="utf-8"))
        if n >= 18:
            return EXP1_B
    return EXP1_B_V6 if (EXP1_B_V6 / "hydroagent_menu" / "trials.jsonl").exists() else EXP1_B


_M2B_ROOT = _pick_m2b_root()

METHODS = [
    # (label,         root_dir,    subdir)
    ("M0_min",        EXP1_A,      "default_script_min"),
    ("M0",            EXP1_A,      "default_script"),
    ("M0_max",        EXP1_A,      "default_script_max"),
    ("M2_A",          EXP1_A,      "hydroagent_menu"),
    ("M1_B",          EXP1_B,      "human_script"),
    ("M2_B",          _M2B_ROOT,   "hydroagent_menu"),
]


def _load(p):
    if not p.exists(): return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def main() -> None:
    # collect best NSE/KGE + total cost per (basin, method)
    rows = []
    method_aggregate = {}
    for label, root, sub in METHODS:
        path = root / sub / "trials.jsonl"
        records = _load(path)
        if not records:
            continue
        by_b = defaultdict(list)
        for r in records:
            by_b[r["basin_id"]].append(r)
        per_basin = {}
        for b, recs in by_b.items():
            valid = [r for r in recs if isinstance((r.get("test_metrics") or {}).get("NSE"), (int, float))]
            if not valid:
                per_basin[b] = None
                continue
            best = max(valid, key=lambda r: (r["test_metrics"] or {}).get("NSE"))
            total_tokens = sum(((r.get("llm_tokens") or {}).get("total_tokens") or 0) for r in recs)
            total_wall = sum((r.get("wall_time_s") or 0) for r in recs)
            total_active = sum((r.get("active_seconds") or 0) for r in recs)
            total_llm_dec = sum(((r.get("llm_tokens") or {}).get("decision_elapsed_s") or 0) for r in recs)
            per_basin[b] = {
                "best_test_NSE": (best["test_metrics"] or {}).get("NSE"),
                "best_test_KGE": (best["test_metrics"] or {}).get("KGE"),
                "best_train_NSE": (best["train_metrics"] or {}).get("NSE"),
                "best_trial_idx": best.get("trial_idx"),
                "best_menu": f"{(best.get('decision') or {}).get('objective')}/{(best.get('decision') or {}).get('budget_level')}/{(best.get('decision') or {}).get('range_policy')}",
                "best_rep": (best.get("algorithm_params") or {}).get("rep"),
                "best_ngs": (best.get("algorithm_params") or {}).get("ngs"),
                "n_trials": len(recs),
                "total_tokens": total_tokens,
                "total_wall_s": round(total_wall, 1),
                "total_active_s": round(total_active, 1),
                "total_llm_dec_s": round(total_llm_dec, 1),
            }
            rows.append({
                "method": label,
                "basin_id": b,
                **per_basin[b],
            })
        # method-level mean
        valid_basins = [v for v in per_basin.values() if v is not None and isinstance(v.get("best_test_NSE"), (int, float))]
        if valid_basins:
            method_aggregate[label] = {
                "n_basins": len(valid_basins),
                "mean_best_NSE": round(statistics.mean(v["best_test_NSE"] for v in valid_basins), 4),
                "stdev_best_NSE": round(statistics.stdev(v["best_test_NSE"] for v in valid_basins), 4) if len(valid_basins) > 1 else 0,
                "mean_n_trials": round(statistics.mean(v["n_trials"] for v in valid_basins), 1),
                "total_tokens_panel": sum(v["total_tokens"] for v in valid_basins),
                "total_wall_s_panel": round(sum(v["total_wall_s"] for v in valid_basins), 0),
                "total_active_s_panel": round(sum(v["total_active_s"] for v in valid_basins), 0),
                "total_llm_dec_s_panel": round(sum(v["total_llm_dec_s"] for v in valid_basins), 0),
            }

    if not rows:
        print("No exp1 data found.")
        return

    rows.sort(key=lambda r: (r["basin_id"], r["method"]))
    TABLES.mkdir(parents=True, exist_ok=True)
    out1 = TABLES / "table_exp1_cross_mode_summary.csv"
    fields = list(rows[0].keys())
    with open(out1, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} per-(basin,method) rows -> {out1}")

    # aggregate table
    out2 = TABLES / "table_exp1_method_aggregate.csv"
    agg_rows = [{"method": m, **vals} for m, vals in method_aggregate.items()]
    if agg_rows:
        with open(out2, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(agg_rows[0].keys()))
            w.writeheader()
            w.writerows(agg_rows)
        print(f"Wrote {len(agg_rows)} method-level rows -> {out2}")

    # print headline
    print()
    print(f"=== Method aggregate (panel-mean best test NSE over {sum(1 for r in rows if r['method']=='M0')} basins) ===")
    print(f"{'method':10} {'n':>3} {'mean':>8} {'stdev':>7} {'n_tr':>5} {'tokens':>8} {'wall_s':>7} {'human_s':>8} {'llm_dec':>8}")
    for m, vals in method_aggregate.items():
        print(f"{m:10} {vals['n_basins']:>3} {vals['mean_best_NSE']:>+8.4f} {vals['stdev_best_NSE']:>7.4f} "
              f"{vals['mean_n_trials']:>5.1f} {vals['total_tokens_panel']:>8} "
              f"{vals['total_wall_s_panel']:>7.0f} {vals['total_active_s_panel']:>8.0f} "
              f"{vals['total_llm_dec_s_panel']:>8.0f}")


if __name__ == "__main__":
    main()
