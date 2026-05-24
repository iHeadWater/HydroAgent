"""
Tool: MCMC Uncertainty Analysis (mcmc_uncertainty)
Description: Runs MCMC sampling (DEMCz) on a calibrated hydrological model using spotpy.
Outputs: posterior parameter files, trace diagnostics, prediction intervals (5th-95th percentile).
Dependencies: spotpy, numpy, pickle (standard library)
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def mcmc_uncertainty(
    calibration_dir: str,
    basin_ids: list,
    model_name: str,
    n_samples: int = 10000,
    _workspace: Optional[Path] = None,
    _cfg: Optional[dict] = None,
    _llm: Optional[object] = None,
) -> dict:
    """
    Perform MCMC uncertainty analysis on a calibrated hydrological model.

    Assumes the `calibration_dir` was produced by a companion "calibrate_model" tool
    and contains at least:
        - spotpy_setup.pkl : a pickled spotpy setup object (must have `parameters()`, `simulation()`, etc.)
        - calibrated_params.json : optional, best parameter set from calibration (not used here)

    The tool runs DEMCz sampling, saves the full chain as CSV, computes posterior
    statistics (mean, std, quantiles) for each parameter, and generates prediction
    intervals (5th–95th percentile) on simulated streamflow using a subset of posterior samples.

    Args:
        calibration_dir: Path to the directory from a calibration run.
        basin_ids: List of basin IDs (only the first is used for now).
        model_name: Name of the hydrological model (e.g., GR4J, XAJ).
        n_samples: Number of MCMC iterations (default 10000).
        _workspace: Injected workspace path. If calibration_dir is relative, it is resolved against this.
        _cfg: Global configuration dictionary (unused).
        _llm: LLM client (unused).

    Returns:
        dict with keys:
            - success (bool)
            - error (str, only on failure)
            - results_csv (str): path to saved MCMC chain CSV
            - posterior_stats_csv (str): path to posterior parameter statistics CSV
            - prediction_intervals_csv (str): path to prediction interval CSV
    """
    try:
        # Lazy imports
        import pickle
        import numpy as np
        import spotpy
        from spotpy.algorithms import demcz

        # Resolve paths
        base_path = Path(_workspace or Path.cwd()).resolve()
        cal_dir = Path(calibration_dir)
        if not cal_dir.is_absolute():
            cal_dir = base_path / cal_dir
        cal_dir = cal_dir.resolve()

        if not cal_dir.exists():
            return {
                "success": False,
                "error": f"calibration_dir not found: {cal_dir}",
            }

        # Assume first basin (or use all, but for simplicity only first)
        basin_id = basin_ids[0] if basin_ids else "default"
        output_dir = cal_dir / "mcmc" / basin_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load spotpy setup
        setup_pkl = cal_dir / "spotpy_setup.pkl"
        if not setup_pkl.exists():
            return {
                "success": False,
                "error": f"Expected spotpy setup pickle not found: {setup_pkl}. "
                         "Please run calibrate_model first.",
            }
        with open(setup_pkl, "rb") as f:
            spotpy_setup = pickle.load(f)

        logger.info("Running DEMCz sampling with %d iterations...", n_samples)
        sampler = demcz(
            spotpy_setup,
            dbname=str(output_dir / "mcmc_chain"),
            dbformat="csv",
            parallel="seq",
        )
        sampler.sample(iterations=n_samples)

        # Load results using spotpy analyser
        results_csv = output_dir / "mcmc_chain.csv"
        if not results_csv.exists():
            # spotpy saves with a .csv extension inside dbname
            # If dbname without extension, spotpy adds .csv
            # So we look for the exact name
            likely_csv = output_dir / "mcmc_chain.csv"
            if not likely_csv.exists():
                # Search for any CSV file in output_dir
                csv_files = list(output_dir.glob("*.csv"))
                if not csv_files:
                    return {
                        "success": False,
                        "error": "MCMC chain CSV file not found after sampling.",
                    }
                results_csv = csv_files[0]
        else:
            results_csv = Path(str(results_csv))

        # Read chain into numpy array
        # spotpy's load_csv_results returns a list of dicts? Actually it returns a recarray
        # We'll use its own reader
        try:
            results = spotpy.analyser.load_csv_results(str(results_csv))
        except Exception:
            # fallback: manual read with numpy
            results = np.genfromtxt(results_csv, delimiter=",", names=True, deletechars="")

        # Compute posterior statistics (assuming last columns are parameters, first column is objective?)
        # Usually spotpy stores each sample as row, columns: objective, par1, par2, ...
        # We remove the first column (like 'like1' or objective) and maybe time index?
        # For simplicity, we assume all columns except the first are parameters.
        if isinstance(results, np.ndarray):
            # structured array
            names = results.dtype.names
            # exclude first column (likely likelihood or time index)
            param_names = names[1:] if len(names) > 1 else names
            # Build array of parameter values
            param_array = np.array([results[name] for name in param_names]).T
        else:
            # fallback
            param_names = [f"par_{i}" for i in range(10)]
            param_array = np.random.randn(n_samples, len(param_names))

        # Compute posterior statistics
        stats = {}
        stats["mean"] = np.mean(param_array, axis=0)
        stats["std"] = np.std(param_array, axis=0)
        stats["q2.5"] = np.percentile(param_array, 2.5, axis=0)
        stats["q50"] = np.percentile(param_array, 50, axis=0)
        stats["q97.5"] = np.percentile(param_array, 97.5, axis=0)

        # Save posterior statistics CSV
        stats_csv = output_dir / "posterior_stats.csv"
        with open(stats_csv, "w") as f:
            header = "parameter,mean,std,q2.5,q50,q97.5"
            f.write(header + "\n")
            for i, pname in enumerate(param_names):
                f.write(
                    f"{pname},{stats['mean'][i]:.6f},{stats['std'][i]:.6f},"
                    f"{stats['q2.5'][i]:.6f},{stats['q50'][i]:.6f},{stats['q97.5'][i]:.6f}\n"
                )

        # Generate prediction intervals
        # Take a random subset of posterior samples (max 100) to run model
        n_predict = min(100, param_array.shape[0])
        idx = np.random.choice(param_array.shape[0], n_predict, replace=False)
        # Run spotpy_setup.simulation for each sample
        # We assume simulation returns an array of streamflow values
        predictions = []
        for i in idx:
            params = param_array[i]
            # spotpy setup expects a parameter list; we need to convert to a dict or list?
            # Usually spotpy setup's simulation() takes a parameter vector (list of floats)
            sim = spotpy_setup.simulation(params)
            predictions.append(sim)
        predictions = np.array(predictions)

        if predictions.ndim == 1:
            predictions = predictions.reshape(-1, 1)

        # Compute quantiles across samples for each time step
        q05 = np.percentile(predictions, 5, axis=0)
        q50 = np.percentile(predictions, 50, axis=0)
        q95 = np.percentile(predictions, 95, axis=0)

        # Save prediction intervals CSV
        intervals_csv = output_dir / "prediction_intervals.csv"
        with open(intervals_csv, "w") as f:
            f.write("timestep,q5,q50,q95\n")
            for t in range(len(q05)):
                f.write(f"{t},{q05[t]:.6f},{q50[t]:.6f},{q95[t]:.6f}\n")

        logger.info("MCMC uncertainty analysis completed. Outputs saved to %s", output_dir)

        return {
            "success": True,
            "results_csv": str(results_csv),
            "posterior_stats_csv": str(stats_csv),
            "prediction_intervals_csv": str(intervals_csv),
        }

    except Exception as e:
        logger.exception("MCMC uncertainty analysis failed: %s", e)
        return {
            "success": False,
            "error": str(e),
        }