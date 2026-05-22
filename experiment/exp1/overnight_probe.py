"""Overnight basin-difficulty probe for Exp1 v2 site selection (SAFE variant).

Custom parameter ranges (climate_prior / wide) make XAJ numerically unstable
once the param_range fix is active (NSE -> -inf). So this probe stays on the
hydromodel built-in default range (always stable) and varies the *budget*
instead: a fast pass vs a thorough (deep) pass. This answers, per (basin,
model):

  - quick_NSE : what a cheap calibration reaches
  - deep_NSE  : the thorough-calibration ceiling on the safe default range
  - gain      : how much extra optimization budget buys

Verdict for Exp1 suitability (based on deep_NSE, the realistic ceiling):
  too_easy  : deep already excellent (>0.70) -> no tuning value
  too_hard  : deep still poor (<0.40)         -> structural ceiling
  SUITABLE  : deep in a usable-but-improvable band, budget/effort matters

Runs gr4j + xaj over all 5 basins x {quick, deep} = 20 calibrations. Each
trial is wrapped by run_trial's try/except, so one failure does not abort the
batch. Resumable: already-finished (basin,model,budget) rows in the jsonl are
skipped.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp1/overnight_probe.py
"""

from __future__ import annotations

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
    read_jsonl,
    run_trial,
    task_id,
)

LOGGER = logging.getLogger(__name__)

MODELS = ["gr4j", "xaj"]
BUDGETS = ["quick", "deep"]  # safe default range; vary only the budget


def verdict(deep_nse: float | None) -> str:
    if deep_nse is None:
        return "FAILED"
    if deep_nse > 0.70:
        return "too_easy"
    if deep_nse < 0.40:
        return "too_hard"
    return "SUITABLE"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    run_dir = OUTPUT_ROOT / "overnight"
    log_path = run_dir / "overnight_trials.jsonl"

    done = {(r["basin_id"], r["model"], r["method"]) for r in read_jsonl(log_path)}

    for basin in BASINS:
        for model in MODELS:
            task = {**basin, "model": model, "task_id": task_id(basin["basin_id"], model)}
            for budget in BUDGETS:
                method = f"PROBE_{budget}"
                if (basin["basin_id"], model, method) in done:
                    LOGGER.info("skip (done): %s %s %s", basin["basin_id"], model, method)
                    continue
                decision = MenuDecision(objective="NSE", budget_level=budget, range_policy="default")
                record = run_trial(
                    method=method, task=task, trial_idx=1, decision=decision,
                    cfg=cfg, run_dir=run_dir / budget,
                )
                append_jsonl(log_path, record)
                LOGGER.info("%s %s %s: test NSE=%s wall=%ss",
                            basin["basin_id"], model, budget,
                            flatten_metric(record, "test", "NSE"), record.get("wall_time_s"))

    # ---- summary table ----
    rows = read_jsonl(log_path)
    by: dict = {}
    for r in rows:
        by.setdefault((r["basin_id"], r["model"]), {})[r["method"]] = flatten_metric(r, "test", "NSE")
    names = {b["basin_id"]: b["climate_zone"] for b in BASINS}

    print("\n" + "=" * 92)
    print(f"{'basin':>9} {'model':>5} {'climate':>16} {'quick':>8} {'deep':>8} {'gain':>8}  verdict")
    print("-" * 92)
    for basin in BASINS:
        for model in MODELS:
            d = by.get((basin["basin_id"], model), {})
            q, dp = d.get("PROBE_quick"), d.get("PROBE_deep")
            qs = f"{q:.3f}" if isinstance(q, float) else "  N/A"
            ds = f"{dp:.3f}" if isinstance(dp, float) else "  N/A"
            gs = f"{dp - q:+.3f}" if isinstance(q, float) and isinstance(dp, float) else "  N/A"
            print(f"{basin['basin_id']:>9} {model:>5} {names[basin['basin_id']]:>16} "
                  f"{qs:>8} {ds:>8} {gs:>8}  {verdict(dp)}")
    print("=" * 92)


if __name__ == "__main__":
    main()
