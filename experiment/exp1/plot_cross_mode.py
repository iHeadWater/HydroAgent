"""Emit paper-grade exp1 figures from table_exp1_cross_mode_summary.csv.

Paper labels (HydroClaw_GMD_0526.docx): only M0_min / M0 / M0_max / M1 / M2
are shown in headline figures. The preset-menu LLM ablation (data column
"M2_A") is dropped from the figures (it remains in the underlying CSV for
the methodology table). Data columns "M1_B" -> "M1", "M2_B" -> "M2".

Produces three figures:
  - fig_exp1_per_basin_winner.png: 5 basins x 5 methods bars + per-basin
    golden-star global best (Findings 3 + 4).
  - fig_exp1_budget_ablation.png:  best NSE vs budget level
    (M0_min / M0 / M0_max) per basin, with M1 as the human-ceiling dotted
    reference (Finding 1).
  - fig_exp1_cost_vs_quality.png:  scatter of (total cost, mean best NSE)
    for the 5 paper methods, separating wall time / tokens / human-attended.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TABLES = Path(__file__).resolve().parent / "tables"
FIGURES = Path(__file__).resolve().parent / "figures"

CROSS = TABLES / "table_exp1_cross_mode_summary.csv"
AGG = TABLES / "table_exp1_method_aggregate.csv"

# Paper labels for headline figures. The preset-menu LLM (data column
# "M2_A") is excluded; "M1_B"/"M2_B" -> "M1"/"M2".
PAPER_METHODS = ["M0_min", "M0", "M0_max", "M1", "M2"]
DATA_KEY = {"M0_min": "M0_min", "M0": "M0", "M0_max": "M0_max",
            "M1": "M1_B", "M2": "M2_B"}
COLORS = {"M0_min": "#cfd8dc", "M0": "#9aa7af", "M0_max": "#546e7a",
          "M1":     "#ef5350", "M2": "#1976d2"}


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

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(basins))
    width = 0.16
    n = len(PAPER_METHODS)
    for i, label in enumerate(PAPER_METHODS):
        key = DATA_KEY[label]
        vals = [cross[b].get(key, {}).get("best_test_NSE") for b in basins]
        vals = [v if isinstance(v, (int, float)) else np.nan for v in vals]
        ax.bar(x + (i - n/2) * width + width/2, vals,
               width, label=label, color=COLORS[label],
               edgecolor="white", linewidth=0.5)
    # Per-basin global best (star) among the 5 paper methods only
    for j, b in enumerate(basins):
        valid = [(label, cross[b].get(DATA_KEY[label], {}).get("best_test_NSE"))
                 for label in PAPER_METHODS]
        valid = [(m, v) for m, v in valid if isinstance(v, (int, float))]
        if not valid:
            continue
        wmeth, wval = max(valid, key=lambda kv: kv[1])
        wi = PAPER_METHODS.index(wmeth)
        ax.scatter(j + (wi - n/2) * width + width/2, wval + 0.015,
                   marker='*', s=180, color='#d4af37',
                   edgecolor='black', linewidth=0.7, zorder=10)

    ax.set_xticks(x)
    ax.set_xticklabels(basins, rotation=0)
    ax.set_ylabel("Best test NSE")
    ax.set_title("Per-basin best test NSE across 5 methods (star = per-basin global best)")
    ax.legend(ncol=n, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              frameon=False, fontsize=10)
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
    labels = ["M0_min\n(rep=100,ngs=10)", "M0\n(rep=500,ngs=50)", "M0_max\n(rep=2000,ngs=200)"]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for b in basins:
        ys = [cross[b].get(m, {}).get("best_test_NSE") for m in budgets]
        ys = [y if isinstance(y, (int, float)) else np.nan for y in ys]
        ax.plot(range(len(budgets)), ys, marker="o", label=b, linewidth=1.5)
        # M1 (human free-form) as horizontal reference per basin
        m1 = cross[b].get(DATA_KEY["M1"], {}).get("best_test_NSE")
        if isinstance(m1, (int, float)):
            ax.axhline(m1, color=ax.get_lines()[-1].get_color(),
                       linestyle=":", alpha=0.45, linewidth=1)

    ax.set_xticks(range(len(budgets)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Best test NSE (single SCE-UA run)")
    ax.set_title("M0 budget ablation per basin (dotted lines = M1 human ceiling)")
    ax.legend(title="Basin", ncol=5, loc="upper center",
              bbox_to_anchor=(0.5, -0.13), frameon=False, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "fig_exp1_budget_ablation.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def fig_cost_quality():
    agg = _load_agg()
    rows = {label: agg.get(DATA_KEY[label]) for label in PAPER_METHODS}
    rows = {k: v for k, v in rows.items() if v}

    nses = [float(v["mean_best_NSE"]) for v in rows.values()]
    y_lo, y_hi = min(nses), max(nses)
    y_pad = (y_hi - y_lo) * 0.18 or 0.05
    YLIM = (y_lo - y_pad, y_hi + y_pad)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))

    # Per-label annotation offsets. Designed so labels do not collide and
    # do not overflow the borders even when three points stack on x=1
    # (zero-cost cluster on the right panel).
    OFFSETS_LEFT = {
        "M0_min": (10,   6,  "left", "bottom"),
        "M0":     (10,  -8,  "left", "top"),
        "M0_max": (-10,  6,  "right", "bottom"),
        "M1":     (-10,  6,  "right", "bottom"),
        "M2":     (10,  -8,  "left", "top"),
    }
    OFFSETS_RIGHT = {
        # zero-cost cluster: spread labels vertically to the right of the dot
        "M0_min": (14,  -4,  "left", "center"),
        "M0":     (14,  -4,  "left", "center"),
        "M0_max": (14,  -4,  "left", "center"),
        "M1":     (-12, -4,  "right", "center"),
        "M2":     (-12, -4,  "right", "center"),
    }

    # Left: wall time vs mean best NSE (single-line labels)
    for label, row in rows.items():
        wall = float(row["total_wall_s_panel"])
        nse = float(row["mean_best_NSE"])
        ax1.scatter(wall, nse, s=160, color=COLORS[label],
                    edgecolor="black", linewidth=0.6, label=label, zorder=5)
        dx, dy, ha, va = OFFSETS_LEFT[label]
        ax1.annotate(label, (wall, nse), xytext=(dx, dy),
                     textcoords="offset points", fontsize=10,
                     ha=ha, va=va)
    walls = [float(r["total_wall_s_panel"]) for r in rows.values()]
    ax1.set_xlim(min(walls) * 0.4, max(walls) * 3.0)
    ax1.set_ylim(*YLIM)
    ax1.set_xlabel("Total panel wall time (s, log scale)")
    ax1.set_ylabel("Mean best test NSE (over 5 basins)")
    ax1.set_xscale("log")
    ax1.set_title("Wall-time vs NSE")
    ax1.grid(alpha=0.3)

    # Right: human-attended seconds (M1) or ktokens (M2); zero-cost cluster
    # at x=1 for M0 variants. Labels are single-line and placed to one side
    # of each marker.
    xs_right = []
    for label, row in rows.items():
        human = float(row["total_active_s_panel"])
        tokens = float(row["total_tokens_panel"])
        nse = float(row["mean_best_NSE"])
        x = human if human > 0 else max(tokens / 1000, 1)
        xs_right.append(x)
        ax2.scatter(x, nse, s=160, color=COLORS[label],
                    edgecolor="black", linewidth=0.6, zorder=5)
        dx, dy, ha, va = OFFSETS_RIGHT[label]
        ax2.annotate(label, (x, nse), xytext=(dx, dy),
                     textcoords="offset points", fontsize=10,
                     ha=ha, va=va, fontweight="bold")
    ax2.set_xlim(min(xs_right) * 0.4, max(xs_right) * 3.0)
    ax2.set_ylim(*YLIM)
    ax2.set_xlabel("Cost (log scale)\n"
                   "M1: human-attended s   |   M2: k tokens   "
                   "|   M0: zero cost (x=1)")
    ax2.set_ylabel("Mean best test NSE")
    ax2.set_xscale("log")
    ax2.set_title("Human-attended time vs LLM tokens")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    out = FIGURES / "fig_exp1_cost_vs_quality.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def fig_cost_money():
    """Variant A: single panel, USD-equivalent cost on x.

    Converts both human-attended seconds and LLM tokens to an estimated
    USD cost so all 5 paper methods land on the same x-axis:
      - M0 variants:  ~$0 (pure local SCE-UA, no human + no LLM).
      - M1:           human time at $30/hr.
      - M2:           DeepSeek-v4-flash blended pricing ~$0.50 / M tokens.
    This is the only view that lets the reader see the "M2 trades human
    attention for ~100x cheaper LLM tokens at near-identical NSE" claim
    in a single direct comparison.
    """
    agg = _load_agg()
    HOURLY_USD = 30.0          # human attended cost
    USD_PER_M_TOKENS = 0.50    # blended deepseek-v4-flash
    EPS_USD = 0.005            # used as a visible "zero-cost" x for M0

    fig, ax = plt.subplots(figsize=(9, 5.5))
    rows = []
    for label in PAPER_METHODS:
        r = agg.get(DATA_KEY[label])
        if not r:
            continue
        nse = float(r["mean_best_NSE"])
        human_usd = float(r["total_active_s_panel"]) / 3600 * HOURLY_USD
        token_usd = float(r["total_tokens_panel"]) / 1e6 * USD_PER_M_TOKENS
        usd = human_usd + token_usd
        x = max(usd, EPS_USD)
        rows.append((label, usd, x, nse))
        ax.scatter(x, nse, s=180, color=COLORS[label],
                   edgecolor="black", linewidth=0.6, zorder=5)

    OFFSETS = {
        "M0_min": ( 14, -8, "left",  "top"),
        "M0":     ( 14,  8, "left",  "bottom"),
        "M0_max": ( 14,  8, "left",  "bottom"),
        "M1":     (-14,  8, "right", "bottom"),
        "M2":     ( 14, -8, "left",  "top"),
    }
    for label, usd, x, nse in rows:
        dx, dy, ha, va = OFFSETS[label]
        suffix = ("  ($0)" if usd < EPS_USD
                  else f"  (${usd:.2f})")
        ax.annotate(label + suffix, (x, nse), xytext=(dx, dy),
                    textcoords="offset points", fontsize=10,
                    ha=ha, va=va, fontweight="bold")

    ax.set_xscale("log")
    nses = [n for _, _, _, n in rows]
    ax.set_xlim(EPS_USD * 0.3, max(x for _, _, x, _ in rows) * 4)
    ax.set_ylim(min(nses) - 0.04, max(nses) + 0.04)
    ax.set_xlabel("Estimated USD cost per 5-trial panel (log scale)\n"
                  "human at $30/hr  |  LLM at $0.50 / 1M tokens "
                  "(deepseek-v4-flash blended)  |  M0 plotted at $0.005")
    ax.set_ylabel("Mean best test NSE (over 5 basins)")
    ax.set_title("Cost vs NSE in USD-equivalent: "
                 "M2 reaches M1's NSE at ~100x lower cost")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "fig_exp1_cost_money.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def fig_cost_decision_time():
    """Variant B: single panel, same-unit decision seconds on x.

    Uses one physical unit (seconds) on x for all methods:
      - M0 variants: 0 s of human/LLM decision time (plotted at x=1
        with a "zero" tag so they land on the log axis).
      - M1: total_active_s_panel (human-typing seconds across the panel).
      - M2: total_llm_dec_s_panel (LLM call latency seconds).
    The token cost of M2 is dropped here on purpose; the comparison is
    strictly about whose clock is ticking (human vs LLM).
    """
    agg = _load_agg()
    EPS_SEC = 1.0  # zero -> 1 s for log placement; flagged in annotation

    fig, ax = plt.subplots(figsize=(9, 5.5))
    rows = []
    for label in PAPER_METHODS:
        r = agg.get(DATA_KEY[label])
        if not r:
            continue
        nse = float(r["mean_best_NSE"])
        if label == "M1":
            sec = float(r["total_active_s_panel"])
            tag = f"  ({sec:.0f} s human)"
        elif label == "M2":
            sec = float(r["total_llm_dec_s_panel"])
            tag = f"  ({sec:.0f} s LLM)"
        else:
            sec = 0.0
            tag = "  (0 s, plotted at x=1)"
        x = max(sec, EPS_SEC)
        rows.append((label, sec, x, nse, tag))
        ax.scatter(x, nse, s=180, color=COLORS[label],
                   edgecolor="black", linewidth=0.6, zorder=5)

    OFFSETS = {
        "M0_min": (14,  -8, "left", "top"),
        "M0":     (14,   0, "left", "center"),
        "M0_max": (14,   8, "left", "bottom"),
        "M1":     (-14,  8, "right", "bottom"),
        "M2":     (-14, -8, "right", "top"),
    }
    for label, sec, x, nse, tag in rows:
        dx, dy, ha, va = OFFSETS[label]
        ax.annotate(label + tag, (x, nse), xytext=(dx, dy),
                    textcoords="offset points", fontsize=10,
                    ha=ha, va=va, fontweight="bold")

    ax.set_xscale("log")
    nses = [n for *_, n, _ in rows]
    xs = [x for _, _, x, _, _ in rows]
    ax.set_xlim(min(xs) * 0.4, max(xs) * 4)
    ax.set_ylim(min(nses) - 0.04, max(nses) + 0.04)
    ax.set_xlabel("Decision time per 5-trial panel (s, log scale)\n"
                  "M1 = human typing seconds   |   M2 = LLM call latency "
                  "  |   M0 = 0 s (no human/LLM, plotted at x=1)")
    ax.set_ylabel("Mean best test NSE (over 5 basins)")
    ax.set_title("Decision-time vs NSE: same physical unit (seconds), "
                 "M2 saves >50% of attention time vs M1")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "fig_exp1_cost_decision_time.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig_per_basin_winner()
    fig_budget_ablation()
    fig_cost_quality()
    fig_cost_money()
    fig_cost_decision_time()


if __name__ == "__main__":
    main()
