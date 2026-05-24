"""DiagScore: diagnostic reasoning quality rubric (Exp 3 / paper §4.3).

5 dimensions × 0/1/2 scoring, normalized to [0, 1].

Dimensions:
  D1 Problem identification    — does the agent name the actual issue?
  D2 Evidence citation         — does the agent cite specific numbers / boundary hits?
  D3 Hydrological causality    — is there a physical causal chain?
  D4 Actionability             — is the recommendation specific and executable?
  D5 Limit acknowledgment      — does the agent honestly bound its claims?

Each dimension scored 0 / 1 / 2 per rubric (see _annot/diag_rubric.md).
DiagScore = (D1+D2+D3+D4+D5) / 10  ∈ [0, 1].

This module provides:
  - load_rubric(): returns dimension definitions
  - DiagScoreCSV: reader/writer for the 2-rater CSV templates
  - cohens_kappa(): per-dimension and overall agreement
  - aggregate(): merge human + LLM scores into a final DataFrame
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Iterable

DIMENSIONS = ["D1", "D2", "D3", "D4", "D5"]
DIM_NAMES = {
    "D1": "Problem identification",
    "D2": "Evidence citation",
    "D3": "Hydrological causality",
    "D4": "Actionability",
    "D5": "Limit acknowledgment",
}


def score_to_normalized(scores: dict) -> float:
    """Convert {D1..D5: 0/1/2} dict to normalized [0,1] DiagScore."""
    total = sum(int(scores.get(d, 0)) for d in DIMENSIONS)
    return round(total / (len(DIMENSIONS) * 2), 3)


def cohens_kappa(rater1: list[int], rater2: list[int], k_levels: int = 3) -> float:
    """Cohen's kappa for two raters on ordinal scores in {0..k_levels-1}.

    No external dependency — computes from scratch.
    Returns kappa ∈ [-1, 1]; 1 = perfect agreement, 0 = chance, < 0 = worse.
    """
    if len(rater1) != len(rater2) or not rater1:
        return float("nan")
    n = len(rater1)
    p_o = sum(1 for a, b in zip(rater1, rater2) if a == b) / n
    # Marginal proportions
    c1 = Counter(rater1)
    c2 = Counter(rater2)
    p_e = sum((c1[k] / n) * (c2[k] / n) for k in range(k_levels))
    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return round((p_o - p_e) / (1 - p_e), 3)


def read_csv(path: str | Path) -> list[dict]:
    """Read a DiagScore CSV.

    Expected columns: task_id, condition, D1, D2, D3, D4, D5, notes (optional).
    Returns list of dicts; scores cast to int when possible.
    """
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out = dict(r)
            for d in DIMENSIONS:
                if d in out and out[d] != "":
                    try:
                        out[d] = int(out[d])
                    except (ValueError, TypeError):
                        pass
            rows.append(out)
    return rows


def aggregate(
    human_csv: str | Path,
    llm_csv: str | Path | None = None,
) -> dict:
    """Compute per-dimension and overall agreement + per-task DiagScores.

    Returns:
      {
        "kappa_per_dim": {"D1": ..., ..., "overall": ...},
        "rows": [ {task_id, condition, human_DS, llm_DS, mean_DS, ...} ],
        "n_items": int,
      }
    """
    human = read_csv(human_csv)
    if llm_csv is None:
        # human-only report
        rows = []
        for h in human:
            ds = score_to_normalized(h)
            rows.append({
                **{k: h.get(k) for k in ("task_id", "condition")},
                "human_DS": ds,
                "mean_DS": ds,
            })
        return {"kappa_per_dim": {}, "rows": rows, "n_items": len(rows)}

    llm = read_csv(llm_csv)
    # Index by (task_id, condition)
    llm_idx = {(r.get("task_id"), r.get("condition")): r for r in llm}

    kappa: dict[str, float] = {}
    rater1_all: list[int] = []
    rater2_all: list[int] = []
    for d in DIMENSIONS:
        r1, r2 = [], []
        for h in human:
            key = (h.get("task_id"), h.get("condition"))
            if key not in llm_idx:
                continue
            if d in h and d in llm_idx[key]:
                try:
                    r1.append(int(h[d]))
                    r2.append(int(llm_idx[key][d]))
                except (ValueError, TypeError):
                    continue
        kappa[d] = cohens_kappa(r1, r2)
        rater1_all.extend(r1)
        rater2_all.extend(r2)
    kappa["overall"] = cohens_kappa(rater1_all, rater2_all)

    rows: list[dict] = []
    for h in human:
        key = (h.get("task_id"), h.get("condition"))
        ds_h = score_to_normalized(h)
        ds_l = score_to_normalized(llm_idx[key]) if key in llm_idx else None
        rows.append({
            "task_id": h.get("task_id"),
            "condition": h.get("condition"),
            "human_DS": ds_h,
            "llm_DS": ds_l,
            "mean_DS": round((ds_h + ds_l) / 2, 3) if ds_l is not None else ds_h,
        })

    return {"kappa_per_dim": kappa, "rows": rows, "n_items": len(rows)}
