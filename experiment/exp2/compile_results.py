"""Compile Exp2 v2 records into paper-facing tables."""

from __future__ import annotations

import collections

from common import (
    METHODS,
    OUTPUT_ROOT,
    TABLES_DIR,
    best_by_train,
    iter_tasks,
    median,
    method_dir,
    metric,
    read_jsonl,
    write_csv,
    write_json,
)


def _all_records() -> list[dict]:
    records: list[dict] = []
    for info in METHODS.values():
        records.extend(read_jsonl(method_dir(info["name"]) / "trials.jsonl"))
    return records


def _group(records: list[dict], *keys: str) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = collections.defaultdict(list)
    for record in records:
        grouped[tuple(record.get(k) for k in keys)].append(record)
    return grouped


def _sum_tokens(records: list[dict]) -> int:
    return int(sum((r.get("llm_tokens") or {}).get("total_tokens", 0) for r in records))


def _sum_time(records: list[dict], key: str) -> float:
    return round(sum(float(r.get(key) or 0.0) for r in records), 3)


def _best_map(records: list[dict]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for (method, task_id), rows in _group(records, "method", "task_id").items():
        if method in ("B", "C"):
            best = best_by_train(rows)
        else:
            best = rows[-1] if rows else None
        if best:
            out[(method, task_id)] = best
    return out


def _task_rows(records: list[dict]) -> list[dict]:
    bests = _best_map(records)
    grouped = _group(records, "method", "task_id")
    rows = []
    for task in iter_tasks(smoke=False):
        a = bests.get(("A", task.task_id), {})
        b = bests.get(("B", task.task_id), {})
        c = bests.get(("C", task.task_id), {})
        d = bests.get(("D", task.task_id), {})
        b_rows = grouped.get(("B", task.task_id), [])
        c_rows = grouped.get(("C", task.task_id), [])
        d_rows = grouped.get(("D", task.task_id), [])
        a_nse = metric(a, "test", "NSE")
        b_nse = metric(b, "test", "NSE")
        c_nse = metric(c, "test", "NSE")
        d_nse = metric(d, "test", "NSE")
        rows.append({
            "task_id": task.task_id,
            "basin_id": task.basin_id,
            "model": task.model,
            "A_test_NSE": a_nse,
            "B_test_NSE": b_nse,
            "C_test_NSE": c_nse,
            "D_test_NSE": d_nse,
            "A_test_KGE": metric(a, "test", "KGE"),
            "B_test_KGE": metric(b, "test", "KGE"),
            "C_test_KGE": metric(c, "test", "KGE"),
            "D_test_KGE": metric(d, "test", "KGE"),
            "delta_B_A_NSE": round(b_nse - a_nse, 6) if b_nse is not None and a_nse is not None else "",
            "delta_C_A_NSE": round(c_nse - a_nse, 6) if c_nse is not None and a_nse is not None else "",
            "delta_D_A_NSE": round(d_nse - a_nse, 6) if d_nse is not None and a_nse is not None else "",
            "delta_C_B_NSE": round(c_nse - b_nse, 6) if c_nse is not None and b_nse is not None else "",
            "delta_D_B_NSE": round(d_nse - b_nse, 6) if d_nse is not None and b_nse is not None else "",
            "delta_D_C_NSE": round(d_nse - c_nse, 6) if d_nse is not None and c_nse is not None else "",
            "B_iterations": len(b_rows),
            "C_iterations": len(c_rows),
            "D_rounds": d.get("rounds", ""),
            "B_valid_proposal_rate": round(
                sum(1 for r in b_rows if r.get("valid_proposal")) / len(b_rows), 4
            ) if b_rows else "",
            "C_valid_proposal_rate": round(
                sum(1 for r in c_rows if r.get("valid_proposal")) / len(c_rows), 4
            ) if c_rows else "",
            "B_tokens": _sum_tokens(b_rows),
            "C_tokens": _sum_tokens(c_rows),
            "D_tokens": _sum_tokens(d_rows),
            "B_wall_time_s": _sum_time(b_rows, "wall_time_s"),
            "C_wall_time_s": _sum_time(c_rows, "wall_time_s"),
            "D_wall_time_s": _sum_time(d_rows, "wall_time_s"),
        })
    return rows


def _method_rows() -> list[dict]:
    rows = []
    for method, info in METHODS.items():
        rows.append({
            "method": method,
            "name": info["name"],
            "llm_position": info["llm_position"],
            "numeric_action": info["numeric_action"],
            "max_rounds": info["max_rounds"],
            "cost_record": info["cost_record"],
        })
    return rows


def _d_evidence_rows(records: list[dict]) -> list[dict]:
    rows = []
    for record in [r for r in records if r.get("method") == "D"]:
        first = (record.get("history") or [{}])[0]
        initial = record.get("initial_range_evidence") or {}
        rows.append({
            "task_id": record.get("task_id"),
            "basin_id": record.get("basin_id"),
            "model": record.get("model"),
            "basin_attributes_used": bool(record.get("basin_attributes_used")),
            "basin_aware_init": bool(record.get("basin_aware_init")),
            "initial_range_changed": bool(initial.get("used")),
            "first_boundary_hit": bool(record.get("first_sceua_boundary_hit")),
            "first_boundary_params": ",".join(h.get("param", "") for h in first.get("boundary_hits", [])),
            "diagnostic_response_match": record.get("diagnostic_response_match"),
            "revised_search_improved": record.get("revised_search_improved"),
            "stop_reason": record.get("stop_reason"),
            "D_rounds": record.get("rounds"),
            "D_test_NSE": metric(record, "test", "NSE"),
            "D_test_KGE": metric(record, "test", "KGE"),
        })
    return rows


def _summary_rows(task_rows: list[dict]) -> list[dict]:
    rows = []
    for method in ["A", "B", "C", "D"]:
        rows.append({
            "method": method,
            "median_test_NSE": median([r.get(f"{method}_test_NSE") for r in task_rows]),
            "median_test_KGE": median([r.get(f"{method}_test_KGE") for r in task_rows]),
            "median_tokens": median([r.get(f"{method}_tokens") for r in task_rows if f"{method}_tokens" in r]),
            "median_wall_time_s": median([r.get(f"{method}_wall_time_s") for r in task_rows if f"{method}_wall_time_s" in r]),
        })
    return rows


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    records = _all_records()
    method_rows = _method_rows()
    task_rows = _task_rows(records)
    d_rows = _d_evidence_rows(records)
    summary_rows = _summary_rows(task_rows)
    write_csv(TABLES_DIR / "table43_methods.csv", method_rows)
    write_csv(TABLES_DIR / "table44_core_results.csv", task_rows)
    write_csv(TABLES_DIR / "table45_hydroagent_process_evidence.csv", d_rows)
    write_csv(TABLES_DIR / "tableS_exp2_method_summary.csv", summary_rows)
    write_json(OUTPUT_ROOT / "compiled_results.json", {
        "schema_version": "exp2_v2_compiled_1",
        "n_records": len(records),
        "methods": method_rows,
        "core_results": task_rows,
        "hydroagent_process_evidence": d_rows,
        "method_summary": summary_rows,
        "records": records,
    })
    print(f"Compiled {len(records)} records -> {OUTPUT_ROOT / 'compiled_results.json'}")


if __name__ == "__main__":
    main()

