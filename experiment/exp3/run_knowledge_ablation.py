"""Run Exp3 v2 knowledge-input ablation."""

from __future__ import annotations

import argparse
import logging
import time

from common import (
    DEFAULT_REPEATS,
    RAW_RECORDS,
    RUNS_DIR,
    TASK_BY_ID,
    append_jsonl,
    apply_condition,
    ensure_dirs,
    estimate_json_tokens,
    evaluate_trial_record,
    iter_trial_keys,
    read_jsonl,
    run_wall_clock,
    summarize_times,
    token_summary,
    tool_sequence,
    write_json,
)


LOGGER = logging.getLogger(__name__)


def _parse_csv_arg(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _make_agent(workspace, max_turns: int):
    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    return HydroAgent(
        workspace=workspace,
        ui=ConsoleUI(mode="user"),
        config_override={"max_turns": max_turns},
    )


def _run_one(key, *, max_turns: int) -> dict:
    task = TASK_BY_ID[key.task_id]
    run_dir = RUNS_DIR / key.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    agent = _make_agent(run_dir, max_turns=max_turns)
    final_response = ""
    error = None
    wall_time_s = 0.0
    condition_meta = {}

    with apply_condition(agent, key.condition_id) as condition_meta:
        context = agent._build_context(task["query"])
        initial_context_tokens_est = estimate_json_tokens(context)
        agent.memory._log.clear()
        t0 = run_wall_clock()
        try:
            final_response = agent.run(task["query"])
        except Exception as exc:
            error = str(exc)
            LOGGER.exception("%s failed", key.run_id)
        finally:
            wall_time_s = round(time.time() - t0, 3)

    tool_log = list(agent.memory._log)
    actual_tools = tool_sequence(tool_log)
    tokens = token_summary(agent)
    record = {
        "schema_version": "exp3_v2_trial_1",
        "run_id": key.run_id,
        "condition_id": key.condition_id,
        "condition_name": condition_meta.get("condition_name", ""),
        "task_id": key.task_id,
        "task_name": task["task_name"],
        "repeat": key.repeat,
        "query": task["query"],
        "description": task["description"],
        "expected_tools": task["expected_tools"],
        "forbidden_tools": task.get("forbidden_tools", []),
        "active_tool_names": condition_meta.get("active_tool_names", []),
        "tool_schema_names": condition_meta.get("tool_schema_names", []),
        "system_prompt_tokens_est": condition_meta.get("system_prompt_tokens_est", 0),
        "tool_schema_tokens_est": condition_meta.get("tool_schema_tokens_est", 0),
        "knowledge_input_tokens_est": condition_meta.get("knowledge_input_tokens_est", 0),
        "initial_context_tokens_est": initial_context_tokens_est,
        "llm_calls": tokens.get("calls", 0),
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
        "cached_tokens": tokens.get("cached_tokens", 0),
        "total_tokens": tokens.get("total_tokens", 0),
        "tool_calls": len(actual_tools),
        "actual_tools": actual_tools,
        "tool_log": tool_log,
        "wall_time_s": wall_time_s,
        "final_response": final_response or "",
        "final_response_preview": (final_response or "")[:1000],
        "error": error,
        "run_dir": str(run_dir),
    }
    record.update(summarize_times(tool_log, wall_time_s))
    record.update(evaluate_trial_record(record, final_response or ""))
    write_json(run_dir / "trial_record.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run K0/K1/K2 on T1 once")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--conditions", default="K0,K1,K2")
    parser.add_argument("--tasks", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    if args.overwrite and RAW_RECORDS.exists():
        RAW_RECORDS.unlink()

    existing = {r.get("run_id") for r in read_jsonl(RAW_RECORDS)}
    keys = iter_trial_keys(
        conditions=_parse_csv_arg(args.conditions),
        task_ids=_parse_csv_arg(args.tasks),
        repeats=args.repeats,
        smoke=args.smoke,
    )
    new_records = []
    for key in keys:
        if key.run_id in existing:
            LOGGER.info("Skip existing %s", key.run_id)
            continue
        record = _run_one(key, max_turns=args.max_turns)
        append_jsonl(RAW_RECORDS, record)
        new_records.append(record)
        LOGGER.info(
            "%s success=%s route=%s hallucination=%s tokens=%s tools=%s",
            key.run_id,
            record["task_success"],
            record["tool_route_success"],
            record["hallucination"],
            record["total_tokens"],
            record["actual_tools"],
        )

    write_json(
        RUNS_DIR / "run_summary.json",
        {
            "new_records": len(new_records),
            "total_records": len(read_jsonl(RAW_RECORDS)),
            "raw_records": str(RAW_RECORDS),
        },
    )
    print(f"Saved {len(new_records)} new Exp3 record(s) -> {RAW_RECORDS}")


if __name__ == "__main__":
    main()
