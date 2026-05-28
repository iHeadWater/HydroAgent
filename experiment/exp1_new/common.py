"""Shared config and utilities for new Experiment 1.

M0 (static SCE-UA baseline) vs M2 (LLM-adaptive, 5-variant parallel per generation).
20 CAMELS basins, GR4J only, NSE only.
"""

from __future__ import annotations

import copy
import csv
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXP_DIR / "results"
M0_DIR = RESULTS_DIR / "m0_baseline"
M2_DIR = RESULTS_DIR / "m2_adaptive"
TABLES_DIR = EXP_DIR / "tables"
FIGURES_DIR = EXP_DIR / "figures"

TRAIN_PERIOD = ["2000-01-01", "2009-12-31"]
TEST_PERIOD = ["2010-01-01", "2014-12-31"]
ALGORITHM = "SCE_UA"

# ── 20-basin pool ─────────────────────────────────────────────────────────────
BASINS = [
    {"basin_id": "12025000", "name": "Newaukum River, WA",      "climate_zone": "mediterranean", "difficulty": "easy",   "huc": "17"},
    {"basin_id": "11532500", "name": "Smith River, CA",         "climate_zone": "mediterranean", "difficulty": "easy",   "huc": "18"},
    {"basin_id": "02246000", "name": "N Fork Black Creek, FL",  "climate_zone": "humid_warm",    "difficulty": "easy",   "huc": "03"},
    {"basin_id": "11482500", "name": "Redwood Creek, CA",       "climate_zone": "humid_warm",    "difficulty": "easy",   "huc": "18"},
    {"basin_id": "05495000", "name": "Fox River, MO",           "climate_zone": "humid_warm",    "difficulty": "easy",   "huc": "07"},
    {"basin_id": "03574500", "name": "Paint Rock River, AL",    "climate_zone": "humid_warm",    "difficulty": "easy",   "huc": "06"},
    {"basin_id": "05595730", "name": "Rayse Creek, IL",         "climate_zone": "humid_warm",    "difficulty": "easy",   "huc": "07"},
    {"basin_id": "01543000", "name": "Driftwood Branch, PA",    "climate_zone": "humid_cold",    "difficulty": "medium", "huc": "02"},
    {"basin_id": "07197000", "name": "Baron Fork, OK",          "climate_zone": "humid_warm",    "difficulty": "medium", "huc": "11"},
    {"basin_id": "06885500", "name": "Black Vermillion, KS",    "climate_zone": "semiarid",      "difficulty": "medium", "huc": "10"},
    {"basin_id": "03049000", "name": "Buffalo Creek, PA",       "climate_zone": "humid_warm",    "difficulty": "medium", "huc": "05"},
    {"basin_id": "02472500", "name": "Bouie Creek, MS",         "climate_zone": "humid_warm",    "difficulty": "medium", "huc": "03"},
    {"basin_id": "01169000", "name": "North River, MA",         "climate_zone": "humid_cold",    "difficulty": "hard",   "huc": "01"},
    {"basin_id": "05057200", "name": "Baldhill Creek, ND",      "climate_zone": "semiarid",      "difficulty": "hard",   "huc": "09"},
    {"basin_id": "09508300", "name": "Wet Bottom Creek, AZ",    "climate_zone": "arid",          "difficulty": "hard",   "huc": "15"},
    {"basin_id": "09378630", "name": "Recapture Creek, UT",     "climate_zone": "arid",          "difficulty": "hard",   "huc": "14"},
    {"basin_id": "10336660", "name": "Blackwood Creek, CA",     "climate_zone": "mountain",      "difficulty": "hard",   "huc": "16"},
    {"basin_id": "04197170", "name": "Rock Creek, OH",          "climate_zone": "humid_cold",    "difficulty": "hard",   "huc": "04"},
    {"basin_id": "08101000", "name": "Cowhouse Creek, TX",      "climate_zone": "semiarid",      "difficulty": "hard",   "huc": "12"},
    {"basin_id": "03439000", "name": "French Broad River, NC",  "climate_zone": "humid_warm",    "difficulty": "hard",   "huc": "06"},
]
BASIN_BY_ID = {b["basin_id"]: b for b in BASINS}

