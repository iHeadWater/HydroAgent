"""
Author: HydroAgent Team
Date: 2026-02-08
LastEditTime: 2026-02-09
Description: LLM-guided iterative calibration - LLM acts as a "virtual hydrologist"
             that adjusts parameter RANGES between SCE-UA calibration rounds.
             Inspired by: Zhu et al. (2026), GRL, doi:10.1029/2025GL120043
"""

import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Default algorithm params — ensures adaptive scaling always has a baseline
_DEFAULT_ALGO_PARAMS = {
    "SCE_UA": {"rep": 750, "ngs": 200, "kstop": 10},
    "GA": {"pop_size": 50, "n_generations": 50},
}

# Default parameter ranges for supported models
DEFAULT_PARAM_RANGES = {
    "gr4j": {
        "x1": [1.0, 2000.0],    # Production store capacity (mm)
        "x2": [-10.0, 10.0],    # Groundwater exchange coefficient (mm/d)
        "x3": [1.0, 500.0],     # Routing store capacity (mm)
        "x4": [0.5, 10.0],      # Unit hydrograph time base (d)
    },
    "gr5j": {
        "x1": [1.0, 2000.0],    # Production store capacity (mm)
        "x2": [-10.0, 10.0],    # Groundwater exchange coefficient (mm/d)
        "x3": [1.0, 500.0],     # Routing store capacity (mm)
        "x4": [0.5, 10.0],      # Unit hydrograph time base (d)
        "x5": [0.0, 1.0],       # Interception store capacity (mm)
    },
    "gr6j": {
        "x1": [1.0, 2000.0],    # Production store capacity (mm)
        "x2": [-10.0, 10.0],    # Groundwater exchange coefficient (mm/d)
        "x3": [1.0, 500.0],     # Routing store capacity (mm)
        "x4": [0.5, 10.0],      # Unit hydrograph time base (d)
        "x5": [0.0, 1.0],       # Interception store capacity (mm)
        "x6": [0.0, 20.0],      # Exponential store depletion coefficient
    },
    "xaj": {
        "K":  [0.1, 1.0],     # Ratio of potential evapotranspiration to pan evaporation
        "B":  [0.1, 0.4],     # Exponent of soil moisture storage capacity curve
        "IM": [0.01, 0.1],    # Ratio of impervious area to total area
        "UM": [0.0, 20.0],    # Upper soil layer tension water storage capacity (mm)
        "LM": [60.0, 90.0],   # Lower soil layer tension water storage capacity (mm)
        "DM": [60.0, 120.0],  # Deep soil layer tension water storage capacity (mm)
        "C":  [0.0, 0.2],     # Coefficient of deep evapotranspiration
        "SM": [1.0, 100.0],   # Free water storage capacity (mm)
        "EX": [1.0, 1.5],     # Exponent of free water storage capacity curve
        "KI": [0.0, 0.7],     # Outflow coefficient of free water to interflow
        "KG": [0.0, 0.7],     # Outflow coefficient of free water to groundwater
        "CS": [0.0, 1.0],     # Recession constant of surface water
        "L":  [1.0, 10.0],    # Lag time of routing (d)
        "CI": [0.0, 0.9],     # Recession constant of interflow
        "CG": [0.98, 0.998],  # Recession constant of groundwater
    },
}

