"""Generate compact Exp1 v2 paper figures."""

from __future__ import annotations

import collections
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import FIGURES_DIR, OUTPUT_ROOT, best_so_far, flatten_metric


def _load() -> dict:
    path = OUTPUT_ROOT / "compiled_results.json"
    if not path.exists():
        raise FileNotFoundError(f"Run compile_results.py first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _best_by_task(records: list[dict], method: str) -> dict[str, dict]:
    out = {}
    for record in records:
        if record.get("method") != method or not record.get("success"):
            continue
        task_id = record["task_id"]
        current = out.get(task_id)
        if current is None or (flatten_metric(record, "test", "NSE") or -999) > (flatten_metric(current, "test", "NSE") or -999):
            out[task_id] = record
    return out


def figure1_noninferiority(records: list[dict]) -> None:
    human = _best_by_task(records, "M1")
    agent = _best_by_task(records, "M2")
    common = sorted(set(human) & set(agent))
    if not common:
        print("[skip] figure1: need both M1 and M2 results")
        return

    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharex=False, sharey=False)
    for ax, metric in zip(axes, ["NSE", "KGE"]):
        xs = [flatten_metric(human[t], "test", metric) for t in common]
        ys = [flatten_metric(agent[t], "test", metric) for t in common]
        pairs = [(x, y, t) for x, y, t in zip(xs, ys, common) if x is not None and y is not None]
        if not pairs:
            continue
        xs, ys, labels = zip(*pairs)
        lo = min(min(xs), min(ys)) - 0.05
        hi = max(max(xs), max(ys)) + 0.05
        ax.scatter(xs, ys, s=42, color="#2f6db3", alpha=0.85)
        ax.plot([lo, hi], [lo, hi], color="#333", lw=1, label="1:1")
        ax.plot([lo, hi], [lo - 0.02, hi - 0.02], color="#c43", lw=1, ls="--", label="-0.02 margin")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_xlabel(f"Human test {metric}")
        ax.set_ylabel(f"HydroAgent test {metric}")
        ax.set_title(f"Test {metric}")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Figure 1. HydroAgent non-inferiority against human menu tuning")
    fig.tight_layout()
    out = FIGURES_DIR / "fig1_noninferiority.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def _trajectories(records: list[dict], method: str) -> dict[str, list[float | None]]:
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        if record.get("method") == method:
            key = record["task_id"] if method != "M3" else f"{record['task_id']}::r{record.get('repeat_idx', 0)}"
            grouped[key].append(record)
    return {k: best_so_far(v, "NSE") for k, v in grouped.items()}


def _pad(values: list[float | None], length: int) -> list[float | None]:
    if not values:
        return [None] * length
    out = list(values)
    while len(out) < length:
        out.append(out[-1])
    return out[:length]


def figure2_search_efficiency(records: list[dict]) -> None:
    max_len = max((int(r.get("trial_idx", 1)) for r in records), default=1)
    if max_len <= 1:
        print("[skip] figure2: need multi-trial results")
        return

    fig, ax = plt.subplots(figsize=(7, 4.2))
    styles = {
        "M1": ("Human", "#444"),
        "M2": ("HydroAgent", "#2f6db3"),
    }
    x = np.arange(1, max_len + 1)
    for method, (label, color) in styles.items():
        trajs = [_pad(v, max_len) for v in _trajectories(records, method).values()]
        arr = np.array([[np.nan if y is None else y for y in row] for row in trajs], dtype=float)
        if arr.size == 0:
            continue
        med = np.nanmedian(arr, axis=0)
        ax.plot(x, med, marker="o", color=color, label=label)

    random_trajs = [_pad(v, max_len) for v in _trajectories(records, "M3").values()]
    if random_trajs:
        arr = np.array([[np.nan if y is None else y for y in row] for row in random_trajs], dtype=float)
        med = np.nanmedian(arr, axis=0)
        q1 = np.nanpercentile(arr, 25, axis=0)
        q3 = np.nanpercentile(arr, 75, axis=0)
        ax.plot(x, med, marker="o", color="#999", label="Random median")
        ax.fill_between(x, q1, q3, color="#bbb", alpha=0.25, label="Random IQR")

    ax.set_xlabel("Trial")
    ax.set_ylabel("Best-so-far test NSE")
    ax.set_title("Figure 2. Search efficiency under the same menu budget")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = FIGURES_DIR / "fig2_search_efficiency.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def figure_s1_tokens(records: list[dict]) -> None:
    agent = [r for r in records if r.get("method") == "M2"]
    if not agent:
        print("[skip] figureS1: no M2 token records")
        return
    prompt = sum((r.get("llm_tokens") or {}).get("prompt_tokens", 0) for r in agent)
    completion = sum((r.get("llm_tokens") or {}).get("completion_tokens", 0) for r in agent)
    cached = sum((r.get("llm_tokens") or {}).get("cached_tokens", 0) for r in agent)
    fig, ax = plt.subplots(figsize=(4.2, 3.5))
    ax.bar(["prompt", "completion", "cached"], [prompt, completion, cached], color=["#4c78a8", "#f58518", "#54a24b"])
    ax.set_ylabel("Tokens")
    ax.set_title("Figure S1. HydroAgent token breakdown")
    fig.tight_layout()
    out = FIGURES_DIR / "figS1_token_breakdown.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    data = _load()
    records = data.get("trial_records", [])
    figure1_noninferiority(records)
    figure2_search_efficiency(records)
    figure_s1_tokens(records)


if __name__ == "__main__":
    main()
