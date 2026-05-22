"""Method C: LLM direct proposal followed by local hydromodel search."""

from __future__ import annotations

import argparse
import logging

from common import (
    LOCAL_SEARCH_BUDGET,
    MAX_ITERS,
    NSE_TARGET,
    append_jsonl,
    ask_llm_for_params,
    ensure_dirs,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    metric,
    parameter_distance,
    read_jsonl,
    run_calibration,
    tight_ranges_around,
    validate_parameter_set,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def _algorithm_for_model(model: str) -> str:
    return "scipy" if model == "gr4j" else "SCE_UA"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    parser.add_argument("--gr4j-window", type=float, default=0.03)
    parser.add_argument("--xaj-window", type=float, default=0.07)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("llm_local_search")
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
            valid, clean_params, issues = validate_parameter_set(task.model, llm_decision["proposed_params"])
            base_record = {
                **task.to_dict(),
                "method": "C",
                "method_name": "llm_local_search",
                "iteration": iteration,
                "basin_attributes": attrs,
                "proposed_params": llm_decision["proposed_params"],
                "valid_proposal": valid,
                "proposal_issues": issues,
                "llm_tokens": llm_decision["llm_tokens"],
                "llm_decision_time_s": llm_decision["llm_decision_time_s"],
                "raw_response": llm_decision["raw_response"],
            }
            if valid:
                frac = args.gr4j_window if task.model == "gr4j" else args.xaj_window
                ranges = tight_ranges_around(task.model, clean_params, frac)
                record = run_calibration(
                    task=task,
                    run_dir=out_dir / task.task_id / f"iter_{iteration:02d}",
                    cfg=cfg,
                    algorithm=_algorithm_for_model(task.model),
                    algorithm_params=LOCAL_SEARCH_BUDGET[task.model],
                    param_ranges=ranges,
                    repeat_seed_offset=iteration * 137,
                )
                record.update(base_record)
                record["local_search_ranges"] = ranges
                record["local_search_best_params"] = record.get("best_params", {})
                record["proposal_to_best_distance"] = parameter_distance(
                    task.model, clean_params, record.get("best_params", {})
                )
                record["wall_time_s"] = round(
                    record.get("hydromodel_compute_time_s", 0.0) + llm_decision["llm_decision_time_s"], 3
                )
            else:
                record = {
                    **base_record,
                    "train_metrics": {},
                    "test_metrics": {},
                    "best_params": {},
                    "local_search_ranges": {},
                    "local_search_best_params": {},
                    "proposal_to_best_distance": None,
                    "hydromodel_compute_time_s": 0.0,
                    "wall_time_s": llm_decision["llm_decision_time_s"],
                    "success": False,
                    "error": "; ".join(issues),
                }

            append_jsonl(log_path, record)
            all_records.append(record)
            history.append(record)
            new_records.append(record)
            LOGGER.info(
                "C %s iter %d: valid=%s train_NSE=%s test_NSE=%s tokens=%s",
                task.task_id,
                iteration,
                valid,
                metric(record, "train", "NSE"),
                metric(record, "test", "NSE"),
                record.get("llm_tokens", {}).get("total_tokens"),
            )
            if (metric(record, "train", "NSE") or -999.0) >= NSE_TARGET:
                break

    write_json(out_dir / "summary.json", {"method": "C", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} Method C iteration record(s) -> {log_path}")


if __name__ == "__main__":
    main()