INITIAL_RANGE_PROPOSER_PROMPT = """You are a senior hydrological model calibration expert.
You will design INITIAL parameter search ranges for {model_name} calibration on basin {basin_id},
based on the basin's measured climate and hydrological attributes.

## Basin: {basin_id}

## Basin Attributes:
{basin_attrs_text}

## Default parameter ranges (full physically-valid space):
{defaults_text}

## Reasoning Principles
Narrow each default range into a more focused, physically reasonable sub-region using the
basin attributes. Reasoning anchors:
  - High aridity (PET/P > 1.0) -> reduce upper bound of soil water storage; expect higher K
  - High frac_snow (>0.1) -> widen lag/recession parameter range (snow accumulation delay)
  - High baseflow_index -> lower CS upper bound; raise CG closer to 1
  - High runoff_ratio (>0.5) -> reduce IM upper bound; lower K upper bound
  - Mediterranean: strong seasonality -> keep K range wide [0.3, 1.0]
  - humid_warm: high ET demand -> K [0.6, 1.0]
  - humid_cold: snow lag -> L [1, 5], CI/CG slightly wider
  - semiarid: low Q/P -> larger DM upper bound; smaller SM upper bound

For XAJ specifically:
  - KI + KG must remain < 0.7 (hard constraint in hydromodel)
  - K range typical [0.2, 1.0]; never go below 0.1
  - CG range typical [0.97, 0.999], near 1 for slow baseflow
  - L range typical [0.5, 5]

For GR4J specifically:
  - x1 (production store): humid [800-2000], arid [100-800]
  - x4 (UH lag time): snow basins [2-5], fast-response [0.5-2]
  - x2 (groundwater exchange): typically [-5, 5]; humid basins may need negative range

## Response Format
Return ALL parameters in one JSON dict. Each value is [lower, upper], must be a sub-range
of the default and lower < upper.
```json
{{"K": [0.3, 0.9], "B": [0.15, 0.35], "IM": [0.01, 0.08], "...": [..., ...]}}
```

After the JSON block, briefly explain (1 sentence each) the key narrowing decisions for
parameters where you deviated significantly from defaults."""


RANGE_ADVISOR_PROMPT = """You are a senior hydrological model calibration expert.
Your role is to analyze SCE-UA calibration results and recommend adjustments for the next round.
You may adjust BOTH parameter ranges AND optimization algorithm parameters.

## Model: {model_name}

## Basin: {basin_id}

## Basin Attributes:
{basin_attrs_text}

## Current Parameter Ranges:
{param_ranges_text}

## Current SCE-UA Algorithm Parameters:
{algo_params_text}

## Your Task:
1. Check for boundary effects: if a parameter value is within 5% of its range boundary, expand that boundary.
2. If NSE is poor but NO boundary hits, the optimizer budget may be insufficient — recommend increasing rep/ngs.
3. If NSE >= target, stop (no adjustment needed).

## Algorithm Parameter Guidance:
- rep (total evaluations): Default 750. If NSE < 0.4 and no boundary hits → try 1500-2000.
- ngs (complexes): Rule of thumb = 2 × n_params. GR4J→8 min; use 100-300 for quality. If NSE very low → try increasing by 50-100.
- kstop: Leave as default (10) unless results oscillate.

## Response Format:
Include ONLY fields that need changing. Examples:

Parameter range change only:
```json
{{"x1": [200, 1500], "x4": [0.5, 15.0]}}
```

Algorithm params change only (ranges are fine):
```json
{{"no_change": true, "algorithm_params": {{"rep": 1500, "ngs": 300}}}}
```

Both ranges and algorithm params:
```json
{{"x1": [200, 1500], "algorithm_params": {{"rep": 1500, "ngs": 300}}}}
```

No adjustment needed at all:
```json
{{"no_change": true}}
```

Always explain your reasoning after the JSON block."""


