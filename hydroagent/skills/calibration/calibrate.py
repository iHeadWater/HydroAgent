"""
Author: HydroAgent Team
Date: 2026-02-08
Description: Model calibration tool - routes to the appropriate PackageAdapter.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def calibrate_model(
    basin_ids: list[str],
    model_name: str = "xaj",
    algorithm: str = "SCE_UA",
    train_period: list[str] | None = None,
    test_period: list[str] | None = None,
    algorithm_params: dict | None = None,
    param_range_file: str | None = None,
    obj_func: str | None = None,
    output_dir: str | None = None,
    data_source: str = "camels_us",
    _workspace: Path | None = None,
    _cfg: dict | None = None,
    _ui=None,
    _round_label: str = "",
) -> dict:
    """Calibrate a hydrological model using the specified algorithm.

    Calls the appropriate package adapter (e.g. hydromodel) for parameter
    optimization (SCE-UA, GA, scipy). Results are saved to the output directory.

    When to use: when you need to find optimal parameters for a model-basin combination.
    When NOT to use: if you already have a calibration_dir and only need metrics —
        call evaluate_model(calibration_dir) directly instead.

    IMPORTANT: this tool returns parameters only, NOT metrics (NSE/KGE/RMSE).
    Always follow up with evaluate_model() to obtain performance metrics.

    Args:
        basin_ids: CAMELS basin ID list, e.g. ["12025000"]. 8-digit strings.
        model_name: Model name. One of "gr4j", "xaj", "gr5j", "gr6j".
            Default "xaj". Use "gr4j" for temperate/humid basins (4 params, fast).
        algorithm: Optimization algorithm. One of "SCE_UA" (recommended), "GA", "scipy".
        train_period: Training period ["YYYY-MM-DD", "YYYY-MM-DD"].
            Default: ["2000-01-01", "2009-12-31"].
        test_period: Testing period ["YYYY-MM-DD", "YYYY-MM-DD"].
            Default: ["2010-01-01", "2014-12-31"].
        algorithm_params: Dict of algorithm parameter overrides. Must be a dict, NOT a string.
            Pass None to use project defaults (recommended for most cases).
            SCE_UA keys: rep (total evaluations), ngs (complexes), kstop (convergence steps).
              e.g. {"rep": 200, "ngs": 50} for a quick test, {"rep": 1500, "ngs": 300} for
              high-quality results. Default: rep=750, ngs=200.
            GA keys: pop_size, n_generations. e.g. {"pop_size": 20, "n_generations": 10}.
            scipy keys: method ("SLSQP"/"L-BFGS-B"), max_iterations.
        param_range_file: Path to custom parameter range YAML. Use when default bounds
            are too narrow (e.g., when previous calibration hit a boundary).
        obj_func: Objective function override. One of "NSE", "KGE", "LOGNSE", "RMSE".
            Takes precedence over the configured default objective.
        output_dir: Output directory for results. Defaults to workspace/results/.
        data_source: Dataset type. One of "camels_us" (default), "camels_gb", "selfmade".

    Returns:
        {
          "success": bool,
          "best_params": dict,        # e.g. {"x1": 342.5, "x2": 0.8, "x3": 47.2, "x4": 1.3}
          "calibration_dir": str,     # absolute path; pass to evaluate_model()
          "output_files": list[str],  # list of saved filenames
          "train_period": list[str],
          "test_period": list[str],
        }

    Example:
        >>> result = calibrate_model(
        ...     basin_ids=["12025000"],
        ...     model_name="gr4j",
        ...     algorithm="SCE_UA",
        ...     train_period=["2000-01-01", "2009-12-31"],
        ...     test_period=["2010-01-01", "2014-12-31"],
        ... )
        >>> cal_dir = result["calibration_dir"]
        >>> # Then evaluate:
        >>> train_metrics = evaluate_model(cal_dir, eval_period=["2000-01-01", "2009-12-31"])
        >>> test_metrics  = evaluate_model(cal_dir)   # None -> uses saved test_period
    """
    from hydroagent.adapters import get_adapter

    adapter = get_adapter(data_source, model_name)
    return adapter.execute("calibrate",
        workspace=_workspace or Path("."),
        model_name=model_name,
        algorithm=algorithm,
        basin_ids=basin_ids,
        train_period=train_period,
        test_period=test_period,
        algorithm_params=algorithm_params,
        param_range_file=param_range_file,
        obj_func=obj_func,
        output_dir=output_dir,
        _cfg=_cfg,
        _ui=_ui,
        _round_label=_round_label,
    )


calibrate_model.__agent_hint__ = (
    "Returns calibration_dir and best_params -- NO metrics (NSE/KGE). "
    "Must call evaluate_model(calibration_dir=...) separately to get metrics. "
    "If NSE is low, check if params hit boundaries via read_file(calibration_results.json)."
)