# ── SCE-UA defaults ───────────────────────────────────────────────────────────
# rep is a ceiling only; convergence is controlled by kstop/peps/pcento.
SCE_DEFAULTS = {
    "rep": 100000,
    "ngs": 20,
    "kstop": 50,
    "peps": 0.01,
    "pcento": 0.1,
}

# M0 wide static range (wider than hydromodel built-in default)
M0_WIDE_RANGES = {
    "x1": [1.0, 2500.0],
    "x2": [-15.0, 15.0],
    "x3": [1.0, 700.0],
    "x4": [0.5, 12.0],
}

# Physical hard bounds for LLM-proposed ranges (clamped into these)
GR4J_HARD_BOUNDS = {
    "x1": [1.0, 3000.0],
    "x2": [-20.0, 20.0],
    "x3": [1.0, 1000.0],
    "x4": [0.1, 15.0],
}

# ── M2 config ─────────────────────────────────────────────────────────────────
M2_MAX_GENERATIONS = 10
M2_VARIANTS_PER_GEN = 1         # LLM generates 1 variant per generation; parallelism is at basin level
M2_EARLY_STOP_PATIENCE = 3     # stop if best NSE doesn't improve for 3 gens
M2_EARLY_STOP_MIN_GAIN = 0.005
M2_NGS_BOUNDS = (10, 100)       # LLM can pick ngs in this range
M2_VARIANT_TIMEOUT_S = 1200     # 20min, from M0 max (06885500: ~19min / 10800 evals)


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class Variant:
    """One SCE-UA configuration proposed by the LLM (or M0 fixed)."""
    ngs: int = 20
    param_ranges: dict[str, list[float]] = field(default_factory=lambda: copy.deepcopy(M0_WIDE_RANGES))
    seed: int = 1234
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ngs": self.ngs,
            "param_ranges": self.param_ranges,
            "seed": self.seed,
            "notes": self.notes,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────
