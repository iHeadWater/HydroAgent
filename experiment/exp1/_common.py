"""Shared utilities for Exp2 v2 LLM-position calibration experiments."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_ROOT = ROOT / "results" / "paper" / "exp2_v2"
TABLES_DIR = Path(__file__).resolve().parent / "tables"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"

TRAIN_PERIOD = ["2000-01-01", "2009-12-31"]
TEST_PERIOD = ["2010-01-01", "2014-12-31"]
OBJECTIVE = "NSE"
MAX_ITERS = 30
NSE_TARGET = 0.80

BASINS: list[dict[str, str]] = [
    {"basin_id": "12025000", "name": "Fish River, ME", "climate_zone": "humid_cold"},
    {"basin_id": "11532500", "name": "Smith River, CA", "climate_zone": "mediterranean"},
    {"basin_id": "03439000", "name": "French Broad River, NC", "climate_zone": "humid_warm"},
]
MODELS = ["gr4j", "xaj"]

METHODS = {
    "A": {
        "name": "standard_sceua",
        "llm_position": "None",
        "numeric_action": "SCE-UA over default parameter ranges",
        "max_rounds": 1,
        "cost_record": "hydromodel wall time",
    },
    "B": {
        "name": "zhu_direct_eval",
        "llm_position": "Before model evaluation",
        "numeric_action": "Directly evaluate each LLM-proposed parameter set",
        "max_rounds": MAX_ITERS,
        "cost_record": "LLM tokens, LLM decision time, direct evaluation time",
    },
    "C": {
        "name": "llm_local_search",
        "llm_position": "Before local optimization",
        "numeric_action": "Search within a tight range around each LLM proposal",
        "max_rounds": MAX_ITERS,
        "cost_record": "LLM tokens, LLM decision time, local-search time",
    },
    "D": {
        "name": "hydroagent_feedback",
        "llm_position": "After basin attributes and SCE-UA feedback",
        "numeric_action": "Revise ranges or budget between SCE-UA rounds",
        "max_rounds": MAX_ITERS,
        "cost_record": "LLM tokens, LLM decision time, hydromodel time",
    },
}

STANDARD_BUDGET = {
    "gr4j": {"rep": 500, "ngs": 50, "kstop": 50, "peps": 0.1, "pcento": 0.1},
    "xaj": {"rep": 750, "ngs": 200, "kstop": 50, "peps": 0.1, "pcento": 0.1},
}
LOCAL_SEARCH_BUDGET = {
    "gr4j": {"method": "SLSQP", "max_iterations": 30},
    "xaj": {"rep": 350, "ngs": 30, "kstop": 30, "peps": 0.1, "pcento": 0.1},
}


@dataclass(frozen=True)
class Task:
    basin_id: str
    basin_name: str
    climate_zone: str
    model: str

    @property
    def task_id(self) -> str:
        return f"{self.basin_id}_{self.model}"

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "basin_id": self.basin_id,
            "basin_name": self.basin_name,
            "climate_zone": self.climate_zone,
            "model": self.model,
        }


def ensure_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def iter_tasks(smoke: bool = False) -> list[Task]:
    tasks = [
        Task(b["basin_id"], b["name"], b["climate_zone"], model)
        for b in BASINS
        for model in MODELS
    ]
    return tasks[:1] if smoke else tasks


def method_dir(method_name: str) -> Path:
    path = OUTPUT_ROOT / method_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_base_config() -> dict[str, Any]:
    from hydroagent.config import load_config

    cfg = load_config()
    cfg.setdefault("defaults", {})
    cfg["defaults"]["train_period"] = TRAIN_PERIOD
    cfg["defaults"]["test_period"] = TEST_PERIOD
    return cfg


def default_ranges(model: str) -> dict[str, list[float]]:
    from hydroagent.skills.llm_calibration.llm_calibrate import DEFAULT_PARAM_RANGES

    return {k: [float(v[0]), float(v[1])] for k, v in DEFAULT_PARAM_RANGES[model].items()}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def metric(record: dict[str, Any], period: str, name: str) -> float | None:
    value = (record.get(f"{period}_metrics") or {}).get(name)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def best_by_train(records: list[dict[str, Any]], metric_name: str = "NSE") -> dict[str, Any] | None:
    valid = []
    for record in records:
        if not record.get("success"):
            continue
        value = metric(record, "train", metric_name)
        if value is not None:
            valid.append((value, record))
    return max(valid, key=lambda item: item[0])[1] if valid else None


def token_summary(llm) -> dict[str, int]:
    try:
        return llm.tokens.summary()
    except Exception:
        return {}


def token_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    keys = ["calls", "prompt_tokens", "completion_tokens", "cached_tokens", "total_tokens"]
    return {k: int(after.get(k, 0) or 0) - int(before.get(k, 0) or 0) for k in keys}


def get_basin_attrs(task: Task, cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        from hydroagent.tools.basin_attrs import get_basin_attributes

        attrs = get_basin_attributes(task.basin_id, data_source="camels_us", _cfg=cfg)
        return attrs if isinstance(attrs, dict) else {"success": False}
    except Exception as exc:
        return {"success": False, "error": str(exc), "basin_id": task.basin_id}


def normalize_params(params: dict[str, float], ranges: dict[str, list[float]]) -> dict[str, float]:
    return {k: (float(params[k]) - lo) / (hi - lo) for k, (lo, hi) in ranges.items()}


def denormalize_params(params: dict[str, float], ranges: dict[str, list[float]]) -> dict[str, float]:
    return {k: lo + float(params[k]) * (hi - lo) for k, (lo, hi) in ranges.items()}


def validate_parameter_set(
    model: str,
    proposed: dict[str, Any],
    ranges: dict[str, list[float]] | None = None,
) -> tuple[bool, dict[str, float], list[str]]:
    ranges = ranges or default_ranges(model)
    issues: list[str] = []
    clean: dict[str, float] = {}
    missing = [p for p in ranges if p not in proposed]
    extra = [p for p in proposed if p not in ranges]
    if missing:
        issues.append("missing:" + ",".join(missing))
    if extra:
        issues.append("unknown:" + ",".join(extra))
    for name, bounds in ranges.items():
        if name not in proposed:
            continue
        try:
            value = float(proposed[name])
        except (TypeError, ValueError):
            issues.append(f"non_numeric:{name}")
            continue
        lo, hi = bounds
        if value < lo or value > hi:
            issues.append(f"out_of_bounds:{name}={value} not in [{lo},{hi}]")
        clean[name] = value
    if model == "xaj" and "KI" in clean and "KG" in clean and clean["KI"] + clean["KG"] >= 0.7:
        issues.append(f"constraint:KI+KG={clean['KI'] + clean['KG']:.4f} >= 0.7")
    return not issues, clean, issues


def write_param_range_file(path: Path, model: str, ranges: dict[str, list[float]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {model: {"param_name": list(ranges.keys()), "param_range": ranges}}
    # sort_keys=False: hydromodel maps normalized params to ranges by param_range
    # value-order; alphabetical sort mis-aligns XAJ (K,B,IM,...) and crashes the sim.
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def prepare_direct_parameter_dir(
    *,
    task: Task,
    params: dict[str, float],
    run_dir: Path,
    cfg: dict[str, Any],
) -> Path:
    """Create a calibration-like directory for direct parameter evaluation."""
    from hydroagent.config import build_hydromodel_config

    ranges = default_ranges(task.model)
    norm = normalize_params(params, ranges)
    run_dir.mkdir(parents=True, exist_ok=True)
    range_file = run_dir / "param_range.yaml"
    write_param_range_file(range_file, task.model, ranges)
    config = build_hydromodel_config(
        basin_ids=[task.basin_id],
        model_name=task.model,
        algorithm="SCE_UA",
        train_period=TRAIN_PERIOD,
        test_period=TEST_PERIOD,
        param_range_file=str(range_file),
        obj_func=OBJECTIVE,
        output_dir=str(run_dir),
        cfg=cfg,
    )
    (run_dir / "calibration_config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    # Some legacy hydromodel evaluators look for config.yaml.
    (run_dir / "config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    # hydromodel evaluators read one normalized value per line, with a header row "0".
    param_file = run_dir / f"{task.basin_id}_calibrate_params.txt"
    values = ["0"] + [f"{norm[name]:.12g}" for name in ranges]
    param_file.write_text("\n".join(values) + "\n", encoding="utf-8")
    write_csv(run_dir / "basins_norm_params.csv", [{"basin_id": task.basin_id, **norm}])
    write_csv(run_dir / "basins_denorm_params.csv", [{"basin_id": task.basin_id, **params}])
    write_json(run_dir / "proposed_params.json", {"physical": params, "normalized": norm})
    write_json(run_dir / "calibration_results.json", {
        task.basin_id: {
            "best_params": {task.model: norm},
            "source": "direct_parameter_evaluation",
        }
    })
    return run_dir


def evaluate_parameter_set(
    *,
    task: Task,
    proposed_params: dict[str, Any],
    run_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Directly evaluate one physical parameter set without local optimization."""
    from hydroagent.skills.evaluation.evaluate import evaluate_model

    t0 = time.time()
    ranges = default_ranges(task.model)
    valid, clean, issues = validate_parameter_set(task.model, proposed_params, ranges)
    record = {
        **task.to_dict(),
        "method": "B",
        "valid_proposal": valid,
        "proposal_issues": issues,
        "proposed_params": proposed_params,
        "evaluated_params": clean if valid else {},
        "train_metrics": {},
        "test_metrics": {},
        "calibration_dir": "",
        "hydromodel_compute_time_s": 0.0,
        "success": False,
        "error": None,
    }
    if not valid:
        record["error"] = "; ".join(issues)
        record["hydromodel_compute_time_s"] = round(time.time() - t0, 3)
        return record
    try:
        cal_dir = prepare_direct_parameter_dir(task=task, params=clean, run_dir=run_dir, cfg=cfg)
        train_eval = evaluate_model(str(cal_dir), eval_period=TRAIN_PERIOD, _cfg=cfg)
        test_eval = evaluate_model(str(cal_dir), eval_period=TEST_PERIOD, _cfg=cfg)
        record["calibration_dir"] = str(cal_dir)
        record["train_metrics"] = train_eval.get("metrics", {}) if train_eval.get("success") else {}
        record["test_metrics"] = test_eval.get("metrics", {}) if test_eval.get("success") else {}
        record["success"] = bool(record["train_metrics"] and record["test_metrics"])
        if not record["success"]:
            record["error"] = train_eval.get("error") or test_eval.get("error") or "evaluation returned no metrics"
    except Exception as exc:
        record["error"] = str(exc)
    finally:
        record["hydromodel_compute_time_s"] = round(time.time() - t0, 3)
    return record


