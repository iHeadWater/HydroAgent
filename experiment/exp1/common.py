"""Shared utilities for Exp1 v2 token-for-time calibration experiments.

The experiment compares four controllers under the same calibration menu:
default script, human menu tuning, HydroAgent/LLM menu tuning, and random menu
tuning. Numerical calibration is always executed by hydromodel through the
HydroAgent tool layer.
"""

from __future__ import annotations

import copy
import csv
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_ROOT = ROOT / "results" / "paper" / "exp1_v2"
TABLES_DIR = Path(__file__).resolve().parent / "tables"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"

TRAIN_PERIOD = ["2000-01-01", "2009-12-31"]
TEST_PERIOD = ["2010-01-01", "2014-12-31"]
ALGORITHM = "SCE_UA"
MAX_TRIALS = 5
RANDOM_REPEATS = 5
NONINFERIORITY_MARGIN = -0.02

# Selected 2026-05-24 from the GR4J screen (default-range, quick budget) over 60
# CAMELS-US basins: the 7 candidates with test NSE in [0.40, 0.65] were filtered
# to 5 with one basin per USGS HUC region (01/03/05/06/07) so the panel covers
# climate diversity without picking from the same hydrologic neighborhood.
# climate_zone is left "unknown" because CAMELS does not ship a labelled
# climate class; downstream `climate_prior` range policy will fall back to the
# default range (probe_difficulty.py:87).
BASINS: list[dict[str, str]] = [
    {"basin_id": "01543000", "name": "HUC01 New England",   "climate_zone": "unknown"},
    {"basin_id": "03574500", "name": "HUC03 South Atlantic", "climate_zone": "unknown"},
    {"basin_id": "05495000", "name": "HUC05 Ohio/Tennessee", "climate_zone": "unknown"},
    {"basin_id": "06885500", "name": "HUC06 Missouri",       "climate_zone": "unknown"},
    {"basin_id": "07197000", "name": "HUC07 Mississippi",    "climate_zone": "unknown"},
]
MODELS = ["gr4j"]  # XAJ only had 1 medium candidate in screen; stick to GR4J for exp1 v2
OBJECTIVES = ["NSE", "KGE", "LOGNSE"]
RANGE_POLICIES = ["default", "climate_prior", "wide", "boundary_expand"]
BUDGET_LEVELS = ["quick", "default", "deep"]

BUDGET_MENU: dict[str, dict[str, dict[str, int | float]]] = {
    "gr4j": {
        "quick": {"rep": 300, "ngs": 30, "kstop": 50, "peps": 0.1, "pcento": 0.1},
        "default": {"rep": 500, "ngs": 50, "kstop": 50, "peps": 0.1, "pcento": 0.1},
        "deep": {"rep": 1000, "ngs": 100, "kstop": 50, "peps": 0.1, "pcento": 0.1},
    },
    "xaj": {
        "quick": {"rep": 500, "ngs": 100, "kstop": 50, "peps": 0.1, "pcento": 0.1},
        "default": {"rep": 750, "ngs": 200, "kstop": 50, "peps": 0.1, "pcento": 0.1},
        "deep": {"rep": 1500, "ngs": 300, "kstop": 50, "peps": 0.1, "pcento": 0.1},
    },
}

METHODS = {
    "M0": {
        "name": "default_script",
        "controller": "Fixed script",
        "human_intervention": "None",
        "token_recorded": "No",
        "max_trials": 1,
    },
    "M1": {
        "name": "human_script",
        "controller": "Human menu decisions",
        "human_intervention": "Menu selection and notes only",
        "token_recorded": "No",
        "max_trials": MAX_TRIALS,
    },
    "M2": {
        "name": "hydroagent_menu",
        "controller": "HydroAgent/LLM menu decisions",
        "human_intervention": "Start task only",
        "token_recorded": "Yes",
        "max_trials": MAX_TRIALS,
    },
    "M3": {
        "name": "random_menu",
        "controller": "Uniform random menu decisions",
        "human_intervention": "None",
        "token_recorded": "No",
        "max_trials": MAX_TRIALS,
    },
}


