"""Compile exp2_new: 4 methods (A/B/C/D) on 10 good/medium basins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import BASINS, MODEL, RESULTS_DIR, TABLES_DIR, ensure_dirs

METHODS = ["A", "B", "C", "D"]
METHOD_DIRS = {
    "A": "method_a", "B": "method_b", "C": "method_c", "D": "method_d",
}
METHOD_NAMES = {
    "A": "standard_sceua", "B": "zhu_direct_eval",
    "C": "llm_local_search", "D": "hydroagent_feedback",
}


def _f(x):
    return float(x) if isinstance(x, (int, float)) else None


def _read(method):
    p = RESULTS_DIR / METHOD_DIRS[method] / "trials.jsonl"
    if not p.exists():
        return []
    out, bad = [], 0
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            bad += 1  # tolerate occasional multiprocessing-write corruption
    if bad:
        print(f"  [warn] {method}: skipped {bad} corrupted line(s)")
    return out


def _metric(r, period, name):
    """Read NSE from train/test metrics; handles both dict and float formats."""
    m = r.get(f"{period}_metrics") or {}
    if isinstance(m, dict):
        v = m.get(name)
        return _f(v)
    return None


def _best_test_nse(rows):
    """Best test NSE across rows (B/C/D pick best across iterations; A has 1 row)."""
    vals = [_metric(r, "test", "NSE") for r in rows]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _total_tokens(rows):
    s = 0
    for r in rows:
        t = (r.get("llm_tokens") or {}).get("total_tokens")
        if isinstance(t, (int, float)):
            s += t
    return s


def _total_wall(rows):
    s = 0.0
    for r in rows:
        w = r.get("wall_time_s")
        if isinstance(w, (int, float)):
            s += w
    return round(s, 1)


def _n_iter(rows):
    return len(rows)


def _iter_at_best(rows):
    """Iteration index where best test NSE was first attained."""
    best = None
    iter_best = None
    for r in sorted(rows, key=lambda x: x.get("iteration", 0)):
        v = _metric(r, "test", "NSE")
        if v is not None and (best is None or v > best):
            best = v
            iter_best = r.get("iteration")
    return iter_best


def main():
    ensure_dirs()
    rows_by_method = {m: _read(m) for m in METHODS}
    print(f"Records per method: " + ", ".join(f"{m}={len(rows_by_method[m])}" for m in METHODS))

    # Group by (basin, method)
    per_task = {}
    for method, rows in rows_by_method.items():
        for r in rows:
            bid = r.get("basin_id")
            per_task.setdefault((bid, method), []).append(r)

    # Per-task summary (wide format: basin x method)
    table_rows = []
    for b in BASINS:
        bid = b["basin_id"]
        row = {
            "basin_id": bid,
            "basin_name": b["name"],
            "climate_zone": b["climate_zone"],
            "difficulty": b["difficulty"],
        }
        for m in METHODS:
            rec = per_task.get((bid, m), [])
            best = _best_test_nse(rec)
            row[f"{m}_best_test_nse"] = round(best, 4) if isinstance(best, (int, float)) else ""
            row[f"{m}_n_iter"] = _n_iter(rec)
            row[f"{m}_iter_at_best"] = _iter_at_best(rec) or ""
            row[f"{m}_total_tokens"] = _total_tokens(rec)
            row[f"{m}_total_wall_s"] = _total_wall(rec)
        # Best delta vs A
        a_nse = _f(row.get("A_best_test_nse"))
        for m in ["B", "C", "D"]:
            m_nse = _f(row.get(f"{m}_best_test_nse"))
            row[f"{m}_gain_vs_A"] = round(m_nse - a_nse, 4) if isinstance(m_nse, (int, float)) and isinstance(a_nse, (int, float)) else ""
        table_rows.append(row)

    # Per-iteration trajectory (long format)
    traj_rows = []
    for method, rows in rows_by_method.items():
        # Sort by (basin, iteration)
        rows_sorted = sorted(rows, key=lambda r: (r.get("basin_id", ""), r.get("iteration", 0)))
        # Group by basin to compute best_so_far
        from collections import defaultdict
        per_basin = defaultdict(list)
        for r in rows_sorted:
            per_basin[r.get("basin_id")].append(r)
        for bid, recs in per_basin.items():
            best = None
            for r in recs:
                v = _metric(r, "test", "NSE")
                if v is not None and (best is None or v > best):
                    best = v
                traj_rows.append({
                    "basin_id": bid,
                    "method": method,
                    "iteration": r.get("iteration"),
                    "test_nse": round(v, 4) if isinstance(v, (int, float)) else "",
                    "train_nse": round(_metric(r, "train", "NSE") or 0, 4) if _metric(r, "train", "NSE") is not None else "",
                    "best_so_far_test_nse": round(best, 4) if isinstance(best, (int, float)) else "",
                    "wall_time_s": _f(r.get("wall_time_s")),
                    "tokens": (r.get("llm_tokens") or {}).get("total_tokens") or 0,
                })

    # Aggregate per method
    agg_rows = []
    for m in METHODS:
        nses = [_f(t.get(f"{m}_best_test_nse")) for t in table_rows]
        nses = [n for n in nses if n is not None]
        gains = [_f(t.get(f"{m}_gain_vs_A")) for t in table_rows if m != "A"]
        gains = [g for g in gains if g is not None]
        agg_rows.append({
            "method": m,
            "method_name": METHOD_NAMES[m],
            "n_basins": len(nses),
            "mean_best_test_nse": round(sum(nses) / len(nses), 4) if nses else "",
            "mean_gain_vs_A": round(sum(gains) / len(gains), 4) if gains else "",
            "wins_vs_A": sum(1 for g in gains if g > 0.005),
            "ties_vs_A": sum(1 for g in gains if abs(g) <= 0.005),
            "losses_vs_A": sum(1 for g in gains if g < -0.005),
            "mean_n_iter": round(sum(t.get(f"{m}_n_iter", 0) for t in table_rows) / max(1, len(table_rows)), 1),
            "total_tokens": sum(t.get(f"{m}_total_tokens", 0) for t in table_rows),
            "total_wall_s": round(sum(_f(t.get(f"{m}_total_wall_s")) or 0 for t in table_rows), 1),
        })

    # Write CSVs
    import csv
    def _write_csv(path, rows):
        if not rows: return
        fields = []
        for r in rows:
            for k in r:
                if k not in fields: fields.append(k)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})
    _write_csv(TABLES_DIR / "table_per_task.csv", table_rows)
    _write_csv(TABLES_DIR / "table_per_iter_trajectory.csv", traj_rows)
    _write_csv(TABLES_DIR / "table_method_aggregate.csv", agg_rows)

    # JSON dump
    out = {
        "schema_version": "exp2_new_compiled_1",
        "n_basins": len(BASINS),
        "per_task": table_rows,
        "trajectory": traj_rows,
        "aggregate": agg_rows,
    }
    (RESULTS_DIR.parent / "exp2_compiled.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print(f"\n=== Aggregate (mean best test NSE) ===")
    for r in agg_rows:
        print(f"  {r['method']} ({r['method_name']:20}): {r['mean_best_test_nse']}  "
              f"gain={r['mean_gain_vs_A']}  W/T/L vs A: {r['wins_vs_A']}/{r['ties_vs_A']}/{r['losses_vs_A']}  "
              f"tokens={r['total_tokens']}")
    print(f"\nWrote tables -> {TABLES_DIR}")


if __name__ == "__main__":
    main()
