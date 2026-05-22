"""Method B: strict Zhu-style direct parameter proposal and evaluation."""

from __future__ import annotations

import argparse
import logging

from common import (
    MAX_ITERS,
    NSE_TARGET,
    append_jsonl,
    ask_llm_for_params,
    ensure_dirs,
    evaluate_parameter_set,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    metric,
    read_jsonl,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("zhu_direct_eval")
    log_path = out_dir / "trials.jsonl"
    if args.overwrite and log_path.exists():
        log_path.unlink()

    from hydroagent.llm import LLMClient

    llm = LLMClient(cfg["llm"])
    all_records = read_jsonl(log_path)
    new_records = []

    for task in iter_tasks(args.smoke):
        history = [r for r in all_records if r.get("task_id") == task.task_id]
        attrs = get_basin_attrs(task, cfg)
        start_iter = len(history) + 1
        for iteration in range(start_iter, min(args.max_iters, MAX_ITERS) + 1):
            llm_decision = ask_llm_for_params(llm, task, attrs, history)
            record = evaluate_parameter_set(
                task=task,
                proposed_params=llm_decision["proposed_params"],
                run_dir=out_dir / task.task_id / f"iter_{iteration:02d}",
                cfg=cfg,
            )
            record.update({
                "method": "B",
                "method_name": "zhu_direct_eval",
                "iteration": iteration,
                "basin_attributes": attrs,
                "llm_tokens": llm_decision["llm_tokens"],
                "llm_decision_time_s": llm_decision["llm_decision_time_s"],
                "raw_response": llm_decision["raw_response"],
                "wall_time_s": round(
                    llm_decision["llm_decision_time_s"] + record.get("hydromodel_compute_time_s", 0.0), 3
                ),
            })
            append_jsonl(log_path, record)
            all_records.append(record)
            history.append(record)
            new_records.append(record)
            LOGGER.info(
                "B %s iter %d: valid=%s train_NSE=%s test_NSE=%s tokens=%s",
                task.task_id,
                iteration,
                record.get("valid_proposal"),
                metric(record, "train", "NSE"),
                metric(record, "test", "NSE"),
                record.get("llm_tokens", {}).get("total_tokens"),
            )
            if (metric(record, "train", "NSE") or -999.0) >= NSE_TARGET:
                break

    write_json(out_dir / "summary.json", {"method": "B", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} Method B iteration record(s) -> {log_path}")


if __name__ == "__main__":
    main()