def llm_calibrate(
    basin_ids: list[str],
    model_name: str = "gr4j",
    max_rounds: int = 5,
    nse_target: float = 0.75,
    param_ranges: dict | None = None,
    algorithm: str = "SCE_UA",
    algorithm_params: dict | None = None,
    train_period: list[str] | None = None,
    test_period: list[str] | None = None,
    output_dir: str | None = None,
    _workspace: Path | None = None,
    _cfg: dict | None = None,
    _llm: object | None = None,
    _ui=None,
) -> dict:
    """LLM-guided iterative calibration using SCE-UA as the optimizer.

    Each round: SCE-UA optimizes within current parameter ranges → LLM analyzes
    results and adjusts ranges → next round. Typically converges in 2-3 rounds.

    Args:
        basin_ids: CAMELS basin ID list
        model_name: Hydrological model name ("gr4j", "xaj", "gr5j", "gr6j")
        max_rounds: Maximum number of LLM-guided rounds (each runs a full SCE-UA)
        nse_target: Target NSE value for early stopping
        param_ranges: Initial parameter ranges as a JSON OBJECT (dict), e.g.
            {"K": [0.1, 1.0], "B": [0.1, 0.4]}. Do NOT pass as a string.
            If omitted, uses default ranges for the model.
        algorithm: Calibration algorithm, default "SCE_UA"
        algorithm_params: Algorithm overrides as a JSON object, e.g. {"rep": 500, "ngs": 200}
        train_period: Training period ["YYYY-MM-DD", "YYYY-MM-DD"]
        test_period: Testing period ["YYYY-MM-DD", "YYYY-MM-DD"]
        output_dir: Directory to save calibration results (optional)

    Returns:
        {"best_params": {...}, "best_nse": float, "rounds": int, "history": [...]}
    """
    if _llm is None:
        return {"error": "LLM client required for LLM calibration", "success": False}

    # Validate param_ranges: must be a dict mapping param_name -> [lo, hi]
    # Agent sometimes passes a JSON string or list by mistake — catch it early.
    # output_dir maps to _workspace (public alias for the internal parameter)
    if output_dir is not None and _workspace is None:
        _workspace = Path(output_dir)

    if param_ranges is not None and not isinstance(param_ranges, dict):
        return {
            "error": (
                f"param_ranges must be a dict like {{'K': [0.1, 1.0], ...}}, "
                f"got {type(param_ranges).__name__}. "
                "Pass the dict directly, not as a JSON string."
            ),
            "success": False,
        }

    defaults_for_model = DEFAULT_PARAM_RANGES.get(model_name, {})
    if not defaults_for_model:
        return {"error": f"No default parameter ranges for model {model_name}", "success": False}

    # ── Basin-aware mode: fetch basin attributes & let LLM propose initial ranges ──
    # Only triggers when caller did not pass explicit param_ranges.
    primary_basin = basin_ids[0] if basin_ids else ""
    basin_attrs: dict | None = None
    used_basin_aware_init = False

    if primary_basin:
        try:
            from hydroagent.tools.basin_attrs import get_basin_attributes
            attrs = get_basin_attributes(
                basin_id=primary_basin,
                data_source=(_cfg or {}).get("dataset", "camels_us"),
                _cfg=_cfg,
            )
            if attrs.get("success"):
                basin_attrs = attrs
                logger.info(
                    f"[basin-aware] Fetched attributes for {primary_basin}: "
                    f"aridity={attrs.get('aridity')}, climate={attrs.get('climate_zone')}, "
                    f"frac_snow={attrs.get('frac_snow')}"
                )
            else:
                logger.warning(
                    f"[basin-aware] Could not fetch attributes for {primary_basin}: "
                    f"{attrs.get('error', 'unknown error')}"
                )
        except Exception as e:
            logger.warning(f"[basin-aware] Exception fetching attributes: {e}")

    if param_ranges is None and basin_attrs and _llm:
        proposed = _propose_initial_ranges_from_attributes(
            llm=_llm,
            model_name=model_name,
            basin_id=primary_basin,
            basin_attributes=basin_attrs,
            defaults=defaults_for_model,
        )
        if proposed:
            current_ranges = proposed
            used_basin_aware_init = True
            # Persist the LLM-proposed initial ranges to disk for transparency / audit
            if _workspace:
                _initial_yaml = Path(_workspace) / "_llm_param_ranges_round0_initial.yaml"
                _initial_yaml.parent.mkdir(parents=True, exist_ok=True)
                _initial_yaml.write_text(
                    yaml.dump(
                        {model_name: {
                            "param_name": list(current_ranges.keys()),
                            "param_range": {k: v for k, v in current_ranges.items()},
                            "_basin_attributes_used": {
                                k: basin_attrs.get(k) for k in
                                ["aridity", "runoff_ratio", "baseflow_index",
                                 "frac_snow", "climate_zone"]
                                if basin_attrs.get(k) is not None
                            },
                        }},
                        default_flow_style=False, allow_unicode=True,
                    ),
                    encoding="utf-8",
                )
                logger.info(f"[basin-aware] Initial LLM-proposed ranges saved: {_initial_yaml}")
        else:
            logger.warning(f"[basin-aware] Initial proposal failed, falling back to defaults")
            current_ranges = dict(defaults_for_model)
    else:
        current_ranges = dict(param_ranges or defaults_for_model)
        if param_ranges is None:
            logger.info("[basin-aware] No basin attributes available; using default ranges")

    from hydroagent.skills.calibration.calibrate import calibrate_model
    from hydroagent.skills.evaluation.evaluate import evaluate_model

    history = []
    best_nse = -999.0
    best_params = None
    best_result = None
    _fixed_params: set[str] = set()          # params locked after convergence detection

    # Resolve base algorithm params once so we can adapt per round.
    # If not explicitly provided, fall back to config defaults so the adaptive
    # scaling has a concrete baseline to work from (e.g. rep=750 -> 562 -> 450 -> 375).
    if isinstance(algorithm_params, dict) and algorithm_params:
        _base_algo_params = dict(algorithm_params)
    else:
        if algorithm_params is not None and not isinstance(algorithm_params, dict):
            logger.warning(
                f"algorithm_params must be a dict, got {type(algorithm_params).__name__}: "
                f"{algorithm_params!r}. Falling back to config defaults."
            )
        _base_algo_params = dict(
            (_cfg or {}).get("algorithms", {}).get(algorithm, {})
        )
    # Ensure baseline always has values so adaptive scaling has something to work with
    if not _base_algo_params:
        _base_algo_params = dict(_DEFAULT_ALGO_PARAMS.get(algorithm, {}))

    for round_idx in range(max_rounds):
        logger.info(f"=== LLM Calibration Round {round_idx + 1}/{max_rounds} ===")

        # Write current ranges to YAML (hydromodel format) for this round
        param_range_file = None
        if round_idx > 0:
            range_dir = _workspace or Path(".")
            param_range_file = str(range_dir / f"_llm_param_ranges_round{round_idx}.yaml")
            param_names = list(current_ranges.keys())
            range_yaml = {
                model_name: {
                    "param_name": param_names,
                    "param_range": {k: v for k, v in current_ranges.items()},
                }
            }
            with open(param_range_file, "w") as f:
                yaml.dump(range_yaml, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"Custom param ranges written to {param_range_file}")

        # Adaptive budget: round 1 uses full budget; later rounds scale down.
        # Later rounds have narrower ranges so fewer evaluations are needed to
        # find the optimum — this saves compute without sacrificing quality.
        round_algo_params = _adaptive_algo_params(
            _base_algo_params, algorithm, round_idx, max_rounds
        )

        # Vary random seed per round so SCE-UA explores different starting points.
        # hydromodel SCE-UA defaults to random_seed=1234 every run — without this fix,
        # same seed + same ranges = identical result every round, making multi-round
        # calibration useless.
        if algorithm == "SCE_UA" and "random_seed" not in round_algo_params:
            round_algo_params = dict(round_algo_params)
            round_algo_params["random_seed"] = 1234 + round_idx * 137
        if round_algo_params != _base_algo_params:
            logger.info(
                f"Round {round_idx + 1}: adaptive budget "
                f"{_base_algo_params} -> {round_algo_params}"
            )

        # Run calibration (pass _ui so progress events are emitted each round)
        result = calibrate_model(
            basin_ids=basin_ids,
            model_name=model_name,
            algorithm=algorithm,
            train_period=train_period,
            test_period=test_period,
            algorithm_params=round_algo_params if round_algo_params else None,
            param_range_file=param_range_file,
            output_dir=str(((_workspace or Path("results")) / f"llm_round_{round_idx}")),
            _workspace=_workspace,
            _cfg=_cfg,
            _ui=_ui,
            _round_label=f"Round {round_idx + 1}/{max_rounds}",
        )

        if not result.get("success"):
            logger.warning(f"Round {round_idx + 1} calibration failed: {result.get('error')}")
            history.append({
                "round": round_idx + 1,
                "error": result.get("error"),
                "diagnosis": result.get("diagnosis", {}),
            })
            continue

        round_params = result.get("best_params", {})
        cal_dir = result.get("calibration_dir", "")

        # Evaluate on training period to get NSE — calibrate_model only returns params
        train_eval = evaluate_model(
            calibration_dir=cal_dir,
            eval_period=result.get("train_period"),
            _cfg=_cfg,
        )
        train_metrics = train_eval.get("metrics", {}) if train_eval.get("success") else {}
        nse = train_metrics.get("NSE", -999.0)
        if not isinstance(nse, float):
            nse = -999.0

        # Detect which parameters are near their boundaries (<5% of range span)
        boundary_hits = _detect_boundary_hits(round_params, current_ranges)

        # Detect converged (stable) params: value changed < 2% of span vs prev round
        # Only fix when current round NSE is near the historical best (>= best * 0.97)
        # to avoid locking params on a regressed round (e.g., best=0.72, current=0.686).
        newly_fixed: list[str] = []
        nse_near_best = (
            isinstance(nse, float) and nse > 0.5
            and (best_nse <= -998.0 or nse >= best_nse * 0.97)
        )
        if round_idx >= 1 and history and nse_near_best:
            prev_params = history[-1].get("best_params", {})
            for pname, pval in round_params.items():
                if pname in _fixed_params or pname not in current_ranges:
                    continue
                prev_val = prev_params.get(pname)
                if prev_val is None:
                    continue
                lo, hi = current_ranges[pname]
                span = hi - lo
                if span > 0 and abs(pval - prev_val) / span < 0.02:
                    # Not hitting boundary and stable across rounds: fix it
                    if not any(h["param"] == pname for h in boundary_hits):
                        _fixed_params.add(pname)
                        newly_fixed.append(pname)
                        # Narrow range to ±1% of span around current value
                        margin = max(span * 0.01, 1e-6)
                        current_ranges[pname] = [
                            max(lo, pval - margin),
                            min(hi, pval + margin),
                        ]
                        logger.info(f"Fixed converged param {pname}={pval:.4f}, range -> {current_ranges[pname]}")

        round_record = {
            "round": round_idx + 1,
            "param_ranges": dict(current_ranges),
            "best_params": round_params,
            "train_metrics": train_metrics,
            "nse": nse,
            "boundary_hits": boundary_hits,
            "calibration_dir": cal_dir,
            "fixed_params": newly_fixed,   # params fixed THIS round
        }
        history.append(round_record)

        if nse > best_nse:
            best_nse = nse
            best_params = dict(round_params)
            best_result = result

        logger.info(
            f"Round {round_idx + 1}: train NSE={nse:.4f} (best={best_nse:.4f}), "
            f"boundary_hits={[h['param'] for h in boundary_hits]}"
        )

        # Early stopping if target reached
        if best_nse >= nse_target:
            logger.info(f"Target NSE {nse_target} reached at round {round_idx + 1}")
            break

        # Last round - no need to ask LLM for adjustments
        if round_idx >= max_rounds - 1:
            break

        # Ask LLM to analyze results and suggest adjustments (ranges + algo params)
        # Pass basin attributes so LLM can reason with physical context, not just optimizer output
        adj = _ask_llm_for_adjustments(
            _llm, model_name, current_ranges, round_params,
            train_metrics, nse_target, round_idx + 1,
            current_algo_params=round_algo_params,
            basin_id=primary_basin,
            basin_attributes=basin_attrs,
        )

        if adj is None:
            logger.info("LLM suggests no further adjustment needed")
            break

        new_ranges = adj.get("ranges")
        new_algo_params = adj.get("algo_params")

        if new_ranges:
            current_ranges = new_ranges
            logger.info(f"LLM adjusted ranges: {current_ranges}")
        if new_algo_params:
            _base_algo_params.update(new_algo_params)
            logger.info(f"LLM adjusted algorithm params: {new_algo_params}")

    final_boundary_hits = _detect_boundary_hits(
        best_params or {}, current_ranges
    )
    # Aggregate fixed_params_by_round from history records
    fixed_params_by_round = {
        h["round"]: h["fixed_params"]
        for h in history
        if h.get("fixed_params")
    }
    return {
        "best_params": best_params or {},
        "best_nse": best_nse if best_nse > -998.0 else None,
        "rounds": len(history),
        "nse_history": [h.get("nse") for h in history],  # compact, preserved in summary
        "history": history,
        "final_boundary_hits": final_boundary_hits,
        "fixed_params_by_round": fixed_params_by_round,
        "model_name": model_name,
        "basin_ids": basin_ids,
        "calibration_dir": best_result.get("calibration_dir", "") if best_result else "",
        "success": best_nse > -998.0,
        # Basin-aware mode evidence (for paper ablation / verification)
        "basin_aware_init": used_basin_aware_init,
        "basin_attributes_used": (
            {k: basin_attrs.get(k) for k in
             ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
             if basin_attrs and basin_attrs.get(k) is not None}
            if basin_attrs else None
        ),
        "observation_hint": (
            f"Each round's boundary_hits shows which params hit their range limits. "
            f"final_boundary_hits={final_boundary_hits}. "
            "If any param still hits boundary after all rounds, consider expanding ranges further."
        ),
    }


