"""Figures for new Experiment 1: M0 static vs M2 LLM-adaptive.

Generates:
  fig_m0_vs_m2.png         : per-basin grouped bars, ordered easy->hard
  fig_m2_convergence.png   : best-so-far NSE vs generation per basin
  fig_m2_ngs_evolution.png : ngs choice per generation per basin (heatmap)
  fig_basin_map.png        : CONUS map of 20 basins, colored by M2 best NSE
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import BASINS, FIGURES_DIR, M2_DIR, M0_DIR, ensure_dirs

DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2}
BASIN_META = {b["basin_id"]: b for b in BASINS}


def _load():
    p = M0_DIR.parent.parent / "exp1_compiled.json"
    if not p.exists():
        raise SystemExit(f"Run compile_results.py first: {p} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _f(v):
    return float(v) if isinstance(v, (int, float)) else None


def _plot_m0_vs_m2(compiled, out):
    import matplotlib.pyplot as plt
    import numpy as np

    rows = compiled["per_basin"]
    labels = [f"{r['basin_id']}\n{r['difficulty']}" for r in rows]
    m0 = [_f(r["m0_test_nse"]) or 0.0 for r in rows]
    m2 = [_f(r["m2_best_test_nse"]) or 0.0 for r in rows]
    x = np.arange(len(rows))
    w = 0.38
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.bar(x - w/2, m0, w, label="M0 static (ngs=20 + wide range)", color="#888888")
    ax.bar(x + w/2, m2, w, label="M2 LLM-adaptive", color="#1B9E77")
    for xi, (a, b) in enumerate(zip(m0, m2)):
        if abs(a) > 0.001:
            ax.text(xi - w/2, a + (0.02 if a > 0 else -0.05), f"{a:.2f}", ha="center", fontsize=7)
        if abs(b) > 0.001:
            ax.text(xi + w/2, b + (0.02 if b > 0 else -0.05), f"{b:.2f}", ha="center", fontsize=7)
    ax.axhline(0.0, color="#444", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7, rotation=0)
    ax.set_ylabel("Best test NSE")
    ax.set_title("Exp1 (new): M0 static baseline vs M2 LLM-adaptive (per basin)")
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    ax.grid(axis="y", color="#DDD", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_m2_convergence(compiled, out):
    import matplotlib.pyplot as plt

    trials = compiled["m2_generations"]
    by_basin = {}
    for t in trials:
        by_basin.setdefault(t["basin_id"], []).append(t)
    if not by_basin:
        return
    fig, ax = plt.subplots(figsize=(10, 6))
    cmap = plt.get_cmap("tab20")
    sorted_basins = sorted(by_basin.items(), key=lambda kv: (DIFF_ORDER.get(BASIN_META.get(kv[0], {}).get("difficulty"), 9), kv[0]))
    for i, (bid, ts) in enumerate(sorted_basins):
        ts.sort(key=lambda r: r.get("generation_idx", 0))
        xs = [t["generation_idx"] for t in ts]
        ys = [_f(t["best_so_far_nse"]) for t in ts]
        diff = BASIN_META.get(bid, {}).get("difficulty", "")
        ax.plot(xs, ys, marker="o", markersize=4, color=cmap(i % 20), label=f"{bid} ({diff})")
    ax.set_xlabel("M2 generation")
    ax.set_ylabel("Best-so-far test NSE")
    ax.set_title("Exp1 (new): M2 LLM-adaptive convergence per basin")
    ax.legend(frameon=False, fontsize=6, ncol=2, loc="lower right")
    ax.grid(color="#DDD", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_ngs_evolution(compiled, out):
    """Heatmap of LLM-chosen ngs per generation per basin."""
    import matplotlib.pyplot as plt
    import numpy as np

    trials = compiled["m2_generations"]
    by_basin = {}
    for t in trials:
        by_basin.setdefault(t["basin_id"], []).append(t)
    if not by_basin:
        return
    sorted_basins = sorted(by_basin.keys(), key=lambda b: (DIFF_ORDER.get(BASIN_META.get(b, {}).get("difficulty"), 9), b))
    max_gen = max(t.get("generation_idx", 0) for t in trials)
    matrix = np.full((len(sorted_basins), max_gen), np.nan)
    for i, bid in enumerate(sorted_basins):
        for t in by_basin[bid]:
            g = t.get("generation_idx", 0)
            ngs = t.get("ngs")
            if g and isinstance(ngs, (int, float)):
                matrix[i, g-1] = ngs
    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(matrix, aspect="auto", cmap="viridis", vmin=10, vmax=100)
    ax.set_xticks(np.arange(max_gen))
    ax.set_xticklabels([f"G{i+1}" for i in range(max_gen)])
    ax.set_yticks(np.arange(len(sorted_basins)))
    ax.set_yticklabels([f"{b} ({BASIN_META.get(b,{}).get('difficulty','?')})" for b in sorted_basins], fontsize=8)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{int(v)}", ha="center", va="center", color="white" if v < 60 else "black", fontsize=7)
    plt.colorbar(im, ax=ax, label="ngs (LLM chose)")
    ax.set_title("Exp1 (new): LLM-chosen ngs per generation per basin")
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_basin_map(compiled, out):
    """CONUS map of the selected basins for the basin-SELECTION narrative.

    Colored by HUC-02 region (geographic spread), no NSE / no title — this is
    the figure used when introducing the pool, before any calibration is run.
    """
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import numpy as np
    from configs.private import DATASET_DIR

    C = next(Path(DATASET_DIR).glob("**/camels_clim.txt")).parent
    topo = {}
    with open(C / "camels_topo.txt", encoding="utf-8") as f:
        hdr = f.readline().strip().split(";")
        for line in f:
            if line.strip():
                p = line.strip().split(";")
                topo[p[0].zfill(8)] = dict(zip(hdr, p))

    # Selected basins with their HUC from exp1_new common.BASINS
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import BASINS
    sel = {b["basin_id"]: b for b in BASINS}

    fig, ax = plt.subplots(figsize=(13, 7))
    # Background: all 671 CAMELS gauges (light grey)
    all_lats = [float(topo[b]["gauge_lat"]) for b in topo]
    all_lons = [float(topo[b]["gauge_lon"]) for b in topo]
    ax.scatter(all_lons, all_lats, c="#DDDDDD", s=6, alpha=0.5, zorder=1,
               label="CAMELS-US (671 gauges)")

    # Selected basins colored by HUC-02 region
    hucs = sorted({b["huc"] for b in BASINS})
    cmap = cm.get_cmap("tab20", len(hucs))
    huc_color = {h: cmap(i) for i, h in enumerate(hucs)}

    for bid, b in sel.items():
        if bid not in topo:
            continue
        lat = float(topo[bid]["gauge_lat"]); lon = float(topo[bid]["gauge_lon"])
        ax.scatter([lon], [lat], color=huc_color[b["huc"]], s=170,
                   edgecolors="black", linewidths=0.9, zorder=3)
        ax.annotate(bid, (lon, lat), fontsize=6.5, ha="center", va="bottom",
                    xytext=(0, 7), textcoords="offset points", zorder=4)

    # HUC legend (region color swatches)
    from matplotlib.lines import Line2D
    huc_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=huc_color[h],
               markeredgecolor="black", markersize=9, label=f"HUC {h}")
        for h in hucs
    ]
    bg_handle = Line2D([0], [0], marker="o", color="w", markerfacecolor="#DDDDDD",
                       markersize=7, label="CAMELS-US (671)")
    ax.legend(handles=[bg_handle] + huc_handles, loc="lower right",
              ncol=3, fontsize=8, frameon=True, framealpha=0.9,
              title=f"{len(BASINS)} selected basins by HUC-02 region")

    ax.set_xlim(-126, -66); ax.set_ylim(24, 50)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
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
    _plot_m0_vs_m2(compiled, FIGURES_DIR / "fig_m0_vs_m2.png")
    _plot_m2_convergence(compiled, FIGURES_DIR / "fig_m2_convergence.png")
    _plot_ngs_evolution(compiled, FIGURES_DIR / "fig_m2_ngs_evolution.png")
    _plot_basin_map(compiled, FIGURES_DIR / "fig_basin_map.png")
    print(f"Saved figures -> {FIGURES_DIR}")


if __name__ == "__main__":
    main()
