"""Method A: standard SCE-UA baseline for Exp2 v2."""

from __future__ import annotations

import argparse
import logging

from common import (
    STANDARD_BUDGET,
    append_jsonl,
    ensure_dirs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    run_calibration,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run one basin-model task")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("standard_sceua")
    log_path = out_dir / "trials.jsonl"
    if args.overwrite and log_path.exists():
        log_path.unlink()

    existing = {(r.get("task_id"), r.get("method")) for r in read_jsonl(log_path)}
    new_records = []
    for task in iter_tasks(args.smoke):
        if (task.task_id, "A") in existing:
            LOGGER.info("Skip existing A %s", task.task_id)
            continue
        record = run_calibration(
            task=task,
            run_dir=out_dir / task.task_id,
            cfg=cfg,
            algorithm="SCE_UA",
            algorithm_params=STANDARD_BUDGET[task.model],
        )
        record.update({"method": "A", "method_name": "standard_sceua", "iteration": 1})
        append_jsonl(log_path, record)
        new_records.append(record)
        LOGGER.info("A %s: success=%s test_NSE=%s", task.task_id, record["success"], record["test_metrics"].get("NSE"))

    write_json(out_dir / "summary.json", {"method": "A", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} Method A record(s) -> {log_path}")


if __name__ == "__main__":
    main()

