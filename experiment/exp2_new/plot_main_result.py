"""Main result figure for exp2_new.

X = cumulative wall_time (log scale) per (basin, method).
Y = test NSE.
4 colors = 4 methods. Method order (per user):
  A standard SCE-UA, B HydroAgent (M2 feedback), C Zhu direct eval,
  D Zhu + local search (LLM + scipy SLSQP).

- A: 1 dot per basin (single calibration).
- B/C/D: filled colored box of NSE distribution across all iterations.
- If a method's distribution is degenerate for a basin (single point or
  range < 0.005), draw a single dot instead of a 1-pixel box.
Legend at bottom, no title.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import BASINS, FIGURES_DIR, RESULTS_DIR, ensure_dirs

# Method assignment AFTER reorder (per user):
#   A -> method_a (standard SCE-UA, no LLM, 1 calibration per basin)
#   B -> method_d (HydroAgent / M2 feedback loop)
#   C -> method_b (Zhu direct param eval)
#   D -> method_c (LLM + scipy local search)
METHOD_DIRS = {"A": "method_a", "B": "method_d", "C": "method_b", "D": "method_c"}
METHOD_COLOR = {"A": "#9E9E9E", "B": "#7FBC7F", "C": "#F4A582", "D": "#9E9AC8"}
METHOD_LABEL = {
    "A": "A standard SCE-UA",
    "B": "B HydroAgent",
    "C": "C Zhu direct eval",
    "D": "D direct eval + scipy local search",
}

DEGENERATE_RANGE = 0.04    # if NSE span < 0.04, box is visually too thin → plot as a dot
MIN_BOX_POINTS = 2         # 2+ iterations are enough to draw a (possibly thin) box
BOX_LOG_WIDTH = 0.010      # box width in log10(x) units (slim boxes)


def _read(method_key):
    p = RESULTS_DIR / METHOD_DIRS[method_key] / "trials.jsonl"
    if not p.exists():
        return []
    rows = []
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return rows


def _metric(r, period, name):
    m = r.get(f"{period}_metrics") or {}
    if isinstance(m, dict):
        v = m.get(name)
        return float(v) if isinstance(v, (int, float)) else None
    return None


def _wall(r):
    w = r.get("wall_time_s")
    return float(w) if isinstance(w, (int, float)) else 0.0


def _gather():
    """Return dict[method_key][basin_id] -> {wall_total_s, nses}."""
    out = {m: {} for m in ["A", "B", "C", "D"]}
    for method in ["A", "B", "C", "D"]:
        rows = _read(method)
        per_basin: dict[str, list] = {}
        for r in rows:
            per_basin.setdefault(r.get("basin_id"), []).append(r)
        for bid, recs in per_basin.items():
            nses = [_metric(r, "test", "NSE") for r in recs]
            nses = [n for n in nses if isinstance(n, (int, float))]
            wall_total = sum(_wall(r) for r in recs)
            out[method][bid] = {"wall_total_s": wall_total, "nses": nses}
    return out


def _iqr(values):
    s = sorted(values)
    n = len(s)
    if n < 4:
        return max(s) - min(s) if s else 0
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return q3 - q1


def _draw_axes(ax, data, basin_ids, y_min, y_max, clip_note=True):
    import matplotlib.pyplot as plt

    width_mult = 10 ** BOX_LOG_WIDTH - 1

    for method in ["A", "B", "C", "D"]:
        color = METHOD_COLOR[method]
        for bid in basin_ids:
            d = data[method].get(bid)
            if d is None or not d["nses"]:
                continue
            x = max(d["wall_total_s"], 1.0)
            nses = d["nses"]

            # Degenerate (draw a dot, not a box) when the box BODY would be a
            # thin line: A always; too few points; or IQR (Q3-Q1) below threshold
            # even if long whiskers make max-min look large.
            degenerate = (
                method == "A"
                or len(nses) < MIN_BOX_POINTS
                or _iqr(nses) < DEGENERATE_RANGE
            )
            if degenerate:
                import statistics
                y = nses[0] if method == "A" else statistics.median(nses)
                ax.scatter([x], [y], color=color, s=45,
                           edgecolors="black", linewidths=0.6, zorder=4, alpha=0.95)
            else:
                ax.boxplot(
                    [nses], positions=[x], widths=[x * width_mult],
                    patch_artist=True, manage_ticks=False, showfliers=False,
                    boxprops=dict(facecolor=color, alpha=0.85, edgecolor="black", linewidth=0.6),
                    medianprops=dict(color="black", linewidth=1.0),
                    whiskerprops=dict(color="black", linewidth=0.6),
                    capprops=dict(color="black", linewidth=0.6),
                )

    ax.set_xscale("log")
    ax.set_xlabel("Calibration wall time per basin (s, log scale)", fontsize=11)
    ax.set_ylabel("Test NSE", fontsize=12, fontweight="bold")
    ax.axhline(0.0, color="#444", linewidth=0.7, linestyle="--", alpha=0.6)
    ax.axhline(0.5, color="#888", linewidth=0.6, linestyle=":", alpha=0.5)
    ax.grid(True, color="#DDDDDD", linewidth=0.6, which="both", alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_ylim(y_min, y_max)
    if clip_note:
        n_clipped = sum(
            1 for m in ["A", "B", "C", "D"] for bid, d in data[m].items()
            if d.get("nses") and min(d["nses"]) < y_min
        )
        if n_clipped:
            ax.text(
                0.99, 0.03,
                f"{n_clipped} entries clipped below NSE={y_min}",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color="#666", style="italic",
            )


def _add_legend(ax):
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=METHOD_COLOR["A"],
               markersize=9, markeredgecolor="black", markeredgewidth=0.6,
               label=METHOD_LABEL["A"]),
        Patch(facecolor=METHOD_COLOR["B"], alpha=0.85, edgecolor="black",
              linewidth=0.7, label=METHOD_LABEL["B"]),
        Patch(facecolor=METHOD_COLOR["C"], alpha=0.85, edgecolor="black",
              linewidth=0.7, label=METHOD_LABEL["C"]),
        Patch(facecolor=METHOD_COLOR["D"], alpha=0.85, edgecolor="black",
              linewidth=0.7, label=METHOD_LABEL["D"]),
    ]
    ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              ncol=4, frameon=False, fontsize=10)


def main():
    ensure_dirs()
    import matplotlib.pyplot as plt

    data = _gather()
    basin_ids = sorted([b["basin_id"] for b in BASINS])

    # Version 1: zoomed to [-0.2, 1.0] for good-basin detail
    fig, ax = plt.subplots(figsize=(13, 6.5))
    _draw_axes(ax, data, basin_ids, y_min=-0.2, y_max=1.0, clip_note=True)
    _add_legend(ax)
    fig.tight_layout()
    out1 = FIGURES_DIR / "fig_main_nse_vs_walltime.png"
    fig.savefig(out1, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out1}")

    # Version 2: full range [-1.0, 1.0]
    fig, ax = plt.subplots(figsize=(13, 6.5))
    _draw_axes(ax, data, basin_ids, y_min=-1.0, y_max=1.0, clip_note=True)
    _add_legend(ax)
    fig.tight_layout()
    out2 = FIGURES_DIR / "fig_main_nse_vs_walltime_full.png"
    fig.savefig(out2, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out2}")


if __name__ == "__main__":
    main()