def run_calibration(
    *,
    task: Task,
    run_dir: Path,
    cfg: dict[str, Any],
    algorithm: str = "SCE_UA",
    algorithm_params: dict[str, Any] | None = None,
    param_ranges: dict[str, list[float]] | None = None,
    repeat_seed_offset: int = 0,
) -> dict[str, Any]:
    from hydroagent.skills.calibration.calibrate import calibrate_model
    from hydroagent.skills.evaluation.evaluate import evaluate_model

    t0 = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    param_range_file = None
    if param_ranges:
        param_range_file = write_param_range_file(run_dir / "param_range_input.yaml", task.model, param_ranges)
    params = dict(algorithm_params or STANDARD_BUDGET[task.model])
    if "random_seed" not in params:
        params["random_seed"] = 1234 + repeat_seed_offset
    record = {
        **task.to_dict(),
        "algorithm": algorithm,
        "algorithm_params": params,
        "param_ranges": param_ranges or default_ranges(task.model),
        "param_range_file": param_range_file,
        "calibration_dir": "",
        "best_params": {},
        "train_metrics": {},
        "test_metrics": {},
        "hydromodel_compute_time_s": 0.0,
        "success": False,
        "error": None,
    }
    try:
        cal = calibrate_model(
            basin_ids=[task.basin_id],
            model_name=task.model,
            algorithm=algorithm,
            train_period=TRAIN_PERIOD,
            test_period=TEST_PERIOD,
            algorithm_params=params,
            param_range_file=param_range_file,
            obj_func=OBJECTIVE,
            output_dir=str(run_dir),
            _workspace=run_dir,
            _cfg=cfg,
        )
        record["calibration_dir"] = cal.get("calibration_dir", "")
        record["best_params"] = cal.get("best_params", {})
        record["effective_config"] = cal.get("effective_config", {})
        if not cal.get("success"):
            record["error"] = cal.get("error", "calibrate_model returned success=False")
            return record
        train_eval = evaluate_model(record["calibration_dir"], eval_period=TRAIN_PERIOD, _cfg=cfg)
        test_eval = evaluate_model(record["calibration_dir"], eval_period=TEST_PERIOD, _cfg=cfg)
        record["train_metrics"] = train_eval.get("metrics", {}) if train_eval.get("success") else {}
        record["test_metrics"] = test_eval.get("metrics", {}) if test_eval.get("success") else {}
        record["success"] = bool(record["train_metrics"] and record["test_metrics"])
        if not record["success"]:
            record["error"] = train_eval.get("error") or test_eval.get("error") or "evaluation returned no metrics"
    except Exception as exc:
        record["error"] = str(exc)
    finally:
        record["hydromodel_compute_time_s"] = round(time.time() - t0, 3)
    return record


