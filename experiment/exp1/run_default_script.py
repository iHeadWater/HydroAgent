"""M0 default-script baseline for Exp1 v2.

Runs one default SCE-UA calibration for each basin-model task. This is the
numerical reference arm and uses no human or LLM controller decisions.
"""

from __future__ import annotations

import argparse
import logging

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing trial log")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("default_script")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    records = []
    for task in iter_tasks(smoke=args.smoke):
        LOGGER.info("M0 default_script: %s", task["task_id"])
        decision = MenuDecision(objective="NSE", budget_level="default", range_policy="default")
        record = run_trial(
            method="M0",
            task=task,
            trial_idx=1,
            decision=decision,
            cfg=cfg,
            run_dir=out_dir,
        )
        append_jsonl(trial_log, record)
        records.append(record)

    write_json(out_dir / "summary.json", {"method": "M0", "n_records": len(records), "records": records})
    print(f"Saved {len(records)} M0 trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
