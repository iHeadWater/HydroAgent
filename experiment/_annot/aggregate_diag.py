"""Aggregate human + LLM DiagScore ratings, compute Cohen's κ, flag disagreements.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/_annot/aggregate_diag.py \\
    --human experiment/_annot/human_scores.csv \\
    --llm experiment/_annot/llm_scores.csv \\
    --out experiment/_annot/combined_scores.csv
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from experiment._metrics import diag_score  # noqa: E402

logger = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", default="experiment/_annot/human_scores.csv",
                    help="Human rater CSV (filled from human_template.csv)")
    ap.add_argument("--llm", default="experiment/_annot/llm_scores.csv",
                    help="LLM rater CSV (output of llm_rater.py)")
    ap.add_argument("--out", default="experiment/_annot/combined_scores.csv")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    human_path = Path(args.human)
    if not human_path.exists():
        logger.error(f"Human scores CSV not found: {human_path}")
        logger.error("Fill in experiment/_annot/human_template.csv and save as human_scores.csv")
        sys.exit(1)

    llm_path = Path(args.llm) if Path(args.llm).exists() else None
    if llm_path is None:
        logger.warning(f"LLM scores not found at {args.llm}; running human-only summary")

    result = diag_score.aggregate(human_path, llm_path)

    print("\n=== DiagScore Aggregation ===")
    print(f"N items: {result['n_items']}")
    if result["kappa_per_dim"]:
        print("\nCohen's κ (human vs LLM):")
        for d, k in result["kappa_per_dim"].items():
            label = diag_score.DIM_NAMES.get(d, "overall")
            flag = " ← LOW" if isinstance(k, float) and k < 0.6 else ""
            print(f"  {d} ({label}): {k}{flag}")
    print("\nPer-instance DiagScores:")
    print(f"  {'Task':<6} {'Cond':<6} {'Human':>7} {'LLM':>7} {'Mean':>7}")
    for r in result["rows"]:
        h = r.get("human_DS", "")
        l = r.get("llm_DS", "")
        m = r.get("mean_DS", "")
        print(f"  {r.get('task_id', ''):<6} {r.get('condition', ''):<6} {h:>7} {l:>7} {m:>7}")

    # Save combined CSV
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        cols = ["task_id", "condition", "human_DS", "llm_DS", "mean_DS"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(result["rows"])
    logger.info(f"Saved combined scores: {out_path}")

    # Flag disagreements >1 point in any dimension (for human re-review)
    if llm_path:
        logger.info("Disagreements >1 point (re-review recommended):")
        h_rows = {(r["task_id"], r["condition"]): r for r in diag_score.read_csv(human_path)}
        l_rows = {(r["task_id"], r["condition"]): r for r in diag_score.read_csv(llm_path)}
        n_disagree = 0
        for key, hr in h_rows.items():
            if key not in l_rows:
                continue
            lr = l_rows[key]
            for d in diag_score.DIMENSIONS:
                if d in hr and d in lr and isinstance(hr[d], int) and isinstance(lr[d], int):
                    diff = abs(hr[d] - lr[d])
                    if diff > 1:
                        print(f"  {key[0]} × {key[1]} {d}: human={hr[d]}, llm={lr[d]} (diff={diff})")
                        n_disagree += 1
        if n_disagree == 0:
            print("  (none)")
        else:
            print(f"  Total disagreements >1: {n_disagree}")


if __name__ == "__main__":
    main()