def tight_ranges_around(
    model: str,
    params: dict[str, float],
    frac: float,
) -> dict[str, list[float]]:
    ranges = default_ranges(model)
    tight = {}
    for name, value in params.items():
        lo, hi = ranges[name]
        margin = (hi - lo) * frac
        tight[name] = [max(lo, value - margin), min(hi, value + margin)]
    return tight


def parameter_distance(
    model: str,
    proposed: dict[str, float],
    found: dict[str, float],
) -> float | None:
    ranges = default_ranges(model)
    vals = []
    for name, pval in proposed.items():
        if name not in found or name not in ranges:
            continue
        lo, hi = ranges[name]
        span = hi - lo
        if span > 0:
            vals.append(abs(float(found[name]) - float(pval)) / span)
    return round(statistics.mean(vals), 6) if vals else None


def parse_json_object(text: str) -> dict[str, Any]:
    import re

    text = (text or "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def proposal_prompt(task: Task, attrs: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, str]]:
    ranges = default_ranges(task.model)
    compact_history = []
    for row in history[-5:]:
        compact_history.append({
            "iteration": row.get("iteration"),
            "valid": row.get("valid_proposal"),
            "issues": row.get("proposal_issues", []),
            "train_NSE": metric(row, "train", "NSE"),
            "train_KGE": metric(row, "train", "KGE"),
            "params": row.get("proposed_params", {}),
        })
    attrs_small = {
        k: attrs.get(k)
        for k in ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
        if attrs.get(k) is not None
    }
    system = (
        "You are a hydrological calibration expert. Return exactly one JSON object "
        "containing one physical value for every model parameter. Do not include text."
    )
    user = json.dumps({
        "task": task.to_dict(),
        "parameter_ranges": ranges,
        "basin_attributes": attrs_small,
        "previous_iterations": compact_history,
        "constraints": [
            "All parameters must be present.",
            "Values must stay within parameter_ranges.",
            "For XAJ, KI + KG must be less than 0.7.",
            "Only train metrics are shown during iteration; test metrics are hidden until reporting.",
            "Optimize train NSE without using test metrics as a selection target.",
        ],
    }, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def ask_llm_for_params(llm, task: Task, attrs: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    before = token_summary(llm)
    t0 = time.time()
    response = llm.chat(proposal_prompt(task, attrs, history), temperature=0.2)
    elapsed = round(time.time() - t0, 3)
    after = token_summary(llm)
    raw = response.text or ""
    return {
        "raw_response": raw[:4000],
        "proposed_params": parse_json_object(raw),
        "llm_tokens": token_delta(before, after),
        "llm_decision_time_s": elapsed,
    }


def median(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return round(statistics.median(clean), 6) if clean else None
