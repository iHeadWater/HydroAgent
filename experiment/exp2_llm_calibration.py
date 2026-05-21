"""
Experiment 2 - LLM Calibration vs Standard vs Zhu et al. (Hybrid Agent+Script)
================================================================================
Purpose: Validate HydroAgent's LLM parameter-range adjustment mechanism against
         standard SCE-UA and the Zhu et al. 2026 direct-proposal baseline.

Method - three arms:
  A. Standard SCE-UA (agent-driven, N_SEEDS_A=3 runs -> mean+/-std)
  B. Zhu et al. 2026 (scripted, single run)
  C1. HydroAgent LLM range adjustment - primary LLM (agent-driven, single run)
  C2. HydroAgent LLM range adjustment - alternative LLM (agent-driven, single run)
      [Set C2_MODEL to enable; skip if None]

Statistical design:
  - Method A: 3 independent runs to establish SCE-UA variance (mean+/-std baseline)
  - Method B: single scripted run (scipy-based, internal iterations cover variance)
  - Method C1/C2: single run each (multi-round LLM iteration already provides variance
    via NSE trajectory; adding 3 repeats would be prohibitively expensive)
  - Primary metric: NSE; secondary: KGE
  - Key comparison: C_nse >= B_nse (C not worse than scripted LLM); C_nse APPROX= A_nse
    consistent with Zhu et al. 2026 finding (LLM value = automation equivalence)

LLM comparison (C1 vs C2):
  - Tests whether reasoning-type LLMs (e.g., DeepSeek-R1) outperform dialogue-type
    LLMs (e.g., Qwen) in detecting parameter boundary effects
  - Set C2_MODEL and optionally C2_BASE_URL to enable

Basins: Fish River (humid_cold control), Smith River (mediterranean),
        Gallatin River (semiarid_mountain, GR4J structural mismatch case)

Paper:   Section 4.3 - LLM Calibration Comparison
Reference: Zhu et al. 2026 (GRL), doi:10.1029/2025GL120043
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
import re
import statistics
import time
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)

# ── Experiment configuration ─────────────────────────────────────────────────

BASINS = [
    ("12025000", "Fish River, ME",   "humid_cold"),
    ("11532500", "Smith River, CA",  "mediterranean"),
    ("03439000", "French Broad, NC", "humid_warm"),
]

MODEL = "gr4j"
ZHU_MAX_ITERS = 5
LLM_MAX_ROUNDS = 5
NSE_TARGET = 0.80

# Method A repetitions: 1 run representing standard practice (not best-of-N)
N_SEEDS_A = 1

# Method C LLM comparison:
#   C1 = primary LLM from config (loaded automatically)
#   C2 = alternative LLM model name; set to None to skip
#   Example: C2_MODEL = "deepseek-reasoner"
C2_MODEL = None
C2_BASE_URL = None  # set if C2 uses a different API endpoint

# Run mode: set to "C" to skip Method A and B, only run Method C1 (and C2 if configured)
# Useful for re-running Method C after fixing Agent behavior without re-running A/B.
# Results for A/B are loaded from the existing checkpoint if available.
RUN_ONLY = "AC"   # None = run all | "B" = only B | "C" = only C1/C2 | "AC" = A+C1, skip B

# SCE-UA budget constants (for total evaluation count comparison)
SCE_UA_REP_DEFAULT = 750
SCE_UA_NGS_DEFAULT = 200
OUTPUT_DIR = Path("results/paper/exp2")


def setup_logging():
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / f"exp2_{ts}.log", encoding="utf-8"),
        ],
    )


# ── Failure classification (shared with Exp1 pattern) ────────────────────────

def _classify_failure(record: dict) -> str:
    if record.get("success"):
        return "none"
    tools = set(record.get("tool_sequence", []))
    err = str(record.get("error", "")).lower()
    if "calibrate_model" not in tools and "llm_calibrate" not in tools:
        return "WRONG_SKILL"
    if "context" in err or "token" in err or "too long" in err:
        return "CONTEXT_OVERFLOW"
    if "calibration" in err or "optimizer" in err or "nan" in err:
        return "CALIBRATION_ERR"
    if "evaluation" in err or "metrics" in err or "yaml" in err:
        return "EVALUATION_ERR"
    return "AGENT_ERROR"


# ── Log extraction helpers ────────────────────────────────────────────────────

def _extract_from_log(memory_log: list[dict]) -> dict:
    result = {
        "calibration_dir": "",
        "best_params": {},
        "tool_sequence": [],
        "llm_calibrate_best_nse": None,
        "llm_calibrate_best_kge": None,
        "nse_history": [],
        "rounds": None,
        "llm_calibrate_failed": False,
        "fixed_params_by_round": {},
        "initial_param_ranges_llm": {},   # ranges used in round 1 (Agent's prior)
        "basin_attributes": {},            # from get_basin_attributes call
    }
    calibrate_model_dirs = []

    for entry in memory_log:
        tool = entry.get("tool", "")
        result["tool_sequence"].append(tool)
        r = entry.get("result_summary", {})
        if not isinstance(r, dict):
            continue

        if tool == "get_basin_attributes" and r.get("success"):
            # Capture basin climate attributes for paper data
            result["basin_attributes"] = {
                k: r[k] for k in (
                    "aridity", "runoff_ratio", "baseflow_index",
                    "frac_snow", "p_mean", "pet_mean", "climate_zone",
                ) if k in r
            }

        elif tool == "llm_calibrate":
            if r.get("success"):
                cal_dir = r.get("calibration_dir", "")
                if cal_dir:
                    result["calibration_dir"] = str(cal_dir)
                result["best_params"] = r.get("best_params", {})
                result["llm_calibrate_best_nse"] = r.get("best_nse")
                result["rounds"] = r.get("rounds")
                result["nse_history"] = r.get("nse_history", [])
                result["llm_calibrate_failed"] = False
                result["fixed_params_by_round"] = r.get("fixed_params_by_round", {})
                # Extract round-1 param_ranges from history (Agent's prior reasoning)
                history = r.get("history", [])
                if history and isinstance(history[0], dict):
                    result["initial_param_ranges_llm"] = history[0].get("param_ranges", {})
            elif r.get("error"):
                result["llm_calibrate_failed"] = True
                logger.warning(f"llm_calibrate failed: {r.get('error', '')[:100]}")

        elif tool == "calibrate_model" and r.get("success"):
            cal_dir = r.get("calibration_dir", "")
            if cal_dir:
                calibrate_model_dirs.append(str(cal_dir))
            result["best_params"] = r.get("best_params", {})

    if not result["calibration_dir"] and calibrate_model_dirs:
        result["calibration_dir"] = calibrate_model_dirs[-1]

    return result


def _evaluate_from_disk(cal_dir: str, cfg: dict) -> tuple[dict, dict]:
    from hydroagent.skills.evaluation.evaluate import evaluate_model
    try:
        import yaml
        config_file = Path(cal_dir) / "calibration_config.yaml"
        if not config_file.exists():
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
    except Exception as e:
        logger.warning(f"Post-run evaluation failed for {cal_dir}: {e}")
        return {}, {}


# ── Boundary detection ────────────────────────────────────────────────────────

def _detect_boundaries(best_params: dict, model_name: str, default_ranges: dict) -> list:
    ranges = default_ranges.get(model_name, {})
    hits = []
    for name, value in best_params.items():
        if name not in ranges:
            continue
        lo, hi = ranges[name]
        span = hi - lo
        if span <= 0:
            continue
        lo_pct = (value - lo) / span * 100
        hi_pct = (hi - value) / span * 100
        if lo_pct < 5:
            hits.append({"param": name, "boundary": "lower", "pct": round(lo_pct, 1)})
        elif hi_pct < 5:
            hits.append({"param": name, "boundary": "upper", "pct": round(hi_pct, 1)})
    return hits


# ── Aggregation for Method A (N_SEEDS_A runs) ────────────────────────────────

def _stats(vals: list) -> dict:
    clean = [v for v in vals if isinstance(v, (int, float))]
    if not clean:
        return {"mean": None, "std": None, "n": 0}
    mean = statistics.mean(clean)
    std = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4), "n": len(clean)}


def _aggregate_method_a(runs: list[dict]) -> dict:
    success_runs = [r for r in runs if r["success"]]
    return {
        "n_runs": len(runs),
        "n_success": len(success_runs),
        # KGE primary
        "kge_train": _stats([r["train_metrics"].get("KGE") for r in success_runs]),
        "kge_test":  _stats([r["test_metrics"].get("KGE")  for r in success_runs]),
        # NSE secondary
        "nse_train": _stats([r["train_metrics"].get("NSE") for r in success_runs]),
        "nse_test":  _stats([r["test_metrics"].get("NSE")  for r in success_runs]),
        "wall_time_s_mean": round(statistics.mean(r["wall_time_s"] for r in runs), 1),
        "total_tokens_sum": sum(r.get("total_tokens", 0) for r in runs),
        "boundary_hits_any": [h for r in success_runs for h in r.get("boundary_hits", [])],
        "failure_types": [_classify_failure(r) for r in runs if not r["success"]],
        "tool_sequences": [r.get("tool_sequence", []) for r in runs],
    }


# ── Method B: Zhu et al. 2026 (scripted) ─────────────────────────────────────

def _zhu_method(basin_id: str, model_name: str, llm, cfg: dict, output_dir: str) -> dict:
    """Reproduce Zhu et al. 2026: LLM directly proposes parameter values, iteratively.

    For GR4J (original paper model): scipy + 3% tight window (faithful reproduction).
    For XAJ (15 params): SCE-UA + 7% window, KI+KG sum constraint enforced.
    scipy SLSQP with 3% window cannot navigate 15-param space; SCE-UA is used instead.
    """
    from hydroagent.skills.calibration.calibrate import calibrate_model
    from hydroagent.skills.evaluation.evaluate import evaluate_model
    from hydroagent.skills.llm_calibration.llm_calibrate import DEFAULT_PARAM_RANGES
    import yaml

    is_xaj = model_name.lower() == "xaj"
    _window_frac = 0.07 if is_xaj else 0.03

    param_ranges = DEFAULT_PARAM_RANGES.get(model_name, {})
    history = []
    best_nse = -999.0
    best_kge = -999.0
    best_result = {}

    for iteration in range(ZHU_MAX_ITERS):
        history_text = "\n".join(
            f"  Iter {h['iter']}: proposed={h['proposed']}  NSE={h['nse']:.4f}  KGE={h.get('kge', 'N/A')}"
            for h in history[-5:]
        ) if history else "(no previous iterations)"

        prompt = (
            f"You are calibrating a {model_name.upper()} hydrological model for basin {basin_id}.\n"
            f"Parameter physical ranges: {json.dumps(param_ranges)}\n\n"
            f"Previous iterations:\n{history_text}\n\n"
            f"Based on the history and hydrological knowledge, propose specific parameter VALUES "
            f"to maximize Nash-Sutcliffe Efficiency (NSE). "
            f"Reply ONLY with a JSON object like: "
            f'{{"{list(param_ranges.keys())[0]}": 250.0, ...}}'
        )
        messages = [
            {"role": "system", "content": "Expert hydrologist. Reply with valid JSON only."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = llm._chat_text(messages, temperature=0.2)
            text = response.text or ""
            match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
            if not match:
                logger.warning(f"Zhu iter {iteration}: no JSON found in response")
                continue
            proposed = json.loads(match.group())
        except Exception as e:
            logger.warning(f"Zhu iter {iteration}: LLM parse error: {e}")
            continue

        # Enforce KI+KG < 0.7 for XAJ before building tight ranges
        if is_xaj and "KI" in proposed and "KG" in proposed:
            ki, kg = float(proposed["KI"]), float(proposed["KG"])
            if ki + kg >= 0.7:
                scale = 0.65 / (ki + kg)
                proposed["KI"] = round(ki * scale, 4)
                proposed["KG"] = round(kg * scale, 4)

        logger.info(f"  Zhu iter {iteration}: LLM proposed: {proposed}")

        tight_ranges = {}
        param_names = []
        for k, v in proposed.items():
            if k not in param_ranges:
                continue
            lo, hi = param_ranges[k]
            margin = (hi - lo) * _window_frac
            r_lo = max(lo, float(v) - margin)
            r_hi = min(hi, float(v) + margin)
            if r_lo >= r_hi:
                logger.warning(
                    "Zhu iter %d: tight range degenerated for '%s' "
                    "(proposed=%.4f, margin=%.4f, range=[%.4f, %.4f]). "
                    "Falling back to full range.",
                    iteration, k, float(v), margin, lo, hi,
                )
                r_lo, r_hi = lo, hi
            tight_ranges[k] = [r_lo, r_hi]
            param_names.append(k)

        if not tight_ranges:
            continue

        range_yaml = {model_name: {"param_name": param_names, "param_range": tight_ranges}}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tf:
            yaml.dump(range_yaml, tf, allow_unicode=True)
            range_file = tf.name

        iter_dir = str(Path(output_dir) / f"iter_{iteration:02d}")
        if is_xaj:
            n_params = len(tight_ranges)
            result = calibrate_model(
                basin_ids=[basin_id],
                model_name=model_name,
                algorithm="SCE_UA",
                param_range_file=range_file,
                output_dir=iter_dir,
                algorithm_params={"rep": 350, "ngs": max(10, 2 * n_params), "random_seed": 1234 + iteration * 137},
                _cfg=cfg,
            )
        else:
            scipy_method = cfg.get("algorithms", {}).get("scipy", {}).get("method", "SLSQP")
            result = calibrate_model(
                basin_ids=[basin_id],
                model_name=model_name,
                algorithm="scipy",
                param_range_file=range_file,
                output_dir=iter_dir,
                algorithm_params={"method": scipy_method, "max_iterations": 30},
                _cfg=cfg,
            )

        nse, kge = -999.0, -999.0
        if result.get("success") and result.get("calibration_dir"):
            evl = evaluate_model(
                calibration_dir=result["calibration_dir"],
                eval_period=result.get("train_period"),
                _cfg=cfg,
            )
            if evl.get("success"):
                m = evl.get("metrics", {})
                v = m.get("NSE", -999.0)
                nse = v if isinstance(v, float) else -999.0
                v = m.get("KGE", -999.0)
                kge = v if isinstance(v, float) else -999.0

        history.append({
            "iter": iteration,
            "proposed": proposed,
            "params": result.get("best_params", proposed),
            "nse": nse,
            "kge": kge,
        })

        if kge > best_kge:
            best_kge = kge
            best_result = result
        if nse > best_nse:
            best_nse = nse

        logger.info(f"  Zhu iter {iteration}: train NSE={nse:.4f}  KGE={kge:.4f}")

        if isinstance(nse, float) and nse >= NSE_TARGET:
            logger.info(f"  Zhu: target NSE reached at iter {iteration}")
            break

    return {
        "success": bool(best_result.get("success")),
        "best_nse": best_nse if best_nse > -998.0 else None,
        "best_kge": best_kge if best_kge > -998.0 else None,
        "best_params": best_result.get("best_params", {}),
        "calibration_dir": best_result.get("calibration_dir", ""),
        "train_period": best_result.get("train_period"),
        "iterations": len(history),
        "nse_history": [h["nse"] for h in history],
        "kge_history": [h["kge"] for h in history],
        "proposed_history": [h["proposed"] for h in history],
        "method": "zhu_direct_propose",
    }


# ── Method A: Standard SCE-UA (agent-driven, N_SEEDS_A runs) ─────────────────

def _run_method_a_single(basin_id: str, run_idx: int, cfg: dict) -> dict:
    """One independent run of Method A (standard SCE-UA via agent)."""
    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI
    from hydroagent.skills.llm_calibration.llm_calibrate import DEFAULT_PARAM_RANGES

    task_workspace = OUTPUT_DIR / f"A_{MODEL}_{basin_id}" / f"run{run_idx+1}"
    task_workspace.mkdir(parents=True, exist_ok=True)

    model_upper = MODEL.upper()
    query = (
        f"请率定{model_upper}模型，流域{basin_id}，使用SCE-UA算法，"
        f"输出目录保存在 {task_workspace}。"
        f"完成后评估训练期和测试期的NSE和KGE指标。"
    )

    agent = HydroAgent(workspace=task_workspace, ui=ConsoleUI(mode="dev"))
    t0 = time.time()
    try:
        agent.run(query)
    except Exception as e:
        logger.error(f"Method A run{run_idx+1} error for {basin_id}: {e}", exc_info=True)
        return {
            "success": False, "error": str(e),
            "wall_time_s": round(time.time() - t0, 2), "total_tokens": 0,
            "train_metrics": {}, "test_metrics": {}, "tool_sequence": [],
            "boundary_hits": [],
        }

    wall_time = round(time.time() - t0, 2)
    try:
        tok = agent.llm.tokens.summary()
        total_tokens = tok.get("total_tokens", 0)
    except Exception:
        total_tokens = 0

    log_info = _extract_from_log(agent.memory._log)
    entry = {
        "success": False,
        "best_params": log_info["best_params"],
        "tool_sequence": log_info["tool_sequence"],
        "wall_time_s": wall_time,
        "total_tokens": total_tokens,
        "train_metrics": {},
        "test_metrics": {},
        "boundary_hits": [],
        "error": None,
    }

    cal_dir = log_info.get("calibration_dir", "")
    if cal_dir and Path(cal_dir).exists():
        train_m, test_m = _evaluate_from_disk(cal_dir, cfg)
        entry["train_metrics"] = train_m
        entry["test_metrics"] = test_m
        entry["success"] = bool(
            train_m.get("KGE") is not None or train_m.get("NSE") is not None
        )
        if not entry["success"]:
            entry["error"] = "Evaluation failed after calibration"
    else:
        entry["error"] = f"No valid calibration_dir (got: '{cal_dir}')"

    if entry.get("best_params"):
        entry["boundary_hits"] = _detect_boundaries(
            entry["best_params"], MODEL, DEFAULT_PARAM_RANGES
        )

    return entry


# ── Method C: HydroAgent LLM range adjustment (agent-driven) ──────────────────

def _run_method_c(basin_id: str, cfg: dict, label: str,
                  model_override: str | None = None,
                  base_url_override: str | None = None) -> dict:
    """Method C: LLM-guided range adjustment via HydroAgent agent.

    label: "C1" or "C2" (for workspace naming)
    model_override: if set, temporarily use this LLM model instead of config default
    """
    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    task_workspace = OUTPUT_DIR / f"{label}_{MODEL}_{basin_id}"
    task_workspace.mkdir(parents=True, exist_ok=True)

    # Optionally override LLM config for C2
    import copy
    run_cfg = copy.deepcopy(cfg)
    if model_override:
        run_cfg["llm"]["model"] = model_override
        logger.info(f"  Method {label}: using model override = {model_override}")
    if base_url_override:
        run_cfg["llm"]["base_url"] = base_url_override

    model_upper = MODEL.upper()
    query = (
        f"请对流域 {basin_id} 进行LLM智能率定{model_upper}模型，目标NSE>={NSE_TARGET}，"
        f"最多{LLM_MAX_ROUNDS}轮，使用SCE-UA算法，输出目录 {task_workspace}。\n\n"
        f"必须严格按照以下三步执行，不可跳过：\n"
        f"第一步：调用 get_basin_attributes(basin_id='{basin_id}') 获取流域气候属性（aridity、"
        f"runoff_ratio、baseflow_index、frac_snow、climate_zone）\n"
        f"第二步：根据返回的属性，参照 skill.md 中的 {model_upper} 参数气候区对照表，推理每个参数的"
        "初始搜索范围，写出推理依据（如：aridity=0.45，属于湿润气候区，因此参数范围设为...）\n"
        f"第三步：将推理出的 param_ranges dict 作为参数传入 llm_calibrate，"
        f"让工具以此为起点进行迭代优化\n\n"
        f"完成所有轮次后，评估训练期和测试期的NSE和KGE指标。"
    )

    agent = HydroAgent(workspace=task_workspace, ui=ConsoleUI(mode="dev"), config_override=run_cfg)
    t0 = time.time()
    try:
        agent.run(query)
    except Exception as e:
        logger.error(f"Method {label} error for {basin_id}: {e}", exc_info=True)
        return {
            "success": False, "error": str(e), "label": label,
            "wall_time_s": round(time.time() - t0, 2), "total_tokens": 0,
            "train_metrics": {}, "test_metrics": {}, "tool_sequence": [],
            "nse_history": [], "rounds": None,
        }

    wall_time = round(time.time() - t0, 2)
    try:
        tok = agent.llm.tokens.summary()
        total_tokens = tok.get("total_tokens", 0)
    except Exception:
        total_tokens = 0

    log_info = _extract_from_log(agent.memory._log)

    # Compute range_delta: how much LLM narrowed each param vs default
    from hydroagent.skills.llm_calibration.llm_calibrate import DEFAULT_PARAM_RANGES
    default_ranges = DEFAULT_PARAM_RANGES.get(MODEL, {})
    initial_ranges = log_info.get("initial_param_ranges_llm", {})
    range_delta = {}
    for param, (d_lo, d_hi) in default_ranges.items():
        if param in initial_ranges:
            i_lo, i_hi = initial_ranges[param]
            range_delta[param] = [round(i_lo - d_lo, 4), round(i_hi - d_hi, 4)]

    entry = {
        "success": False,
        "label": label,
        "model_used": model_override or cfg.get("llm", {}).get("model", "unknown"),
        "best_nse": log_info.get("llm_calibrate_best_nse"),
        "best_params": log_info["best_params"],
        "rounds": log_info.get("rounds"),
        "tool_sequence": log_info["tool_sequence"],
        "wall_time_s": wall_time,
        "total_tokens": total_tokens,
        "train_metrics": {},
        "test_metrics": {},
        "nse_history": log_info.get("nse_history", []),
        "llm_calibrate_failed": log_info.get("llm_calibrate_failed", False),
        "error": None,
        # Paper data: agent prior reasoning artifacts
        "basin_attributes": log_info.get("basin_attributes", {}),
        "initial_param_ranges_llm": initial_ranges,
        "initial_param_ranges_default": {k: list(v) for k, v in default_ranges.items()},
        "range_delta": range_delta,
        "fixed_params_by_round": log_info.get("fixed_params_by_round", {}),
    }

    if "llm_calibrate" not in log_info["tool_sequence"]:
        entry["error"] = "Agent did not call llm_calibrate (wrong skill selected)"
        entry["failure_type"] = "WRONG_SKILL"
    elif log_info.get("llm_calibrate_failed"):
        entry["error"] = "llm_calibrate failed; agent fell back to calibrate_model"

    cal_dir = log_info.get("calibration_dir", "")
    if cal_dir and Path(cal_dir).exists():
        train_m, test_m = _evaluate_from_disk(cal_dir, cfg)
        entry["train_metrics"] = train_m
        entry["test_metrics"] = test_m
        entry["success"] = bool(
            entry.get("best_nse") is not None
            or train_m.get("KGE") is not None
        )
        # Use KGE as primary final metric
        if train_m.get("KGE") is not None:
            entry["best_kge"] = train_m["KGE"]

    if not entry.get("failure_type"):
        entry["failure_type"] = _classify_failure(entry)

    return entry


# ── Evaluation budget estimate ────────────────────────────────────────────────

def _estimate_c_total_evals(rounds: int) -> int:
    """Estimate total SCE-UA function evaluations for Method C across all rounds."""
    scales = [1.0, 0.75, 0.60, 0.50]
    total = 0
    for i in range(rounds or 0):
        scale = scales[min(i, len(scales) - 1)]
        total += int(SCE_UA_REP_DEFAULT * scale)
    return total


# ── Checkpoint helpers ────────────────────────────────────────────────────────

CHECKPOINT_FILE = OUTPUT_DIR / "exp2_checkpoint.json"


def _load_existing_basin_record(basin_id: str) -> dict:
    """Load the existing basin record from exp2_results.json or checkpoint.

    Used by RUN_ONLY='C' to preserve A/B results when only re-running Method C.
    Returns the record dict if found, else empty dict.
    """
    # Try checkpoint first (more recent), then final results
    for candidate in [CHECKPOINT_FILE, OUTPUT_DIR / "exp2_results.json"]:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                for r in data.get("results", []):
                    if r.get("basin_id") == basin_id:
                        logger.info(
                            f"[checkpoint] Loaded existing A/B record for {basin_id} "
                            f"from {candidate.name}"
                        )
                        return r
            except Exception as e:
                logger.warning(f"Could not read {candidate.name} for {basin_id}: {e}")
    logger.warning(
        f"[checkpoint] No existing record found for {basin_id}; A/B fields will be empty"
    )
    return {}


def _load_checkpoint() -> list:
    """Return already-completed basin records from checkpoint, or []."""
    if CHECKPOINT_FILE.exists():
        try:
            data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
            done = data.get("results", [])
            logger.info(f"[checkpoint] Resuming: {len(done)} basin(s) already done: "
                        f"{[r['basin_id'] for r in done]}")
            return done
        except Exception as e:
            logger.warning(f"[checkpoint] Failed to read checkpoint: {e}")
    return []


def _save_checkpoint(results: list, meta: dict):
    """Write partial results after each basin completes."""
    payload = {**meta, "results": results}
    CHECKPOINT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info(f"[checkpoint] Saved ({len(results)} basin(s) done)")


# ── Main experiment ───────────────────────────────────────────────────────────

def run_experiment() -> dict:
    from hydroagent.config import load_config
    from hydroagent.llm import LLMClient

    cfg = load_config()
    llm = LLMClient(cfg["llm"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"LLM: model={cfg['llm']['model']}, base_url={cfg['llm']['base_url']}"
    )
    if C2_MODEL:
        logger.info(f"C2 LLM: model={C2_MODEL}, base_url={C2_BASE_URL or '(same)'}")
    else:
        logger.info("C2 LLM: not configured (set C2_MODEL to enable)")

    # Resume from checkpoint if it exists
    results = _load_checkpoint()
    done_basins = {r["basin_id"] for r in results}

    meta = {
        "experiment": "exp2_llm_calibration",
        "mode": f"A(agent x{N_SEEDS_A}) + B(scripted x1) + C1(agent x1) + C2({'agent' if C2_MODEL else 'skipped'})",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "primary_metric": "KGE (Knoben et al. 2019)",
        "n_seeds_a": N_SEEDS_A,
        "c2_model": C2_MODEL,
        "nse_target": NSE_TARGET,
    }

    for basin_id, basin_name, climate_zone in BASINS:
        logger.info(f"\n{'='*60}")
        logger.info(f"Basin: {basin_id} ({basin_name}, {climate_zone})")
        logger.info(f"{'='*60}")

        # Skip already-completed basins (resume support)
        if basin_id in done_basins:
            logger.info(f"[checkpoint] Skipping {basin_id} (already done)")
            continue

        record = {
            "basin_id": basin_id,
            "basin_name": basin_name,
            "climate_zone": climate_zone,
            "model": MODEL,
            "basin_attributes": {},  # from get_basin_attributes (filled after C1 runs)
            "method_A_runs": [],     # N_SEEDS_A individual runs
            "method_A_agg": {},      # mean+/-std aggregation
            "method_B": {},
            "method_C1": {},
            "method_C2": {},         # empty dict if C2_MODEL not set
        }

        # ── Method A: N_SEEDS_A independent runs ──
        if RUN_ONLY in ("B", "C"):
            logger.info(f"[A] Skipped (RUN_ONLY='{RUN_ONLY}') — loading from existing results if available")
            existing = _load_existing_basin_record(basin_id)
            record["method_A_runs"] = existing.get("method_A_runs", [])
            record["method_A_agg"] = existing.get("method_A_agg", {})
        else:
            existing = {}
            logger.info(f"[A] Standard SCE-UA (agent-driven, {N_SEEDS_A} independent runs)")
            # RUN_ONLY="AC" falls through here (runs A, skips B, runs C)
            a_runs = []
            for run_idx in range(N_SEEDS_A):
                logger.info(f"  A run {run_idx+1}/{N_SEEDS_A}")
                a_entry = _run_method_a_single(basin_id, run_idx, cfg)
                a_runs.append(a_entry)
                def _f(v): return f"{v:.4f}" if isinstance(v, (int, float)) else "N/A"
                logger.info(
                    f"  A run{run_idx+1}: KGE={_f(a_entry['train_metrics'].get('KGE'))} "
                    f"NSE={_f(a_entry['train_metrics'].get('NSE'))} "
                    f"boundary_hits={len(a_entry.get('boundary_hits', []))}"
                )
            record["method_A_runs"] = a_runs
            record["method_A_agg"] = _aggregate_method_a(a_runs)

        # ── Method B: Zhu et al. (scripted, single run) ──
        if RUN_ONLY in ("C", "AC"):
            logger.info(f"[B] Skipped (RUN_ONLY='{RUN_ONLY}') — loading from existing results if available")
            record["method_B"] = existing.get("method_B", {})
        else:
            logger.info("[B] Zhu et al. 2026 direct parameter proposal (scripted)")
            b_dir = str(OUTPUT_DIR / f"B_{MODEL}_{basin_id}")
            t0 = time.time()
            b_entry = _zhu_method(basin_id, MODEL, llm, cfg, b_dir)
            b_entry["wall_time_s"] = round(time.time() - t0, 2)
            if b_entry.get("success") and b_entry.get("calibration_dir"):
                b_tr, b_te = _evaluate_from_disk(b_entry["calibration_dir"], cfg)
                b_entry["train_metrics"] = b_tr
                b_entry["test_metrics"] = b_te
            record["method_B"] = b_entry
            logger.info(
                f"  B: KGE={b_entry.get('best_kge', 'N/A')} "
                f"NSE={b_entry.get('best_nse', 'N/A')} iters={b_entry.get('iterations', 0)}"
            )

        # ── Method C1: HydroAgent LLM range adjustment (primary LLM) ──
        if RUN_ONLY == "B":  # "AC" falls through to run C1
            logger.info("[C1] Skipped (RUN_ONLY='B') — loading from existing results if available")
            c1_entry = existing.get("method_C1", {})
            record["method_C1"] = c1_entry
        else:
            logger.info("[C1] HydroAgent LLM range adjustment (primary LLM)")
            c1_entry = _run_method_c(basin_id, cfg, "C1")
            record["method_C1"] = c1_entry
            # Propagate basin_attributes to top-level record for easy access
            if c1_entry.get("basin_attributes"):
                record["basin_attributes"] = c1_entry["basin_attributes"]
        def _f(v): return f"{v:.4f}" if isinstance(v, (int, float)) else "N/A"
        logger.info(
            f"  C1: KGE={_f(c1_entry.get('best_kge'))} "
            f"NSE={_f(c1_entry.get('best_nse'))} "
            f"rounds={c1_entry.get('rounds', 0)} model={c1_entry.get('model_used', '?')}"
        )

        # ── Method C2: alternative LLM (optional) ──
        if C2_MODEL:
            logger.info(f"[C2] HydroAgent LLM range adjustment (alt LLM: {C2_MODEL})")
            c2_entry = _run_method_c(
                basin_id, cfg, "C2",
                model_override=C2_MODEL,
                base_url_override=C2_BASE_URL,
            )
            record["method_C2"] = c2_entry
            logger.info(
                f"  C2: KGE={_f(c2_entry.get('best_kge'))} "
                f"NSE={_f(c2_entry.get('best_nse'))} "
                f"rounds={c2_entry.get('rounds', 0)} model={c2_entry.get('model_used', '?')}"
            )
        else:
            record["method_C2"] = {"skipped": True, "reason": "C2_MODEL not configured"}

        # ── Delta: C1 vs A_mean, C2 vs A_mean (NSE primary) ──
        a_nse_mean = record["method_A_agg"].get("nse_test", {}).get("mean") if isinstance(record["method_A_agg"], dict) else None
        c1_nse = c1_entry.get("test_metrics", {}).get("NSE")
        c2_nse = record["method_C2"].get("test_metrics", {}).get("NSE") if C2_MODEL else None

        record["delta_C1_vs_A_nse"] = (
            round(c1_nse - a_nse_mean, 4)
            if isinstance(c1_nse, float) and isinstance(a_nse_mean, float) else None
        )
        record["delta_C2_vs_A_nse"] = (
            round(c2_nse - a_nse_mean, 4)
            if isinstance(c2_nse, float) and isinstance(a_nse_mean, float) else None
        )
        # Keep KGE delta for reference
        a_kge_mean = record["method_A_agg"].get("kge_train", {}).get("mean") if isinstance(record["method_A_agg"], dict) else None
        c1_kge = c1_entry.get("train_metrics", {}).get("KGE")
        record["delta_C1_vs_A_kge"] = (
            round(c1_kge - a_kge_mean, 4)
            if isinstance(c1_kge, float) and isinstance(a_kge_mean, float) else None
        )

        results.append(record)
        _save_checkpoint(results, meta)  # persist after each basin

    # All basins done: remove checkpoint, write final results
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("[checkpoint] Cleared (all basins complete)")

    return {
        **meta,
        "results": results,
        "llm_token_usage": llm.tokens.summary(),
    }


def save_results(results: dict):
    f = OUTPUT_DIR / "exp2_results.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info(f"Saved -> {f}")


def _ms(d: dict) -> str:
    """Format mean+/-std dict for display."""
    if not isinstance(d, dict) or d.get("mean") is None:
        return "    N/A"
    return f"{d['mean']:.3f}+/-{d['std']:.3f}"


def print_summary(results: dict):
    data = results["results"]
    print(f"\n{'='*110}")
    print(f"  Exp2: LLM Calibration Comparison  ({results['mode']})")
    print(f"  Primary metric: NSE | Secondary: KGE")
    print(f"  A = SCE-UA standard ({N_SEEDS_A} runs, mean+/-std)  |  B = Zhu 2026 (scripted)")
    print(f"  C1 = HydroAgent LLM-guided (primary LLM)  |  C2 = alt LLM ({'enabled' if C2_MODEL else 'not configured'})")
    print(f"  Key insight: C_nse >= B_nse (C not worse than scripted LLM); C_nse APPROX= A_nse (automation equivalence)")
    print(f"{'='*110}")

    def _f(v): return f"{v:.4f}" if isinstance(v, (int, float)) else "  N/A "

    # NSE primary table
    print("\n  [NSE Results - primary metric]")
    hdr = (
        f"{'Basin':<12} {'Zone':<20} "
        f"{'A_train':>16} {'B_train':>8} {'C1_train':>8} "
        f"{'A_test':>12} {'C1_test':>8} "
        f"{'dC1-A(test)':>11} {'C1_rn':>6} {'eval_ratio':>10}"
    )
    print(hdr)
    print("-" * 110)

    for r in data:
        a_agg = r["method_A_agg"]
        c1 = r["method_C1"]
        b = r["method_B"]

        a_tr = _ms(a_agg["nse_train"])
        b_tr = _f(b.get("best_nse"))
        c1_tr = _f(c1.get("best_nse"))
        a_te = _ms(a_agg["nse_test"])
        c1_te = _f(c1.get("test_metrics", {}).get("NSE"))
        d_c1a = _f(r.get("delta_C1_vs_A_nse"))

        c1_rounds = c1.get("rounds") or 0
        a_eval = SCE_UA_REP_DEFAULT
        c1_eval = _estimate_c_total_evals(c1_rounds)
        ratio = f"{c1_eval/a_eval:.1f}x" if a_eval > 0 else "N/A"

        print(
            f"{r['basin_id']:<12} {r['climate_zone']:<20} "
            f"{a_tr:>16} {b_tr:>8} {c1_tr:>8} "
            f"{a_te:>12} {c1_te:>8} "
            f"{d_c1a:>11} {c1_rounds:>6} {ratio:>10}"
        )

    # C2 comparison (if enabled)
    if C2_MODEL:
        print(f"\n  [C1 vs C2 LLM comparison - NSE test]")
        print(f"  {'Basin':<12} {'C1 ('+cfg_model_name(results)+')':>20} {'C2 ('+C2_MODEL+')':>20} {'dC2-A':>8}")
        print("-" * 65)
        for r in data:
            c1_nse = _f(r["method_C1"].get("test_metrics", {}).get("NSE"))
            c2_nse = _f(r["method_C2"].get("test_metrics", {}).get("NSE"))
            d_c2a = _f(r.get("delta_C2_vs_A_nse"))
            print(f"  {r['basin_id']:<12} {c1_nse:>20} {c2_nse:>20} {d_c2a:>8}")

    # KGE secondary table
    print(f"\n  [KGE Results - secondary metric]")
    hdr2 = f"  {'Basin':<12} {'A_train KGE':>16} {'B_train':>8} {'C1_train':>8} {'A_test':>12} {'C1_test':>8}"
    print(hdr2)
    print("  " + "-" * 65)
    for r in data:
        a_agg = r["method_A_agg"]
        c1 = r["method_C1"]
        b = r["method_B"]
        a_tr = _ms(a_agg["kge_train"])
        b_tr = _f(b.get("best_kge"))
        c1_tr = _f(c1.get("train_metrics", {}).get("KGE"))
        a_te = _ms(a_agg["kge_test"])
        c1_te = _f(c1.get("test_metrics", {}).get("KGE"))
        print(f"  {r['basin_id']:<12} {a_tr:>16} {b_tr:>8} {c1_tr:>8} {a_te:>12} {c1_te:>8}")

    # NSE trajectory for C1
    print(f"\n  [C1 NSE trajectory per round - each round uses different SCE-UA seed]")
    for r in data:
        hist = r["method_C1"].get("nse_history", [])
        traj = " -> ".join(f"{v:.3f}" for v in hist if isinstance(v, float))
        print(f"    {r['basin_id']}: {traj or 'no data'}")

    # Boundary hits from Method A (parameter sensitivity)
    print(f"\n  [Parameter boundary analysis - Method A across {N_SEEDS_A} runs]")
    for r in data:
        hits = r["method_A_agg"].get("boundary_hits_any", [])
        if hits:
            from collections import Counter
            hit_summary = Counter(f"{h['param']}({h['boundary']})" for h in hits)
            print(f"    {r['basin_id']}: {dict(hit_summary)}")
        else:
            print(f"    {r['basin_id']}: no boundary hits detected")

    # Tool sequence + automation story
    print(f"\n  [Automation: tool sequences]")
    for r in data:
        a_seqs = r["method_A_agg"].get("tool_sequences", [])
        c1_tools = "->".join(r["method_C1"].get("tool_sequence", []))
        consistent = sum(1 for i in range(len(a_seqs)-1) if a_seqs[i] == a_seqs[i+1])
        a_repr = "->".join(a_seqs[0]) if a_seqs else "?"
        print(f"    {r['basin_id']} A (repr): {a_repr}  [consistency {consistent}/{max(len(a_seqs)-1,1)}]")
        print(f"    {r['basin_id']} C1:        {c1_tools}")

    # Failure analysis
    print(f"\n  [Failure analysis]")
    all_a_failures = []
    for r in data:
        all_a_failures.extend(r["method_A_agg"].get("failure_types", []))
    if all_a_failures:
        from collections import Counter
        print(f"    Method A failures: {dict(Counter(all_a_failures))}")
    else:
        print(f"    Method A: no failures")

    tokens = results.get("llm_token_usage", {})
    print(f"\n  LLM (shared for B): {tokens.get('calls', 0)} calls, {tokens.get('total_tokens', 0)} tokens")


def cfg_model_name(results: dict) -> str:
    """Extract primary LLM model name from results for display."""
    for r in results.get("results", []):
        return r.get("method_C1", {}).get("model_used", "primary")
    return "primary"


def main():
    setup_logging()
    logger.info(f"Starting Exp2: LLM Calibration Comparison (N_SEEDS_A={N_SEEDS_A})")
    if C2_MODEL:
        logger.info(f"  C2 LLM enabled: {C2_MODEL}")
    results = run_experiment()
    save_results(results)
    print_summary(results)
    logger.info("Exp2 complete")


if __name__ == "__main__":
    main()
