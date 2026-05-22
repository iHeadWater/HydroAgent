"""Probe basin difficulty for Exp1 v2 site selection.

For each (basin, model) it runs two fixed menu decisions and compares test NSE:
  - floor  : objective=NSE, budget=default, range_policy=default
  - tuned  : objective=NSE, budget=deep,    range_policy=climate_prior

A basin is a good Exp1 site when the floor is not already excellent AND tuning
yields a clear gain -- i.e. calibration effort actually matters there. Basins
that are already excellent at floor (no need to tune) or hopeless even when
tuned (structural ceiling) cannot demonstrate "LLM replaces human tuning".

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp1/probe_difficulty.py --models gr4j
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp1/probe_difficulty.py --models gr4j xaj
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from common import (
    BASINS,
    MenuDecision,
    OUTPUT_ROOT,
    append_jsonl,
    ensure_dirs,
    flatten_metric,
    load_base_config,
    run_trial,
    task_id,
)

LOGGER = logging.getLogger(__name__)

PROBE_CONFIGS = {
    "floor": MenuDecision(objective="NSE", budget_level="default", range_policy="default"),
    "tuned": MenuDecision(objective="NSE", budget_level="deep", range_policy="climate_prior"),
}


def verdict(floor_nse: float | None, tuned_nse: float | None) -> str:
    if floor_nse is None or tuned_nse is None:
        return "FAILED"
    gain = tuned_nse - floor_nse
    if tuned_nse < 0.4:
        return "too_hard (ceiling)"
    if floor_nse > 0.70:
        return "too_easy (floor already good)"
    if gain >= 0.05:
        return "SUITABLE (tuning helps)"
    return "marginal (small gain)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["gr4j"], help="models to probe")
    parser.add_argument("--budget", default="default", choices=["quick", "default", "deep"],
                        help="shared budget for floor & tuned (single-variable: only range_policy differs). "
                             "Use 'quick' for fast probing of slow models like xaj.")
    parser.add_argument("--basins", nargs="+", default=None,
                        help="subset of basin_ids to probe (default: all)")
    parser.add_argument("--tuned-policy", default="climate_prior",
                        choices=["climate_prior", "wide", "boundary_expand"],
                        help="range policy for the 'tuned' run (use 'wide' to avoid the "
                             "buggy climate_prior XAJ ranges)")
    args = parser.parse_args()

    # floor vs tuned differ ONLY in range_policy at the same budget, so the gain
    # cleanly attributes to parameter-range tuning (not budget).
    configs = {
        "floor": MenuDecision(objective="NSE", budget_level=args.budget, range_policy="default"),
        "tuned": MenuDecision(objective="NSE", budget_level=args.budget, range_policy=args.tuned_policy),
    }

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    run_dir = OUTPUT_ROOT / "probe"
    log_path = run_dir / "probe_trials.jsonl"

    if args.basins:
        known = {b["basin_id"]: b for b in BASINS}
        # accept basin_ids outside the built-in list (e.g. screening candidates);
        # climate_zone unknown is fine for default/wide range policies.
        basins = [known.get(bid, {"basin_id": bid, "name": bid, "climate_zone": "unknown"})
                  for bid in args.basins]
    else:
        basins = BASINS

    rows = []
    for basin in basins:
        for model in args.models:
            task = {**basin, "model": model, "task_id": task_id(basin["basin_id"], model)}
            results = {}
            for cfg_name, decision in configs.items():
                record = run_trial(
                    method=f"PROBE_{cfg_name}",
                    task=task,
                    trial_idx=1,
                    decision=decision,
                    cfg=cfg,
                    run_dir=run_dir / cfg_name,
                )
                append_jsonl(log_path, record)
                nse = flatten_metric(record, "test", "NSE")
                results[cfg_name] = nse
                LOGGER.info("%s %s %s: test NSE=%s", basin["basin_id"], model, cfg_name, nse)
            floor_nse, tuned_nse = results.get("floor"), results.get("tuned")
            gain = (tuned_nse - floor_nse) if (floor_nse is not None and tuned_nse is not None) else None
            rows.append({
                "basin": basin["basin_id"], "name": basin["name"],
                "climate": basin["climate_zone"], "model": model,
                "floor_NSE": floor_nse, "tuned_NSE": tuned_nse,
                "gain": gain, "verdict": verdict(floor_nse, tuned_nse),
            })

    print("\n" + "=" * 100)
    print(f"{'basin':>9} {'model':>5} {'climate':>16} {'floor':>7} {'tuned':>7} {'gain':>7}  verdict")
    print("-" * 100)
    for r in rows:
        f = f"{r['floor_NSE']:.3f}" if isinstance(r["floor_NSE"], float) else "  N/A"
        t = f"{r['tuned_NSE']:.3f}" if isinstance(r["tuned_NSE"], float) else "  N/A"
        g = f"{r['gain']:+.3f}" if isinstance(r["gain"], float) else "  N/A"
        print(f"{r['basin']:>9} {r['model']:>5} {r['climate']:>16} {f:>7} {t:>7} {g:>7}  {r['verdict']}")
    print("=" * 100)


if __name__ == "__main__":
    main()
