"""HydroAgent (M2) parameter-range evolution analysis.

Shows, for a few representative basins, how the LLM-proposed search range
[lo, hi] and the SCE-UA best parameter evolve generation-by-generation for
each GR4J parameter (x1-x4), aligned with the test-NSE trajectory below.

Goal: reveal whether the LLM reasons physically (tightens ranges around good
values, relocates by attributes) or just mechanically widens hit boundaries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import FIGURES_DIR, M0_DIR, M2_DIR, ensure_dirs

# Representative basins spanning the calibration-behaviour types:
#   07197000 good        : train & test both rise (real generalizing gain)
#   01543000 over-fit    : train rises a lot, test flat (over-fitting)
#   10336660 under-fit   : train rises but model still poor (GR4J unsuited)
#   03574500 already-opt : M0 near ceiling, little change
BASINS_TO_SHOW = [
    ("07197000", "good",       "Baron Fork, OK"),
    ("01543000", "over-fit",   "Driftwood Branch, PA"),
    ("10336660", "under-fit",  "Blackwood Creek, CA"),
    ("03574500", "near-opt",   "Paint Rock River, AL"),
]
PARAMS = ["x1", "x2", "x3", "x4"]
PARAM_LABEL = {
    "x1": "x1 production store [mm]",
    "x2": "x2 gw exchange [mm/d]",
    "x3": "x3 routing store [mm]",
    "x4": "x4 UH time base [d]",
}
RANGE_COLOR = "#9E9AC8"
BEST_COLOR = "#1B9E77"
NSE_COLOR = "#D95F02"


def _read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def _f(v):
    return float(v) if isinstance(v, (int, float)) else None


def main():
    ensure_dirs()
    import matplotlib.pyplot as plt

    m2 = _read_jsonl(M2_DIR / "trials.jsonl")
    m0 = {r["basin_id"]: r for r in _read_jsonl(M0_DIR / "trials.jsonl")}
    from collections import defaultdict
    by_basin = defaultdict(list)
    for r in m2:
        by_basin[r["basin_id"]].append(r)

    ncols = len(BASINS_TO_SHOW)
    nrows = len(PARAMS) + 1  # 4 params + NSE row
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 2.0 * nrows),
                             squeeze=False)

    for col, (bid, diff, name) in enumerate(BASINS_TO_SHOW):
        rs = sorted(by_basin[bid], key=lambda r: r.get("generation_idx", 0))
        gens = [r["generation_idx"] for r in rs]
        # g1 best_params come from M0 (warm-start reuse); backfill so the best
        # trajectory is complete.
        m0_best = (m0.get(bid) or {}).get("best_params", {})

        train_nses = [_f(r.get("train_NSE")) for r in rs]
        test_nses = [_f(r.get("test_NSE")) for r in rs]

        # ── parameter rows ──
        for row, p in enumerate(PARAMS):
            ax = axes[row][col]
            los, his, bests = [], [], []
            for r in rs:
                pr = (r.get("variant", {}) or {}).get("param_ranges", {})
                rng = pr.get(p)
                los.append(rng[0] if rng else None)
                his.append(rng[1] if rng else None)
                bp = r.get("best_params", {})
                b = _f(bp.get(p))
                if b is None and r["generation_idx"] == 1:
                    b = _f(m0_best.get(p))  # backfill g1 from M0
                bests.append(b)
            # Range band
            xs_band = [g for g, lo, hi in zip(gens, los, his) if lo is not None]
            lo_band = [lo for lo in los if lo is not None]
            hi_band = [hi for lo, hi in zip(los, his) if lo is not None]
            if xs_band:
                ax.fill_between(xs_band, lo_band, hi_band, color=RANGE_COLOR,
                                alpha=0.30, label="LLM range [lo,hi]", zorder=1)
            # Best param trajectory
            xs_b = [g for g, b in zip(gens, bests) if b is not None]
            ys_b = [b for b in bests if b is not None]
            if xs_b:
                ax.plot(xs_b, ys_b, "o-", color=BEST_COLOR, markersize=4,
                        linewidth=1.6, label="SCE-UA best", zorder=3)
            ax.set_ylabel(PARAM_LABEL[p], fontsize=7.5)
            ax.grid(color="#EEE", linewidth=0.5)
            ax.set_axisbelow(True)
            # Basin id only (no difficulty/gain), as small corner text
            if row == 0:
                ax.annotate(bid, xy=(0.5, 1.03), xycoords="axes fraction",
                            ha="center", va="bottom", fontsize=9, fontweight="bold")

        # ── NSE row: train (solid) + test (dashed) ──
        ax = axes[nrows - 1][col]
        xs_tr = [g for g, nn in zip(gens, train_nses) if nn is not None]
        ys_tr = [nn for nn in train_nses if nn is not None]
        xs_te = [g for g, nn in zip(gens, test_nses) if nn is not None]
        ys_te = [nn for nn in test_nses if nn is not None]
        if xs_tr:
            ax.plot(xs_tr, ys_tr, "o-", color=NSE_COLOR, markersize=5,
                    linewidth=2.0, zorder=3, label="train NSE")
        if xs_te:
            ax.plot(xs_te, ys_te, "s--", color="#377EB8", markersize=4,
                    linewidth=1.6, zorder=3, label="test NSE")
        ax.set_ylabel("NSE", fontsize=9, fontweight="bold")
        ax.set_xlabel("generation", fontsize=8)
        ax.grid(color="#EEE", linewidth=0.5)
        ax.set_axisbelow(True)

    # Single legend at the bottom
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [
        Patch(facecolor=RANGE_COLOR, alpha=0.3, label="LLM-proposed search range [lo, hi]"),
        Line2D([0], [0], color=BEST_COLOR, marker="o", markersize=5, label="SCE-UA best parameter"),
        Line2D([0], [0], color=NSE_COLOR, marker="o", markersize=5, label="train NSE"),
        Line2D([0], [0], color="#377EB8", marker="s", linestyle="--", markersize=5, label="test NSE"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=8.5, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out = FIGURES_DIR / "fig_param_evolution.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
