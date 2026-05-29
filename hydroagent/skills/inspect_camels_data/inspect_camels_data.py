"""
Tool: inspect_camels_data

Safely inspect raw CAMELS dataset variables, units, attributes, and data quality
for a specified basin. Uses the hydrodataset package to load the data.

This tool assumes the hydrodataset API: hydrodataset.Camels(data_dir).load_data(basin_id)
returns an xarray.Dataset. If this API changes, the import path must be verified.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def inspect_camels_data(
    basin_id: str,
    data_dir: str | None = None,
    _workspace: Path | None = None,
    _cfg: dict | None = None,
) -> dict[str, Any]:
    """Inspect a CAMELS basin dataset: variables, units, attributes, and quality checks.

    Loads the dataset for the given basin using hydrodataset, then extracts variable
    metadata, descriptive statistics, checks for negative or anomalous values, and
    computes basic diagnostics.

    Args:
        basin_id: CAMELS gauge ID (e.g., '01013500').
        data_dir: Directory containing CAMELS data. If None, uses _workspace / 'camels_data'.
        _workspace: Working directory (injected by agent).
        _cfg: Global configuration (injected by agent, unused here).

    Returns:
        dict with keys:
            - success: bool
            - basin_id: str
            - variables: list of variable names
            - stats: dict of variable -> dict of descriptive stats
            - negative_checks: dict of variable -> bool/str (True if no negative values)
            - missing_checks: dict of variable -> count of NaN values
            - warnings: list of any warnings found
            - error: str if failure occurred
    """
    # Determine data directory
    if data_dir is None:
        if _workspace is not None:
            data_dir = str(_workspace / "camels_data")
        else:
            data_dir = "./camels_data"

    logger.info("Inspecting CAMELS data for basin %s from %s", basin_id, data_dir)

    # Lazy imports
    try:
        import numpy as np
        from hydrodataset import Camels  # type: ignore[import-untyped]
    except ImportError as e:
        return {
            "success": False,
            "error": f"Required package not installed: {e}. "
                      "Please install hydrodataset and numpy.",
        }

    try:
        # Load the CAMELS dataset
        camels = Camels(data_dir)
        ds = camels.load_data(basin_id)  # type: ignore[attr-defined]
        if ds is None:
            return {
                "success": False,
                "error": f"hydrodataset.load_data('{basin_id}') returned None. "
                         "Check if the basin ID exists and data files are present.",
            }
        if not hasattr(ds, "data_vars") or len(ds.data_vars) == 0:
            return {
                "success": False,
                "error": f"Dataset for basin {basin_id} has no data variables.",
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load CAMELS data for basin {basin_id}: {e}",
        }

    # Variables that by CAMELS convention should never be negative
    NON_NEGATIVE_VARS = {"prcp", "swe", "snow", "tmean", "tmin", "tmax", "obs_runoff"}

    result: dict[str, Any] = {
        "success": True,
        "basin_id": basin_id,
        "variables": [],
        "stats": {},
        "negative_checks": {},
        "missing_checks": {},
        "warnings": [],
    }

    # Process each data variable
    for var_name in ds.data_vars:
        var_da = ds[var_name]
        attrs = var_da.attrs
        result["variables"].append(var_name)

        # Variable metadata
        units = attrs.get("units", "unknown")
        long_name = attrs.get("long_name", var_name)
        logger.debug("Variable: %s (units=%s, long_name=%s)", var_name, units, long_name)

        # Compute descriptive statistics (using .values to force computation)
        values = var_da.values
        # Flatten if necessary
        if values.ndim > 1:
            values_flat = values.ravel()
        else:
            values_flat = values

        # Convert to float, ignoring non-numeric types
        try:
            numeric = np.asarray(values_flat, dtype=float)
        except (ValueError, TypeError):
            result["warnings"].append(
                f"Variable '{var_name}' contains non-numeric data; skipping stats."
            )
            continue

        finite = numeric[~np.isnan(numeric)]
        if len(finite) == 0:
            result["stats"][var_name] = {"count": int(np.isnan(numeric).sum()), "all_nan": True}
            result["missing_checks"][var_name] = int(np.isnan(numeric).sum())
            continue

        stats = {
            "mean": float(np.nanmean(numeric)),
            "std": float(np.nanstd(numeric)),
            "min": float(np.nanmin(numeric)),
            "max": float(np.nanmax(numeric)),
            "count_finite": int(len(finite)),
            "count_missing": int(np.isnan(numeric).sum()),
        }
        result["stats"][var_name] = stats
        result["missing_checks"][var_name] = stats["count_missing"]

        # Check for negative values in non‑negative variables
        if var_name.lower() in {v.lower() for v in NON_NEGATIVE_VARS}:
            has_negative = np.any(finite < 0)
            info = f"no negatives" if not has_negative else f"{int(np.sum(finite < 0))} negative values"
            result["negative_checks"][var_name] = info
            if has_negative:
                result["warnings"].append(
                    f"Variable '{var_name}' has negative values (expected non‑negative)."
                )
        else:
            result["negative_checks"][var_name] = "not checked (not in non‑negative list)"

        # Additional anomaly: check for zero values in variables like precipitation
        if var_name.lower() in {"prcp", "swe", "obs_runoff"}:
            zero_count = int(np.sum(finite == 0))
            if zero_count > 0.5 * len(finite):  # more than 50% zeros
                result["warnings"].append(
                    f"Variable '{var_name}' has {zero_count} zero values ({100*zero_count/len(finite):.1f}%)."
                )

    logger.info(
        "Inspection complete for basin %s: %d variables, %d warnings",
        basin_id,
        len(result["variables"]),
        len(result["warnings"]),
    )
    return result