"""Compile Exp3 v2 trial records into paper-facing tables."""

from __future__ import annotations

import collections

from common import (
    CONDITIONS,
    OUTPUT_ROOT,
    RAW_RECORDS,
    TABLES_DIR,
    TASKS,
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


def _condition_design_rows(records: list[dict]) -> list[dict]:
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
            "tools_enabled": condition["tools_enabled"],
            "knowledge_level": condition["knowledge_level"],
            "tool_schema_names": ",".join(sample.get("tool_schema_names", [])),
            "skill_injected": cid == "K2",
            "knowledge_injected": cid == "K2",
            "memory_injected": cid == "K2",
            "system_prompt_tokens_est": sample.get("system_prompt_tokens_est", ""),
            "tool_schema_tokens_est": sample.get("tool_schema_tokens_est", ""),
            "knowledge_input_tokens_est": sample.get("knowledge_input_tokens_est", 0 if cid != "K2" else ""),
        })
    return rows


def _condition_metrics(rows: list[dict]) -> dict:
    successes = [r.get("task_success") for r in rows]
    total_success = sum(1 for v in successes if bool(v))
    total_tokens = sum(float(r.get("total_tokens") or 0) for r in rows)
    return {
        "n_runs": len(rows),
        "task_success_rate": rate(successes),
        "tool_route_success_rate": rate([r.get("tool_route_success") for r in rows]),
        "first_tool_accuracy": rate([r.get("first_tool_accuracy") for r in rows]),
        "forbidden_tool_rate": rate([r.get("forbidden_tool_hit") for r in rows]),
        "hallucination_rate": rate([r.get("hallucination") for r in rows]),
        "mean_llm_calls": mean([r.get("llm_calls") for r in rows]),
        "mean_tool_calls": mean([r.get("tool_calls") for r in rows]),
        "mean_total_tokens": mean([r.get("total_tokens") for r in rows]),
        "mean_prompt_tokens": mean([r.get("prompt_tokens") for r in rows]),
        "mean_completion_tokens": mean([r.get("completion_tokens") for r in rows]),
        "mean_cached_tokens": mean([r.get("cached_tokens") for r in rows]),
        "mean_wall_time_s": mean([r.get("wall_time_s") for r in rows]),
        "mean_tool_compute_time_s": mean([r.get("tool_compute_time_s") for r in rows]),
        "mean_llm_decision_time_s": mean([r.get("llm_decision_time_s") for r in rows]),
        "mean_knowledge_input_tokens_est": mean([r.get("knowledge_input_tokens_est") for r in rows]),
        "tokens_per_success": round(total_tokens / total_success, 6) if total_success else "",
    }


def _core_rows(records: list[dict]) -> list[dict]:
    grouped = _group(records, "condition_id")
    metrics_by_condition = {}
    for condition in CONDITIONS:
        cid = condition["condition_id"]
        metrics_by_condition[cid] = _condition_metrics(grouped.get((cid,), []))

    k0 = metrics_by_condition.get("K0", {})
    k1 = metrics_by_condition.get("K1", {})
    k2 = metrics_by_condition.get("K2", {})
    success_k0 = k0.get("task_success_rate")
    success_k1 = k1.get("task_success_rate")
    success_k2 = k2.get("task_success_rate")
    tokens_k1 = k1.get("mean_total_tokens")
    tokens_k2 = k2.get("mean_total_tokens")

    rows = []
    for condition in CONDITIONS:
        cid = condition["condition_id"]
        row = {
            "condition_id": cid,
            "condition_name": condition["condition_name"],
            **metrics_by_condition[cid],
            "success_gain_vs_K0": "",
            "success_gain_vs_K1": "",
            "extra_tokens_vs_K1": "",
            "marginal_gain_per_10k_tokens": "",
        }
        if cid == "K1" and success_k1 is not None and success_k0 is not None:
            row["success_gain_vs_K0"] = round(success_k1 - success_k0, 6)
        if cid == "K2":
            if success_k2 is not None and success_k1 is not None:
                row["success_gain_vs_K1"] = round(success_k2 - success_k1, 6)
            if isinstance(tokens_k2, (int, float)) and isinstance(tokens_k1, (int, float)):
                delta_tokens = tokens_k2 - tokens_k1
                row["extra_tokens_vs_K1"] = round(delta_tokens, 6)
                if delta_tokens > 0 and success_k2 is not None and success_k1 is not None:
                    row["marginal_gain_per_10k_tokens"] = round((success_k2 - success_k1) / (delta_tokens / 10000), 6)
        rows.append(row)
    return rows


def _task_rows(records: list[dict]) -> list[dict]:
    grouped = _group(records, "condition_id", "task_id")
    rows = []
    for task in TASKS:
        for condition in CONDITIONS:
            cid = condition["condition_id"]
            subset = grouped.get((cid, task["task_id"]), [])
            rows.append({
                "task_id": task["task_id"],
                "task_name": task["task_name"],
                "condition_id": cid,
                "condition_name": condition["condition_name"],
                **_condition_metrics(subset),
            })
    return rows


def _trial_rows(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        rows.append({
            "run_id": r.get("run_id"),
            "condition_id": r.get("condition_id"),
            "task_id": r.get("task_id"),
            "repeat": r.get("repeat"),
            "task_success": r.get("task_success"),
            "tool_route_success": r.get("tool_route_success"),
            "first_tool_accuracy": r.get("first_tool_accuracy"),
            "forbidden_tool_hit": r.get("forbidden_tool_hit"),
            "hallucination": r.get("hallucination"),
            "llm_calls": r.get("llm_calls"),
            "tool_calls": r.get("tool_calls"),
            "total_tokens": r.get("total_tokens"),
            "wall_time_s": r.get("wall_time_s"),
            "tool_compute_time_s": r.get("tool_compute_time_s"),
            "llm_decision_time_s": r.get("llm_decision_time_s"),
            "knowledge_input_tokens_est": r.get("knowledge_input_tokens_est"),
            "actual_tools": ",".join(r.get("actual_tools", [])),
            "error": r.get("error"),
        })
    return rows


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(RAW_RECORDS)
    condition_design = _condition_design_rows(records)
    core = _core_rows(records)
    task = _task_rows(records)
    trials = _trial_rows(records)

    write_csv(TABLES_DIR / "table_exp3_condition_design.csv", condition_design)
    write_csv(TABLES_DIR / "table_exp3_core_results.csv", core)
    write_csv(TABLES_DIR / "table_exp3_task_level.csv", task)
    write_csv(TABLES_DIR / "tableS_exp3_trial_records.csv", trials)
    write_json(OUTPUT_ROOT / "compiled_results.json", {
        "schema_version": "exp3_v2_compiled_1",
        "n_records": len(records),
        "condition_design": condition_design,
        "core_results": core,
        "task_level_results": task,
        "trial_records": records,
    })
    print(f"Compiled {len(records)} Exp3 record(s) -> {OUTPUT_ROOT / 'compiled_results.json'}")


if __name__ == "__main__":
    main()
