"""
HydroAgent Tool Module: param_distribution_comparison

Description:
    Compares parameter distributions from two calibration result directories and generates
    boxplot visualizations. Suitable for model comparison, algorithm comparison, or 
    sensitivity analysis across different basins.

Usage:
    param_distribution_comparison(dir1="/path/to/dir1", dir2="/path/to/dir2")
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

def param_distribution_comparison(
    dir1: str,
    dir2: str,
    _workspace: Optional[Path] = None,
    _cfg: Optional[Dict[str, Any]] = None,
    _llm: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Compare parameter distributions from two calibration result directories and generate boxplot visualizations.

    This tool scans the provided directories for calibration result files (typically CSVs),
    extracts numeric parameter values, and creates a comparative boxplot to visualize
    distribution differences between the two sets of results.

    Args:
        dir1 (str): Path to the first calibration result directory.
        dir2 (str): Path to the second calibration result directory.
        _workspace (Optional[Path]): Working directory for saving output files. Defaults to current working dir.
        _cfg (Optional[Dict]): Global configuration dictionary (unused in this tool).
        _llm (Optional[Any]): LLM client instance (unused in this tool).

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation completed successfully.
            - plot_path (str): Path to the generated boxplot image file.
            - stats_summary (str): Text summary of parameter statistics.
            - message (str): Status message or error description.
    """
    logger = logging.getLogger(__name__)
    
    # Initialize return structure
    result = {
        "success": False,
        "plot_path": None,
        "stats_summary": "",
        "message": ""
    }

    try:
        # Lazy import heavy dependencies
        import pandas as pd
        import matplotlib
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # Set non-interactive backend for server environments
        matplotlib.use('Agg')

        # Validate inputs
        path1 = Path(dir1)
        path2 = Path(dir2)

        if not path1.exists():
            raise FileNotFoundError(f"Directory 1 does not exist: {dir1}")
        if not path2.exists():
            raise FileNotFoundError(f"Directory 2 does not exist: {dir2}")

        # Determine output workspace
        out_dir = _workspace if _workspace else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)

        # Helper to extract data from directory
        def extract_param_data(directory: Path) -> pd.DataFrame:
            dfs = []
            # Look for csv files recursively
            pattern = "**/*.csv"
            files = list(directory.glob(pattern))
            
            if not files:
                # Fallback to txt if no csv
                files = list(directory.glob("**/*.txt"))
            
            if not files:
                logger.warning(f"No CSV or TXT files found in {directory}")
                return pd.DataFrame()

            for f in files:
                try:
                    df = pd.read_csv(f)
                    # Filter only numeric columns
                    numeric_df = df.select_dtypes(include=['number'])
                    if not numeric_df.empty:
                        dfs.append(numeric_df)
                except Exception as e:
                    logger.debug(f"Failed to read {f}: {e}")
                    continue
            
            if not dfs:
                return pd.DataFrame()
            
            # Concatenate all found dataframes
            combined = pd.concat(dfs, ignore_index=True)
            return combined

        # Extract data
        data1 = extract_param_data(path1)
        data2 = extract_param_data(path2)

        if data1.empty or data2.empty:
            raise ValueError("No numeric parameter data found in the provided directories.")

        # Identify common columns or union of columns
        all_columns = sorted(set(data1.columns) | set(data2.columns))
        
        records = []
        for col in all_columns:
            # Source 1
            if col in data1.columns:
                vals = data1[col].dropna().tolist()
                for v in vals:
                    records.append({"parameter": col, "value": v, "source": "Dir1"})
            # Source 2
            if col in data2.columns:
                vals = data2[col].dropna().tolist()
                for v in vals:
                    records.append({"parameter": col, "value": v, "source": "Dir2"})
        
        long_df = pd.DataFrame(records)
        
        if long_df.empty:
            raise ValueError("No valid numeric values extracted for plotting.")

        # Calculate basic stats for summary
        stats_lines = []
        for col in all_columns:
            s1 = data1[col].describe() if col in data1.columns else pd.Series(dtype=float)
            s2 = data2[col].describe() if col in data2.columns else pd.Series(dtype=float)
            stats_lines.append(f"\nParameter: {col}\n  Dir1: {s1.to_dict()}\n  Dir2: {s2.to_dict()}")
        stats_text = "".join(stats_lines)

        # Generate Plot
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Map colors
        palette = {"Dir1": "blue", "Dir2": "orange"}
        
        sns.boxplot(
            data=long_df, 
            x="parameter", 
            y="value", 
            hue="source", 
            ax=ax,
            palette=palette
        )
        
        plt.title("Parameter Distribution Comparison")
        plt.xlabel("Parameters")
        plt.ylabel("Values")
        plt.legend(title="Calibration Set")
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Save figure
        filename = "param_dist_comparison.png"
        output_path = out_dir / filename
        fig.savefig(output_path, dpi=150)
        plt.close(fig)

        result["success"] = True
        result["plot_path"] = str(output_path)
        result["stats_summary"] = stats_text[:500] + "..." if len(stats_text) > 500 else stats_text
        result["message"] = f"Successfully generated comparison plot saved to {output_path}"
        logger.info(result["message"])

    except Exception as e:
        result["error"] = str(e)
        result["message"] = str(e)
        logger.error(f"Error in param_distribution_comparison: {e}")

    return result