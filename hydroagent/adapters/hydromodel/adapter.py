"""
HydromodelAdapter: wraps the hydromodel Python package.

Handles all hydromodel-specific logic (config building, calibration,
evaluation, visualization, simulation).  The routing functions in
hydroagent/skills/ and hydroagent/tools/ delegate here.
"""

import logging
import threading
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from hydroagent.adapters.base import PackageAdapter

logger = logging.getLogger(__name__)


def _inject_param_range_into_model_cfgs(config: dict, param_dir=None) -> dict:
    """Make the configured parameter range actually reach the model.

    Workaround for a hydromodel unified-architecture limitation: the
    `param_range_file` is loaded for parameter names and the [0,1] search
    bounds, but is NOT fed into the model's denormalization. Both
    `unified_calibrate.calibrate()` and `unified_evaluate.evaluate()` build the
    model config as `{"name": model_name, **model_cfgs["model_params"]}`, so the
    model only ever sees the built-in default range (MODEL_PARAM_DICT) and any
    custom range is silently ignored — calibration and evaluation become
    insensitive to the parameter range.

    Fix: inject the resolved param_range into
    `config["model_cfgs"]["model_params"][model_name]` so it is unpacked into
    the model kwargs and used for denormalization.

    Idempotent and forward-compatible: if the slot already carries a
    param_range (e.g. a future fixed hydromodel populates it), it is left
    untouched; failures degrade to the previous (default-range) behaviour.
    """
    import os

    try:
        from hydromodel.models.model_config import read_model_param_dict
    except ImportError:
        return config

    model_cfgs = config.get("model_cfgs") or {}
    model_name = model_cfgs.get("model_name")
    if not model_name:
        return config
    model_params = model_cfgs.setdefault("model_params", {})

    existing = model_params.get(model_name)
    if isinstance(existing, dict) and "param_range" in existing:
        return config  # already populated -- respect it (forward-compatible)

    # Resolve the range file: prefer the copy saved alongside the calibration
    # output (most faithful to this run), then the configured path.
    prf = None
    if param_dir:
        cand = os.path.join(str(param_dir), "param_range.yaml")
        if os.path.exists(cand):
            prf = cand
    if not prf:
        tprf = (config.get("training_cfgs") or {}).get("param_range_file")
        if tprf and os.path.exists(str(tprf)):
            prf = str(tprf)

    try:
        pdict = read_model_param_dict(prf)  # prf=None -> hydromodel defaults
        if model_name in pdict:
            model_params[model_name] = pdict[model_name]
    except Exception as e:  # noqa: BLE001 - never break the run over this
        logger.warning("param_range injection skipped (%s): %s", model_name, e)
    return config


