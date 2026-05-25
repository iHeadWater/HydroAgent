"""M0 default-script baseline for Exp1 v2.

Runs one default SCE-UA calibration for each basin-model task. This is the
numerical reference arm and uses no human or LLM controller decisions.

EXP1_M0_BUDGET env var controls budget for the M0 ablation:
  - default (or unset) : standard preset (rep=500 ngs=50 for GR4J)
  - min                : starving budget (rep=100 ngs=10) — lower-bound stress test
  - max                : brute-force max (rep=2000 ngs=200) — upper-bound stress test
Each setting writes to a separate output subdir to keep the spectrum visible:
  - default → default_script/
  - min     → default_script_min/
  - max     → default_script_max/
"""

from __future__ import annotations

import argparse
import logging
import os

from common import (
    BUDGET_LEVELS,
    MenuDecision,
    ensure_dirs,
    iter_tasks,
    load_base_config,
    method_dir,
    append_jsonl,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


# Free-form override values for the M0 budget ablation.
# Kept in this file (not common.py) because they are a per-runner concern;
# common.py's BUDGET_MENU/FREEFORM_BOUNDS stay the menu space for M1/M2.
_M0_BUDGET_OVERRIDES = {
    # rep, ngs, kstop, peps, pcento
    "min":     {"rep": 100,  "ngs": 10,  "kstop": 50, "peps": 0.1, "pcento": 0.1},
    "default": {},  # use BUDGET_MENU[model]["default"]
    "max":     {"rep": 2000, "ngs": 200, "kstop": 50, "peps": 0.1, "pcento": 0.1},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing trial log")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()

    m0_budget = os.environ.get("EXP1_M0_BUDGET", "default").lower()
    if m0_budget not in _M0_BUDGET_OVERRIDES:
        raise ValueError(f"EXP1_M0_BUDGET must be one of {sorted(_M0_BUDGET_OVERRIDES)}, got {m0_budget!r}")

    subdir = "default_script" if m0_budget == "default" else f"default_script_{m0_budget}"
    out_dir = method_dir(subdir)
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    override = _M0_BUDGET_OVERRIDES[m0_budget]
    LOGGER.info(
        "M0 default_script: EXP1_M0_BUDGET=%s subdir=%s freeform_override=%s",
        m0_budget, subdir, override,
    )

    records = []
    for task in iter_tasks(smoke=args.smoke):
        LOGGER.info("M0 (%s): %s", m0_budget, task["task_id"])
        # Freeform-mode field overrides on top of default budget preset.
        # If EXP1_M0_BUDGET=default, all freeform fields stay None and the
        # standard preset is used; behaviour identical to pre-ablation M0.
        decision = MenuDecision(
            objective="NSE",
            budget_level="default",
            range_policy="default",
            rep=override.get("rep"),
            ngs=override.get("ngs"),
            kstop=override.get("kstop"),
            peps=override.get("peps"),
            pcento=override.get("pcento"),
        )
        record = run_trial(
            method=f"M0_{m0_budget}",
            task=task,
            trial_idx=1,
            decision=decision,
            cfg=cfg,
            run_dir=out_dir,
        )
        append_jsonl(trial_log, record)
        records.append(record)

    write_json(out_dir / "summary.json", {
        "method": f"M0_{m0_budget}",
        "budget_override": override,
        "n_records": len(records),
        "records": records,
    })
    print(f"Saved {len(records)} M0 ({m0_budget}) trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
