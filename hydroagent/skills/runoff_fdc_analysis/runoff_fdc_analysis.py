"""
HydroAgent Tool Module: runoff_fdc_analysis

This tool calculates the Runoff Coefficient and Flow Duration Curve (FDC) 
statistics for a given watershed using CAMELS data from hydrodataset.

Author: HydroAgent
Version: 1.0.0
"""

import logging
from pathlib import Path
from typing import Dict, Optional

# Standard library imports are allowed at top level, but external packages 
# must be imported inside the function body per Rule 4.
# We import logging here as it is standard.

logger = logging.getLogger(__name__)


def runoff_fdc_analysis(
    basin_id: str,
    start_date: str,
    end_date: str,
    _workspace: Optional[Path] = None,
    _cfg: Optional[Dict] = None,
    _llm: Optional[object] = None
) -> Dict:
    """
    Calculate Runoff Coefficient and Flow Duration Curve (FDC) statistics for a basin.

    This tool reads streamflow and precipitation data from the CAMELS dataset,
    computes the annual runoff coefficient (Runoff/Precipitation), and generates
    FDC statistics (Q90, Q75, Q50, Q25, Q10) along with a plot.

    Args:
        basin_id (str): The identifier for the basin/watershed (e.g., USGS gage ID).
        start_date (str): Start date for the analysis period in 'YYYY-MM-DD' format.
        end_date (str): End date for the analysis period in 'YYYY-MM-DD' format.
        _workspace (Path | None): Working directory for saving output files (injected).
        _cfg (dict | None): Global configuration dictionary containing data paths (injected).
        _llm (object | None): LLM client instance (not used in this tool).

    Returns:
        dict: A dictionary containing:
            - "success" (bool): Whether the operation completed successfully.
            - "runoff_coefficient" (float): Mean annual runoff coefficient.
            - "fdc_stats" (dict): Dictionary with Q90, Q75, Q50, Q25, Q10 values.
            - "chart_path" (str | None): Path to the generated FDC chart image.
            - "error" (str | None): Error message if success is False.
    """
    # Initialize result structure
    result = {
        "success": False,
        "runoff_coefficient": None,
        "fdc_stats": {},
        "chart_path": None,
        "error": None
    }

    try:
        # Lazy import external packages to avoid startup errors (Rule 4)
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        
        # Import hydrodataset specifically as per example usage (Rule 7)
        from hydrodataset.camels_us import CamelsUs

        logger.info(f"Starting runoff FDC analysis for basin {basin_id}")

        # Retrieve data path from config (Rule 2: _cfg is injected)
        data_path = None
        if _cfg and isinstance(_cfg, dict):
            data_path = _cfg.get("data_path")
        
        if not data_path:
            raise ValueError("Configuration missing 'data_path'. Please configure hydrodataset path.")

        # Initialize CAMELS dataset reader
        ds = CamelsUs(data_path=data_path)

        # Prepare time range list as per example usage
        t_range = [start_date, end_date]

        # Read streamflow data (Rule 7: Follow example usage exactly)
        streamflow_ds = ds.read_ts_xrdataset(
            gage_id_lst=[basin_id],
            t_range=t_range,
            var_lst=["streamflow"]
        )
        
        # Read precipitation data (Rule 7: Follow example usage exactly)
        precip_ds = ds.read_ts_xrdataset(
            gage_id_lst=[basin_id],
            t_range=t_range,
            var_lst=["precipitation"]
        )

        # Convert to DataFrame and reset index as per example usage
        sf_df = streamflow_ds.to_dataframe().reset_index()
        p_df = precip_ds.to_dataframe().reset_index()

        # Validate data presence
        if sf_df.empty or p_df.empty:
            raise ValueError(f"No data returned for basin {basin_id} in range {t_range}.")

        # Ensure 'time' column is datetime for grouping
        sf_df['time'] = pd.to_datetime(sf_df['time'])
        p_df['time'] = pd.to_datetime(p_df['time'])

        # Calculate Annual Runoff Coefficient (Rule 7: Follow example usage logic)
        # Group by year and sum
        annual_runoff = sf_df.groupby(sf_df['time'].dt.year)['streamflow'].sum()
        annual_precip = p_df.groupby(p_df['time'].dt.year)['precipitation'].sum()

        # Align indices to avoid mismatch errors
        common_years = annual_runoff.index.intersection(annual_precip.index)
        if len(common_years) == 0:
            raise ValueError("No overlapping years found between streamflow and precipitation data.")

        annual_runoff = annual_runof.loc[common_years]
        annual_precip = annual_precip.loc[common_years]

        # Calculate ratio, handling division by zero
        runoff_coeff_series = annual_runoff / annual_precip
        # Replace inf/nan resulting from div by zero
        runoff_coeff_series = runoff_coeff_series.replace([np.inf, -np.inf], np.nan)
        
        mean_runoff_coeff = runoff_coeff_series.mean()
        if pd.isna(mean_runoff_coeff):
            raise ValueError("Could not compute valid runoff coefficient (all values NaN).")

        result["runoff_coefficient"] = float(mean_runoff_coeff)
        logger.info(f"Calculated mean runoff coefficient: {mean_runoff_coeff:.4f}")

        # Calculate FDC Statistics (Q90, Q75, Q50, Q25, Q10)
        # Sort streamflow descending for FDC curve logic, but percentile works on raw data
        # Qx means x% of flows are greater than this value.
        # np.percentile sorts internally.
        q_values = np.percentile(sf_df['streamflow'], [90, 75, 50, 25, 10])
        
        fdc_labels = ['Q90', 'Q75', 'Q50', 'Q25', 'Q10']
        fdc_stats = {label: float(val) for label, val in zip(q_values, fdc_labels)}
        result["fdc_stats"] = fdc_stats
        logger.info(f"FDC Stats calculated: {fdc_stats}")

        # Generate FDC Plot
        # Set backend to Agg for headless environments
        plt.switch_backend('Agg')
        
        # Sort streamflow descending for plotting
        sorted_sf = sf_df['streamflow'].sort_values(ascending=False)
        n = len(sorted_sf)
        # Exceedance probability (Rank / (N + 1))
        prob = np.arange(1, n + 1) / (n + 1)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(prob, sorted_sf.values, label='Observed Flow')
        ax.set_xlabel('Exceedance Probability')
        ax.set_ylabel('Streamflow')
        ax.set_title(f'Flow Duration Curve for Basin {basin_id}')
        ax.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()

        # Save chart to workspace if available
        chart_path_str = None
        if _workspace and isinstance(_workspace, Path):
            try:
                _workspace.mkdir(parents=True, exist_ok=True)
                chart_filename = f"{basin_id}_fdc_{start_date}_{end_date}.png"
                chart_path = _workspace / chart_filename
                fig.savefig(chart_path)
                chart_path_str = str(chart_path.absolute())
                logger.info(f"Saved FDC chart to {chart_path_str}")
            except Exception as e:
                logger.warning(f"Failed to save chart: {e}")
        else:
            logger.warning("No workspace provided, skipping chart save.")
        
        result["chart_path"] = chart_path_str
        plt.close(fig)

        # Mark success
        result["success"] = True
        logger.info("Runoff FDC analysis completed successfully.")

    except ImportError as e:
        error_msg = f"Required package not found: {e}. Please ensure hydrodataset is installed."
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Analysis failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result["error"] = error_msg

    return result