"""
Compile exp2 results table from disk directories.
Reads A/B/C1 metrics from their respective output directories.
Run after all three methods have completed.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path("results/paper/exp2")
BASINS = [
    ("12025000", "Fish River, ME",    "humid_cold"),
    ("11532500", "Smith River, CA",   "mediterranean"),
    ("03439000", "French Broad, NC",  "humid_warm"),
]
MODEL = "xaj"


def read_metrics_csv(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {}
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    if not rows:
        return {}
    r = rows[0]
    result = {}
    for k, v in r.items():
        try:
            result[k] = float(v) if v else None
        except ValueError:
            result[k] = v
    return result


def best_iter_metrics(method_dir: Path) -> tuple[dict, dict]:
    """Find best iteration (by train KGE) in a Zhu-method dir, return (train, test)."""
    best_kge = -999.0
    best_train, best_test = {}, {}

    iter_dirs = sorted(
        [d for d in method_dir.iterdir() if d.is_dir() and d.name.startswith("iter_")]
    )
    for iter_d in iter_dirs:
        train_m = read_metrics_csv(iter_d / "train_metrics" / "basins_metrics.csv")
        kge = train_m.get("KGE", -999.0) or -999.0
        if kge > best_kge:
            best_kge = kge
            best_train = train_m
            best_test = read_metrics_csv(iter_d / "test_metrics" / "basins_metrics.csv")

    # If best iter has no test metrics, fall back to iter_00 test
    if not best_test:
        iter00 = method_dir / "iter_00"
        if iter00.exists():
            best_test = read_metrics_csv(iter00 / "test_metrics" / "basins_metrics.csv")

    return best_train, best_test


def c1_best_metrics(c1_dir: Path) -> tuple[dict, dict]:
    """Extract best-round metrics from a C1 (llm_calibrate) output dir."""
    best_train_nse = -999.0
    best_train, best_test = {}, {}

    # Check llm_round_* subdirectories first
    round_dirs = sorted(
        [d for d in c1_dir.iterdir() if d.is_dir() and d.name.startswith("llm_round_")]
    )
    for rd in round_dirs:
        train_m = read_metrics_csv(rd / "train_metrics" / "basins_metrics.csv")
        nse = train_m.get("NSE", -999.0) or -999.0
        if nse > best_train_nse:
            best_train_nse = nse
            best_train = train_m
            best_test = read_metrics_csv(rd / "test_metrics" / "basins_metrics.csv")

    # Fall back to top-level metrics if no round subdirs
    if not best_train:
        for sub in c1_dir.rglob("train_metrics/basins_metrics.csv"):
            m = read_metrics_csv(sub)
            if (m.get("NSE") or -999) > best_train_nse:
                best_train_nse = m.get("NSE", -999)
                best_train = m
        for sub in c1_dir.rglob("test_metrics/basins_metrics.csv"):
            m = read_metrics_csv(sub)
            if (m.get("NSE") or -999) > (best_test.get("NSE") or -999):
                best_test = m

    return best_train, best_test


def a_metrics_from_json(basin_id: str) -> tuple[dict, dict]:
    """Load Method A train/test metrics from exp2_results.json."""
    json_path = RESULTS_DIR / "exp2_results.json"
    if not json_path.exists():
        return {}, {}
    d = json.loads(json_path.read_text(encoding="utf-8"))
    for r in d.get("results", []):
        if r.get("basin_id") == basin_id:
            runs = r.get("method_A_runs", [])
            if runs and runs[0].get("success"):
                return runs[0].get("train_metrics", {}), runs[0].get("test_metrics", {})
    return {}, {}


def fmt(v, digits=4):
    if v is None or v == "":
        return "N/A"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def main():
    rows = []

    for basin_id, basin_name, climate_zone in BASINS:
        # Method A — always use run1 (N_SEEDS_A=1 standard-practice design)
        a_dir = RESULTS_DIR / f"A_{MODEL}_{basin_id}"
        run1 = a_dir / "run1"
        if run1.exists():
            a_train = read_metrics_csv(run1 / "train_metrics" / "basins_metrics.csv")
            a_test  = read_metrics_csv(run1 / "test_metrics"  / "basins_metrics.csv")
        elif a_dir.exists():
            # Fallback: pick the first available run alphabetically
            a_train, a_test = {}, {}
            for sub_run in sorted(a_dir.iterdir()):
                if sub_run.is_dir():
                    a_train = read_metrics_csv(sub_run / "train_metrics" / "basins_metrics.csv")
                    a_test  = read_metrics_csv(sub_run / "test_metrics"  / "basins_metrics.csv")
                    break
        else:
            a_train, a_test = a_metrics_from_json(basin_id)

        # Method B (Zhu + SCE-UA for XAJ)
        b_dir = RESULTS_DIR / f"B_{MODEL}_{basin_id}"
        b_train, b_test = best_iter_metrics(b_dir) if b_dir.exists() else ({}, {})

        # Method C1 (HydroAgent LLM calibration)
        c1_dir = RESULTS_DIR / f"C1_{MODEL}_{basin_id}"
        c1_train, c1_test = c1_best_metrics(c1_dir) if c1_dir.exists() else ({}, {})

        rows.append({
            "basin_id":      basin_id,
            "basin_name":    basin_name,
            "climate_zone":  climate_zone,
            # NSE
            "A_nse_train":   a_train.get("NSE"),
            "A_nse_test":    a_test.get("NSE"),
            "B_nse_train":   b_train.get("NSE"),
            "B_nse_test":    b_test.get("NSE"),
            "C1_nse_train":  c1_train.get("NSE"),
            "C1_nse_test":   c1_test.get("NSE"),
            # KGE
            "A_kge_train":   a_train.get("KGE"),
            "A_kge_test":    a_test.get("KGE"),
            "B_kge_train":   b_train.get("KGE"),
            "B_kge_test":    b_test.get("KGE"),
            "C1_kge_train":  c1_train.get("KGE"),
            "C1_kge_test":   c1_test.get("KGE"),
            # Delta C1 vs A (test NSE)
            "delta_C1_A":    (
                round(c1_test["NSE"] - a_test["NSE"], 4)
                if isinstance(c1_test.get("NSE"), float) and isinstance(a_test.get("NSE"), float)
                else None
            ),
        })

    # Print table
    print("=" * 100)
    print("Exp2 Results: LLM Calibration Comparison (XAJ, 3 basins)")
    print("=" * 100)
    header = (
        f"{'Basin':12s} {'Climate':15s} | "
        f"{'A: SCE-UA (agent)':>20s} | "
        f"{'B: Zhu (scripted)':>20s} | "
        f"{'C1: HydroAgent LLM':>20s} | Delta"
    )
    sub = (
        f"{'':12s} {'':15s} | "
        f"{'train NSE':>10s} {'test NSE':>10s} | "
        f"{'train NSE':>10s} {'test NSE':>10s} | "
        f"{'train NSE':>10s} {'test NSE':>10s} | C1-A"
    )
    print(header)
    print(sub)
    print("-" * 100)

    for r in rows:
        print(
            f"{r['basin_id']:12s} {r['climate_zone']:15s} | "
            f"{fmt(r['A_nse_train']):>10s} {fmt(r['A_nse_test']):>10s} | "
            f"{fmt(r['B_nse_train']):>10s} {fmt(r['B_nse_test']):>10s} | "
            f"{fmt(r['C1_nse_train']):>10s} {fmt(r['C1_nse_test']):>10s} | "
            f"{fmt(r['delta_C1_A'], 4)}"
        )

    print("=" * 100)
    print("\nKGE (test period):")
    print(f"{'Basin':12s} | {'A KGE':>10s} | {'B KGE':>10s} | {'C1 KGE':>10s}")
    print("-" * 50)
    for r in rows:
        print(
            f"{r['basin_id']:12s} | "
            f"{fmt(r['A_kge_test']):>10s} | "
            f"{fmt(r['B_kge_test']):>10s} | "
            f"{fmt(r['C1_kge_test']):>10s}"
        )

    # Save JSON
    out_path = RESULTS_DIR / "exp2_compiled.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
