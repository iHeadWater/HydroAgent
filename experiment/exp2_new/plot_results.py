"""Figures for exp2_new: 4 methods (A/B/C/D) on 10 good/medium basins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import FIGURES_DIR, RESULTS_DIR, ensure_dirs

METHOD_COLOR = {"A": "#888888", "B": "#D95F02", "C": "#7570B3", "D": "#1B9E77"}
METHOD_LABEL = {"A": "A standard SCE-UA",
                "B": "B Zhu direct eval",
                "C": "C LLM + local search",
                "D": "D HydroAgent feedback"}


def _f(v):
    return float(v) if isinstance(v, (int, float)) else None


def _load():
    p = RESULTS_DIR.parent / "exp2_compiled.json"
    if not p.exists():
        raise SystemExit(f"Run compile_results.py first: {p} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _plot_method_comparison(compiled, out):
    """Grouped bars: per basin, 4 methods side-by-side, test NSE."""
    import matplotlib.pyplot as plt
    import numpy as np
    rows = compiled["per_task"]
    rows.sort(key=lambda r: ({"easy": 0, "medium": 1, "hard": 2}.get(r["difficulty"], 9), r["basin_id"]))
    basins = [r["basin_id"] for r in rows]
    x = np.arange(len(basins))
    methods = ["A", "B", "C", "D"]
    w = 0.20
    fig, ax = plt.subplots(figsize=(13, 5.5))
    for i, m in enumerate(methods):
        vals = [_f(r.get(f"{m}_best_test_nse")) or 0.0 for r in rows]
        ax.bar(x + (i - 1.5) * w, vals, w, label=METHOD_LABEL[m], color=METHOD_COLOR[m])
        for j, v in enumerate(vals):
            if abs(v) > 0.005:
                ax.text(x[j] + (i - 1.5) * w, v + (0.015 if v >= 0 else -0.05),
                        f"{v:.2f}", ha="center", fontsize=6)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r['basin_id']}\n{r['difficulty']}" for r in rows], fontsize=7)
    ax.axhline(0.0, color="#444", linewidth=0.8)
    ax.set_ylabel("Best test NSE")
    ax.set_title("Exp2 (new): 4-method comparison on good/medium basins")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=9)
    ax.grid(axis="y", color="#DDD", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_convergence(compiled, out):
    """Best-so-far test NSE vs iteration, per method. One panel per basin.

    Display method order (per user 2026-05-28):
      A standard SCE-UA, B HydroAgent (M2), C Zhu direct eval,
      D direct eval + scipy local search.
    The compiled trajectory uses legacy keys A/B/C/D where B=Zhu, C=LLM-local,
    D=HydroAgent. We remap below.
    """
    import matplotlib.pyplot as plt
    import math
    # display_key -> legacy_compile_key (where data is stored)
    DISPLAY_TO_LEGACY = {"A": "A", "B": "D", "C": "B", "D": "C"}
    NEW_COLOR = {"A": "#9E9E9E", "B": "#7FBC7F", "C": "#F4A582", "D": "#9E9AC8"}
    NEW_LABEL = {
        "A": "A standard SCE-UA",
        "B": "B HydroAgent",
        "C": "C Zhu direct eval",
        "D": "D direct eval + scipy local search",
    }

    traj = compiled["trajectory"]
    from collections import defaultdict
    by_basin = defaultdict(lambda: defaultdict(list))
    for r in traj:
        by_basin[r["basin_id"]][r["method"]].append(r)
    basins = sorted(by_basin.keys())
    n = len(basins)
    cols = 5
    rows_n = math.ceil(n / cols)
    fig, axes = plt.subplots(rows_n, cols, figsize=(cols * 3, rows_n * 2.5), sharey=False)
    axes = axes.flatten() if rows_n > 1 else [axes] if cols == 1 else axes
    # PLOT MODE: NSE relative to A baseline (NSE_method - NSE_A).
    # This pins A to y=0 so B's positive gain over A is visually obvious.
    DRAW_ORDER = ["C", "D", "B"]  # A is the y=0 reference line
    Z_BY_METHOD = {"A": 2, "C": 3, "D": 4, "B": 6}
    PHI = 0.618  # golden-ratio: place A baseline line at this fraction of axes height
    MAX_DOWN = 1.0  # show at most this much below A; lower values are clipped off-panel
    for i, bid in enumerate(basins):
        ax = axes[i] if n > 1 else axes
        a_records = by_basin[bid][DISPLAY_TO_LEGACY["A"]]
        a_nse = _f(a_records[0].get("best_so_far_test_nse")) if a_records else None
        if a_nse is None:
            ax.set_title(f"{bid} (A=NA)", fontsize=9)
            continue

        # Collect absolute NSE values across B/C/D (+A) for axis sizing
        all_vals = [a_nse]
        for display_m in DRAW_ORDER:
            for r in by_basin[bid][DISPLAY_TO_LEGACY[display_m]]:
                v = _f(r.get("best_so_far_test_nse"))
                if v is not None:
                    all_vals.append(v)
        vmax = max(all_vals)
        vmin = max(min(all_vals), a_nse - MAX_DOWN)  # clip extreme low values

        # Size axes so a_nse sits at PHI of axes height (from bottom):
        #   (a_nse - y_lo)/(y_hi - y_lo) = PHI
        # need_up covers vmax above A; need_down covers vmin below A.
        need_up = max(vmax - a_nse, 0.02)
        need_down = max(a_nse - vmin, 0.02)
        scale = max(need_up / (1 - PHI), need_down / PHI) * 1.15
        y_hi = a_nse + scale * (1 - PHI)
        y_lo = a_nse - scale * PHI
        ax.set_ylim(y_lo, y_hi)

        # A baseline (absolute NSE), now at PHI of axes height
        ax.axhline(a_nse, color="#999999", linewidth=1.2, linestyle="--",
                   alpha=0.85, zorder=Z_BY_METHOD["A"])

        import numpy as np
        best_gain = None  # (gain, color) of the single method that beats A the most
        for display_m in DRAW_ORDER:
            rs = sorted(by_basin[bid][DISPLAY_TO_LEGACY[display_m]],
                        key=lambda r: r.get("iteration", 0))
            if not rs:
                continue
            xs = [r["iteration"] for r in rs]
            ys = [_f(r["best_so_far_test_nse"]) for r in rs]
            if display_m == "B":
                ax.plot(xs, ys, color=NEW_COLOR["B"], linewidth=2.4,
                        zorder=Z_BY_METHOD["B"])
                ys_arr = np.array([y if y is not None else a_nse for y in ys])
                ax.fill_between(xs, a_nse, ys_arr, where=(ys_arr > a_nse),
                                color=NEW_COLOR["B"], alpha=0.3, zorder=Z_BY_METHOD["B"] - 1,
                                interpolate=True)
            else:
                ax.plot(xs, ys, color=NEW_COLOR[display_m], linewidth=1.3,
                        alpha=0.9, zorder=Z_BY_METHOD[display_m])
            final = ys[-1]
            if final is not None and (final - a_nse) > 0.005:
                g = final - a_nse
                if best_gain is None or g > best_gain[0]:
                    best_gain = (g, NEW_COLOR[display_m])

        # Label only the single best gain over A, in the top-left corner
        # (clear of the rising curves which end at the right).
        if best_gain is not None:
            ax.annotate(f"+{best_gain[0]:.3f}", xy=(0.03, 0.93), xycoords="axes fraction",
                        color=best_gain[1], fontsize=8, fontweight="bold",
                        ha="left", va="top", zorder=10)
        ax.set_title(bid, fontsize=9)
        ax.grid(color="#DDD", linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)
    for j in range(n, len(axes)):
        axes[j].axis("off")

    # Legend at bottom, horizontal, 4 columns
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], color="#999999", linewidth=1.2, linestyle="--",
               label=NEW_LABEL["A"] + " (ref. line)"),
        Line2D([0], [0], color=NEW_COLOR["B"], linewidth=2.2,
               label=NEW_LABEL["B"]),
        Line2D([0], [0], color=NEW_COLOR["C"], linewidth=1.3,
               label=NEW_LABEL["C"]),
        Line2D([0], [0], color=NEW_COLOR["D"], linewidth=1.3,
               label=NEW_LABEL["D"]),
    ]
    fig.legend(handles=legend_handles, loc="lower center",
               bbox_to_anchor=(0.5, 0.00), ncol=4, frameon=False, fontsize=9)
    fig.text(0.5, 0.06, "iteration", ha="center", fontsize=10)
    fig.text(0.005, 0.55, "Best-so-far test NSE",
             va="center", rotation="vertical", fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0.02, 0.10, 1, 0.99))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_efficiency(compiled, out):
    """NSE vs total model-evaluations (or tokens) - efficiency frontier."""
    import matplotlib.pyplot as plt
    import numpy as np
    agg = compiled["aggregate"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for r in agg:
        x = r["total_wall_s"]
        y = _f(r["mean_best_test_nse"]) or 0
        c = METHOD_COLOR[r["method"]]
        ax.scatter(x, y, s=200, color=c, edgecolors="black", linewidths=1, zorder=3, label=METHOD_LABEL[r["method"]])
        ax.annotate(f"{r['method']}", (x, y), fontsize=11, fontweight="bold",
                    ha="center", va="center", color="white", zorder=4)
    ax.set_xlabel("Total wall time (s, summed across all basins)")
    ax.set_ylabel("Mean best test NSE")
    ax.set_title("Exp2 (new): Efficiency frontier (mean NSE vs total compute)")
    ax.grid(color="#DDD", linewidth=0.7); ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    ensure_dirs()
    compiled = _load()
    try:
        import matplotlib  # noqa
    except ImportError as e:
        raise SystemExit("matplotlib required") from e
    _plot_method_comparison(compiled, FIGURES_DIR / "fig_method_comparison.png")
    _plot_convergence(compiled, FIGURES_DIR / "fig_convergence.png")
    _plot_efficiency(compiled, FIGURES_DIR / "fig_efficiency.png")
    print(f"Saved -> {FIGURES_DIR}")


if __name__ == "__main__":
    main()