def _adaptive_algo_params(base: dict, algorithm: str, round_idx: int, max_rounds: int) -> dict:
    """Scale down SCE-UA/GA budget for later rounds.

    Round 1 runs at full budget (wide global search).
    Subsequent rounds run at reduced budget because the parameter range
    has been narrowed by the LLM advisor, requiring fewer evaluations
    to find the optimum within the tighter space.

    Scale schedule: round 1=100%, round 2=75%, round 3=60%, round 4+=50%.
    """
    if round_idx == 0 or algorithm not in ("SCE_UA", "GA"):
        return base

    scales = [1.0, 0.75, 0.60, 0.50]
    scale = scales[min(round_idx, len(scales) - 1)]

    result = dict(base)
    if algorithm == "SCE_UA":
        for key in ("rep", "ngs", "kstop"):
            if key in result:
                result[key] = max(50, int(result[key] * scale))
    elif algorithm == "GA":
        for key in ("pop_size", "n_generations"):
            if key in result:
                result[key] = max(10, int(result[key] * scale))
    return result


def _detect_boundary_hits(params: dict, ranges: dict, threshold_pct: float = 5.0) -> list:
    """Return list of params that are within threshold_pct% of their range boundary."""
    hits = []
    for name, value in params.items():
        if name not in ranges:
            continue
        lo, hi = ranges[name]
        span = hi - lo
        if span <= 0:
            continue
        lo_pct = (value - lo) / span * 100
        hi_pct = (hi - value) / span * 100
        if lo_pct < threshold_pct:
            hits.append({"param": name, "boundary": "lower",
                         "value": value, "bound": lo, "pct_from_bound": round(lo_pct, 1)})
        elif hi_pct < threshold_pct:
            hits.append({"param": name, "boundary": "upper",
                         "value": value, "bound": hi, "pct_from_bound": round(hi_pct, 1)})
    return hits


