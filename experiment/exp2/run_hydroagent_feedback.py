"""Method D: HydroAgent feedback-style calibration with basin-aware initialization."""

from __future__ import annotations

import argparse
import logging
import time

from common import (
    MAX_ITERS,
    NSE_TARGET,
    OBJECTIVE,
    STANDARD_BUDGET,
    TEST_PERIOD,
    TRAIN_PERIOD,
    append_jsonl,
    ensure_dirs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    token_delta,
    token_summary,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def _best_history_round(history: list[dict]) -> dict:
    valid = []
    for row in history:
        nse = (row.get("train_metrics") or {}).get("NSE")
        if isinstance(nse, (int, float)):
            valid.append((float(nse), row))
    return max(valid, key=lambda item: item[0])[1] if valid else {}


def _diagnostic_response_match(first_round: dict, target: float) -> bool | None:
    if not first_round:
        return None
    adjustment = first_round.get("llm_adjustment") or {}
    changed = set((adjustment.get("changed_ranges") or {}).keys())
    hits = {h.get("param") for h in first_round.get("boundary_hits", []) if h.get("param")}
    if hits:
        return bool(changed.intersection(hits))
    nse = (first_round.get("train_metrics") or {}).get("NSE")
    if isinstance(nse, (int, float)) and nse < target:
        return bool(changed or adjustment.get("algorithm_params"))
    return adjustment.get("stop_reason") in ("target_reached", "llm_no_change", "max_rounds")


def _revised_search_improved(history: list[dict]) -> bool | None:
    if not history:
        return None
    first_nse = (history[0].get("train_metrics") or {}).get("NSE")
    if not isinstance(first_nse, (int, float)):
        return None
    for row in history[1:]:
        nse = (row.get("train_metrics") or {}).get("NSE")
        if isinstance(nse, (int, float)) and nse > first_nse:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=MAX_ITERS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("hydroagent_feedback")
    log_path = out_dir / "trials.jsonl"
    if args.overwrite and log_path.exists():
        log_path.unlink()

    from hydroagent.llm import LLMClient
    from hydroagent.skills.llm_calibration.llm_calibrate import llm_calibrate

    llm = LLMClient(cfg["llm"])
    existing = {(r.get("task_id"), r.get("method")) for r in read_jsonl(log_path)}
    new_records = []

    for task in iter_tasks(args.smoke):
        if (task.task_id, "D") in existing:
            LOGGER.info("Skip existing D %s", task.task_id)
            continue
        task_dir = out_dir / task.task_id
        before = token_summary(llm)
        t0 = time.time()
        result = llm_calibrate(
            basin_ids=[task.basin_id],
            model_name=task.model,
            max_rounds=min(args.max_rounds, MAX_ITERS),
            nse_target=NSE_TARGET,
            algorithm="SCE_UA",
            algorithm_params=STANDARD_BUDGET[task.model],
            train_period=TRAIN_PERIOD,
            test_period=TEST_PERIOD,
            obj_func=OBJECTIVE,
            output_dir=str(task_dir),
            _workspace=task_dir,
            _cfg=cfg,
            _llm=llm,
        )
        wall = round(time.time() - t0, 3)
        tokens = token_delta(before, token_summary(llm))
        history = result.get("history", []) if isinstance(result, dict) else []
        best_round = _best_history_round(history)
        first_round = history[0] if history else {}
        last_round = history[-1] if history else {}
        record = {
            **task.to_dict(),
            "method": "D",
            "method_name": "hydroagent_feedback",
            "success": bool(result.get("success")) if isinstance(result, dict) else False,
            "error": result.get("error") if isinstance(result, dict) else "llm_calibrate returned non-dict",
            "rounds": result.get("rounds") if isinstance(result, dict) else 0,
            "best_params": result.get("best_params", {}) if isinstance(result, dict) else {},
            "calibration_dir": result.get("calibration_dir", "") if isinstance(result, dict) else "",
            "train_metrics": best_round.get("train_metrics", {}),
            "test_metrics": best_round.get("test_metrics", {}),
            "history": history,
            "nse_history": result.get("nse_history", []) if isinstance(result, dict) else [],
            "test_nse_history": result.get("test_nse_history", []) if isinstance(result, dict) else [],
            "kge_history": result.get("kge_history", []) if isinstance(result, dict) else [],
            "test_kge_history": result.get("test_kge_history", []) if isinstance(result, dict) else [],
            "basin_attributes_used": result.get("basin_attributes_used") if isinstance(result, dict) else None,
            "basin_aware_init": result.get("basin_aware_init") if isinstance(result, dict) else False,
            "initial_range_evidence": result.get("initial_range_evidence", {}) if isinstance(result, dict) else {},
            "first_sceua_boundary_hit": bool(first_round.get("boundary_hits")),
            "diagnostic_response_match": _diagnostic_response_match(first_round, NSE_TARGET),
            "revised_search_improved": _revised_search_improved(history),
            "stop_reason": (last_round.get("llm_adjustment") or {}).get("stop_reason", ""),
            "llm_tokens": tokens,
            "wall_time_s": wall,
            "hydromodel_compute_time_s": round(
                sum(float(r.get("hydromodel_compute_time_s") or 0.0) for r in history), 3
            ),
            "llm_decision_time_s": round(
                sum(float(r.get("llm_decision_time_s") or 0.0) for r in history)
                + float((result.get("initial_range_evidence") or {}).get("elapsed_s") or 0.0),
                3,
            ) if isinstance(result, dict) else 0.0,
        }
        append_jsonl(log_path, record)
        new_records.append(record)
        LOGGER.info("D %s: success=%s rounds=%s test_NSE=%s", task.task_id, record["success"], record["rounds"], record["test_metrics"].get("NSE"))

    write_json(out_dir / "summary.json", {"method": "D", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} Method D record(s) -> {log_path}")


if __name__ == "__main__":
    main()
