"""Compile Exp1 v2 trial logs into paper-ready tables."""

from __future__ import annotations

import collections
import math

from common import (
    METHODS,
    OUTPUT_ROOT,
    TABLES_DIR,
    auc_best_so_far,
    best_record,
    flatten_metric,
    iqr,
    median,
    method_dir,
    percentile,
    read_jsonl,
    write_csv,
    write_json,
)


def _all_trials() -> list[dict]:
    trials: list[dict] = []
    for info in METHODS.values():
        name = info["name"]
        path = method_dir(name) / "trials.jsonl"
        trials.extend(read_jsonl(path))
    return trials


def _group(records: list[dict], *keys: str) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = collections.defaultdict(list)
    for record in records:
        grouped[tuple(record.get(k) for k in keys)].append(record)
    return grouped


def _best_by_task(records: list[dict]) -> dict[tuple[str, str], dict]:
    out = {}
    for (method, task_id), rows in _group(records, "method", "task_id").items():
        if method == "M3":
            continue
        best = best_record(rows)
        if best:
            out[(method, task_id)] = best
    return out


def _random_best_distribution(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for (task_id, repeat_idx), rows in _group([r for r in records if r.get("method") == "M3"], "task_id", "repeat_idx").items():
        best = best_record(rows)
        if best:
            out[task_id].append(best)
    return out


def table1_methods() -> list[dict]:
    rows = []
    for method, info in METHODS.items():
        rows.append({
            "method": method,
            "name": info["name"],
            "controller": info["controller"],
            "max_trials": info["max_trials"],
            "human_intervention": info["human_intervention"],
            "token_recorded": info["token_recorded"],
            "allowed_menu": "objective + budget + range_policy",
        })
    return rows


def _sum_tokens(records: list[dict]) -> int:
    return int(sum((r.get("llm_tokens") or {}).get("total_tokens", 0) for r in records))


def _sum_active(records: list[dict]) -> float:
    return round(sum(float(r.get("active_seconds") or 0.0) for r in records) / 60.0, 4)


def _metric_values(best_records: list[dict], period: str, metric: str) -> list[float]:
    vals = []
    for record in best_records:
        value = flatten_metric(record, period, metric)
        if isinstance(value, (int, float)) and math.isfinite(value):
            vals.append(value)
    return vals


def table2_summary(records: list[dict]) -> tuple[list[dict], list[dict]]:
    best_map = _best_by_task(records)
    random_dist = _random_best_distribution(records)
    rows = []
    task_rows = []

    for method in ["M0", "M1", "M2"]:
        bests = [record for (m, _), record in best_map.items() if m == method]
        method_trials = [r for r in records if r.get("method") == method]
        rows.append({
            "method": method,
            "n_tasks": len(bests),
            "median_test_NSE": median(_metric_values(bests, "test", "NSE")),
            "median_test_KGE": median(_metric_values(bests, "test", "KGE")),
            "median_trials_to_best": median([float(r.get("trial_idx", 0)) for r in bests]),
            "human_active_min": _sum_active(method_trials),
            "total_tokens": _sum_tokens(method_trials),
            "minutes_saved_per_10k_tokens": "",
            "agent_vs_random_percentile": "",
        })

    # Random aggregate over per-repeat best records.
    random_bests = [b for vals in random_dist.values() for b in vals]
    rows.append({
        "method": "M3",
        "n_tasks": len(random_dist),
        "median_test_NSE": median(_metric_values(random_bests, "test", "NSE")),
        "median_test_KGE": median(_metric_values(random_bests, "test", "KGE")),
        "median_trials_to_best": median([float(r.get("trial_idx", 0)) for r in random_bests]),
        "human_active_min": 0,
        "total_tokens": 0,
        "minutes_saved_per_10k_tokens": "",
        "agent_vs_random_percentile": "",
    })

    agent_percentiles = []
    saved_minutes = []
    for (_, task_id), agent in sorted((k, v) for k, v in best_map.items() if k[0] == "M2"):
        human = best_map.get(("M1", task_id))
        random_scores = [flatten_metric(r, "test", "NSE") for r in random_dist.get(task_id, [])]
        random_scores = [v for v in random_scores if isinstance(v, (int, float))]
        agent_nse = flatten_metric(agent, "test", "NSE")
        pct = percentile(agent_nse, random_scores)
        if pct is not None:
            agent_percentiles.append(pct)
        human_trials = [r for r in records if r.get("method") == "M1" and r.get("task_id") == task_id]
        agent_trials = [r for r in records if r.get("method") == "M2" and r.get("task_id") == task_id]
        saved = _sum_active(human_trials)
        if human:
            saved_minutes.append(saved)
        random_q1, random_q3 = iqr(random_scores)
        task_rows.append({
            "task_id": task_id,
            "basin_id": agent.get("basin_id"),
            "model": agent.get("model"),
            "human_test_NSE": flatten_metric(human, "test", "NSE") if human else "",
            "agent_test_NSE": agent_nse,
            "delta_agent_human_NSE": round(agent_nse - flatten_metric(human, "test", "NSE"), 6) if human and agent_nse is not None and flatten_metric(human, "test", "NSE") is not None else "",
            "agent_test_KGE": flatten_metric(agent, "test", "KGE"),
            "random_median_NSE": median(random_scores),
            "random_IQR_low": random_q1,
            "random_IQR_high": random_q3,
            "agent_random_percentile": pct,
            "agent_auc_best_NSE": auc_best_so_far(agent_trials),
            "human_auc_best_NSE": auc_best_so_far(human_trials),
            "human_active_min": _sum_active(human_trials),
            "agent_tokens": _sum_tokens(agent_trials),
        })

    for row in rows:
        if row["method"] == "M2":
            tokens = row["total_tokens"]
            saved = sum(saved_minutes)
            row["human_active_min"] = 0
            row["minutes_saved_per_10k_tokens"] = round(saved * 10000 / tokens, 4) if tokens else ""
            row["agent_vs_random_percentile"] = median(agent_percentiles)
        if row["method"] == "M1":
            row["human_active_min"] = round(row["human_active_min"], 4)

    return rows, task_rows


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    records = _all_trials()
    table1 = table1_methods()
    table2, task_rows = table2_summary(records)

    write_csv(TABLES_DIR / "table1_methods.csv", table1)
    write_csv(TABLES_DIR / "table2_core_results.csv", table2)
    write_csv(TABLES_DIR / "tableS1_task_level_results.csv", task_rows)
    write_json(OUTPUT_ROOT / "compiled_results.json", {
        "schema_version": "exp1_v2_compiled_1",
        "n_trials": len(records),
        "table1_methods": table1,
        "table2_core_results": table2,
        "task_level_results": task_rows,
        "trial_records": records,
    })
    print(f"Compiled {len(records)} trial records -> {OUTPUT_ROOT / 'compiled_results.json'}")


if __name__ == "__main__":
    main()
