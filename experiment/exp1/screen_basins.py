"""Screen CAMELS-US basins for Exp1 v2 site selection (coarse pass).

Goal: find "medium-difficulty" basins where the GR4J default-range calibration
lands in a usable-but-improvable band (test NSE ~0.40-0.65). Those are the
candidates where range tuning can plausibly lift performance to a good level,
i.e. where M0 (no tuning) is clearly worse than M1/M2 (tuning) -- the regime
Exp1 needs to demonstrate value.

This is the COARSE pass: GR4J, default range, quick budget, on a random sample
of basins. A later verification pass would run range tuning on the survivors to
confirm the gain. Focuses on GR4J because its range tuning is numerically safe
(XAJ goes -inf on custom ranges -- see memory).

Robust: resumable (skips basins already in the jsonl), and each calibration is
wrapped so a failed/missing-data basin is recorded and skipped without aborting
the batch.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp1/screen_basins.py --n 60
"""

from __future__ import annotations

import argparse
import glob
import logging
import random
from pathlib import Path

from common import (
    MenuDecision,
    OUTPUT_ROOT,
    append_jsonl,
    ensure_dirs,
    flatten_metric,
    load_base_config,
    read_jsonl,
    run_trial,
    task_id,
)

LOGGER = logging.getLogger(__name__)

MEDIUM_LO, MEDIUM_HI = 0.40, 0.65


def load_basin_ids(cfg) -> list[str]:
    """All CAMELS-US gauge_ids from camels_clim.txt."""
    from configs.private import DATASET_DIR

    hits = glob.glob(str(Path(DATASET_DIR) / "**" / "camels_clim.txt"), recursive=True)
    if not hits:
        raise FileNotFoundError("camels_clim.txt not found under DATASET_DIR")
    with open(hits[0], encoding="utf-8") as f:
        header = f.readline()
        sep = ";" if ";" in header else ","
        ids = [line.split(sep)[0].strip() for line in f if line.strip()]
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=60, help="number of basins to sample")
    parser.add_argument("--seed", type=int, default=20260522, help="sampling seed (reproducible)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    run_dir = OUTPUT_ROOT / "screen"
    log_path = run_dir / "screen_trials.jsonl"

    all_ids = load_basin_ids(cfg)
    rng = random.Random(args.seed)
    sample = rng.sample(all_ids, min(args.n, len(all_ids)))
    LOGGER.info("Sampled %d / %d basins (seed=%d)", len(sample), len(all_ids), args.seed)

    done = {r["basin_id"] for r in read_jsonl(log_path)}

    for i, bid in enumerate(sample, 1):
        if bid in done:
            LOGGER.info("[%d/%d] skip (done): %s", i, len(sample), bid)
            continue
        task = {"basin_id": bid, "name": bid, "climate_zone": "unknown",
                "model": "gr4j", "task_id": task_id(bid, "gr4j")}
        decision = MenuDecision(objective="NSE", budget_level="quick", range_policy="default")
        try:
            record = run_trial(method="SCREEN", task=task, trial_idx=1,
                               decision=decision, cfg=cfg, run_dir=run_dir)
        except Exception as exc:  # noqa: BLE001 - never abort the batch
            record = {"basin_id": bid, "model": "gr4j", "method": "SCREEN",
                      "test_metrics": {}, "success": False, "error": str(exc)}
        append_jsonl(log_path, record)
        nse = flatten_metric(record, "test", "NSE") if record.get("test_metrics") else None
        LOGGER.info("[%d/%d] %s: test NSE=%s err=%s", i, len(sample), bid, nse,
                    (record.get("error") or "")[:60])

    # ---- summary ----
    rows = read_jsonl(log_path)
    scored = []
    for r in rows:
        nse = flatten_metric(r, "test", "NSE") if r.get("test_metrics") else None
        scored.append((r["basin_id"], nse, r.get("error")))
    ok = [(b, n) for b, n, e in scored if isinstance(n, float)]
    failed = [b for b, n, e in scored if not isinstance(n, float)]
    medium = sorted([(b, n) for b, n in ok if MEDIUM_LO <= n <= MEDIUM_HI],
                    key=lambda x: -x[1])

    print("\n" + "=" * 70)
    print(f"Screened: {len(scored)}  |  succeeded: {len(ok)}  |  failed/no-data: {len(failed)}")
    print(f"NSE distribution (default-range, quick GR4J):")
    if ok:
        ns = sorted(n for _, n in ok)
        print(f"  min={ns[0]:.3f}  median={ns[len(ns)//2]:.3f}  max={ns[-1]:.3f}")
        bands = {"<0.0": 0, "0.0-0.40": 0, "0.40-0.65 (MEDIUM)": 0, "0.65-0.80": 0, ">0.80": 0}
        for _, n in ok:
            if n < 0: bands["<0.0"] += 1
            elif n < 0.40: bands["0.0-0.40"] += 1
            elif n <= 0.65: bands["0.40-0.65 (MEDIUM)"] += 1
            elif n <= 0.80: bands["0.65-0.80"] += 1
            else: bands[">0.80"] += 1
        for k, v in bands.items():
            print(f"  {k:>22}: {v}")
    print(f"\n>>> MEDIUM-difficulty candidates (NSE in [{MEDIUM_LO}, {MEDIUM_HI}]): {len(medium)}")
    for b, n in medium:
        print(f"    {b}  default_NSE={n:.3f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