@dataclass(frozen=True)
class MenuDecision:
    objective: str = "NSE"
    budget_level: str = "default"
    range_policy: str = "default"
    stop: bool = False
    notes: str = ""

    def normalized(self) -> "MenuDecision":
        objective = self.objective.upper()
        if objective == "LOG_NSE":
            objective = "LOGNSE"
        budget = self.budget_level.lower()
        policy = self.range_policy.lower()
        if objective not in OBJECTIVES:
            objective = "NSE"
        if budget not in BUDGET_LEVELS:
            budget = "default"
        if policy not in RANGE_POLICIES:
            policy = "default"
        return MenuDecision(objective, budget, policy, bool(self.stop), self.notes)

    def to_dict(self) -> dict[str, Any]:
        d = self.normalized()
        return {
            "objective": d.objective,
            "budget_level": d.budget_level,
            "range_policy": d.range_policy,
            "stop": d.stop,
            "notes": d.notes,
        }


def iter_tasks(smoke: bool = False) -> list[dict[str, str]]:
    tasks = []
    for basin in BASINS:
        for model in MODELS:
            tasks.append({**basin, "model": model, "task_id": task_id(basin["basin_id"], model)})
    return tasks[:1] if smoke else tasks


def task_id(basin_id: str, model: str) -> str:
    return f"{basin_id}_{model}"


def ensure_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def method_dir(method_name: str) -> Path:
    path = OUTPUT_ROOT / method_name
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_base_config() -> dict[str, Any]:
    from hydroagent.config import load_config

    cfg = load_config()
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("defaults", {})
    cfg["defaults"]["train_period"] = TRAIN_PERIOD
    cfg["defaults"]["test_period"] = TEST_PERIOD
    return cfg


