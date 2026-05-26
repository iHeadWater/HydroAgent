"""Generate Exp4 v2 paper figures."""

from __future__ import annotations

import json

from common import CONDITIONS, FIGURES_DIR, OUTPUT_ROOT, ensure_dirs


def _load_compiled() -> dict:
    path = OUTPUT_ROOT / "compiled_results.json"
    if not path.exists():
        raise SystemExit(
            f"Compiled results not found: {path}\n"
            "Run `python experiment/exp4/compile_results.py` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _val(row: dict, key: str) -> float:
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _plot_failure_stack(compiled: dict, out) -> None:
    import matplotlib.pyplot as plt

    rows = compiled.get("failure_modes", [])
    if not rows or not compiled.get("trial_records"):
        raise SystemExit("No Exp4 trial records found. Run run_boundary_experiment.py before plotting.")
    labels = [r["condition_id"] for r in rows]
    series = [
        ("Success", "task_success_rate", "#1B9E77"),
        ("Controlled failure", "controlled_failure_rate", "#5B8DEF"),
        ("Logic error", "logic_error_rate", "#D95F02"),
        ("Hallucination", "hallucination_rate", "#B2182B"),
    ]
    bottoms = [0.0 for _ in rows]
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    for label, key, color in series:
        vals = [_val(r, key) for r in rows]
        ax.bar(labels, vals, bottom=bottoms, label=label, color=color, alpha=0.88)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Rate")
    ax.set_xlabel("Tool condition")
    ax.legend(frameon=False, ncol=2)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_recovery_cost(compiled: dict, out) -> None:
    """Grouped-bar comparison of dynamic-recovery metrics across all 4 conditions.

    Original chart only showed B2 (create_skill_rate=0 → all bars empty,
    chart looked like a render bug). v2 shows B0/B1/B2/B3 side-by-side on
    the metrics that actually distinguish them: task_success_rate,
    hallucination_rate, ask_user_rate, create_skill_rate. The four-bar layout
    makes the B0→B1 hallucination collapse and the B2→B3 create_skill jump
    visible at a glance.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    fm = {r["condition_id"]: r for r in compiled.get("failure_modes", [])}
    conditions = [c for c in ("B0", "B1", "B2", "B3") if c in fm]
    if not conditions:
        raise SystemExit("No condition rows found in failure_modes.")
    metrics = [
        ("task_success_rate",   "Task success",     "#1B9E77"),
        ("hallucination_rate",  "Hallucination",    "#B2182B"),
        ("ask_user_rate",       "ask_user",         "#5B8DEF"),
        ("create_skill_rate",   "create_skill",     "#7570B3"),
    ]

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    x = np.arange(len(conditions))
    width = 0.20
    for i, (key, label, color) in enumerate(metrics):
        vals = [_val(fm[c], key) for c in conditions]
        ax.bar(x + (i - 1.5) * width, vals, width=width, label=label,
               color=color, edgecolor="white", linewidth=0.6, alpha=0.92)
        # annotate non-zero bars
        for j, v in enumerate(vals):
            if v > 0.001:
                ax.text(x[j] + (i - 1.5) * width, v + 0.015,
                        f"{int(round(v*100))}%", ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{c}\n({_condition_label(c)})" for c in conditions])
    ax.set_ylabel("Rate (n = 20 per condition)")
    ax.set_title("Failure-mode + dynamic-recovery comparison across tool conditions")
    ax.set_ylim(0, 1.0)
    ax.axhline(0.0, color="#888888", linewidth=0.8)
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              frameon=False, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _condition_label(cid: str) -> str:
    return {"B0": "basic", "B1": "full toolchain",
            "B2": "+create_skill", "B3": "+create_skill\n+policy"}.get(cid, cid)


def main() -> None:
    ensure_dirs()
    compiled = _load_compiled()
    try:
        import matplotlib  # noqa: F401
    except ImportError as exc:
        raise SystemExit("matplotlib is required for Exp4 plotting.") from exc

    _plot_failure_stack(compiled, FIGURES_DIR / "fig_exp4_failure_mode_stack.png")
    _plot_recovery_cost(compiled, FIGURES_DIR / "fig_exp4_recovery_cost.png")
    print(f"Saved Exp4 figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