def ensure_dirs() -> None:
    for d in (M0_DIR, M2_DIR, TABLES_DIR, FIGURES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_base_config() -> dict[str, Any]:
    from hydroagent.config import load_config
    cfg = copy.deepcopy(load_config())
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


def clamp_param_ranges(ranges: dict[str, Any] | None) -> dict[str, list[float]]:
    """Sanitize LLM-proposed param ranges into GR4J hard bounds."""
    if not ranges:
        return copy.deepcopy(M0_WIDE_RANGES)
    out = {}
    for name, hb in GR4J_HARD_BOUNDS.items():
        bounds = ranges.get(name)
        if not (isinstance(bounds, (list, tuple)) and len(bounds) == 2):
            out[name] = list(M0_WIDE_RANGES[name])
            continue
        try:
            lo, hi = float(bounds[0]), float(bounds[1])
        except (TypeError, ValueError):
            out[name] = list(M0_WIDE_RANGES[name])
            continue
        lo = max(hb[0], min(lo, hi))
        hi = min(hb[1], max(lo, hi))
        if lo >= hi:
            lo, hi = hb
        out[name] = [round(lo, 4), round(hi, 4)]
    return out


def write_range_file(output_dir: Path, ranges: dict[str, list[float]], tag: str = "") -> str:
    fname = f"param_ranges{'_' + tag if tag else ''}.yaml"
    path = output_dir / fname
    data = {"gr4j": {"param_name": list(ranges.keys()), "param_range": ranges}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return str(path)


def run_single_calibration(
    *,
    basin_id: str,
    variant: Variant,
    output_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Run one SCE-UA calibration + evaluation. Returns a result dict."""
    from hydroagent.skills.calibration.calibrate import calibrate_model
    from hydroagent.skills.evaluation.evaluate import evaluate_model

    output_dir.mkdir(parents=True, exist_ok=True)
    ranges = clamp_param_ranges(variant.param_ranges)
    rf = write_range_file(output_dir, ranges, f"s{variant.seed}")
    ap = {
        "rep": SCE_DEFAULTS["rep"],
        "ngs": max(M2_NGS_BOUNDS[0], min(M2_NGS_BOUNDS[1], variant.ngs)),
        "kstop": SCE_DEFAULTS["kstop"],
        "peps": SCE_DEFAULTS["peps"],
        "pcento": SCE_DEFAULTS["pcento"],
        "random_seed": variant.seed,
    }

    result: dict[str, Any] = {
        "basin_id": basin_id,
        "variant": variant.to_dict(),
        "algorithm_params": ap,
        "param_ranges": ranges,
        "param_range_file": rf,
        "wall_time_s": 0.0,
        "icall": 0,
        "best_params": {},
        "boundary_hits": [],
        # NSE/KGE convenience fields (most cited)
        "train_NSE": None,
        "test_NSE": None,
        "train_KGE": None,
        "test_KGE": None,
        # Full metric dicts from evaluate_model (Bias, RMSE, ubRMSE, Corr, R2, NSE, KGE, FHV, FLV)
        "train_metrics": {},
        "test_metrics": {},
        "success": False,
        "error": None,
    }

    t0 = time.time()
    try:
        cal = calibrate_model(
            basin_ids=[basin_id], model_name="gr4j", algorithm=ALGORITHM,
            train_period=TRAIN_PERIOD, test_period=TEST_PERIOD,
            algorithm_params=ap, param_range_file=rf, obj_func="NSE",
            output_dir=str(output_dir), data_source="camels_us",
            _workspace=output_dir, _cfg=cfg,
        )
        result["calibration_dir"] = cal.get("calibration_dir", "")
        result["best_params"] = cal.get("best_params", {})
        if not cal.get("success"):
            result["error"] = cal.get("error", "calibration failed")
            return result

        train_eval = evaluate_model(
            calibration_dir=result["calibration_dir"],
            eval_period=TRAIN_PERIOD, _workspace=output_dir, _cfg=cfg,
        )
        test_eval = evaluate_model(
            calibration_dir=result["calibration_dir"],
            eval_period=TEST_PERIOD, _workspace=output_dir, _cfg=cfg,
        )
        train_m = train_eval.get("metrics") or {}
        test_m = test_eval.get("metrics") or {}
        result["train_metrics"] = train_m
        result["test_metrics"] = test_m
        result["train_NSE"] = train_m.get("NSE")
        result["test_NSE"] = test_m.get("NSE")
        result["train_KGE"] = train_m.get("KGE")
        result["test_KGE"] = test_m.get("KGE")
        result["success"] = result["test_NSE"] is not None

        # boundary hits
        if ranges and result["best_params"]:
            result["boundary_hits"] = _detect_boundary_hits(result["best_params"], ranges)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["wall_time_s"] = round(time.time() - t0, 3)

    # count actual evaluations from SCE-UA csv
    csv_files = list(output_dir.glob("*sceua.csv"))
    if csv_files:
        with open(csv_files[0], encoding="utf-8") as f:
            result["icall"] = sum(1 for _ in f) - 1

    return result


def _detect_boundary_hits(
    params: dict[str, Any], ranges: dict[str, list[float]], threshold_pct: float = 5.0
) -> list[dict[str, Any]]:
    hits = []
    for name, raw in params.items():
        if name not in ranges:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        lo, hi = ranges[name]
        span = hi - lo
        if span <= 0:
            continue
        if (value - lo) / span * 100 < threshold_pct:
            hits.append({"param": name, "boundary": "lower", "value": value, "bound": lo})
        elif (hi - value) / span * 100 < threshold_pct:
            hits.append({"param": name, "boundary": "upper", "value": value, "bound": hi})
    return hits


# ── IO ────────────────────────────────────────────────────────────────────────
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
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


# ══════════════════════════════════════════════════════════════════════════════
# M3 (split-sample + dual-candidate) helpers — ADDITIVE, do not touch M0/M2 above
# ══════════════════════════════════════════════════════════════════════════════
# Split the former 2000-2009 train into a calibration window (SCE-UA optimises
# here) and a held-out validation window (used to SELECT between candidates and
# to detect over-fitting). 2010-2014 TEST stays fully held out (report only).
CAL_PERIOD = ["2000-01-01", "2006-12-31"]
VAL_PERIOD = ["2007-01-01", "2009-12-31"]
# TEST_PERIOD reuses the module-level constant (2010-01-01 .. 2014-12-31).

# Direct LLM parameter guesses are evaluated against hydromodel's normalisation
# ranges. We reuse exp2's proven direct-evaluation layout, whose normalisation
# uses these default GR4J ranges, so guesses must live inside them.
GR4J_DIRECT_RANGES = {
    "x1": [1.0, 2000.0],
    "x2": [-10.0, 10.0],
    "x3": [1.0, 500.0],
    "x4": [0.5, 10.0],
}


def _load_exp2_common():
    """Import exp2/common.py under a unique name (avoids clashing with this
    module, which is also called ``common``)."""
    import importlib.util
    name = "exp2_common_for_m3"
    if name in sys.modules:
        return sys.modules[name]
    path = EXP_DIR.parent / "exp2" / "common.py"
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ during class body.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def clamp_direct_params(params: dict[str, Any] | None) -> dict[str, float]:
    """Clamp an LLM direct parameter guess into GR4J_DIRECT_RANGES."""
    out: dict[str, float] = {}
    params = params or {}
    for name, (lo, hi) in GR4J_DIRECT_RANGES.items():
        try:
            v = float(params.get(name))
        except (TypeError, ValueError):
            v = (lo + hi) / 2.0
        out[name] = round(min(hi, max(lo, v)), 6)
    return out


def _eval_three_periods(calibration_dir: str, cfg: dict[str, Any], workspace: Path | None = None) -> dict[str, dict]:
    """Evaluate one calibration_dir on CAL / VAL / TEST and return metric dicts."""
    from hydroagent.skills.evaluation.evaluate import evaluate_model
    metrics = {}
    for tag, period in (("cal", CAL_PERIOD), ("val", VAL_PERIOD), ("test", TEST_PERIOD)):
        kw = {"eval_period": period, "_cfg": cfg}
        if workspace is not None:
            kw["_workspace"] = workspace
        ev = evaluate_model(calibration_dir, **kw)
        metrics[tag] = ev.get("metrics") or {} if ev.get("success") else {}
    return metrics


def run_sceua_candidate_split(
    *,
    basin_id: str,
    variant: Variant,
    output_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """SCE-UA candidate: optimise on CAL_PERIOD, evaluate on CAL/VAL/TEST."""
    from hydroagent.skills.calibration.calibrate import calibrate_model

    output_dir.mkdir(parents=True, exist_ok=True)
    ranges = clamp_param_ranges(variant.param_ranges)
    rf = write_range_file(output_dir, ranges, f"s{variant.seed}")
    ap = {
        "rep": SCE_DEFAULTS["rep"],
        "ngs": max(M2_NGS_BOUNDS[0], min(M2_NGS_BOUNDS[1], variant.ngs)),
        "kstop": SCE_DEFAULTS["kstop"],
        "peps": SCE_DEFAULTS["peps"],
        "pcento": SCE_DEFAULTS["pcento"],
        "random_seed": variant.seed,
    }
    result: dict[str, Any] = {
        "candidate_type": "sceua",
        "basin_id": basin_id,
        "variant": variant.to_dict(),
        "algorithm_params": ap,
        "param_ranges": ranges,
        "param_range_file": rf,
        "wall_time_s": 0.0,
        "icall": 0,
        "best_params": {},
        "boundary_hits": [],
        "cal_NSE": None, "val_NSE": None, "test_NSE": None,
        "cal_KGE": None, "val_KGE": None, "test_KGE": None,
        "cal_metrics": {}, "val_metrics": {}, "test_metrics": {},
        "success": False,
        "error": None,
        "calibration_dir": "",
    }
    t0 = time.time()
    try:
        cal = calibrate_model(
            basin_ids=[basin_id], model_name="gr4j", algorithm=ALGORITHM,
            train_period=CAL_PERIOD, test_period=TEST_PERIOD,
            algorithm_params=ap, param_range_file=rf, obj_func="NSE",
            output_dir=str(output_dir), data_source="camels_us",
            _workspace=output_dir, _cfg=cfg,
        )
        result["calibration_dir"] = cal.get("calibration_dir", "")
        result["best_params"] = cal.get("best_params", {})
        if not cal.get("success"):
            result["error"] = cal.get("error", "calibration failed")
            return result
        m = _eval_three_periods(result["calibration_dir"], cfg, workspace=output_dir)
        for tag in ("cal", "val", "test"):
            result[f"{tag}_metrics"] = m[tag]
            result[f"{tag}_NSE"] = m[tag].get("NSE")
            result[f"{tag}_KGE"] = m[tag].get("KGE")
        result["success"] = result["val_NSE"] is not None
        if ranges and result["best_params"]:
            result["boundary_hits"] = _detect_boundary_hits(result["best_params"], ranges)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["wall_time_s"] = round(time.time() - t0, 3)

    csv_files = list(output_dir.glob("*sceua.csv"))
    if csv_files:
        with open(csv_files[0], encoding="utf-8") as f:
            result["icall"] = sum(1 for _ in f) - 1
    return result


def eval_direct_params_split(
    *,
    basin_id: str,
    basin_name: str,
    climate_zone: str,
    params: dict[str, Any],
    output_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Direct-guess candidate: evaluate one fixed parameter set (no optimisation)
    on CAL/VAL/TEST. Reuses exp2's proven direct-evaluation directory layout."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clamped = clamp_direct_params(params)
    result: dict[str, Any] = {
        "candidate_type": "direct",
        "basin_id": basin_id,
        "proposed_params": params,
        "evaluated_params": clamped,
        "best_params": clamped,
        "boundary_hits": [],
        "wall_time_s": 0.0,
        "cal_NSE": None, "val_NSE": None, "test_NSE": None,
        "cal_KGE": None, "val_KGE": None, "test_KGE": None,
        "cal_metrics": {}, "val_metrics": {}, "test_metrics": {},
        "success": False,
        "error": None,
        "calibration_dir": "",
    }
    t0 = time.time()
    try:
        exp2c = _load_exp2_common()
        task = exp2c.Task(basin_id=basin_id, basin_name=basin_name,
                          climate_zone=climate_zone, model="gr4j")
        cal_dir = exp2c.prepare_direct_parameter_dir(
            task=task, params=clamped, run_dir=output_dir, cfg=cfg,
        )
        result["calibration_dir"] = str(cal_dir)
        m = _eval_three_periods(str(cal_dir), cfg)
        for tag in ("cal", "val", "test"):
            result[f"{tag}_metrics"] = m[tag]
            result[f"{tag}_NSE"] = m[tag].get("NSE")
            result[f"{tag}_KGE"] = m[tag].get("KGE")
        result["success"] = result["val_NSE"] is not None
        if not result["success"]:
            result["error"] = "direct evaluation returned no VAL metrics"
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["wall_time_s"] = round(time.time() - t0, 3)
    return result
