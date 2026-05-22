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
    import matplotlib.pyplot as plt

    rows = [r for r in compiled.get("failure_modes", []) if r.get("condition_id") == "B2"]
    if not rows or not compiled.get("trial_records"):
        raise SystemExit("No B2 recovery records found. Run the experiment before plotting.")
    row = rows[0]
    labels = ["create_skill rate", "recovery success", "mean turns/10", "mean tokens/10k"]
    values = [
        _val(row, "create_skill_rate"),
        _val(row, "recovery_success_rate"),
        _val(row, "mean_recovery_turns") / 10.0,
        _val(row, "mean_recovery_tokens") / 10000.0,
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.bar(labels, values, color=["#7570B3", "#1B9E77", "#5B8DEF", "#D95F02"], alpha=0.88)
    ax.set_ylabel("Normalized value")
    ax.set_title("B2 dynamic recovery cost")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


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
