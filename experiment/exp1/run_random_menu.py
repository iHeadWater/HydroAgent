"""M3 random-menu baseline for Exp1 v2."""

from __future__ import annotations

import argparse
import logging
import random

from common import (
    BUDGET_LEVELS,
    MAX_TRIALS,
    OBJECTIVES,
    RANDOM_REPEATS,
    RANGE_POLICIES,
    MenuDecision,
    append_jsonl,
    best_record,
    ensure_dirs,
    flatten_metric,
    iter_tasks,
    load_base_config,
    method_dir,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing random trial log")
    parser.add_argument("--repeats", type=int, default=RANDOM_REPEATS)
    parser.add_argument("--seed", type=int, default=20260521)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("random_menu")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    rng = random.Random(args.seed)
    records = []
    for task in iter_tasks(smoke=args.smoke):
        repeat_count = 1 if args.smoke else args.repeats
        for repeat_idx in range(repeat_count):
            history = []
            for trial_idx in range(1, MAX_TRIALS + 1):
                policies = list(RANGE_POLICIES)
                if not history or not history[-1].get("boundary_hits"):
                    policies = [p for p in policies if p != "boundary_expand"]
                decision = MenuDecision(
                    objective=rng.choice(OBJECTIVES),
                    budget_level=rng.choice(BUDGET_LEVELS),
                    range_policy=rng.choice(policies),
                    stop=False,
                    notes="uniform random menu selection",
                )
                record = run_trial(
                    method="M3",
                    task=task,
                    trial_idx=trial_idx,
                    repeat_idx=repeat_idx,
                    decision=decision,
                    cfg=cfg,
                    run_dir=out_dir,
                    previous_best=best_record(history),
                )
                append_jsonl(trial_log, record)
                history.append(record)
                records.append(record)
                LOGGER.info(
                    "M3 %s repeat %d trial %d: test NSE=%s",
                    task["task_id"], repeat_idx, trial_idx, flatten_metric(record, "test", "NSE"),
                )

    write_json(out_dir / "summary.json", {"method": "M3", "n_records": len(records), "seed": args.seed})
    print(f"Saved {len(records)} M3 trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
