"""Fair budget comparison for Exp2 BCD: best NSE + iter@best + cum cost.

For each (basin, model) task, we extract per-iteration test_NSE trajectories and
compute (i) the best NSE achieved up to the cap, (ii) the iteration at which
that best was first reached (cumulative-best semantics — once attained, not
lost), (iii) cumulative wall-time and token cost up to that iteration, and (iv)
the cumulative total over the full budget. This is the table required to judge
whether one method reaches a comparable NSE faster / cheaper than another, and
whether the cap was binding or the method had already plateaued.

Outputs:
  experiment/exp2/tables/table_exp2_fair_compare.csv
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP2_ROOT = ROOT / "results" / "paper" / "exp2_v2"
TABLES_DIR = Path(__file__).resolve().parent / "tables"

METHODS = {
    "B": "zhu_direct_eval",
    "C": "llm_local_search",
    # D is a single aggregated record per task (agent run with internal history);
    # handled separately because it has nse_history not per-iter records.
}


def _tokens(record: dict) -> int:
    """Total tokens for one iteration record (LLM tokens for B/C)."""
    tok = record.get("llm_tokens") or {}
    return tok.get("total_tokens") or tok.get("total") or 0


def _iter_index(record: dict) -> int:
    return record.get("iteration") or record.get("round") or 0


def _nse(record: dict, period: str = "test") -> float | None:
    m = record.get(f"{period}_metrics") or {}
    v = m.get("NSE")
    return v if isinstance(v, (int, float)) else None


def _stats_per_method(method_letter: str, method_dir: str) -> dict[tuple, dict]:
    """For each (basin, model) task return summary dict.

    Uses cumulative-best semantics: best_so_far[i] = max(NSE_1..NSE_i); the
    'iter_at_best' is the iteration at which the best NSE was first reached.
    """
    path = EXP2_ROOT / method_dir / "trials.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    by_task = defaultdict(list)
    for r in rows:
        by_task[(r.get("basin_id"), r.get("model"))].append(r)

    out: dict[tuple, dict] = {}
    for task, rs in by_task.items():
        rs_sorted = sorted(rs, key=_iter_index)
        # cumulative best on test_NSE
        best = float("-inf")
        best_iter = 0
        cum_wall = 0.0
        cum_tok = 0
        cum_wall_at_best = 0.0
        cum_tok_at_best = 0
        last_test = None
        last_train = None
        for r in rs_sorted:
            i = _iter_index(r)
            n_test = _nse(r, "test")
            n_train = _nse(r, "train")
            wall = r.get("wall_time_s", 0) or 0
            tok = _tokens(r)
            cum_wall += wall
            cum_tok += tok
            if isinstance(n_test, (int, float)) and n_test > best:
                best = n_test
                best_iter = i
                cum_wall_at_best = cum_wall
                cum_tok_at_best = cum_tok
            if isinstance(n_test, (int, float)):
                last_test = n_test
            if isinstance(n_train, (int, float)):
                last_train = n_train
        # converged = best reached before the last iteration
        n_iters = max((_iter_index(r) for r in rs_sorted), default=0)
        cap_binding = (best_iter == n_iters and best == float("-inf") and False) or \
                      (best_iter == n_iters)
        # The "still rising" heuristic: best reached at the last iter -> cap binding
        out[task] = dict(
            method=method_letter,
            iters=n_iters,
            best_nse=best if best != float("-inf") else None,
            iter_at_best=best_iter,
            cap_binding=cap_binding,
            cum_wall_s=round(cum_wall, 1),
            cum_tok=cum_tok,
            cum_wall_at_best_s=round(cum_wall_at_best, 1),
            cum_tok_at_best=cum_tok_at_best,
            last_train_nse=last_train,
            last_test_nse=last_test,
        )
    return out


def _stats_method_D() -> dict[tuple, dict]:
    """D (hydroagent_feedback) record: one record per task with nse_history.

    test_nse_history is the per-round trajectory; rounds == len(history).
    We approximate cum_wall/cum_tok at best by linear allocation (the record
    only stores totals), and flag that as 'aggregated'.
    """
    path = EXP2_ROOT / "hydroagent_feedback" / "trials.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    out: dict[tuple, dict] = {}
    for r in rows:
        task = (r.get("basin_id"), r.get("model"))
        hist = r.get("test_nse_history") or []
        train_hist = r.get("nse_history") or []
        n_rounds = len(hist)
        total_wall = r.get("wall_time_s", 0) or 0
        total_tok = (r.get("llm_tokens") or {}).get("total_tokens") or \
                    (r.get("llm_tokens") or {}).get("total") or 0
        best = float("-inf")
        best_iter = 0
        running = float("-inf")
        for i, n in enumerate(hist, start=1):
            if isinstance(n, (int, float)) and n > running:
                running = n
                best = n
                best_iter = i
        # linear approx of cum-cost at best
        frac = (best_iter / n_rounds) if n_rounds else 0
        out[task] = dict(
            method="D",
            iters=n_rounds,
            best_nse=best if best != float("-inf") else None,
            iter_at_best=best_iter,
            cap_binding=(best_iter == n_rounds),
            cum_wall_s=round(total_wall, 1),
            cum_tok=total_tok,
            cum_wall_at_best_s=round(total_wall * frac, 1),
            cum_tok_at_best=int(total_tok * frac),
            last_train_nse=train_hist[-1] if train_hist else None,
            last_test_nse=hist[-1] if hist else None,
        )
    return out


def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    all_stats: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for letter, mdir in METHODS.items():
        for task, st in _stats_per_method(letter, mdir).items():
            all_stats[task][letter] = st
    for task, st in _stats_method_D().items():
        all_stats[task]["D"] = st

    csv_path = TABLES_DIR / "table_exp2_fair_compare.csv"
    fields = [
        "basin_id", "model", "method", "iters", "best_nse", "iter_at_best",
        "cap_binding", "cum_wall_at_best_s", "cum_tok_at_best",
        "cum_wall_s", "cum_tok",
    ]
    rows = []
    for task in sorted(all_stats.keys()):
        for m in ("B", "C", "D"):
            if m not in all_stats[task]:
                continue
            st = all_stats[task][m]
            rows.append({
                "basin_id": task[0],
                "model": task[1],
                "method": m,
                "iters": st["iters"],
                "best_nse": (f"{st['best_nse']:.4f}" if st['best_nse'] is not None else "N/A"),
                "iter_at_best": st["iter_at_best"],
                "cap_binding": "Y" if st["cap_binding"] else "N",
                "cum_wall_at_best_s": st["cum_wall_at_best_s"],
                "cum_tok_at_best": st["cum_tok_at_best"],
                "cum_wall_s": st["cum_wall_s"],
                "cum_tok": st["cum_tok"],
            })
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {csv_path}")

    # print compact table to stdout
    print()
    print(f"{'task':18} {'M':2} {'it':>3} {'best':>7} {'@':>3} {'cap':>3} {'w@best':>7} {'tok@best':>9} {'totw':>6} {'tottok':>7}")
    print("-" * 78)
    for task in sorted(all_stats.keys()):
        for m in ("B", "C", "D"):
            if m not in all_stats[task]:
                continue
            st = all_stats[task][m]
            tname = f"{task[0]}/{task[1]}"
            best = f"{st['best_nse']:.4f}" if st['best_nse'] is not None else "  N/A "
            print(f"{tname:18} {m:2} {st['iters']:>3} {best:>7} "
                  f"{st['iter_at_best']:>3} {('Y' if st['cap_binding'] else 'N'):>3} "
                  f"{st['cum_wall_at_best_s']:>7.0f} {st['cum_tok_at_best']:>9} "
                  f"{st['cum_wall_s']:>6.0f} {st['cum_tok']:>7}")
        print()

    # aggregate per method (over tasks where method has data)
    print("=== Aggregate (over tasks each method covers) ===")
    agg = defaultdict(list)
    for task, by_m in all_stats.items():
        for m, st in by_m.items():
            if st["best_nse"] is not None:
                agg[m].append(st)
    for m in ("B", "C", "D"):
        rs = agg[m]
        if not rs:
            print(f"  {m}: no data")
            continue
        n = len(rs)
        mean_best = sum(s["best_nse"] for s in rs) / n
        mean_iter_at_best = sum(s["iter_at_best"] for s in rs) / n
        cap_hits = sum(1 for s in rs if s["cap_binding"])
        mean_wall_at_best = sum(s["cum_wall_at_best_s"] for s in rs) / n
        mean_tok_at_best = sum(s["cum_tok_at_best"] for s in rs) / n
        max_iters = max((s.get("iters") or 0) for s in rs) or "?"
        print(f"  {m}: tasks={n}  mean_best_NSE={mean_best:+.4f}  "
              f"mean_iter@best={mean_iter_at_best:.1f}/{max_iters}  cap_binding={cap_hits}/{n}  "
              f"mean_wall@best={mean_wall_at_best:.0f}s  mean_tok@best={mean_tok_at_best:.0f}")


if __name__ == "__main__":
    main()
