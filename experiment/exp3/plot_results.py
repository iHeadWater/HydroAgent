"""Generate Exp3 v2 paper figures."""

from __future__ import annotations

import json
from pathlib import Path

from common import CONDITIONS, FIGURES_DIR, OUTPUT_ROOT, TASKS, ensure_dirs


COLORS = {"K0": "#D95F02", "K1": "#1B9E77", "K2": "#7570B3"}

_TASK_GROUP_LABEL = {
    "execution": "execution",
    "general_diagnosis": "general diagnosis",
    "system_specific_knowledge": "system-specific knowledge",
}


def _load_compiled() -> dict:
    path = OUTPUT_ROOT / "compiled_results.json"
    if not path.exists():
        raise SystemExit(
            f"Compiled results not found: {path}\n"
            "Run `python experiment/exp3/compile_results.py` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value):
    return value if isinstance(value, (int, float)) else None


def _plot_success_vs_tokens(compiled: dict, out: Path) -> None:
    import matplotlib.pyplot as plt

    rows = compiled.get("core_results", [])
    if not rows or not compiled.get("trial_records"):
        raise SystemExit("No Exp3 trial records found.")

    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    points = {}
    for row in rows:
        cid = row["condition_id"]
        x = _num(row.get("mean_total_tokens"))
        y = _num(row.get("task_success_rate"))
        if x is None or y is None:
            continue
        points[cid] = (x, y)
        ax.scatter(x, y, s=140, color=COLORS.get(cid, "#666666"),
                   label=f"{cid} {row['condition_name']}", zorder=5)
        ax.annotate(f"{cid}\n{y:.0%}", (x, y), textcoords="offset points",
                    xytext=(12, -5), fontsize=10, fontweight="bold")

    if "K0" in points and "K1" in points:
        x0, y0 = points["K0"]
        x1, y1 = points["K1"]
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color="#888888",
                                   lw=1.5, connectionstyle="arc3,rad=0.15"))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx, my + 0.06, f"+{y1-y0:.0%} (tools)",
                ha="center", fontsize=9, color="#555555")

    if "K1" in points and "K2" in points:
        x1, y1 = points["K1"]
        x2, y2 = points["K2"]
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#888888",
                                   lw=1.5, connectionstyle="arc3,rad=0.15"))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my + 0.06, f"+{y2-y1:.0%} (knowledge)",
                ha="center", fontsize=9, color="#555555")

    ax.set_xlabel("Mean total tokens per run")
    ax.set_ylabel("Task success rate")
    ax.set_ylim(-0.03, 1.12)
    ax.grid(color="#DDDDDD", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_task_heatmap(compiled: dict, out: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    rows = compiled.get("task_level_results", [])
    if not rows or not compiled.get("trial_records"):
        raise SystemExit("No Exp3 task-level records found.")
    lookup = {(r["task_id"], r["condition_id"]): r for r in rows}
    matrix = []
    ylabels = []
    for task in TASKS:
        matrix.append([
            lookup.get((task["task_id"], cond["condition_id"]), {}).get("task_success_rate", float("nan"))
            for cond in CONDITIONS
        ])
        group = _TASK_GROUP_LABEL.get(task.get("task_group", ""), "")
        ylabels.append(f"{task['task_id']} {group}: {task['task_name']}")
    arr = np.array(matrix, dtype=float)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    im = ax.imshow(arr, vmin=0, vmax=1, cmap="YlGnBu")
    ax.set_xticks(range(len(CONDITIONS)))
    ax.set_xticklabels([c["condition_id"] for c in CONDITIONS])
    ax.set_yticks(range(len(TASKS)))
    ax.set_yticklabels(ylabels, fontsize=9)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            if np.isnan(val):
                continue
            text_color = "#FFFFFF" if val > 0.55 else "#111111"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=text_color, fontsize=10, fontweight="bold")
    ax.set_xlabel("Knowledge input condition")
    ax.set_title("Task success rate (K2 only strictly improves over K1 on T4)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ensure_dirs()
    compiled = _load_compiled()
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        raise SystemExit("matplotlib and numpy are required for Exp3 plotting.") from exc

    _plot_success_vs_tokens(compiled, FIGURES_DIR / "fig_exp3_success_vs_tokens.png")
    _plot_task_heatmap(compiled, FIGURES_DIR / "fig_exp3_task_heatmap.png")
    print(f"Saved Exp3 figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
