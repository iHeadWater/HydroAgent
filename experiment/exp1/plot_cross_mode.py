"""Emit paper-grade exp1 figures from table_exp1_cross_mode_summary.csv.

Produces three figures:
  - fig_exp1_per_basin_winner.png: bar chart, 5 basins × 6 methods, with
    per-basin global best highlighted (Findings 3 + 4).
  - fig_exp1_budget_ablation.png:  best NSE vs budget level (M0_min /
    M0_default / M0_max) per basin, with M1_B + M2_B as horizontal
    reference lines (Finding 1).
  - fig_exp1_cost_vs_quality.png:  scatter of (total cost, mean best NSE)
    for each method, separating wall time / tokens / human-attended time.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TABLES = Path(__file__).resolve().parent / "tables"
FIGURES = Path(__file__).resolve().parent / "figures"

CROSS = TABLES / "table_exp1_cross_mode_summary.csv"
AGG = TABLES / "table_exp1_method_aggregate.csv"


def _load_cross():
    out = defaultdict(dict)  # basin -> method -> row
    for r in csv.DictReader(open(CROSS, encoding="utf-8")):
        try:
            r["best_test_NSE"] = float(r["best_test_NSE"])
        except (ValueError, TypeError):
            r["best_test_NSE"] = None
        out[r["basin_id"]][r["method"]] = r
    return out


def _load_agg():
    out = {}
    for r in csv.DictReader(open(AGG, encoding="utf-8")):
        out[r["method"]] = r
    return out


def fig_per_basin_winner():
    cross = _load_cross()
    basins = sorted(cross.keys())
    methods = ["M0_min", "M0", "M0_max", "M2_A", "M2_B", "M1_B"]
    colors = {"M0_min": "#cfd8dc", "M0": "#9aa7af", "M0_max": "#546e7a",
              "M2_A":   "#90caf9", "M2_B": "#1976d2",
              "M1_B":   "#ef5350"}

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(basins))
    width = 0.14
    for i, m in enumerate(methods):
        vals = [cross[b].get(m, {}).get("best_test_NSE") if cross[b].get(m) else None for b in basins]
        vals = [v if isinstance(v, (int, float)) else np.nan for v in vals]
        bars = ax.bar(x + (i - len(methods)/2) * width + width/2, vals,
                      width, label=m, color=colors[m], edgecolor="white", linewidth=0.5)
        # mark winner per basin with a star
    # winner per basin
    for j, b in enumerate(basins):
        valid = [(m, cross[b].get(m, {}).get("best_test_NSE")) for m in methods]
        valid = [(m, v) for m, v in valid if isinstance(v, (int, float))]
        if not valid: continue
        wmeth, wval = max(valid, key=lambda x: x[1])
        wi = methods.index(wmeth)
        ax.scatter(j + (wi - len(methods)/2) * width + width/2, wval + 0.015,
                   marker='*', s=180, color='#d4af37', edgecolor='black', linewidth=0.7, zorder=10)

    ax.set_xticks(x)
    ax.set_xticklabels(basins, rotation=0)
    ax.set_ylabel("Best test NSE (out of 1 or 5 trials)")
    ax.set_title("Per-basin best test NSE across 6 methods (★ = per-basin global best)")
    ax.legend(ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.10), frameon=False, fontsize=9)
    ax.axhline(0.5, color="#bbbbbb", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_ylim(-0.05, 0.85)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "fig_exp1_per_basin_winner.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def fig_budget_ablation():
    cross = _load_cross()
    basins = sorted(cross.keys())
    budgets = ["M0_min", "M0", "M0_max"]
    labels = ["min\n(rep=100,ngs=10)", "default\n(rep=500,ngs=50)", "max\n(rep=2000,ngs=200)"]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for b in basins:
        ys = [cross[b].get(m, {}).get("best_test_NSE") for m in budgets]
        ys = [y if isinstance(y, (int, float)) else np.nan for y in ys]
        ax.plot(range(len(budgets)), ys, marker="o", label=b, linewidth=1.5)
        # M1_B and M2_B as horizontal references
        m1 = cross[b].get("M1_B", {}).get("best_test_NSE")
        if isinstance(m1, (int, float)):
            ax.axhline(m1, color=ax.get_lines()[-1].get_color(), linestyle=":", alpha=0.45, linewidth=1)

    ax.set_xticks(range(len(budgets)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Best test NSE (single SCE-UA run)")
    ax.set_title("M0 budget ablation per basin (dotted lines = M1_B human ceiling)")
    ax.legend(title="Basin", ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "fig_exp1_budget_ablation.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def fig_cost_quality():
    agg = _load_agg()
    methods = ["M0_min", "M0", "M0_max", "M2_A", "M2_B", "M1_B"]
    colors = {"M0_min": "#cfd8dc", "M0": "#9aa7af", "M0_max": "#546e7a",
              "M2_A":   "#90caf9", "M2_B": "#1976d2", "M1_B": "#ef5350"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    # Left: wall time vs mean best NSE
    for m in methods:
        if m not in agg: continue
        wall = float(agg[m]["total_wall_s_panel"])
        nse = float(agg[m]["mean_best_NSE"])
        ax1.scatter(wall, nse, s=160, color=colors[m], edgecolor="black", linewidth=0.6, label=m, zorder=5)
        ax1.annotate(m, (wall, nse), xytext=(7, 7), textcoords="offset points", fontsize=9)
    ax1.set_xlabel("Total panel wall time (s, log scale)")
    ax1.set_ylabel("Mean best test NSE (over 5 basins)")
    ax1.set_xscale("log")
    ax1.set_title("Wall-time vs NSE")
    ax1.grid(alpha=0.3)

    # Right: human-attended time + LLM tokens vs NSE
    for m in methods:
        if m not in agg: continue
        human = float(agg[m]["total_active_s_panel"])
        tokens = float(agg[m]["total_tokens_panel"])
        nse = float(agg[m]["mean_best_NSE"])
        # combine: x = human_s + tokens/1000 (rough cost equivalence)
        x = human if human > 0 else max(tokens / 1000, 1)
        ax2.scatter(x, nse, s=160, color=colors[m], edgecolor="black", linewidth=0.6, zorder=5)
        kind = f"\n(human-attended)" if human > 0 else (f"\n({tokens} tokens)" if tokens > 0 else "\n(zero-cost)")
        ax2.annotate(m + kind, (x, nse), xytext=(7, 7), textcoords="offset points", fontsize=9)
    ax2.set_xlabel("Cost: human-attended seconds OR ktokens (log scale)")
    ax2.set_ylabel("Mean best test NSE")
    ax2.set_xscale("log")
    ax2.set_title("Human-attended time vs LLM tokens")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    out = FIGURES / "fig_exp1_cost_vs_quality.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig_per_basin_winner()
    fig_budget_ablation()
    fig_cost_quality()


if __name__ == "__main__":
    main()
