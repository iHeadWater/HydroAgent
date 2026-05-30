"""Exp1 - Method C: LLM-Direct calibration (Zhu-style direct parameter proposal).

每代 LLM 直接吐一组物理参数;hydromodel 拿这组参数 as-is 评估(无任何数值优化)。
靠多代独立提议形成的多样性做隐式正则化,避免局部过拟合。

This script DELIBERATELY bypasses the HydroAgent agentic loop and uses the LLM
client + hydromodel skills directly — the loop is too heavy for a tight
per-iteration numerical search. See ``exp1_hydroagent.py`` for the variant
that does use ``agent.run()`` end-to-end.

Numeric / LLM helpers come from ``experiment/exp1/_common.py``.

Run (default: 3 demo basins, min50/max200 with early-stop):
    python experiment/exp1/exp1_llm_direct.py

Quick smoke (1 basin, 10 iterations):
    python experiment/exp1/exp1_llm_direct.py --basins 08101000 --max-iters 10 --overwrite

Output: experiment/exp1/results_llm_direct/trials.jsonl
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
    evaluate_parameter_set,
    get_basin_attrs,
    load_base_config,
    metric,
)

# 3 representative CAMELS-US basins (easy / medium / hard) for GR4J.
BASINS = [
    {"basin_id": "12025000", "name": "Newaukum River, WA", "climate_zone": "mediterranean"},
    {"basin_id": "07197000", "name": "Baron Fork, OK",     "climate_zone": "humid_warm"},
    {"basin_id": "08101000", "name": "Cowhouse Creek, TX", "climate_zone": "semiarid"},
]
MODEL = "gr4j"

# Iteration budget + early stop (same policy as the original Zhu runner).
MIN_ITERS = 50
MAX_ITERS = 200
EARLY_STOP_PATIENCE = 10
EARLY_STOP_EPS = 0.005

OUT = Path(__file__).parent / "results_llm_direct"


def run_on_basin(basin: dict, cfg: dict, log_path: Path, max_iters: int) -> list[dict]:
    """Sequential LLM-Direct loop on one basin; early-stop on best train NSE."""
    from hydroagent.llm import LLMClient

    task = Task(basin_id=basin["basin_id"], basin_name=basin["name"],
                climate_zone=basin["climate_zone"], model=MODEL)
    llm = LLMClient(cfg["llm"])
    attrs = get_basin_attrs(task, cfg)

    history, records = [], []
    best_train, no_improve = None, 0
    for iteration in range(1, max_iters + 1):
        decision = ask_llm_for_params(llm, task, attrs, history)
        record = evaluate_parameter_set(
            task=task,
            proposed_params=decision["proposed_params"],
            run_dir=log_path.parent / task.task_id / f"iter_{iteration:02d}",
            cfg=cfg,
        )
        record.update({
            "method": "C",
            "method_name": "llm_direct",
            "iteration": iteration,
            "basin_attributes": attrs,
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
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    cfg = load_base_config()
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "trials.jsonl"
    if args.overwrite and log_path.exists():
        log_path.unlink()

    selected = [b.strip() for b in args.basins.split(",") if b.strip()]
    basins = [b for b in BASINS if not selected or b["basin_id"] in selected]

    print(f"=== Method C (LLM-Direct / Zhu): {len(basins)} basin(s), "
          f"min={MIN_ITERS} max={args.max_iters} patience={EARLY_STOP_PATIENCE} ===")
    t0 = time.time()
    for basin in basins:
        recs = run_on_basin(basin, cfg, log_path, args.max_iters)
        bt, be = _best(recs, "train"), _best(recs, "test")
        bts = f"{bt:.3f}" if isinstance(bt, (int, float)) else "NA"
        bes = f"{be:.3f}" if isinstance(be, (int, float)) else "NA"
        print(f"  {basin['basin_id']}: {len(recs)} iter, best train={bts} test={bes}")
    print(f"Method C done in {time.time() - t0:.0f}s -> {log_path}")


if __name__ == "__main__":
    main()
