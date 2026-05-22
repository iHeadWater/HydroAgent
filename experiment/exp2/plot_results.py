"""Plot paper-facing Exp2 v2 figures from compiled records."""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path
from typing import Any

from common import FIGURES_DIR, METHODS, OUTPUT_ROOT, ensure_dirs


METHOD_ORDER = ["A", "B", "C", "D"]
METHOD_LABELS = {
    "A": "A SCE-UA",
    "B": "B Direct",
    "C": "C Local",
    "D": "D Feedback",
}


def _load_compiled() -> dict[str, Any]:
    path = OUTPUT_ROOT / "compiled_results.json"
    if not path.exists():
        raise SystemExit(
            f"Compiled results not found: {path}\n"
            "Run `python experiment/exp2/compile_results.py` after the method runners."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _metric(record: dict[str, Any], period: str, name: str) -> float | None:
    return _finite((record.get(f"{period}_metrics") or {}).get(name))


def _quantile(values: list[float], q: float) -> float | None:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return clean[lo]
    weight = pos - lo
    return clean[lo] * (1 - weight) + clean[hi] * weight


def _task_label(task_id: str) -> str:
    basin, model = task_id.rsplit("_", 1)
    return f"{basin[-4:]}-{model.upper()}"


def _plot_method_comparison(compiled: dict[str, Any], out: Path) -> None:
    import matplotlib.pyplot as plt

    rows = compiled.get("core_results", [])
    task_ids = [r["task_id"] for r in rows]
    if not task_ids:
        raise SystemExit("No core result rows found. Run at least one method runner before plotting.")
    has_numeric = any(
        _finite(r.get(f"{method}_test_{metric_name}")) is not None
        for r in rows
        for method in METHOD_ORDER
        for metric_name in ("NSE", "KGE")
    )
    if not has_numeric:
        raise SystemExit("No numeric test NSE/KGE values found. Run method scripts before plotting.")

    x = list(range(len(task_ids)))
    width = 0.18
    colors = {"A": "#5B8DEF", "B": "#D95F02", "C": "#1B9E77", "D": "#7570B3"}

    fig, axes = plt.subplots(2, 1, figsize=(max(8.5, len(task_ids) * 1.15), 7.2), sharex=True)
    for ax, metric_name in zip(axes, ["NSE", "KGE"]):
        for idx, method in enumerate(METHOD_ORDER):
            values = [_finite(r.get(f"{method}_test_{metric_name}")) for r in rows]
            offsets = [v + (idx - 1.5) * width for v in x]
            ax.bar(
                offsets,
                [v if v is not None else float("nan") for v in values],
                width=width,
                label=METHOD_LABELS[method],
                color=colors[method],
                alpha=0.86,
            )
        ax.axhline(0.0, color="#888888", linewidth=0.8)
        ax.set_ylabel(f"Test {metric_name}")
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.7, alpha=0.8)
        ax.set_axisbelow(True)

    axes[0].legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels([_task_label(t) for t in task_ids], rotation=35, ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _test_nse_of_train_selected_best(rows: list[dict[str, Any]]) -> list[float | None]:
    best_train: float | None = None
    best_test: float | None = None
    out: list[float | None] = []
    for row in rows:
        train_nse = _metric(row, "train", "NSE")
        test_nse = _metric(row, "test", "NSE")
        if train_nse is not None and (best_train is None or train_nse > best_train):
            best_train = train_nse
            best_test = test_nse
        out.append(best_test)
    return out


def _trajectories(records: list[dict[str, Any]]) -> dict[str, list[list[float | None]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        grouped[(record.get("method"), record.get("task_id"))].append(record)

    out: dict[str, list[list[float | None]]] = {"B": [], "C": [], "D": []}
    for (method, _task_id), rows in grouped.items():
        if method in ("B", "C"):
            ordered = sorted(rows, key=lambda r: int(r.get("iteration") or 0))
            out[method].append(_test_nse_of_train_selected_best(ordered))
        elif method == "D":
            for record in rows:
                out[method].append(_test_nse_of_train_selected_best(record.get("history", [])))
    return out


def _plot_trajectories(compiled: dict[str, Any], out: Path) -> None:
    import matplotlib.pyplot as plt

    records = compiled.get("records", [])
    traj = _trajectories(records)
    colors = {"B": "#D95F02", "C": "#1B9E77", "D": "#7570B3"}

    fig, ax = plt.subplots(figsize=(8.3, 4.8))
    has_data = False
    for method in ["B", "C", "D"]:
        sequences = [seq for seq in traj.get(method, []) if seq]
        if not sequences:
            continue
        has_data = True
        max_len = max(len(seq) for seq in sequences)
        xs = list(range(1, max_len + 1))
        medians: list[float | None] = []
        lows: list[float | None] = []
        highs: list[float | None] = []
        for idx in range(max_len):
            vals = [seq[idx] for seq in sequences if idx < len(seq) and seq[idx] is not None]
            vals = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
            medians.append(_quantile(vals, 0.50))
            lows.append(_quantile(vals, 0.25))
            highs.append(_quantile(vals, 0.75))
        y = [v if v is not None else float("nan") for v in medians]
        lo = [v if v is not None else float("nan") for v in lows]
        hi = [v if v is not None else float("nan") for v in highs]
        ax.plot(xs, y, marker="o", linewidth=2.0, color=colors[method], label=METHOD_LABELS[method])
        ax.fill_between(xs, lo, hi, color=colors[method], alpha=0.16, linewidth=0)

    if not has_data:
        raise SystemExit("No B/C/D trajectory records found. Run those method scripts before plotting.")

    ax.set_xlabel("LLM iteration / feedback round")
    ax.set_ylabel("Test NSE of train-selected best")
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.grid(color="#DDDDDD", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ensure_dirs()
    compiled = _load_compiled()
    if not compiled.get("records"):
        raise SystemExit("No experiment records found. Run method scripts and compile_results.py before plotting.")
    try:
        import matplotlib  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. Install it in the project environment "
            "or run only compile_results.py for table outputs."
        ) from exc

    _plot_method_comparison(compiled, FIGURES_DIR / "fig43_method_comparison.png")
    _plot_trajectories(compiled, FIGURES_DIR / "fig44_search_trajectories.png")
    print(f"Saved figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
