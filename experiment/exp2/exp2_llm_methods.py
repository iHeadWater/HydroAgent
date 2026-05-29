"""Exp2 LLM-in-the-loop calibration methods C and D (minimal handover demo).

Two LLM-driven calibration strategies, both of which place the LLM *before* the
numerical step (so they bypass the full HydroAgent agentic loop and call the
LLM client + hydromodel skills directly — this is intentional, the loop is too
heavy for a tight per-iteration numerical search):

  - Method C  "LLM-Direct" (a.k.a. Zhu direct evaluation):
        each iteration the LLM proposes ONE physical parameter set; it is
        evaluated as-is (no optimisation). Diversified sampling regularises
        against over-fitting.

  - Method D  "LLM-LocalSearch":
        each iteration the LLM proposes a parameter set, then a tight scipy
        local search (SLSQP, +/-3% window) refines it on the TRAIN objective.

Both run a sequential per-basin loop: at least MIN_ITERS iterations, then stop
once the best TRAIN NSE has not improved for EARLY_STOP_PATIENCE iterations
(capped at MAX_ITERS). All numeric/LLM helpers are reused from
``experiment/exp2/common.py``.

Run (single basin, one method, quick smoke):
    python experiment/exp2/exp2_llm_methods.py --method C --basins 08101000 --max-iters 20

Run (default: both methods, the 3 demo basins):
    python experiment/exp2/exp2_llm_methods.py

Output:
    experiment/exp2/results_llm_methods/method_{C,D}/trials.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))      # exp2/ for common.py

from common import (  # noqa: E402  (from experiment/exp2/common.py)
    Task,
    append_jsonl,
    ask_llm_for_params,
    evaluate_parameter_set,
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

# Iteration budget + early stop (same policy as the full exp2_new runners).
MIN_ITERS = 50
MAX_ITERS = 200
EARLY_STOP_PATIENCE = 10
EARLY_STOP_EPS = 0.005
LOCAL_SEARCH_BUDGET = {"gr4j": {"method": "SLSQP", "max_iterations": 30}}
LOCAL_SEARCH_WINDOW = 0.03  # +/-3% normalized window around the LLM proposal

OUT = Path(__file__).parent / "results_llm_methods"


def _eval_one_iteration(method: str, task: Task, attrs: dict, history: list,
                        llm, iteration: int, run_dir: Path, cfg: dict) -> dict:
    """One LLM proposal -> evaluation/refinement. Returns a trial record."""
    decision = ask_llm_for_params(llm, task, attrs, history)

    if method == "C":
        # LLM-Direct: evaluate the proposed params as-is (no optimisation).
        record = evaluate_parameter_set(
            task=task,
            proposed_params=decision["proposed_params"],
            run_dir=run_dir,
            cfg=cfg,
        )
        record["method"] = "C"
        record["method_name"] = "llm_direct"
    else:
        # LLM-LocalSearch: tight scipy search around the (validated) proposal.
        valid, clean, issues = validate_parameter_set(task.model, decision["proposed_params"])
        if valid:
            ranges = tight_ranges_around(task.model, clean, LOCAL_SEARCH_WINDOW)
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
            record = {"train_metrics": {}, "test_metrics": {}, "best_params": {},
                      "success": False, "error": "; ".join(issues),
                      "hydromodel_compute_time_s": 0.0}
        record["method"] = "D"
        record["method_name"] = "llm_local_search"
        record["valid_proposal"] = valid
        record["proposal_issues"] = issues

    record.update({
        **task.to_dict(),
        "iteration": iteration,
        "proposed_params": decision["proposed_params"],
        "llm_tokens": decision["llm_tokens"],
        "llm_decision_time_s": decision["llm_decision_time_s"],
        "wall_time_s": round(
            decision["llm_decision_time_s"] + record.get("hydromodel_compute_time_s", 0.0), 3),
    })
    return record


def run_method_on_basin(method: str, basin: dict, cfg: dict, log_path: Path,
                        max_iters: int) -> list[dict]:
    """Sequential LLM loop for one (method, basin); early-stops on train NSE."""
    from hydroagent.llm import LLMClient

    task = Task(basin_id=basin["basin_id"], basin_name=basin["name"],
                climate_zone=basin["climate_zone"], model=MODEL)
    llm = LLMClient(cfg["llm"])
    attrs = get_basin_attrs(task, cfg)

    history, records = [], []
    best_train, no_improve = None, 0
    for iteration in range(1, max_iters + 1):
        run_dir = log_path.parent / task.task_id / f"iter_{iteration:02d}"
        record = _eval_one_iteration(method, task, attrs, history, llm,
                                     iteration, run_dir, cfg)
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
    parser.add_argument("--method", choices=["C", "D", "both"], default="both")
    parser.add_argument("--basins", default="", help="逗号分隔的 basin_id,默认 3 个示范流域")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    cfg = load_base_config()
    selected = [b.strip() for b in args.basins.split(",") if b.strip()]
    basins = [b for b in BASINS if not selected or b["basin_id"] in selected]
    methods = ["C", "D"] if args.method == "both" else [args.method]

    for method in methods:
        out_dir = OUT / f"method_{method}"
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "trials.jsonl"
        if args.overwrite and log_path.exists():
            log_path.unlink()

        label = "LLM-Direct (Zhu)" if method == "C" else "LLM-LocalSearch"
        print(f"\n=== Method {method} ({label}): {len(basins)} basin(s), "
              f"min={MIN_ITERS} max={args.max_iters} patience={EARLY_STOP_PATIENCE} ===")
        t0 = time.time()
        for basin in basins:
            recs = run_method_on_basin(method, basin, cfg, log_path, args.max_iters)
            bt, be = _best(recs, "train"), _best(recs, "test")
            bts = f"{bt:.3f}" if isinstance(bt, (int, float)) else "NA"
            bes = f"{be:.3f}" if isinstance(be, (int, float)) else "NA"
            print(f"  {basin['basin_id']}: {len(recs)} iter, best train={bts} test={bes}")
        print(f"Method {method} done in {time.time() - t0:.0f}s -> {log_path}")


if __name__ == "__main__":
    main()
