"""
Experiment 1 - Scripted Baseline (no Agent layer)
==================================================
Purpose: Provide a numerical baseline by directly invoking calibrate_model /
         evaluate_model without the LLM-driven agent layer. Confirms that the
         Agent-driven workflow in exp1_standard_calibration.py is *interface
         abstraction*, not numerical modification — same NSE/KGE to within
         SCE-UA stochastic noise.

Method:  For each (basin, model) cell, call calibrate_model() directly with
         the exact same config the agent constructs. Then evaluate_model() on
         both train and test periods. Save metrics to results/paper/exp1_scripted/.

Compare-with: results/paper/exp1/exp1_results.json (Agent-driven)
              -> aggregated paired-t test reported in 4.1.

Paper:   Section 4.1 (Implementation Gap I-1 closure).
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 for stdout/stderr on Windows so calibrate_model's emoji prints
# don't crash with GBKEncodeError. Must be set before importing hydromodel paths.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

BASINS = [
    ("12025000", "Fish River, ME",        "humid_cold"),
    ("03439000", "French Broad River, NC", "humid_warm"),
    ("06043500", "Gallatin River, MT",     "semiarid_mountain"),
    ("08101000", "Cowhouse Creek, TX",     "semiarid_flashy"),
    ("11532500", "Smith River, CA",        "mediterranean"),
]

MODELS = ["xaj", "gr4j"]
ALGORITHM = "SCE_UA"
N_SEEDS = 1   # SCE-UA is deterministic with fixed seed; multi-seed adds no info here
OUTPUT_DIR = Path("results/paper/exp1_scripted")

TRAIN_PERIOD = ["2000-01-01", "2009-12-31"]
TEST_PERIOD  = ["2010-01-01", "2014-12-31"]


def setup_logging():
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / f"exp1_scripted_{ts}.log", encoding="utf-8"),
        ],
    )


def _evaluate_from_disk(cal_dir: str, cfg: dict) -> tuple[dict, dict]:
    """Read calibration config and evaluate both train and test periods from disk."""
    from hydroagent.skills.evaluation.evaluate import evaluate_model
    import yaml

    config_file = Path(cal_dir) / "calibration_config.yaml"
    if not config_file.exists():
        logger.warning("calibration_config.yaml not found in %s", cal_dir)
        return {}, {}
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    train_period = config["data_cfgs"]["train_period"]

    train_evl = evaluate_model(
        calibration_dir=cal_dir, eval_period=train_period, _cfg=cfg
    )
    test_evl = evaluate_model(
        calibration_dir=cal_dir, eval_period=None, _cfg=cfg
    )
    train_m = train_evl.get("metrics", {}) if train_evl.get("success") else {}
    test_m = test_evl.get("metrics", {}) if test_evl.get("success") else {}
    return train_m, test_m


def run_single(basin_id, basin_name, climate_zone, model_name, run_idx, cfg):
    """One scripted calibration: direct calibrate_model + evaluate_model, no agent."""
    from hydroagent.skills.calibration.calibrate import calibrate_model

    combo = f"{model_name}_{basin_id}"
    task_workspace = OUTPUT_DIR / combo / f"run{run_idx + 1}"
    task_workspace.mkdir(parents=True, exist_ok=True)

    record = {
        "basin_id": basin_id,
        "basin_name": basin_name,
        "climate_zone": climate_zone,
        "model_name": model_name,
        "algorithm": ALGORITHM,
        "run_idx": run_idx,
        "success": False,
        "train_metrics": {},
        "test_metrics": {},
        "best_params": {},
        "wall_time_s": 0.0,
        "calibration_dir": "",
        "error": None,
    }

    t0 = time.time()
    try:
        cal = calibrate_model(
            basin_ids=[basin_id],
            model_name=model_name,
            algorithm=ALGORITHM,
            train_period=TRAIN_PERIOD,
            test_period=TEST_PERIOD,
            output_dir=str(task_workspace),
            data_source="camels_us",
            _workspace=task_workspace,
            _cfg=cfg,
        )
    except Exception as e:
        logger.error("calibrate_model failed for %s run%d: %s", combo, run_idx + 1, e, exc_info=True)
        record["error"] = str(e)
        record["wall_time_s"] = round(time.time() - t0, 2)
        return record

    record["wall_time_s"] = round(time.time() - t0, 2)
    record["calibration_dir"] = cal.get("calibration_dir", "")
    record["best_params"] = cal.get("best_params", {})

    if not cal.get("success"):
        record["error"] = cal.get("error", "calibrate_model returned success=False")
        return record

    cal_dir = record["calibration_dir"]
    if not cal_dir or not Path(cal_dir).exists():
        record["error"] = "calibration_dir missing"
        return record

    try:
        train_m, test_m = _evaluate_from_disk(cal_dir, cfg)
        record["train_metrics"] = train_m
        record["test_metrics"] = test_m
        record["success"] = bool(train_m and test_m)
    except Exception as e:
        logger.error("evaluation failed for %s run%d: %s", combo, run_idx + 1, e, exc_info=True)
        record["error"] = f"eval: {e}"
        return record

    return record


def aggregate_seeds(records: list[dict]) -> dict:
    """Aggregate N_SEEDS independent runs."""
    succ = [r for r in records if r["success"]]
    if not succ:
        return {"n_runs": len(records), "n_success": 0, "failure_types": []}

    def col(metric_dict_key, period):
        vals = [r[period].get(metric_dict_key) for r in succ if r[period].get(metric_dict_key) is not None]
        if not vals:
            return None
        return {"mean": round(sum(vals) / len(vals), 4),
                "std": round((sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5, 4),
                "n": len(vals)}

    r0 = succ[0]
    return {
        "basin_id": r0["basin_id"],
        "basin_name": r0["basin_name"],
        "climate_zone": r0["climate_zone"],
        "model_name": r0["model_name"],
        "n_runs": len(records),
        "n_success": len(succ),
        "kge_train": col("KGE", "train_metrics"),
        "kge_test":  col("KGE", "test_metrics"),
        "nse_train": col("NSE", "train_metrics"),
        "nse_test":  col("NSE", "test_metrics"),
        "wall_time_s_mean": round(sum(r["wall_time_s"] for r in succ) / len(succ), 1),
    }


def main():
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from hydroagent.config import load_config
    cfg = load_config()

    all_records = []
    aggregated = []

    for model_name in MODELS:
        for basin_id, basin_name, cz in BASINS:
            seed_records = []
            for run_idx in range(N_SEEDS):
                logger.info("=== Running %s %s run%d ===", model_name, basin_id, run_idx + 1)
                rec = run_single(basin_id, basin_name, cz, model_name, run_idx, cfg)
                all_records.append(rec)
                seed_records.append(rec)
            agg = aggregate_seeds(seed_records)
            aggregated.append(agg)
            logger.info("aggregated: %s", agg)

    out = {
        "experiment": "exp1_scripted_baseline",
        "mode": "scripted (no agent)",
        "timestamp": datetime.now().isoformat(),
        "basins": [b[0] for b in BASINS],
        "models": MODELS,
        "algorithm": ALGORITHM,
        "n_seeds": N_SEEDS,
        "data_periods": {"train": TRAIN_PERIOD, "test": TEST_PERIOD},
        "results_per_run": all_records,
        "results_agg": aggregated,
    }

    out_file = OUTPUT_DIR / "exp1_scripted_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logger.info("Saved -> %s", out_file)
    print(f"Saved -> {out_file}")


if __name__ == "__main__":
    main()
