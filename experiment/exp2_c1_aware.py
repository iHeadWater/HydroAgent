"""
Exp2 — Method C1 (basin-aware variant) re-run.

Re-runs ONLY Method C1 for XAJ on 3 basins, using the upgraded `llm_calibrate`
that now (1) auto-fetches basin attributes via `get_basin_attributes` and
(2) lets the LLM design *basin-aware* initial parameter ranges before SCE-UA.

Output goes to results/paper/exp2/C1_aware_xaj_<basin>/, leaving the original
"reactive" results (C1_xaj_<basin>_reactive/) untouched for ablation comparison.

A/B/old-C1 results are NOT touched.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp2_c1_aware.py
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib
matplotlib.use("Agg")

# Reuse the existing exp2 machinery (Method C runner, evaluation helpers, etc.)
import experiment.exp2_llm_calibration as exp2_mod
from experiment.exp2_llm_calibration import (
    BASINS, OUTPUT_DIR, _run_method_c, _evaluate_from_disk, setup_logging
)
from hydroagent.config import load_config

logger = logging.getLogger(__name__)

# Force XAJ for this aware-variant script regardless of what exp2's module
# global MODEL is set to. We monkey-patch the module global so _run_method_c
# (which references it) uses the right model.
exp2_mod.MODEL = "xaj"
MODEL = "xaj"


def main():
    setup_logging()
    cfg = load_config()

    out_dir = Path("results/paper/exp2")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    meta = {
        "experiment": "exp2_c1_aware",
        "mode": "C1_aware (basin-aware initial ranges + per-round attribute injection)",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "label_suffix": "C1_aware",
        "compared_against": "C1_xaj_*_reactive/ (backed up earlier)",
    }

    for basin_id, basin_name, climate_zone in BASINS:
        logger.info(f"\n{'='*60}")
        logger.info(f"C1-aware: {basin_id} ({basin_name}, {climate_zone})")
        logger.info(f"{'='*60}")

        # Run Method C with new label "C1_aware" -> dir C1_aware_xaj_<basin>/
        entry = _run_method_c(basin_id, cfg, label="C1_aware")

        # Evaluate from disk (test period metrics)
        if entry.get("success") and entry.get("calibration_dir"):
            tr, te = _evaluate_from_disk(entry["calibration_dir"], cfg)
            entry["train_metrics"] = tr
            entry["test_metrics"] = te

        record = {
            "basin_id": basin_id,
            "basin_name": basin_name,
            "climate_zone": climate_zone,
            "model": MODEL,
            "method_C1_aware": entry,
        }
        results.append(record)

        def _fmt(v): return f"{v:.4f}" if isinstance(v, (int, float)) else "N/A"
        logger.info(
            f"  C1-aware {basin_id}: "
            f"train NSE={_fmt(entry.get('train_metrics', {}).get('NSE'))} | "
            f"test NSE={_fmt(entry.get('test_metrics', {}).get('NSE'))} | "
            f"test KGE={_fmt(entry.get('test_metrics', {}).get('KGE'))} | "
            f"basin_aware_init={entry.get('basin_aware_init', '?')}"
        )

        # Save incrementally so partial progress isn't lost
        out_json = out_dir / "exp2_c1_aware_results.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({**meta, "results": results}, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"  Saved progress: {out_json}")

    logger.info("\n" + "="*60)
    logger.info("All 3 basins done. C1-aware results saved.")
    logger.info("="*60)


if __name__ == "__main__":
    main()