def get_basin_attrs(basin_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        from hydroagent.tools.basin_attrs import get_basin_attributes

        attrs = get_basin_attributes(basin_id=basin_id, data_source="camels_us", _cfg=cfg)
        if attrs.get("success"):
            return attrs
    except Exception:
        pass
    return {"basin_id": basin_id, "success": False}


def budget_params(model: str, budget_level: str, trial_idx: int, repeat_idx: int = 0) -> dict[str, Any]:
    decision = MenuDecision(budget_level=budget_level).normalized()
    params = dict(BUDGET_MENU[model][decision.budget_level])
    params["random_seed"] = 1234 + trial_idx * 137 + repeat_idx * 1009
    return params


def default_ranges(model: str) -> dict[str, list[float]]:
    from hydroagent.skills.llm_calibration.llm_calibrate import DEFAULT_PARAM_RANGES

    return copy.deepcopy(DEFAULT_PARAM_RANGES[model])


def ranges_for_policy(
    model: str,
    policy: str,
    climate_zone: str,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, list[float]] | None:
    policy = policy.lower()
    if policy == "default":
        return None
    base = default_ranges(model)
    if policy == "wide":
        return base
    if policy == "boundary_expand":
        prev_ranges = (previous_best or {}).get("param_ranges") or base
        prev_hits = (previous_best or {}).get("boundary_hits") or []
        return expand_boundary_ranges(model, prev_ranges, prev_hits)
    return climate_prior_ranges(model, climate_zone, base)


def climate_prior_ranges(
    model: str, climate_zone: str, base: dict[str, list[float]]
) -> dict[str, list[float]]:
    ranges = copy.deepcopy(base)
    cz = climate_zone.lower()
    if model == "gr4j":
        if "semiarid" in cz:
            ranges.update({"x1": [100.0, 900.0], "x2": [-8.0, 2.0], "x3": [1.0, 250.0], "x4": [0.5, 4.0]})
        elif "cold" in cz or "mountain" in cz:
            ranges.update({"x1": [500.0, 2000.0], "x2": [-5.0, 5.0], "x3": [50.0, 500.0], "x4": [1.5, 8.0]})
        else:
            ranges.update({"x1": [300.0, 1800.0], "x2": [-5.0, 5.0], "x3": [20.0, 450.0], "x4": [0.5, 5.0]})
        return clamp_ranges(ranges, base)

    ranges.update({"KI": [0.05, 0.32], "KG": [0.05, 0.32]})
    if "semiarid" in cz:
        ranges.update({
            "K": [0.3, 0.8], "B": [0.2, 0.4], "IM": [0.01, 0.1],
            "UM": [5.0, 20.0], "LM": [60.0, 90.0], "DM": [80.0, 120.0],
            "C": [0.05, 0.15], "SM": [5.0, 50.0], "CS": [0.3, 0.9], "L": [1.0, 4.0],
            "CI": [0.2, 0.7], "CG": [0.98, 0.998],
        })
    elif "cold" in cz or "mountain" in cz:
        ranges.update({
            "K": [0.6, 1.0], "B": [0.1, 0.3], "IM": [0.01, 0.06],
            "UM": [10.0, 20.0], "LM": [70.0, 90.0], "DM": [80.0, 120.0],
            "C": [0.1, 0.2], "SM": [30.0, 90.0], "KI": [0.2, 0.32],
            "KG": [0.2, 0.32], "CS": [0.2, 0.7], "L": [2.0, 8.0],
            "CI": [0.5, 0.9], "CG": [0.985, 0.998],
        })
    elif "mediterranean" in cz:
        ranges.update({"K": [0.4, 1.0], "B": [0.15, 0.4], "SM": [15.0, 70.0], "L": [1.0, 5.0]})
    else:
        ranges.update({"K": [0.5, 1.0], "B": [0.1, 0.3], "IM": [0.01, 0.06], "SM": [20.0, 80.0], "L": [1.0, 5.0]})
    return clamp_ranges(ranges, base)


def clamp_ranges(ranges: dict[str, list[float]], base: dict[str, list[float]]) -> dict[str, list[float]]:
    out = {}
    for name, bounds in ranges.items():
        lo, hi = bounds
        base_lo, base_hi = base[name]
        lo = max(float(lo), float(base_lo))
        hi = min(float(hi), float(base_hi))
        if lo >= hi:
            lo, hi = base_lo, base_hi
        out[name] = [lo, hi]
    return out


def expand_boundary_ranges(
    model: str, current_ranges: dict[str, list[float]], boundary_hits: list[dict[str, Any]]
) -> dict[str, list[float]]:
    base = default_ranges(model)
    expanded = copy.deepcopy(current_ranges)
    for hit in boundary_hits:
        name = hit.get("param")
        if name not in expanded or name not in base:
            continue
        lo, hi = expanded[name]
        base_lo, base_hi = base[name]
        span = max(hi - lo, 1e-9)
        if hit.get("boundary") == "lower":
            lo = max(base_lo, lo - span * 0.5)
        elif hit.get("boundary") == "upper":
            hi = min(base_hi, hi + span * 0.5)
        expanded[name] = [lo, hi]
    return clamp_ranges(expanded, base)


def write_range_file(
    output_dir: Path, model: str, ranges: dict[str, list[float]] | None, trial_idx: int
) -> str | None:
    if not ranges:
        return None
    path = output_dir / f"param_ranges_trial{trial_idx}.yaml"
    data = {
        model: {
            "param_name": list(ranges.keys()),
            "param_range": ranges,
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys=False is CRITICAL: hydromodel maps normalized params to ranges
    # by the param_range dict's value order. Alphabetical sorting (yaml default)
    # mis-aligns XAJ params (K,B,IM,... != alphabetical) and crashes the sim.
    # GR4J (x1..x4) happens to be alphabetical so it was never hit.
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def detect_boundary_hits(
    params: dict[str, Any], ranges: dict[str, list[float]] | None, threshold_pct: float = 5.0
) -> list[dict[str, Any]]:
    if not ranges:
        return []
    hits = []
    for name, raw_value in params.items():
        if name not in ranges:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        lo, hi = ranges[name]
        span = hi - lo
        if span <= 0:
            continue
        lo_pct = (value - lo) / span * 100
        hi_pct = (hi - value) / span * 100
        if lo_pct < threshold_pct:
            hits.append({"param": name, "boundary": "lower", "value": value, "bound": lo, "pct_from_bound": round(lo_pct, 2)})
        elif hi_pct < threshold_pct:
            hits.append({"param": name, "boundary": "upper", "value": value, "bound": hi, "pct_from_bound": round(hi_pct, 2)})
    return hits


def run_trial(
    *,
    method: str,
    task: dict[str, str],
    trial_idx: int,
    decision: MenuDecision,
    cfg: dict[str, Any],
    run_dir: Path,
    repeat_idx: int = 0,
    active_seconds: float = 0.0,
    llm_tokens: dict[str, Any] | None = None,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from hydroagent.skills.calibration.calibrate import calibrate_model
    from hydroagent.skills.evaluation.evaluate import evaluate_model

    ensure_dirs()
    decision = decision.normalized()
    task_output = run_dir / task["task_id"] / f"repeat{repeat_idx}" / f"trial{trial_idx}"
    task_output.mkdir(parents=True, exist_ok=True)

    algorithm_params = budget_params(task["model"], decision.budget_level, trial_idx, repeat_idx)
    param_ranges = ranges_for_policy(task["model"], decision.range_policy, task["climate_zone"], previous_best)
    param_range_file = write_range_file(task_output, task["model"], param_ranges, trial_idx)
    effective_ranges = param_ranges or default_ranges(task["model"])

    record: dict[str, Any] = {
        "schema_version": "exp1_v2_trial_1",
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "task_id": task["task_id"],
        "basin_id": task["basin_id"],
        "basin_name": task["name"],
        "climate_zone": task["climate_zone"],
        "model": task["model"],
        "trial_idx": trial_idx,
        "repeat_idx": repeat_idx,
        "decision": decision.to_dict(),
        "algorithm": ALGORITHM,
        "algorithm_params": algorithm_params,
        "param_range_file": param_range_file,
        "param_ranges": effective_ranges,
        "active_seconds": round(active_seconds, 3),
        "llm_tokens": llm_tokens or {},
        "wall_time_s": 0.0,
        "calibration_dir": "",
        "best_params": {},
        "boundary_hits": [],
        "train_metrics": {},
        "test_metrics": {},
        "effective_config": {},
        "success": False,
        "error": None,
    }

    t0 = time.time()
    try:
        cal = calibrate_model(
            basin_ids=[task["basin_id"]],
            model_name=task["model"],
            algorithm=ALGORITHM,
            train_period=TRAIN_PERIOD,
            test_period=TEST_PERIOD,
            algorithm_params=algorithm_params,
            param_range_file=param_range_file,
            obj_func=decision.objective,
            output_dir=str(task_output),
            data_source="camels_us",
            _workspace=task_output,
            _cfg=cfg,
        )
        record["calibration_dir"] = cal.get("calibration_dir", "")
        record["best_params"] = cal.get("best_params", {})
        record["effective_config"] = cal.get("effective_config", {})
        if not cal.get("success"):
            record["error"] = cal.get("error", "calibrate_model returned success=False")
            return record

        train_eval = evaluate_model(
            calibration_dir=record["calibration_dir"],
            eval_period=TRAIN_PERIOD,
            _workspace=task_output,
            _cfg=cfg,
        )
        test_eval = evaluate_model(
            calibration_dir=record["calibration_dir"],
            eval_period=TEST_PERIOD,
            _workspace=task_output,
            _cfg=cfg,
        )
        record["train_metrics"] = train_eval.get("metrics", {}) if train_eval.get("success") else {}
        record["test_metrics"] = test_eval.get("metrics", {}) if test_eval.get("success") else {}
        record["boundary_hits"] = detect_boundary_hits(record["best_params"], effective_ranges)
        record["success"] = bool(record["train_metrics"] and record["test_metrics"])
        if not record["success"]:
            record["error"] = "Evaluation returned no metrics"
    except Exception as exc:
        record["error"] = str(exc)
    finally:
        record["wall_time_s"] = round(time.time() - t0, 3)

    return record


def score_record(record: dict[str, Any], metric: str = "NSE") -> float | None:
    value = record.get("test_metrics", {}).get(metric)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def best_record(records: list[dict[str, Any]], metric: str = "NSE") -> dict[str, Any] | None:
    valid = [(score_record(r, metric), r) for r in records if r.get("success")]
    valid = [(s, r) for s, r in valid if s is not None]
    if not valid:
        return None
    return max(valid, key=lambda item: item[0])[1]


def best_so_far(records: list[dict[str, Any]], metric: str = "NSE") -> list[float | None]:
    out: list[float | None] = []
    best: float | None = None
    for record in sorted(records, key=lambda r: r.get("trial_idx", 0)):
        value = score_record(record, metric)
        if value is not None:
            best = value if best is None else max(best, value)
        out.append(best)
    return out


def auc_best_so_far(records: list[dict[str, Any]], metric: str = "NSE") -> float | None:
    values = [v for v in best_so_far(records, metric) if v is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def median(values: list[float]) -> float | None:
    clean = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return round(statistics.median(clean), 6) if clean else None


def iqr(values: list[float]) -> tuple[float | None, float | None]:
    clean = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if not clean:
        return None, None
    if len(clean) == 1:
        return clean[0], clean[0]
    q1 = statistics.quantiles(clean, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(clean, n=4, method="inclusive")[2]
    return round(q1, 6), round(q3, 6)


def percentile(value: float | None, distribution: list[float]) -> float | None:
    if value is None:
        return None
    clean = [v for v in distribution if isinstance(v, (int, float)) and math.isfinite(v)]
    if not clean:
        return None
    return round(100.0 * sum(1 for v in clean if v <= value) / len(clean), 2)


def flatten_metric(record: dict[str, Any], period: str, metric: str) -> float | None:
    value = record.get(f"{period}_metrics", {}).get(metric)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None