class Adapter(PackageAdapter):
    name = "hydromodel"
    priority = 10

    def can_handle(self, data_source: str, model_name: str) -> bool:
        # hydromodel handles standard datasets; selfmade/custom go to hydrodatasource adapter
        return data_source not in ("selfmade", "custom")

    def supported_operations(self) -> list[str]:
        return ["calibrate", "evaluate", "visualize", "simulate"]

    # ── calibrate ────────────────────────────────────────────────────

    def calibrate(self, workspace: Path, **kw) -> dict:
        """Run SCE-UA/GA/scipy calibration via hydromodel."""
        model_name = kw.get("model_name", "xaj")
        algorithm = kw.get("algorithm", "SCE_UA")
        basin_ids = kw.get("basin_ids", [])
        train_period = kw.get("train_period")
        test_period = kw.get("test_period")
        algorithm_params = kw.get("algorithm_params")
        param_range_file = kw.get("param_range_file")
        obj_func = kw.get("obj_func")
        output_dir = kw.get("output_dir")
        _cfg = kw.get("_cfg")
        _ui = kw.get("_ui")
        _round_label = kw.get("_round_label", "")

        from hydroagent.config import build_hydromodel_config
        from hydroagent.utils.result_parser import parse_calibration_result

        config = build_hydromodel_config(
            basin_ids=basin_ids,
            model_name=model_name,
            algorithm=algorithm,
            train_period=train_period,
            test_period=test_period,
            algorithm_params=algorithm_params,
            param_range_file=param_range_file,
            obj_func=obj_func,
            output_dir=output_dir,
            cfg=_cfg,
        )
        # Ensure the configured param_range reaches the model (hydromodel
        # unified arch otherwise ignores it -- see helper docstring).
        _inject_param_range_into_model_cfgs(config)

        try:
            from hydromodel import calibrate as hm_calibrate
        except ImportError as e:
            return {"error": f"hydromodel not available: {e}", "success": False}

        # Inject negated loss functions for maximization metrics (NSE/KGE)
        self._inject_negated_losses()

        logger.info(
            "Starting calibration: %s/%s for basins %s", model_name, algorithm, basin_ids
        )

        cal_output_dir = config["training_cfgs"]["output_dir"]

        # Determine total evaluations for progress estimation
        _algo_p = algorithm_params or {}
        if algorithm == "SCE_UA":
            _rep = int(_algo_p.get("rep", 750))
        elif algorithm == "GA":
            _rep = int(_algo_p.get("pop_size", 50)) * int(
                _algo_p.get("n_generations", 50)
            )
        else:
            _rep = int(_algo_p.get("max_iterations", 100))

        # Start progress monitor thread
        _stop_monitor = threading.Event()
        _monitor = None
        if _ui and hasattr(_ui, "on_calibration_progress"):
            Path(cal_output_dir).mkdir(parents=True, exist_ok=True)
            _monitor = threading.Thread(
                target=self._progress_monitor,
                args=(_stop_monitor, _ui, cal_output_dir, _rep, algorithm, _round_label),
                daemon=True,
                name="cal-progress",
            )
            _monitor.start()

        try:
            result = hm_calibrate(config)
        except KeyboardInterrupt:
            logger.warning("Calibration interrupted by user")
            raise
        except Exception as e:
            error_msg = str(e)
            is_retryable = "NetCDF: HDF error" in error_msg or "KeyError" in error_msg
            if is_retryable:
                self._clear_caches()
                try:
                    result = hm_calibrate(config)
                except Exception as e2:
                    return self._calibration_error(str(e2), cal_output_dir)
            else:
                return self._calibration_error(error_msg, cal_output_dir)
        finally:
            _stop_monitor.set()
            if _monitor:
                _monitor.join(timeout=3.0)

        parsed = parse_calibration_result(result, config)
        cal_dir = parsed.get("calibration_dir", "")

        observable_files = {}
        if cal_dir:
            _d = Path(cal_dir)
            for fname in [
                "calibration_results.json",
                "basins_denorm_params.csv",
                "param_range.yaml",
                "calibration_config.yaml",
            ]:
                if (_d / fname).exists():
                    observable_files[fname] = str(_d / fname)

        training_cfg = config.get("training_cfgs", {})
        loss_cfg = training_cfg.get("loss_config", {})
        effective_config = {
            "obj_func": loss_cfg.get("requested_obj_func", obj_func),
            "hydromodel_obj_func": loss_cfg.get("obj_func"),
            "algorithm_params": dict(training_cfg.get("algorithm_params", {})),
            "random_seed": training_cfg.get("random_seed"),
            "param_range_file": training_cfg.get("param_range_file"),
            "train_period": config["data_cfgs"]["train_period"],
            "test_period": config["data_cfgs"]["test_period"],
            "output_dir": training_cfg.get("output_dir"),
        }

        return {
            "best_params": parsed.get("best_params", {}),
            "calibration_dir": cal_dir,
            "train_period": config["data_cfgs"]["train_period"],
            "test_period": config["data_cfgs"]["test_period"],
            "effective_config": effective_config,
            "output_files": parsed.get("output_files", []),
            "observable_files": observable_files,
            "model_name": model_name,
            "algorithm": algorithm,
            "basin_ids": basin_ids,
            "success": True,
            "next_steps": [
                f"Call evaluate_model('{cal_dir}', eval_period=train_period) to get train NSE/KGE.",
                f"Call evaluate_model('{cal_dir}', eval_period=test_period) to get test NSE/KGE.",
                "Or call inspect_dir(calibration_dir) to see all output files.",
                "Or call read_file(observable_files['calibration_results.json']) to inspect raw parameters.",
            ],
        }

    # ── evaluate ─────────────────────────────────────────────────────

    def evaluate(self, workspace: Path, **kw) -> dict:
        """Evaluate calibrated model; returns NSE/KGE/RMSE metrics."""
        calibration_dir = kw.get("calibration_dir", "")
        eval_period = kw.get("eval_period")
        output_subdir = kw.get("output_subdir")
        _workspace = kw.get("_workspace") or workspace

        from hydroagent.utils.result_parser import parse_evaluation_result
        from hydroagent.utils.path_utils import resolve_path

        try:
            from hydromodel.trainers.unified_evaluate import evaluate
            from hydromodel.configs.config_manager import load_config_from_calibration
        except ImportError as e:
            return {"error": f"hydromodel not available: {e}", "success": False}

        resolved = resolve_path(calibration_dir, _workspace)
        logger.info(
            "Evaluating model from: %s -> resolved: %s", calibration_dir, resolved
        )
        cal_path = resolved if resolved is not None else Path(calibration_dir)

        if not cal_path.exists():
            return {
                "error": f"calibration_dir not found: {calibration_dir}",
                "success": False,
                "diagnosis": {"calibration_dir_exists": False},
                "hint": "Check that calibrate_model completed successfully and returned the correct calibration_dir.",
            }

        config_candidates = list(cal_path.glob("calibration_config.yaml"))
        if not config_candidates:
            files_present = [f.name for f in cal_path.iterdir() if f.is_file()]
            return {
                "error": "calibration_config.yaml not found -- cannot load calibration config.",
                "success": False,
                "diagnosis": {
                    "calibration_dir_exists": True,
                    "files_found": files_present,
                },
                "hint": (
                    "calibration_config.yaml is missing. "
                    f"Files present: {files_present}. "
                    "This may mean calibration did not complete. "
                    f"Call inspect_dir('{calibration_dir}') to investigate."
                ),
            }

        try:
            config = load_config_from_calibration(calibration_dir)
            # Ensure the configured param_range reaches the model for
            # denormalization (hydromodel unified arch otherwise ignores it).
            _inject_param_range_into_model_cfgs(config, param_dir=cal_path)
            actual_period = eval_period or config["data_cfgs"]["test_period"]

            if output_subdir is None:
                train_period = config["data_cfgs"].get("train_period", [])
                test_period = config["data_cfgs"].get("test_period", [])
                if actual_period == train_period:
                    output_subdir = "train_metrics"
                elif actual_period == test_period:
                    output_subdir = "test_metrics"
                else:
                    start = actual_period[0][:7].replace("-", "")
                    end = actual_period[1][:7].replace("-", "")
                    output_subdir = f"eval_{start}_{end}"

            metrics_dir = cal_path / output_subdir
            metrics_dir.mkdir(exist_ok=True)

            # hydromodel may print emoji which crashes GBK terminals on Windows
            import sys as _sys

            if hasattr(_sys.stdout, "reconfigure"):
                try:
                    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            result = evaluate(
                config,
                param_dir=calibration_dir,
                eval_period=actual_period,
                eval_output_dir=str(metrics_dir),
            )

            parsed = parse_evaluation_result(result, calibration_dir=str(metrics_dir))
            metrics = parsed.get("metrics", {})

            metrics_csv = metrics_dir / "basins_metrics.csv"
            observable = {"metrics_csv": str(metrics_csv)} if metrics_csv.exists() else {}

            return {
                "metrics": metrics,
                "eval_period": actual_period,
                "metrics_dir": str(metrics_dir),
                "observable_files": observable,
                "output_files": parsed.get("output_files", []),
                "success": True,
                "hint": (
                    f"Full metrics saved to {metrics_dir / 'basins_metrics.csv'}. "
                    "Call read_file(observable_files['metrics_csv']) to see all columns."
                )
                if metrics_csv.exists()
                else None,
            }

        except Exception as e:
            logger.error("Evaluation failed: %s", e, exc_info=True)
            files_present = [f.name for f in cal_path.iterdir() if f.is_file()]
            return {
                "error": f"Evaluation failed: {e}",
                "success": False,
                "diagnosis": {
                    "calibration_dir_exists": True,
                    "files_found": files_present,
                    "eval_period_requested": eval_period,
                },
                "hint": (
                    f"Calibration directory exists with files: {files_present}. "
                    f"Call read_file('{calibration_dir}/calibration_config.yaml') "
                    "to inspect the config and verify train/test periods match your request."
                ),
            }

    # ── visualize ────────────────────────────────────────────────────

    def visualize(self, workspace: Path, **kw) -> dict:
        """Generate hydrograph and scatter plots from calibration results."""
        calibration_dir = kw.get("calibration_dir", "")
        plot_types = kw.get("plot_types") or ["timeseries", "scatter"]
        basin_ids = kw.get("basin_ids")
        _workspace = kw.get("_workspace") or workspace

        try:
            from hydromodel.datasets.data_visualize import visualize_evaluation
        except ImportError as e:
            return {
                "error": f"hydromodel visualization not available: {e}",
                "plot_files": [],
                "plot_count": 0,
            }

        from hydroagent.utils.path_utils import resolve_path

        resolved = resolve_path(calibration_dir, _workspace)
        if resolved is None:
            return {
                "error": f"calibration_dir not found: {calibration_dir}",
                "plot_files": [],
                "plot_count": 0,
            }
        calib_path = resolved
        eval_dirs = list(calib_path.glob("evaluation_*"))
        if not eval_dirs:
            eval_dirs = [calib_path]

        plot_files = []
        for eval_dir in eval_dirs:
            try:
                hydro_types = []
                for pt in plot_types:
                    if pt == "hydrograph":
                        hydro_types.append("timeseries")
                    elif pt == "metrics":
                        hydro_types.append("scatter")
                    else:
                        hydro_types.append(pt)

                visualize_evaluation(
                    eval_dir=str(eval_dir),
                    output_dir=None,
                    plot_types=hydro_types or ["timeseries", "scatter"],
                    basins=basin_ids,
                )

                figures_dir = eval_dir / "figures"
                if figures_dir.exists():
                    for f in figures_dir.glob("*.png"):
                        plot_files.append(str(f))

            except Exception as e:
                logger.warning("Failed to visualize %s: %s", eval_dir, e)

        logger.info("Generated %d plots", len(plot_files))
        return {"plot_files": plot_files, "plot_count": len(plot_files)}

    # ── simulate ─────────────────────────────────────────────────────

    def simulate(self, workspace: Path, **kw) -> dict:
        """Run model simulation with calibrated or given parameters."""
        calibration_dir = kw.get("calibration_dir", "")
        sim_period = kw.get("sim_period")
        params = kw.get("params")

        try:
            from hydromodel import evaluate as hm_evaluate
            from hydromodel.configs.config_manager import load_config_from_calibration
        except ImportError as e:
            return {"error": f"hydromodel not available: {e}", "success": False}

        logger.info("Running simulation from: %s", calibration_dir)

        try:
            config = load_config_from_calibration(calibration_dir)
            period = sim_period or config.get("data_cfgs", {}).get("test_period")

            result = hm_evaluate(
                config,
                param_dir=calibration_dir,
                eval_period=period,
                eval_output_dir=None,
            )

            return {
                "simulation_dir": calibration_dir,
                "sim_period": period,
                "raw_result": str(type(result)),
                "success": True,
            }

        except Exception as e:
            logger.error("Simulation failed: %s", e, exc_info=True)
            return {"error": f"Simulation failed: {e}", "success": False}

    # ── internal helpers ──────────────────────────────────────────────

    def _inject_negated_losses(self):
        """Add neg_nashsutcliffe / neg_kge / neg_lognashsutcliffe to LOSS_DICT.

        Patched 2026-05-25: spotpy.objectivefunctions.kge() calls np.corrcoef
        which fails with "m has more than 2 dimensions" when obs/sim arrive
        as 3D arrays. Hydromodel passes streamflow as shape (time, basin, 1)
        on some SCE-UA code paths. Flatten obs and sim to 1D before calling
        any spotpy objective so all three negated losses behave consistently.
        Before this fix, the KGE objective crashed 100% of the time across
        all HydroAgent exp1/exp2 SCE-UA calibrations (the earlier patch to
        hydroutils.KGE was on the wrong code path — the real call site is
        spotpy.objectivefunctions, not hydroutils).
        """
        try:
            import numpy as _np
            import spotpy.objectivefunctions as _sof
            from hydromodel.models.model_dict import LOSS_DICT

            def _flat2(obs, sim):
                return _np.asarray(obs).reshape(-1), _np.asarray(sim).reshape(-1)

            if "neg_nashsutcliffe" not in LOSS_DICT:
                LOSS_DICT["neg_nashsutcliffe"] = (
                    lambda obs, sim: -_sof.nashsutcliffe(*_flat2(obs, sim))
                )
            if "neg_kge" not in LOSS_DICT:
                LOSS_DICT["neg_kge"] = (
                    lambda obs, sim: -_sof.kge(*_flat2(obs, sim))
                )
            if "neg_lognashsutcliffe" not in LOSS_DICT:
                LOSS_DICT["neg_lognashsutcliffe"] = (
                    lambda obs, sim: -_sof.lognashsutcliffe(*_flat2(obs, sim))
                )
        except Exception:
            pass

    def _clear_caches(self):
        """Clear xarray and gc caches before a retry."""
        try:
            import xarray as xr

            if hasattr(xr.backends, "file_manager") and hasattr(
                xr.backends.file_manager, "_FILE_CACHE"
            ):
                xr.backends.file_manager._FILE_CACHE.clear()
        except Exception:
            pass
        try:
            import gc

            gc.collect()
        except Exception:
            pass

    @staticmethod
    def _count_spotpy_evals(output_dir: str) -> int:
        try:
            csvs = list(Path(output_dir).glob("*.csv"))
            if not csvs:
                return 0
            biggest = max(csvs, key=lambda f: f.stat().st_size)
            return max(
                0,
                biggest.read_text(encoding="utf-8", errors="ignore").count("\n") - 1,
            )
        except Exception:
            return 0

    def _progress_monitor(
        self,
        stop_event: threading.Event,
        ui,
        output_dir: str,
        rep: int,
        algo: str,
        round_label: str = "",
    ):
        t0 = time.time()
        estimated_s = max(rep * 0.15, 30.0)
        while not stop_event.wait(timeout=2.0):
            elapsed = time.time() - t0
            ev_count = self._count_spotpy_evals(output_dir)
            if ev_count > 0 and rep > 0:
                pct = min(ev_count / rep * 100.0, 99.0)
            else:
                pct = min(elapsed / estimated_s * 100.0, 95.0)
            if hasattr(ui, "on_calibration_progress"):
                ui.on_calibration_progress(
                    pct=pct,
                    elapsed=elapsed,
                    eval_count=ev_count,
                    rep=rep,
                    algo=algo,
                    round_label=round_label,
                )

    @staticmethod
    def _calibration_error(error_msg: str, output_dir: str) -> dict:
        p = Path(output_dir)
        diagnosis = {
            "output_dir_exists": p.exists(),
            "files_found": [f.name for f in p.iterdir() if f.is_file()]
            if p.exists()
            else [],
        }
        if "HDF error" in error_msg or "NetCDF" in error_msg:
            hint = "HDF/NetCDF file lock -- try again or call inspect_dir(output_dir) to check partial output."
        elif "No such file" in error_msg or "dataset" in error_msg.lower():
            hint = "Dataset path issue -- check DATASET_DIR in configs/private.py points to the parent of CAMELS_US/."
        elif not diagnosis["output_dir_exists"]:
            hint = "Output directory was never created -- calibration likely failed before writing any files."
        else:
            hint = f"Use inspect_dir('{output_dir}') to see what was produced before the failure."

        return {
            "error": f"Calibration failed: {error_msg}",
            "success": False,
            "diagnosis": diagnosis,
            "hint": hint,
        }
