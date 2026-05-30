"""Exp1 - Method D: LLM-LocalSearch calibration.

每代 LLM 提议一组参数,然后在该提议周围 +/-3% 的 NORMALIZED 窗口里用 scipy
SLSQP 做局部精修(目标:训练期 NSE)。相比纯 LLM-Direct (C),这一步把 LLM
的物理直觉和数值优化的精度结合起来 — 但也会因为优化 TRAIN NSE 在结构性
硬流域上反过来放大过拟合(见正文 D vs C 讨论)。

This script DELIBERATELY bypasses the HydroAgent agentic loop and uses the LLM
client + hydromodel skills directly — the loop is too heavy for a tight
per-iteration numerical search. See ``exp1_hydroagent.py`` for the variant
that does use ``agent.run()`` end-to-end.

Numeric / LLM helpers come from ``experiment/exp1/_common.py``.

Run (default: 3 demo basins, min50/max200 with early-stop):
    python experiment/exp1/exp1_llm_localsearch.py

Quick smoke (1 basin, 5 iterations):
    python experiment/exp1/exp1_llm_localsearch.py --basins 12025000 --max-iters 5 --overwrite

Output: experiment/exp1/results_llm_localsearch/trials.jsonl
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))      # exp1/ for _common.py

from _common import (  # noqa: E402
    Task,
    append_jsonl,
    ask_llm_for_params,
    get_basin_attrs,
    load_base_config,
    metric,
    parameter_distance,
    run_calibration,
    tight_ranges_around,
    validate_parameter_set,
)

# 3 representative CAMELS-US basins (easy / medium / hard) for GR4J.
BASINS = [
    {"basin_id": "12025000", "name": "Newaukum River, WA", "climate_zone": "mediterranean"},
    {"basin_id": "07197000", "name": "Baron Fork, OK",     "climate_zone": "humid_warm"},
    {"basin_id": "08101000", "name": "Cowhouse Creek, TX", "climate_zone": "semiarid"},
]
MODEL = "gr4j"

MIN_ITERS = 50
MAX_ITERS = 200
EARLY_STOP_PATIENCE = 10
EARLY_STOP_EPS = 0.005
LOCAL_SEARCH_BUDGET = {"gr4j": {"method": "SLSQP", "max_iterations": 30}}
LOCAL_SEARCH_WINDOW = 0.03   # +/-3% normalized window around each LLM proposal

OUT = Path(__file__).parent / "results_llm_localsearch"


def run_on_basin(basin: dict, cfg: dict, log_path: Path, max_iters: int,
                 window: float) -> list[dict]:
    """Sequential LLM-LocalSearch loop on one basin; early-stop on best train NSE."""
    from hydroagent.llm import LLMClient

    task = Task(basin_id=basin["basin_id"], basin_name=basin["name"],
                climate_zone=basin["climate_zone"], model=MODEL)
    llm = LLMClient(cfg["llm"])
    attrs = get_basin_attrs(task, cfg)

    history, records = [], []
    best_train, no_improve = None, 0
    for iteration in range(1, max_iters + 1):
        decision = ask_llm_for_params(llm, task, attrs, history)
        valid, clean, issues = validate_parameter_set(task.model, decision["proposed_params"])

        run_dir = log_path.parent / task.task_id / f"iter_{iteration:02d}"
        if valid:
            ranges = tight_ranges_around(task.model, clean, window)
            record = run_calibration(
                task=task, run_dir=run_dir, cfg=cfg,
                algorithm="scipy",
                algorithm_params=LOCAL_SEARCH_BUDGET[task.model],
                param_ranges=ranges,
                repeat_seed_offset=iteration * 137,
            )
            record["local_search_ranges"] = ranges
            record["proposal_to_best_distance"] = parameter_distance(
                task.model, clean, record.get("best_params", {})
            )
        else:
            record = {**task.to_dict(),
                      "train_metrics": {}, "test_metrics": {}, "best_params": {},
                      "success": False, "error": "; ".join(issues),
                      "hydromodel_compute_time_s": 0.0}

        record.update({
            "method": "D",
            "method_name": "llm_local_search",
            "iteration": iteration,
            "basin_attributes": attrs,
            "proposed_params": decision["proposed_params"],
            "valid_proposal": valid,
            "proposal_issues": issues,
            "llm_tokens": decision["llm_tokens"],
            "llm_decision_time_s": decision["llm_decision_time_s"],
            "raw_response": decision["raw_response"],
            "wall_time_s": round(
                decision["llm_decision_time_s"] + record.get("hydromodel_compute_time_s", 0.0), 3),
        })
        append_jsonl(log_path, record)
        history.append(record)
        records.append(record)

        tr = metric(record, "train", "NSE")
        if isinstance(tr, (int, float)):
            if best_train is None or tr > best_train + EARLY_STOP_EPS:
                best_train = tr if best_train is None else max(best_train, tr)
                no_improve = 0
            else:
                best_train = max(best_train, tr) if best_train is not None else tr
                no_improve += 1
        if iteration >= MIN_ITERS and no_improve >= EARLY_STOP_PATIENCE:
            break
    return records


def _best(records: list[dict], period: str) -> float | None:
    vals = [metric(r, period, "NSE") for r in records]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max(vals) if vals else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basins", default="", help="逗号分隔的 basin_id,默认 3 个示范流域")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    parser.add_argument("--window", type=float, default=LOCAL_SEARCH_WINDOW)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    cfg = load_base_config()
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "trials.jsonl"
    if args.overwrite and log_path.exists():
        log_path.unlink()

    selected = [b.strip() for b in args.basins.split(",") if b.strip()]
    basins = [b for b in BASINS if not selected or b["basin_id"] in selected]

    print(f"=== Method D (LLM-LocalSearch): {len(basins)} basin(s), "
          f"min={MIN_ITERS} max={args.max_iters} patience={EARLY_STOP_PATIENCE} "
          f"window=±{args.window*100:.0f}% ===")
    t0 = time.time()
    for basin in basins:
        recs = run_on_basin(basin, cfg, log_path, args.max_iters, args.window)
        bt, be = _best(recs, "train"), _best(recs, "test")
        bts = f"{bt:.3f}" if isinstance(bt, (int, float)) else "NA"
        bes = f"{be:.3f}" if isinstance(be, (int, float)) else "NA"
        print(f"  {basin['basin_id']}: {len(recs)} iter, best train={bts} test={bes}")
    print(f"Method D done in {time.time() - t0:.0f}s -> {log_path}")


if __name__ == "__main__":
    main()
