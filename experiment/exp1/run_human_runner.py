"""M1 human menu-tuning runner for Exp1 v2.

The timer is active only while the operator reads feedback and chooses the next
menu decision. Numerical calibration/evaluation waits are recorded as wall time
but excluded from human active time.
"""

from __future__ import annotations

import argparse
import logging
import time

from common import (
    BUDGET_LEVELS,
    MAX_TRIALS,
    OBJECTIVES,
    RANGE_POLICIES,
    MenuDecision,
    append_jsonl,
    best_record,
    ensure_dirs,
    flatten_metric,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def _prompt_choice(label: str, options: list[str], default: str) -> str:
    print(f"{label}:")
    for idx, option in enumerate(options, 1):
        suffix = " [default]" if option == default else ""
        print(f"  {idx}. {option}{suffix}")
    raw = input(f"Select {label} ({default}): ").strip()
    if not raw:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw


def _show_feedback(task: dict, history: list[dict], attrs: dict) -> None:
    print("\n" + "=" * 78)
    print(f"Task: {task['task_id']}  basin={task['basin_id']}  model={task['model'].upper()}")
    print(f"Climate label: {task['climate_zone']}")
    if attrs:
        keys = ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
        print("Basin attributes:", {k: attrs.get(k) for k in keys if k in attrs})
    if not history:
        print("No previous trial for this task.")
        return
    last = history[-1]
    print(f"Previous trial {last['trial_idx']} decision: {last.get('decision')}")
    print(
        "Metrics: "
        f"train NSE={flatten_metric(last, 'train', 'NSE')} "
        f"test NSE={flatten_metric(last, 'test', 'NSE')} "
        f"train KGE={flatten_metric(last, 'train', 'KGE')} "
        f"test KGE={flatten_metric(last, 'test', 'KGE')}"
    )
    print("Boundary hits:", last.get("boundary_hits", []))
    best = best_record(history)
    if best:
        print(f"Best so far: trial {best['trial_idx']} test NSE={flatten_metric(best, 'test', 'NSE')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing human trial log")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("human_script")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    all_records = read_jsonl(trial_log)
    new_records = []

    for task in iter_tasks(smoke=args.smoke):
        task_history = [r for r in all_records if r.get("task_id") == task["task_id"]]
        attrs = get_basin_attrs(task["basin_id"], cfg)
        for trial_idx in range(len(task_history) + 1, MAX_TRIALS + 1):
            _show_feedback(task, task_history, attrs)
            print("\nActive timer starts now. Decide using only the controlled menu.")
            t_active = time.time()
            objective = _prompt_choice("objective", OBJECTIVES, "NSE")
            budget = _prompt_choice("budget_level", BUDGET_LEVELS, "default")
            policy_default = "boundary_expand" if task_history and task_history[-1].get("boundary_hits") else "default"
            range_policy = _prompt_choice("range_policy", RANGE_POLICIES, policy_default)
            stop_raw = input("Stop after this trial if metrics are satisfactory? [y/N]: ").strip().lower()
            notes = input("Short diagnostic notes: ").strip()
            active_seconds = time.time() - t_active

            decision = MenuDecision(
                objective=objective,
                budget_level=budget,
                range_policy=range_policy,
                stop=stop_raw in ("y", "yes"),
                notes=notes,
            )
            previous_best = best_record(task_history)
            record = run_trial(
                method="M1",
                task=task,
                trial_idx=trial_idx,
                decision=decision,
                cfg=cfg,
                run_dir=out_dir,
                active_seconds=active_seconds,
                previous_best=previous_best,
            )
            append_jsonl(trial_log, record)
            all_records.append(record)
            task_history.append(record)
            new_records.append(record)
            print(f"Trial saved. Active seconds={active_seconds:.1f}, wall={record['wall_time_s']:.1f}s")
            print(f"Test NSE={flatten_metric(record, 'test', 'NSE')} Test KGE={flatten_metric(record, 'test', 'KGE')}")
            if decision.stop:
                break

    write_json(out_dir / "summary.json", {"method": "M1", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} new M1 trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
