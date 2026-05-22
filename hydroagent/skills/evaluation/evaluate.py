"""
Author: HydroAgent Team
Date: 2026-02-08
Description: Model evaluation tool - routes to the appropriate PackageAdapter.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def evaluate_model(
    calibration_dir: str,
    eval_period: list[str] | None = None,
    output_subdir: str | None = None,
    _workspace: Path | None = None,
    _cfg: dict | None = None,
) -> dict:
    """Evaluate a calibrated hydrological model on any time period.

    Call this after calibrate_model to get NSE/KGE/RMSE metrics. Can be called
    multiple times with different eval_period to get both train and test metrics.

    When to use: immediately after calibrate_model; also when calibration_dir already
        exists on disk and you only need to (re-)compute metrics.
    When NOT to use: if calibration_dir does not exist yet — run calibrate_model first.

    Args:
        calibration_dir: Absolute path to calibration output directory.
            Use the exact value returned by calibrate_model(), do not construct manually.
        eval_period: Evaluation period ["YYYY-MM-DD", "YYYY-MM-DD"].
            If None, uses the test_period saved in calibration_config.yaml (recommended
            for the final test evaluation).
            Pass the train period explicitly to get training metrics.
        output_subdir: Subdirectory name inside calibration_dir for saving results.
            Auto-detected as "train_metrics" or "test_metrics" when left as None.

    Returns:
        {
          "success": bool,
          "metrics": {
            "NSE": float,   # Nash-Sutcliffe Efficiency, range (-inf, 1], higher is better
            "KGE": float,   # Kling-Gupta Efficiency, range (-inf, 1]
            "RMSE": float,  # Root Mean Square Error (same unit as streamflow)
          },
          "eval_period": list[str],   # actual period evaluated
          "metrics_dir": str,         # directory where metrics files are saved
          "output_files": list[str],  # e.g. ["metrics.csv", "hydrograph.png"]
        }

    Example:
        >>> # Standard pattern: train then test evaluation
        >>> cal = calibrate_model(["12025000"], "gr4j")
        >>> train = evaluate_model(
        ...     cal["calibration_dir"],
        ...     eval_period=["2000-01-01", "2009-12-31"],
        ... )
        >>> test = evaluate_model(cal["calibration_dir"])  # None -> test period from config
        >>> print(f"Train NSE={train['metrics']['NSE']:.3f}, Test NSE={test['metrics']['NSE']:.3f}")
    """
    from hydroagent.adapters import get_adapter

    # data_source/model_name not needed here since hydromodel adapter handles all calibration dirs
    # Defensive: flatten LLM-wrapped nested period [["start","end"]] -> ["start","end"].
    if (isinstance(eval_period, list) and len(eval_period) == 1
            and isinstance(eval_period[0], list)):
        eval_period = eval_period[0]

    adapter = get_adapter("camels_us", "")
    return adapter.execute("evaluate",
        workspace=_workspace or Path("."),
        calibration_dir=calibration_dir,
        eval_period=eval_period,
        output_subdir=output_subdir,
        _workspace=_workspace,
        _cfg=_cfg,
    )


evaluate_model.__agent_hint__ = (
    "Requires calibration_dir from calibrate_model. "
    "eval_period=None uses the test period from calibration config (typical for final evaluation). "
    "Call twice -- once with train period, once with None -- to get both train and test metrics."
)
