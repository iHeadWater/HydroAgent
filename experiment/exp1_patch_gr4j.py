"""
Patch script: run GR4J Agent calibration for the two missing combos
  - gr4j_08101000 (Cowhouse Creek, TX — semiarid_flashy)
  - gr4j_11532500 (Smith River, CA  — mediterranean)

These two were skipped when exp1 was narrowed to XAJ-only.
This script reuses run_single_task() from exp1 verbatim and saves
results into the same directory structure so downstream aggregation
can treat them identically to the existing GR4J runs.

Results land in:
  results/paper/exp1/gr4j_08101000/run{1,2,3}/
  results/paper/exp1/gr4j_11532500/run{1,2,3}/
"""

import sys
import os
from pathlib import Path
# Force UTF-8 for Windows terminals that default to GBK
os.environ.setdefault("PYTHONUTF8", "1")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
import time
from datetime import datetime

# ── Config (mirrors exp1) ─────────────────────────────────────────────────────

MISSING_COMBOS = [
    ("08101000", "Cowhouse Creek, TX", "semiarid_flashy"),
    ("11532500", "Smith River, CA",    "mediterranean"),
]
MODEL_NAME = "gr4j"
ALGORITHM  = "SCE_UA"
N_SEEDS    = 3
OUTPUT_DIR = Path("results/paper/exp1")

EXPECTED_TOOLS = {"validate_basin", "calibrate_model", "evaluate_model"}


def setup_logging():
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / f"exp1_patch_{ts}.log", encoding="utf-8"),
        ],
    )


# ── Helpers (verbatim from exp1) ──────────────────────────────────────────────

def _classify_failure(record: dict) -> str:
    if record.get("success"):
        return "none"
    tools = set(record.get("tool_sequence", []))
    err = str(record.get("error", "")).lower()
    if "calibrate_model" not in tools and "llm_calibrate" not in tools:
        return "WRONG_SKILL"
    if "context" in err or "token" in err or "length" in err or "too long" in err:
        return "CONTEXT_OVERFLOW"
    if "calibration" in err or "optimizer" in err or "nan" in err or "no valid" in err:
        return "CALIBRATION_ERR"
    if "evaluation" in err or "metrics" in err or "yaml" in err:
        return "EVALUATION_ERR"
    return "AGENT_ERROR"


def _extract_from_log(memory_log: list) -> dict:
    result = {"calibration_dir": "", "best_params": {}, "tool_sequence": []}
    for entry in memory_log:
        tool = entry.get("tool", "")
        result["tool_sequence"].append(tool)
        r = entry.get("result_summary", {})
        if not isinstance(r, dict):
            continue
        if tool in ("calibrate_model", "llm_calibrate") and r.get("success"):
            cal_dir = r.get("calibration_dir", "")
            if cal_dir:
                result["calibration_dir"] = str(cal_dir)
            result["best_params"] = r.get("best_params", {})
    return result


def _evaluate_from_disk(cal_dir: str, cfg: dict) -> tuple:
    from hydroagent.skills.evaluation.evaluate import evaluate_model
    try:
        import yaml
        config_file = Path(cal_dir) / "calibration_config.yaml"
        if not config_file.exists():
            return {}, {}
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        train_period = config["data_cfgs"]["train_period"]
        train_evl = evaluate_model(calibration_dir=cal_dir, eval_period=train_period, _cfg=cfg)
        test_evl  = evaluate_model(calibration_dir=cal_dir, eval_period=None, _cfg=cfg)
        train_m = train_evl.get("metrics", {}) if train_evl.get("success") else {}
        test_m  = test_evl.get("metrics",  {}) if test_evl.get("success")  else {}
        return train_m, test_m
    except Exception as e:
        logging.warning(f"Post-run evaluation failed for {cal_dir}: {e}")
        return {}, {}