def _format_basin_attrs(basin_attributes: dict | None) -> str:
    """Format basin attributes for LLM prompt injection."""
    if not basin_attributes or not basin_attributes.get("success", True):
        return "  (no basin attributes available)"
    keys = ["aridity", "runoff_ratio", "baseflow_index", "frac_snow",
            "p_mean", "pet_mean", "slope_mean", "area_km2", "climate_zone"]
    lines = []
    for k in keys:
        v = basin_attributes.get(k)
        if v is not None:
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines) if lines else "  (no recognized attributes)"


def _parse_initial_ranges(text: str, defaults: dict) -> dict | None:
    """Parse a JSON dict of {param: [lo, hi]} ranges from LLM response."""
    import re as _re
    match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
    if not match:
        match = _re.search(r"(\{[^{}]+\})", text)
    if not match:
        return None
    try:
        ranges = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(ranges, dict):
        return None
    validated: dict = {}
    for name, val in ranges.items():
        if isinstance(val, list) and len(val) == 2 \
           and all(isinstance(x, (int, float)) for x in val) and val[0] < val[1]:
            validated[name] = [float(val[0]), float(val[1])]
    # Fill any missing keys with defaults so SCE-UA has all parameters
    for k, v in defaults.items():
        validated.setdefault(k, list(v))
    return validated if validated else None


