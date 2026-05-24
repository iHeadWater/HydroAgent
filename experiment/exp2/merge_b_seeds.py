"""Aggregate B (zhu_direct_eval) across 3 seeds.

Inputs:
  results/paper/exp2_v2/zhu_direct_eval/trials_seed{0,1,2}.jsonl
  (each = 180 records = 6 tasks x 30 iter)

Outputs:
  experiment/exp2/tables/table_exp2_B_multiseed.csv
    one row per (basin, model) task with per-seed best NSE + mean + stdev +
    convergence iter and per-seed cost-at-best.

This is the table the paper cites when reporting "B has substantial single-seed
variance; mean+/-stdev across 3 seeds is X+/-Y on the 6-task panel". Compare
with D's single-seed result and A's single-seed result (A and D have no LLM
sampling stochasticity at this scope).
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B_DIR = ROOT / "results" / "paper" / "exp2_v2" / "zhu_direct_eval"
TABLES = Path(__file__).resolve().parent / "tables"

SEEDS = [0, 1, 2]


def _per_task_best(records: list[dict]) -> dict[tuple[str, str], dict]:
    """For one seed's full records, return best NSE + iter@best + cum cost per task."""
    by = defaultdict(list)
    for r in records:
        by[(r.get("basin_id"), r.get("model"))].append(r)
    out: dict[tuple, dict] = {}
    for task, rs in by.items():
        rs_sorted = sorted(rs, key=lambda r: r.get("iteration") or 0)
        best = float("-inf")
        best_iter = 0
        cum_wall = 0.0
        cum_tok = 0
        cum_wall_at_best = 0.0
        cum_tok_at_best = 0
        for r in rs_sorted:
            n = (r.get("test_metrics") or {}).get("NSE")
            wall = r.get("wall_time_s") or 0
            tok = (r.get("llm_tokens") or {}).get("total_tokens") or 0
            cum_wall += wall
            cum_tok += tok
            if isinstance(n, (int, float)) and n > best:
                best = n
                best_iter = r.get("iteration") or 0
                cum_wall_at_best = cum_wall
                cum_tok_at_best = cum_tok
        out[task] = {
            "best_test_NSE": best if best != float("-inf") else None,
            "iter_at_best": best_iter,
            "cum_wall_at_best_s": round(cum_wall_at_best, 1),
            "cum_tokens_at_best": cum_tok_at_best,
        }
    return out


def main() -> None:
    seed_results: dict[int, dict] = {}
    for s in SEEDS:
        path = B_DIR / f"trials_seed{s}.jsonl"
        if not path.exists():
            print(f"WARN: missing {path}")
            continue
        rs = [json.loads(l) for l in open(path, encoding="utf-8")]
        seed_results[s] = _per_task_best(rs)

    tasks = sorted({t for d in seed_results.values() for t in d.keys()})
    rows = []
    for t in tasks:
        per_seed = {s: seed_results[s].get(t) for s in SEEDS if t in seed_results.get(s, {})}
        nse_vals = [d["best_test_NSE"] for d in per_seed.values() if isinstance(d.get("best_test_NSE"), (int, float))]
        iter_vals = [d["iter_at_best"] for d in per_seed.values() if d.get("iter_at_best") is not None]
        wall_vals = [d["cum_wall_at_best_s"] for d in per_seed.values()]
        tok_vals = [d["cum_tokens_at_best"] for d in per_seed.values()]
        row = {"basin_id": t[0], "model": t[1]}
        for s in SEEDS:
            d = per_seed.get(s, {})
            v = d.get("best_test_NSE")
            row[f"seed{s}_best_NSE"] = round(v, 4) if isinstance(v, (int, float)) else None
            row[f"seed{s}_iter_at_best"] = d.get("iter_at_best", "")
        row["mean_best_NSE"]  = round(statistics.mean(nse_vals), 4) if nse_vals else None
        row["stdev_best_NSE"] = round(statistics.stdev(nse_vals), 4) if len(nse_vals) > 1 else 0
        row["range_NSE"]      = round(max(nse_vals) - min(nse_vals), 4) if len(nse_vals) > 1 else 0
        row["mean_iter_at_best"]      = round(statistics.mean(iter_vals), 1) if iter_vals else None
        row["mean_cum_wall_at_best_s"]   = round(statistics.mean(wall_vals), 1)
        row["mean_cum_tokens_at_best"]   = int(round(statistics.mean(tok_vals)))
        rows.append(row)

    TABLES.mkdir(parents=True, exist_ok=True)
    out = TABLES / "table_exp2_B_multiseed.csv"
    fields = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")

    # print
    print()
    print(f"{'task':18} {'s0':>8} {'s1':>8} {'s2':>8} {'mean':>8} {'stdev':>7} {'range':>7} {'mean_iter@best':>14}")
    print("-" * 90)
    for r in rows:
        fmt = lambda v: f"{v:+.3f}" if isinstance(v, (int, float)) else "  N/A  "
        print(f"{r['basin_id']}/{r['model']:4} "
              f"{fmt(r['seed0_best_NSE']):>8} {fmt(r['seed1_best_NSE']):>8} {fmt(r['seed2_best_NSE']):>8} "
              f"{fmt(r['mean_best_NSE']):>8} {r['stdev_best_NSE']:>7.3f} {r['range_NSE']:>7.3f} "
              f"{r['mean_iter_at_best']:>14}")

    # method-level aggregate (across all 6 tasks x 3 seeds)
    all_nse = []
    for s in SEEDS:
        for t in tasks:
            d = seed_results.get(s, {}).get(t)
            if d and isinstance(d.get("best_test_NSE"), (int, float)):
                all_nse.append(d["best_test_NSE"])
    if all_nse:
        print()
        print(f"=== B aggregate over 6 tasks x {len(SEEDS)} seeds = {len(all_nse)} samples ===")
        print(f"  mean best test NSE: {statistics.mean(all_nse):+.4f}")
        print(f"  stdev:              {statistics.stdev(all_nse):.4f}")
        print(f"  median:             {statistics.median(all_nse):+.4f}")
        # per-task seed-mean aggregate (more comparable to per-task A/D)
        per_task_means = [r["mean_best_NSE"] for r in rows if isinstance(r.get("mean_best_NSE"), (int, float))]
        print(f"  per-task mean-of-means: {statistics.mean(per_task_means):+.4f}  "
              f"(this is the headline 'B mean best NSE' to compare with A=+0.339, D=+0.460)")


if __name__ == "__main__":
    main()