def run_single_task(basin_id, basin_name, climate_zone, model_name, run_idx, cfg):
    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    combo = f"{model_name}_{basin_id}"
    task_workspace = OUTPUT_DIR / combo / f"run{run_idx + 1}"
    task_workspace.mkdir(parents=True, exist_ok=True)

    query = (
        f"请率定{model_name.upper()}模型，流域{basin_id}，使用SCE-UA算法。"
        f"请先验证流域数据，然后进行率定，最后分别评估训练期和测试期的KGE和NSE指标，"
        f"输出目录请保存在 {task_workspace}。"
    )

    agent = HydroAgent(workspace=task_workspace, ui=ConsoleUI(mode="dev"))

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
        "total_tokens": 0,
        "agent_turns": 0,
        "tool_sequence": [],
        "failure_type": "none",
        "error": None,
    }

    t0 = time.time()
    try:
        agent.run(query)
    except Exception as e:
        logging.error(f"Agent run failed for {combo} run{run_idx+1}: {e}", exc_info=True)
        record["error"] = str(e)
        record["wall_time_s"] = round(time.time() - t0, 2)
        record["failure_type"] = _classify_failure(record)
        return record

    record["wall_time_s"] = round(time.time() - t0, 2)
    record["agent_turns"] = len(agent.memory._log)

    try:
        tok = agent.llm.tokens.summary()
        record["total_tokens"] = tok.get("total_tokens", 0)
    except Exception:
        pass

    log_info = _extract_from_log(agent.memory._log)
    record["tool_sequence"] = log_info["tool_sequence"]
    record["best_params"]   = log_info["best_params"]

    cal_dir = log_info.get("calibration_dir", "")
    if cal_dir and Path(cal_dir).exists():
        train_m, test_m = _evaluate_from_disk(cal_dir, cfg)
        record["train_metrics"] = train_m
        record["test_metrics"]  = test_m
        record["success"] = bool(
            train_m.get("KGE") is not None or train_m.get("NSE") is not None
        )
        if not record["success"]:
            record["error"] = "Calibration completed but evaluation failed"
    else:
        record["success"] = False
        record["error"] = f"No valid calibration_dir in agent log (got: '{cal_dir}')"

    record["failure_type"] = _classify_failure(record)
    return record


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    from hydroagent.config import load_config
    cfg = load_config()

    all_records = []

    for basin_id, basin_name, climate_zone in MISSING_COMBOS:
        combo = f"{MODEL_NAME}_{basin_id}"
        combo_runs = []

        # skip if already has run directories with session files
        existing = sorted((OUTPUT_DIR / combo).glob("run*/sessions/*_summary.json"))
        if len(existing) >= N_SEEDS:
            logging.info(f"[skip] {combo} already has {len(existing)} session(s), skipping")
            continue

        logging.info(f"\n{'='*60}")
        logging.info(f"Combo: {combo} ({basin_name}, {climate_zone})")
        logging.info(f"{'='*60}")

        for run_idx in range(N_SEEDS):
            logging.info(f"  -- Run {run_idx+1}/{N_SEEDS} --")
            record = run_single_task(
                basin_id, basin_name, climate_zone, MODEL_NAME, run_idx, cfg
            )
            combo_runs.append(record)
            all_records.append(record)

            def _fmt(v):
                return f"{v:.3f}" if isinstance(v, (int, float)) else "N/A"

            if record["success"]:
                logging.info(
                    f"  Run{run_idx+1}: "
                    f"train KGE={_fmt(record['train_metrics'].get('KGE'))} "
                    f"NSE={_fmt(record['train_metrics'].get('NSE'))}  "
                    f"test KGE={_fmt(record['test_metrics'].get('KGE'))} "
                    f"NSE={_fmt(record['test_metrics'].get('NSE'))}  "
                    f"time={record['wall_time_s']:.0f}s  tokens={record['total_tokens']}"
                )
            else:
                logging.info(
                    f"  Run{run_idx+1}: FAILED [{record['failure_type']}] {record['error']}"
                )

        # save per-combo summary
        summary_path = OUTPUT_DIR / combo / "patch_results.json"
        summary_path.write_text(
            json.dumps(combo_runs, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logging.info(f"  Saved -> {summary_path}")

    # save combined patch summary
    out = OUTPUT_DIR / "exp1_patch_gr4j_results.json"
    out.write_text(
        json.dumps({
            "patch": "exp1_patch_gr4j",
            "timestamp": datetime.now().isoformat(),
            "combos": [f"gr4j_{b[0]}" for b in MISSING_COMBOS],
            "n_seeds": N_SEEDS,
            "records": all_records,
        }, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logging.info(f"\nAll done. Full patch results -> {out}")


if __name__ == "__main__":
    main()
