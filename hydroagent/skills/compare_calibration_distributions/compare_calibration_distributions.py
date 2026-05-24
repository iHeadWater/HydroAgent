"""
HydroAgent Tool Module: compare_calibration_distributions

Skill: compare_calibration_distributions
Description: 对比两个水文模型率定结果目录的参数分布，生成箱线图可视化。
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Note: External packages are imported lazily inside the function to avoid startup errors.


def compare_calibration_distributions(
    calibration_dir_1: str,
    calibration_dir_2: str,
    _workspace: Optional[Path] = None,
    _cfg: Optional[Dict[str, Any]] = None,
    _llm: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Compare parameter distributions from two hydrological model calibration directories.

    Reads calibration_results.json from both directories, extracts parameter values
    (assuming a list of runs with parameter dictionaries), calculates statistics,
    and generates a side-by-side box plot visualization.

    Args:
        calibration_dir_1 (str): Path to the first calibration directory containing calibration_results.json.
        calibration_dir_2 (str): Path to the second calibration directory containing calibration_results.json.
        _workspace (Path | None, optional): Working directory for saving outputs. Defaults to None.
        _cfg (dict | None, optional): Global configuration dictionary. Not used directly.
        _llm (object | None, optional): LLM client instance. Not used directly.

    Returns:
        dict: A dictionary containing:
            - success (bool): Whether the operation completed successfully.
            - plot_path (str | None): Path to the generated box plot image.
            - summary (str): Textual summary of the statistical comparison.
            - error (str | None): Error message if success is False.
    """
    # Initialize logger
    logger = logging.getLogger(__name__)
    
    # Default workspace if not provided
    workspace = _workspace if _workspace else Path.cwd()
    
    try:
        # Lazy import external packages
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # Set style
        sns.set_theme(style="whitegrid")
        
        # Paths to JSON files
        json_file_1 = Path(calibration_dir_1) / "calibration_results.json"
        json_file_2 = Path(calibration_dir_2) / "calibration_results.json"
        
        # Validate paths exist
        if not json_file_1.exists():
            raise FileNotFoundError(f"Calibration results file not found: {json_file_1}")
        if not json_file_2.exists():
            raise FileNotFoundError(f"Calibration results file not found: {json_file_2}")
            
        logger.info(f"Loading calibration data from {json_file_1} and {json_file_2}")
        
        # Load JSON data
        with open(json_file_1, 'r', encoding='utf-8') as f:
            data_1 = json.load(f)
        with open(json_file_2, 'r', encoding='utf-8') as f:
            data_2 = json.load(f)
            
        # Helper to parse data into DataFrame
        def _parse_calibration_data(data: Any) -> pd.DataFrame:
            """
            Parses calibration JSON data into a DataFrame.
            Expects a list of runs, where each run is a dict of param_name: value.
            # TODO: verify JSON schema structure before deployment
            """
            if isinstance(data, list):
                # Assume list of runs
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # Check if it has a 'runs' or 'results' key
                if 'runs' in data:
                    df = pd.DataFrame(data['runs'])
                elif 'results' in data:
                    df = pd.DataFrame(data['results'])
                else:
                    # Try to find any list of dicts within the dict
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                            df = pd.DataFrame(value)
                            break
                    else:
                        raise ValueError("Unable to parse calibration data structure. Expected list of runs.")
            else:
                raise ValueError("Invalid data structure in calibration_results.json")
            
            # Filter only numeric columns (parameters)
            numeric_df = df.select_dtypes(include=[np.number])
            if numeric_df.empty:
                raise ValueError("No numeric parameter values found in calibration data.")
                
            return numeric_df

        df_1 = _parse_calibration_data(data_1)
        df_2 = _parse_calibration_data(data_2)
        
        # Identify common parameters
        common_params = list(set(df_1.columns) & set(df_2.columns))
        if not common_params:
            raise ValueError("No common parameters found between the two calibration datasets.")
            
        logger.info(f"Found {len(common_params)} common parameters for comparison.")
        
        # Prepare data for plotting (Long Form)
        # Add source column
        df_1_plot = df_1.copy()
        df_1_plot['source'] = 'Dataset 1'
        
        # Melt to long form
        df_1_melted = df_1_plot.melt(id_vars=['source'], var_name='parameter', value_name='value')
        df_1_melted = df_1_melted[df_1_melted['parameter'].isin(common_params)]
        
        df_2_plot = df_2.copy()
        df_2_plot['source'] = 'Dataset 2'
        df_2_melted = df_2_plot.melt(id_vars=['source'], var_name='parameter', value_name='value')
        df_2_melted = df_2_melted[df_2_melted['parameter'].isin(common_params)]
        
        combined_df = pd.concat([df_1_melted, df_2_melted], ignore_index=True)
        
        # Generate Statistics Summary
        summary_parts = []
        summary_parts.append("=== Calibration Parameter Distribution Comparison ===\n")
        summary_parts.append(f"Dataset 1 Samples: {len(df_1)}\n")
        summary_parts.append(f"Dataset 2 Samples: {len(df_2)}\n")
        summary_parts.append(f"Common Parameters: {', '.join(common_params)}\n\n")
        
        for param in common_params:
            vals_1 = df_1[param].dropna().values
            vals_2 = df_2[param].dropna().values
            
            if len(vals_1) == 0 or len(vals_2) == 0:
                continue
                
            mean_1, mean_2 = np.mean(vals_1), np.mean(vals_2)
            std_1, std_2 = np.std(vals_1), np.std(vals_2)
            
            summary_parts.append(f"Parameter: {param}\n")
            summary_parts.append(f"  Dataset 1: Mean={mean_1:.4f}, Std={std_1:.4f}\n")
            summary_parts.append(f"  Dataset 2: Mean={mean_2:.4f}, Std={std_2:.4f}\n")
            summary_parts.append(f"  Difference: {abs(mean_1 - mean_2):.4f}\n")
            
        summary_text = "".join(summary_parts)
        
        # Create Plot
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Boxplot
        sns.boxplot(
            data=combined_df, 
            x='parameter', 
            y='value', 
            hue='source', 
            ax=ax,
            palette='Set2'
        )
        
        plt.title('Comparison of Calibration Parameter Distributions', fontsize=16)
        plt.xlabel('Parameter Name', fontsize=12)
        plt.ylabel('Parameter Value', fontsize=12)
        plt.legend(title='Dataset', loc='upper right')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Save Plot
        output_filename = "calibration_distribution_comparison.png"
        output_path = workspace / output_filename
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"Plot saved to {output_path}")
        
        return {
            "success": True,
            "plot_path": str(output_path),
            "summary": summary_text,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error in compare_calibration_distributions: {str(e)}", exc_info=True)
        return {
            "success": False,
            "plot_path": None,
            "summary": "",
            "error": f"Failed to compare distributions: {str(e)}"
        }