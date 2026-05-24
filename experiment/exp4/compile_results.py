"""Compile Exp4 v2 boundary experiment outputs."""

from __future__ import annotations

import collections

from common import (
    CONDITIONS,
    OUTPUT_ROOT,
    RAW_RECORDS,
    SCENARIOS,
    TABLES_DIR,
    mean,
    rate,
    read_jsonl,
    write_csv,
    write_json,
)


def _group(records: list[dict], *keys: str) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = collections.defaultdict(list)
    for record in records:
        grouped[tuple(record.get(k) for k in keys)].append(record)
    return grouped


def _condition_rows(records: list[dict]) -> list[dict]:
    latest = {}
    for record in records:
        latest[record.get("condition_id")] = record
    rows = []
    for condition in CONDITIONS:
        cid = condition["condition_id"]
        sample = latest.get(cid, {})
        rows.append({
            "condition_id": cid,
            "condition_name": condition["condition_name"],
            "description": condition["description"],
            "allowed_tools": ",".join(condition["allowed_tools"]),
            "observed_tool_schemas": ",".join(sample.get("tool_schema_names", [])),
            "allows_execution": condition["allows_execution"],
            "allows_dynamic_generation": condition["allows_dynamic_generation"],
        })
    return rows


def _metrics(rows: list[dict]) -> dict:
    return {
        "n_runs": len(rows),
        "task_success_rate": rate([r.get("task_success") for r in rows]),
        "controlled_failure_rate": rate([r.get("controlled_failure") for r in rows]),
        "information_missing_rate": rate([r.get("information_missing_failure") for r in rows]),
        "missing_tool_rate": rate([r.get("missing_tool_failure") for r in rows]),
        "logic_error_rate": rate([r.get("logic_error_failure") for r in rows]),
        "hallucination_rate": rate([r.get("hallucinated_result") for r in rows]),
        "fabricated_tool_rate": rate([r.get("fabricated_tool") for r in rows]),
        "wrong_tool_route_rate": rate([r.get("wrong_tool_route") for r in rows]),
        "ask_user_rate": rate([r.get("ask_user_called") for r in rows]),
        "create_skill_rate": rate([r.get("create_skill_called") for r in rows]),
        "recovery_success_rate": rate([r.get("recovery_success") for r in rows]),
        "mean_recovery_turns": mean([r.get("recovery_turns") for r in rows if r.get("create_skill_called")]),
        "mean_recovery_tokens": mean([r.get("recovery_tokens") for r in rows if r.get("create_skill_called")]),
        "mean_llm_calls": mean([r.get("llm_calls") for r in rows]),
        "mean_tool_calls": mean([r.get("tool_calls") for r in rows]),
        "mean_prompt_tokens": mean([r.get("prompt_tokens") for r in rows]),
        "mean_completion_tokens": mean([r.get("completion_tokens") for r in rows]),
        "mean_cached_tokens": mean([r.get("cached_tokens") for r in rows]),
        "mean_total_tokens": mean([r.get("total_tokens") for r in rows]),
        "mean_wall_time_s": mean([r.get("wall_time_s") for r in rows]),
        "mean_tool_compute_time_s": mean([r.get("tool_compute_time_s") for r in rows]),
        "mean_llm_decision_time_s": mean([r.get("llm_decision_time_s") for r in rows]),
    }


def _failure_mode_rows(records: list[dict]) -> list[dict]:
    grouped = _group(records, "condition_id")
    rows = []
    for condition in CONDITIONS:
        cid = condition["condition_id"]
        rows.append({
            "condition_id": cid,
            "condition_name": condition["condition_name"],
            **_metrics(grouped.get((cid,), [])),
        })
    return rows


def _scenario_rows(records: list[dict]) -> list[dict]:
    grouped = _group(records, "condition_id", "scenario_id")
    rows = []
    for scenario in SCENARIOS:
        for condition in CONDITIONS:
            cid = condition["condition_id"]
            rows.append({
                "scenario_id": scenario["scenario_id"],
                "scenario_name": scenario["scenario_name"],
                "boundary_type": scenario["boundary_type"],
                "condition_id": cid,
                "condition_name": condition["condition_name"],
                **_metrics(grouped.get((cid, scenario["scenario_id"]), [])),
            })
    return rows


def _trial_rows(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        rows.append({
            "run_id": r.get("run_id"),
            "condition_id": r.get("condition_id"),
            "scenario_id": r.get("scenario_id"),
            "boundary_type": r.get("boundary_type"),
            "repeat": r.get("repeat"),
            "task_success": r.get("task_success"),
            "controlled_failure": r.get("controlled_failure"),
            "information_missing_failure": r.get("information_missing_failure"),
            "missing_tool_failure": r.get("missing_tool_failure"),
            "logic_error_failure": r.get("logic_error_failure"),
            "hallucinated_result": r.get("hallucinated_result"),
            "fabricated_tool": r.get("fabricated_tool"),
            "wrong_tool_route": r.get("wrong_tool_route"),
            "ask_user_called": r.get("ask_user_called"),
            "create_skill_called": r.get("create_skill_called"),
            "recovery_success": r.get("recovery_success"),
            "recovery_turns": r.get("recovery_turns"),
            "recovery_tokens": r.get("recovery_tokens"),
            "llm_calls": r.get("llm_calls"),
            "tool_calls": r.get("tool_calls"),
            "prompt_tokens": r.get("prompt_tokens"),
            "completion_tokens": r.get("completion_tokens"),
            "cached_tokens": r.get("cached_tokens"),
            "total_tokens": r.get("total_tokens"),
            "wall_time_s": r.get("wall_time_s"),
            "tool_compute_time_s": r.get("tool_compute_time_s"),
            "llm_decision_time_s": r.get("llm_decision_time_s"),
            "actual_tools": ",".join(r.get("actual_tools", [])),
            "error": r.get("error"),
        })
    return rows


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(RAW_RECORDS)
    condition_rows = _condition_rows(records)
    failure_rows = _failure_mode_rows(records)
    scenario_rows = _scenario_rows(records)
    trial_rows = _trial_rows(records)

    write_csv(TABLES_DIR / "table_exp4_tool_conditions.csv", condition_rows)
    write_csv(TABLES_DIR / "table_exp4_failure_modes.csv", failure_rows)
    write_csv(TABLES_DIR / "table_exp4_recovery_cost.csv", scenario_rows)
    write_csv(TABLES_DIR / "tableS_exp4_trial_records.csv", trial_rows)
    write_json(OUTPUT_ROOT / "compiled_results.json", {
        "schema_version": "exp4_v2_compiled_1",
        "n_records": len(records),
        "tool_conditions": condition_rows,
        "failure_modes": failure_rows,
        "recovery_cost": scenario_rows,
        "trial_records": records,
    })
    print(f"Compiled {len(records)} Exp4 record(s) -> {OUTPUT_ROOT / 'compiled_results.json'}")


if __name__ == "__main__":
    main()
