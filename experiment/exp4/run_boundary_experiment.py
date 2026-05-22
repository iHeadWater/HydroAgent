"""Run Exp4 v2 capability-boundary and controlled-failure experiment."""

from __future__ import annotations

import argparse
import logging
import time

from common import (
    DEFAULT_REPEATS,
    RAW_RECORDS,
    RUNS_DIR,
    SCENARIO_BY_ID,
    append_jsonl,
    apply_tool_condition,
    classify_trial,
    ensure_dirs,
    estimate_json_tokens,
    iter_trial_keys,
    now,
    read_jsonl,
    summarize_times,
    token_summary,
    tool_sequence,
    write_json,
)


LOGGER = logging.getLogger(__name__)


class NonInteractiveUI:
    """Minimal UI that records events without blocking on ask_user."""

    def __init__(self):
        self.tool_events = []

    def on_query(self, query):  # noqa: D401
        pass

    def on_answer(self, answer, turn=None):
        pass

    def on_max_turns(self):
        pass

    def on_tool_start(self, name, args):
        self.tool_events.append({"event": "start", "tool": name, "args": args})

    def on_tool_end(self, name, result, elapsed):
        self.tool_events.append({"event": "end", "tool": name, "elapsed": elapsed})

    def on_session_summary(self, **kwargs):
        pass

    def dev_log(self, message):
        pass

    def on_thought(self, thought, turn=None):
        pass

    def ask_user(self, question, context=None):
        self.tool_events.append({"event": "ask_user", "question": question, "context": context})
        return ""

    def thinking(self, turn):
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    def suppress_tool_output(self, name):
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


def _parse_csv_arg(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _make_agent(workspace, max_turns: int):
    from hydroagent.agent import HydroAgent

    return HydroAgent(
        workspace=workspace,
        ui=NonInteractiveUI(),
        config_override={"max_turns": max_turns},
    )


def _run_one(key, *, max_turns: int) -> dict:
    scenario = SCENARIO_BY_ID[key.scenario_id]
    run_dir = RUNS_DIR / key.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    agent = _make_agent(run_dir, max_turns=max_turns)
    final_response = ""
    error = None
    wall_time_s = 0.0
    condition_meta = {}

    with apply_tool_condition(agent, key.condition_id) as condition_meta:
        context = agent._build_context(scenario["query"])
        initial_context_tokens_est = estimate_json_tokens(context)
        agent.memory._log.clear()
        t0 = now()
        try:
            final_response = agent.run(scenario["query"])
        except Exception as exc:
            error = str(exc)
            LOGGER.exception("%s failed", key.run_id)
        finally:
            wall_time_s = round(time.time() - t0, 3)

    tool_log = list(agent.memory._log)
    actual_tools = tool_sequence(tool_log)
    tokens = token_summary(agent)
    record = {
        "schema_version": "exp4_v2_trial_1",
        "run_id": key.run_id,
        "condition_id": key.condition_id,
        "condition_name": condition_meta.get("condition_name", ""),
        "scenario_id": key.scenario_id,
        "scenario_name": scenario["scenario_name"],
        "boundary_type": scenario["boundary_type"],
        "repeat": key.repeat,
        "query": scenario["query"],
        "description": scenario["description"],
        "success_tools": scenario.get("success_tools", []),
        "forbidden_tools": scenario.get("forbidden_tools", []),
        "active_tool_names": condition_meta.get("active_tool_names", []),
        "tool_schema_names": condition_meta.get("tool_schema_names", []),
        "tool_schema_tokens_est": condition_meta.get("tool_schema_tokens_est", 0),
        "initial_context_tokens_est": initial_context_tokens_est,
        "llm_calls": tokens.get("calls", 0),
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
        "cached_tokens": tokens.get("cached_tokens", 0),
        "total_tokens": tokens.get("total_tokens", 0),
        "tool_calls": len(actual_tools),
        "actual_tools": actual_tools,
        "tool_log": tool_log,
        "ui_tool_events": getattr(agent.ui, "tool_events", []),
        "wall_time_s": wall_time_s,
        "final_response": final_response or "",
        "final_response_preview": (final_response or "")[:1000],
        "error": error,
        "run_dir": str(run_dir),
    }
    record.update(summarize_times(tool_log, wall_time_s))
    record.update(classify_trial(record, final_response or ""))
    write_json(run_dir / "trial_record.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run all conditions on S1 once")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--conditions", default="B0,B1,B2")
    parser.add_argument("--scenarios", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-turns", type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    if args.overwrite and RAW_RECORDS.exists():
        RAW_RECORDS.unlink()

    existing = {r.get("run_id") for r in read_jsonl(RAW_RECORDS)}
    keys = iter_trial_keys(
        conditions=_parse_csv_arg(args.conditions),
        scenarios=_parse_csv_arg(args.scenarios),
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
            "%s success=%s controlled=%s hallucination=%s logic_error=%s tools=%s tokens=%s",
            key.run_id,
            record["task_success"],
            record["controlled_failure"],
            record["hallucinated_result"],
            record["logic_error_failure"],
            record["actual_tools"],
            record["total_tokens"],
        )

    write_json(
        RUNS_DIR / "run_summary.json",
        {
            "new_records": len(new_records),
            "total_records": len(read_jsonl(RAW_RECORDS)),
            "raw_records": str(RAW_RECORDS),
        },
    )
    print(f"Saved {len(new_records)} new Exp4 record(s) -> {RAW_RECORDS}")


if __name__ == "__main__":
    main()