def _propose_initial_ranges_from_attributes(
    llm, model_name: str, basin_id: str, basin_attributes: dict, defaults: dict
) -> dict | None:
    """Ask LLM to design initial parameter ranges based on basin attributes."""
    attrs_text = _format_basin_attrs(basin_attributes)
    defaults_text = "\n".join(
        f"  - {name}: [{r[0]}, {r[1]}]" for name, r in defaults.items()
    )
    system_prompt = INITIAL_RANGE_PROPOSER_PROMPT.format(
        model_name=model_name,
        basin_id=basin_id,
        basin_attrs_text=attrs_text,
        defaults_text=defaults_text,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
         f"Design basin-aware initial parameter ranges for {model_name} on basin {basin_id}."},
    ]
    try:
        response = llm.chat(messages)
    except Exception as e:
        logger.warning(f"[basin-aware] Initial-range LLM call failed: {e}")
        return None
    parsed = _parse_initial_ranges(response.text, defaults)
    if parsed:
        logger.info(f"[basin-aware] LLM proposed initial ranges for {basin_id}: "
                    f"{ {k: v for k, v in list(parsed.items())[:3]} } ...")
    return parsed


def _ask_llm_for_adjustments(
    llm, model_name, current_ranges, best_params, metrics, nse_target, round_num,
    current_algo_params: dict | None = None,
    basin_id: str = "",
    basin_attributes: dict | None = None,
) -> dict | None:
    """Ask LLM to analyze results and suggest adjustments to parameter ranges and/or algorithm params.

    Returns {"ranges": dict|None, "algo_params": dict|None}, or None if no change needed.
    """
    ranges_text = "\n".join(
        f"  - {name}: [{r[0]}, {r[1]}]" for name, r in current_ranges.items()
    )
    algo_text = "\n".join(
        f"  - {k}: {v}" for k, v in (current_algo_params or {}).items()
    ) or "  (using defaults)"

    system_prompt = RANGE_ADVISOR_PROMPT.format(
        model_name=model_name,
        basin_id=basin_id or "(unknown)",
        basin_attrs_text=_format_basin_attrs(basin_attributes),
        param_ranges_text=ranges_text,
        algo_params_text=algo_text,
    )

    # Build boundary analysis for context
    boundary_info = []
    for name, value in best_params.items():
        if name in current_ranges:
            lo, hi = current_ranges[name]
            span = hi - lo
            if span > 0:
                lo_pct = (value - lo) / span * 100
                hi_pct = (hi - value) / span * 100
                status = ""
                if lo_pct < 5:
                    status = " ** HITS LOWER BOUND **"
                elif hi_pct < 5:
                    status = " ** HITS UPPER BOUND **"
                boundary_info.append(
                    f"  {name} = {value:.4f}  (range [{lo}, {hi}], "
                    f"at {lo_pct:.1f}% from lower){status}"
                )

    nse_val = metrics.get("NSE", "N/A")
    no_boundary = not any("HITS" in line for line in boundary_info)
    extra_hint = ""
    if no_boundary and isinstance(nse_val, float) and nse_val < nse_target:
        extra_hint = (
            "\nNo boundary hits detected but NSE is still below target. "
            "Consider recommending larger rep or ngs to improve optimizer coverage."
        )

    user_msg = (
        f"Round {round_num} SCE-UA calibration results:\n"
        f"  NSE = {nse_val}\n"
        f"  RMSE = {metrics.get('RMSE', 'N/A')}\n"
        f"  KGE = {metrics.get('KGE', 'N/A')}\n"
        f"  Target NSE = {nse_target}\n\n"
        f"Best parameters and boundary analysis:\n"
        + "\n".join(boundary_info)
        + extra_hint + "\n\n"
        "What adjustments do you recommend for the next calibration round?"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    response = llm.chat(messages)
    return _parse_adjustments(response.text, current_ranges, model_name)


def _parse_adjustments(text: str, current_ranges: dict,
                        model_name: str | None = None) -> dict | None:
    """Parse parameter range and/or algorithm param adjustments from LLM response.

    Returns {"ranges": new_ranges|None, "algo_params": dict|None},
    or None if no adjustment at all.
    """
    import re

    def _extract_data(raw_text):
        # Try code-fenced JSON blocks first
        json_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        matches = re.findall(json_pattern, raw_text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        # Try parsing the whole text (for test/direct JSON input)
        try:
            stripped = raw_text.strip()
            if stripped.startswith("{"):
                return json.loads(stripped)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        # Fallback: find outermost {...} block (handles nested braces)
        start = raw_text.find("{")
        if start >= 0:
            depth = 0
            for i, ch in enumerate(raw_text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(raw_text[start:i + 1])
                        except (json.JSONDecodeError, ValueError, TypeError):
                            break
        return None

    data = _extract_data(text)
    if not isinstance(data, dict):
        return None

    no_range_change = bool(data.get("no_change"))
    algo_params_raw = data.get("algorithm_params")

    # Parse new parameter ranges
    new_ranges = None
    if not no_range_change:
        candidate = dict(current_ranges)
        changed = False
        for name, bounds in data.items():
            if name in ("no_change", "algorithm_params"):
                continue
            if name in current_ranges and isinstance(bounds, list) and len(bounds) == 2:
                try:
                    lo, hi = float(bounds[0]), float(bounds[1])
                except (ValueError, TypeError):
                    logger.warning("_parse_adjustments: cannot parse bounds for %s: %s", name, bounds)
                    continue
                if lo >= hi:
                    logger.warning("_parse_adjustments: invalid range for %s: [%s, %s] (lo >= hi)", name, lo, hi)
                    continue
                # Clamp to physical model boundaries so LLM cannot suggest out-of-spec ranges
                phys = DEFAULT_PARAM_RANGES.get(model_name or "", {}).get(name)
                if phys:
                    phys_lo, phys_hi = phys[0], phys[1]
                    if lo < phys_lo or hi > phys_hi:
                        logger.warning(
                            "_parse_adjustments: clamping %s [%.4f, %.4f] to physical bounds [%.4f, %.4f]",
                            name, lo, hi, phys_lo, phys_hi,
                        )
                        lo = max(lo, phys_lo)
                        hi = min(hi, phys_hi)
                        if lo >= hi:
                            continue
                candidate[name] = [lo, hi]
                changed = True
        if changed:
            new_ranges = candidate

    # Parse algorithm param suggestions
    new_algo_params = None
    if isinstance(algo_params_raw, dict) and algo_params_raw:
        parsed_algo = {}
        for k, v in algo_params_raw.items():
            try:
                parsed_algo[k] = int(v) if isinstance(v, (int, float)) else v
            except (ValueError, TypeError):
                pass
        if parsed_algo:
            new_algo_params = parsed_algo

    if new_ranges is None and new_algo_params is None:
        return None

    return {"ranges": new_ranges, "algo_params": new_algo_params}


llm_calibrate.__agent_hint__ = (
    "LLM-guided iterative calibration: each round runs SCE-UA with a DIFFERENT random seed, "
    "LLM analyzes results and adjusts BOTH parameter ranges AND algorithm params (rep/ngs). "
    "Random seed varies automatically per round to avoid identical results. "
    "If NSE is low with no boundary hits, LLM recommends increasing rep/ngs automatically. "
    "Pass algorithm_params={'rep': 1500, 'ngs': 300} for difficult basins (semiarid, negative NSE). "
    "Returns best_nse and best_params directly. Still call evaluate_model(calibration_dir=...) for test period."
)
