"""Expand exp2 tables to include the stats the README/paper actually needs.

Adds three tables that the original `compile_results.py` does not produce:

- `table_exp2_per_iter_trajectory.csv`: one row per (method, basin, model,
  iteration) with train+test NSE/KGE, prompt/completion/cached/total tokens,
  llm_decision_time_s, hydromodel_compute_time_s, wall_time_s, cumulative
  best-so-far test_NSE. This is the numeric form of fig 4.4 (search
  trajectories).

- `table_exp2_per_task_full.csv`: one row per (method, basin, model) with both
  train and test NSE+KGE at best, plus cumulative cost-at-best (wall, tokens),
  and the cumulative cost over the full budget. Replaces / extends
  fair_compare.csv which only had test_NSE.

- `table_exp2_method_aggregate_full.csv`: one row per method with mean +/-
  std of best NSE (test and train), prompt/completion/cached tokens summed,
  wall/llm/hydromodel time totals. This is the headline table for §4.2.

All fields exist in the raw record; no rerun needed. The only field that is
zero for method A is wall_time_s, because the run_standard_sceua.py wrapper
records it inside the SCE-UA call rather than at trial level — we surface
that gap honestly rather than backfilling it.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP2 = ROOT / "results" / "paper" / "exp2_v2"
TABLES = Path(__file__).resolve().parent / "tables"

METHODS = {
    "A": "standard_sceua",
    "B": "zhu_direct_eval",
    "C": "llm_local_search",
    "D": "hydroagent_feedback",
}


def _metric(record: dict, period: str, name: str) -> float | None:
    m = record.get(f"{period}_metrics") or {}
    v = m.get(name)
    return v if isinstance(v, (int, float)) else None


def _tok(record: dict, field: str) -> int:
    t = record.get("llm_tokens") or {}
    return t.get(field, 0) or 0


def _iter(record: dict) -> int:
    return record.get("iteration") or record.get("round") or 1


def _load(method_dir: str) -> list[dict]:
    p = EXP2 / method_dir / "trials.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def _expand_d(record: dict) -> list[dict]:
    """D stores per-round trajectories inside one aggregated record.

    Reconstruct per-iteration rows from `nse_history`, `test_nse_history`,
    `kge_history`, `test_kge_history`. Tokens / time are total-only, so we
    distribute them linearly across rounds as the cheapest defensible proxy.
    """
    n = record.get("rounds") or 0
    if not n:
        return []
    nse = record.get("nse_history") or []
    kge = record.get("kge_history") or []
    tnse = record.get("test_nse_history") or []
    tkge = record.get("test_kge_history") or []
    tok_total = _tok(record, "total_tokens")
    tok_prompt = _tok(record, "prompt_tokens")
    tok_compl = _tok(record, "completion_tokens")
    tok_cached = _tok(record, "cached_tokens")
    wall = record.get("wall_time_s", 0) or 0
    llm_t = record.get("llm_decision_time_s", 0) or 0
    hyd_t = record.get("hydromodel_compute_time_s", 0) or 0
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "iteration": i,
            "train_NSE": nse[i - 1] if i - 1 < len(nse) else None,
            "train_KGE": kge[i - 1] if i - 1 < len(kge) else None,
            "test_NSE":  tnse[i - 1] if i - 1 < len(tnse) else None,
            "test_KGE":  tkge[i - 1] if i - 1 < len(tkge) else None,
            "prompt_tokens":     tok_prompt // n if n else 0,
            "completion_tokens": tok_compl // n if n else 0,
            "cached_tokens":     tok_cached // n if n else 0,
            "total_tokens":      tok_total // n if n else 0,
            "wall_time_s":              wall / n if n else 0,
            "llm_decision_time_s":      llm_t / n if n else 0,
            "hydromodel_compute_time_s": hyd_t / n if n else 0,
            "_d_per_iter_is_approx": True,
        })
    return rows


def per_iter_rows() -> list[dict]:
    out = []
    for letter, mdir in METHODS.items():
        for r in _load(mdir):
            base = {"method": letter, "basin_id": r.get("basin_id"), "model": r.get("model")}
            if letter == "D":
                for sub in _expand_d(r):
                    out.append({**base, **sub})
            else:
                out.append({
                    **base,
                    "iteration": _iter(r),
                    "train_NSE": _metric(r, "train", "NSE"),
                    "train_KGE": _metric(r, "train", "KGE"),
                    "test_NSE":  _metric(r, "test",  "NSE"),
                    "test_KGE":  _metric(r, "test",  "KGE"),
                    "prompt_tokens":     _tok(r, "prompt_tokens"),
                    "completion_tokens": _tok(r, "completion_tokens"),
                    "cached_tokens":     _tok(r, "cached_tokens"),
                    "total_tokens":      _tok(r, "total_tokens"),
                    "wall_time_s":              r.get("wall_time_s", 0) or 0,
                    "llm_decision_time_s":      r.get("llm_decision_time_s", 0) or 0,
                    "hydromodel_compute_time_s": r.get("hydromodel_compute_time_s", 0) or 0,
                    "_d_per_iter_is_approx": False,
                })
    # add cumulative best so far per (method, basin, model)
    out.sort(key=lambda r: (r["method"], r["basin_id"], r["model"], r["iteration"]))
    cur_key = None
    best = float("-inf")
    for r in out:
        key = (r["method"], r["basin_id"], r["model"])
        if key != cur_key:
            cur_key, best = key, float("-inf")
        n = r.get("test_NSE")
        if isinstance(n, (int, float)) and n > best:
            best = n
        r["best_so_far_test_NSE"] = best if best != float("-inf") else None
    return out


def per_task_rows() -> list[dict]:
    """For each (method, basin, model): best test/train NSE+KGE and cum costs at best."""
    rows = per_iter_rows()
    by_task = defaultdict(list)
    for r in rows:
        by_task[(r["method"], r["basin_id"], r["model"])].append(r)
    out = []
    for (m, bid, mdl), seq in by_task.items():
        seq.sort(key=lambda x: x["iteration"])
        # find iter at best (first time test_NSE == best_so_far_test_NSE strictly improves)
        best = float("-inf")
        best_iter, best_r = 0, None
        cum_wall, cum_tok, cum_llm_t, cum_hyd_t = 0.0, 0, 0.0, 0.0
        cum_wall_at_best, cum_tok_at_best, cum_llm_t_at_best, cum_hyd_t_at_best = 0.0, 0, 0.0, 0.0
        n_iters = 0
        for r in seq:
            n_iters += 1
            cum_wall += r.get("wall_time_s") or 0
            cum_tok += r.get("total_tokens") or 0
            cum_llm_t += r.get("llm_decision_time_s") or 0
            cum_hyd_t += r.get("hydromodel_compute_time_s") or 0
            n = r.get("test_NSE")
            if isinstance(n, (int, float)) and n > best:
                best = n
                best_iter = r["iteration"]
                best_r = r
                cum_wall_at_best = cum_wall
                cum_tok_at_best = cum_tok
                cum_llm_t_at_best = cum_llm_t
                cum_hyd_t_at_best = cum_hyd_t
        if best_r is None:
            continue
        out.append({
            "method": m, "basin_id": bid, "model": mdl,
            "iters": n_iters,
            "iter_at_best": best_iter,
            "cap_binding": "Y" if best_iter == n_iters and n_iters > 1 else "N",
            "best_train_NSE": best_r.get("train_NSE"),
            "best_train_KGE": best_r.get("train_KGE"),
            "best_test_NSE":  best_r.get("test_NSE"),
            "best_test_KGE":  best_r.get("test_KGE"),
            "cum_wall_at_best_s":        round(cum_wall_at_best, 1),
            "cum_tokens_at_best":        cum_tok_at_best,
            "cum_llm_t_at_best_s":       round(cum_llm_t_at_best, 1),
            "cum_hydromodel_t_at_best_s": round(cum_hyd_t_at_best, 1),
            "total_wall_s":              round(cum_wall, 1),
            "total_tokens":              cum_tok,
            "total_llm_t_s":             round(cum_llm_t, 1),
            "total_hydromodel_t_s":      round(cum_hyd_t, 1),
        })
    out.sort(key=lambda r: (r["basin_id"], r["model"], r["method"]))
    return out


def method_aggregate_rows(per_task: list[dict]) -> list[dict]:
    by_m = defaultdict(list)
    for r in per_task:
        by_m[r["method"]].append(r)
    def mean(xs):
        xs = [x for x in xs if isinstance(x, (int, float))]
        return sum(xs) / len(xs) if xs else None
    def stdev(xs):
        xs = [x for x in xs if isinstance(x, (int, float))]
        return statistics.stdev(xs) if len(xs) > 1 else 0
    def fmt(v): return None if v is None else round(v, 4)
    out = []
    for m, rs in by_m.items():
        out.append({
            "method": m,
            "n_tasks": len(rs),
            "mean_best_test_NSE":  fmt(mean(r["best_test_NSE"]  for r in rs)),
            "stdev_best_test_NSE": fmt(stdev(r["best_test_NSE"] for r in rs)),
            "mean_best_train_NSE": fmt(mean(r["best_train_NSE"] for r in rs)),
            "mean_best_test_KGE":  fmt(mean(r["best_test_KGE"]  for r in rs)),
            "mean_best_train_KGE": fmt(mean(r["best_train_KGE"] for r in rs)),
            "mean_iter_at_best":   fmt(mean(r["iter_at_best"]   for r in rs)),
            "n_cap_binding":       sum(1 for r in rs if r["cap_binding"] == "Y"),
            "mean_cum_wall_at_best_s":        fmt(mean(r["cum_wall_at_best_s"]        for r in rs)),
            "mean_cum_tokens_at_best":        int(round(mean(r["cum_tokens_at_best"]   for r in rs) or 0)),
            "mean_cum_llm_t_at_best_s":       fmt(mean(r["cum_llm_t_at_best_s"]       for r in rs)),
            "mean_cum_hydromodel_t_at_best_s": fmt(mean(r["cum_hydromodel_t_at_best_s"] for r in rs)),
        })
    out.sort(key=lambda r: r["method"])
    return out


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    iter_rows = per_iter_rows()
    task_rows = per_task_rows()
    agg_rows = method_aggregate_rows(task_rows)

    for name, rows in [
        ("table_exp2_per_iter_trajectory.csv", iter_rows),
        ("table_exp2_per_task_full.csv", task_rows),
        ("table_exp2_method_aggregate_full.csv", agg_rows),
    ]:
        if not rows:
            continue
        fields = list(rows[0].keys())
        with open(TABLES / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows):>4} rows -> {TABLES / name}")

    print("\n=== headline aggregate ===")
    print(f"{'M':2} {'n':>2} {'test_NSE':>10} {'train_NSE':>10} {'test_KGE':>10} "
          f"{'iter@best':>10} {'cap_bind':>8} {'cum_wall':>9} {'cum_tok':>9}")
    for r in agg_rows:
        print(f"{r['method']:2} {r['n_tasks']:>2} "
              f"{r['mean_best_test_NSE']:>10.4f} "
              f"{r['mean_best_train_NSE']:>10.4f} "
              f"{r['mean_best_test_KGE']:>10.4f} "
              f"{r['mean_iter_at_best']:>10.2f} "
              f"{r['n_cap_binding']:>8} "
              f"{r['mean_cum_wall_at_best_s']:>9.1f} "
              f"{r['mean_cum_tokens_at_best']:>9}")


if __name__ == "__main__":
    main()
