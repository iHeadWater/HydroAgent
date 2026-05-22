"""Generate Exp3 v2 paper figures."""

from __future__ import annotations

import json
from pathlib import Path

from common import CONDITIONS, FIGURES_DIR, OUTPUT_ROOT, TASKS, ensure_dirs


COLORS = {"K0": "#D95F02", "K1": "#1B9E77", "K2": "#7570B3"}


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
        raise SystemExit("No Exp3 trial records found. Run run_knowledge_ablation.py before plotting.")

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    for row in rows:
        cid = row["condition_id"]
        x = _num(row.get("mean_total_tokens"))
        y = _num(row.get("task_success_rate"))
        if x is None or y is None:
            continue
        ax.scatter(x, y, s=120, color=COLORS.get(cid, "#666666"), label=f"{cid} {row['condition_name']}")
        ax.annotate(cid, (x, y), textcoords="offset points", xytext=(8, 8), fontsize=11)

    ax.set_xlabel("Mean total tokens per run")
    ax.set_ylabel("Task success rate")
    ax.set_ylim(-0.03, 1.03)
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
        raise SystemExit("No Exp3 task-level records found. Run the experiment before plotting.")
    lookup = {(r["task_id"], r["condition_id"]): r for r in rows}
    matrix = []
    for task in TASKS:
        matrix.append([
            lookup.get((task["task_id"], cond["condition_id"]), {}).get("task_success_rate", float("nan"))
            for cond in CONDITIONS
        ])
    arr = np.array(matrix, dtype=float)

    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    im = ax.imshow(arr, vmin=0, vmax=1, cmap="YlGnBu")
    ax.set_xticks(range(len(CONDITIONS)))
    ax.set_xticklabels([c["condition_id"] for c in CONDITIONS])
    ax.set_yticks(range(len(TASKS)))
    ax.set_yticklabels([f"{t['task_id']} {t['task_name']}" for t in TASKS])
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            label = "" if np.isnan(val) else f"{val:.2f}"
            ax.text(j, i, label, ha="center", va="center", color="#111111", fontsize=9)
    ax.set_xlabel("Knowledge input condition")
    ax.set_title("Task success rate")
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
