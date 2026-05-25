"""Emit experiment/exp1/tables/table_exp1_per_trial.csv.

Per-trial row with: method, basin_id, trial_idx, objective, budget_level,
range_policy, stop_flag, train/test NSE+KGE, llm tokens (prompt/completion/
cached/total), llm_decision_time_s, wall_time_s, active_seconds.

Reads every method's trials.jsonl under results/paper/exp1_v2/. Methods with
no run yet are silently skipped. The intent is to give the paper agent a
single sortable table when discussing per-trial cost and per-basin trajectory
without having to parse 4 separate jsonl files.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP1_A     = ROOT / "results" / "paper" / "exp1_v2"            # Mode A (preset)
EXP1_B     = ROOT / "results" / "paper" / "exp1_v2_modeb"      # Mode B canonical (live)
EXP1_B_V6  = ROOT / "results" / "paper" / "exp1_v2_modeb_m2_v6"  # last full v6 backup
TABLES = Path(__file__).resolve().parent / "tables"

# For M2_B, prefer the canonical live dir if it has ≥ N_FULL records (a full
# 25-trial run); otherwise fall back to the most-recent backed-up version (v6)
# so paper analysis stays usable while a new M2_B rerun is in progress.
import json as _json
def _pick_m2b_root() -> Path:
    live = EXP1_B / "hydroagent_menu" / "trials.jsonl"
    if live.exists():
        n = sum(1 for _ in open(live, encoding="utf-8"))
        if n >= 18:  # at least most of 5 basins × 4 trials worth
            return EXP1_B
    return EXP1_B_V6 if (EXP1_B_V6 / "hydroagent_menu" / "trials.jsonl").exists() else EXP1_B

_M2B_ROOT = _pick_m2b_root()

# All methods × both modes + the M0 budget ablation.
# Method label format: M{0,1,2,3}_{A,B} except the M0 ablation variants which
# carry the budget level in their label so paper text can cite them directly.
METHODS = [
    # (label,         root_dir,    subdir,                 mode_letter)
    ("M0_A_min",      EXP1_A,      "default_script_min",     "A"),
    ("M0_A",          EXP1_A,      "default_script",         "A"),
    ("M0_A_max",      EXP1_A,      "default_script_max",     "A"),
    ("M1_A",          EXP1_A,      "human_script",           "A"),
    ("M2_A",          EXP1_A,      "hydroagent_menu",        "A"),
    ("M3_A",          EXP1_A,      "random_menu",            "A"),
    ("M0_B",          EXP1_B,      "default_script",         "B"),
    ("M1_B",          EXP1_B,      "human_script",           "B"),
    ("M2_B",          _M2B_ROOT,   "hydroagent_menu",        "B"),
]


def _metric(rec: dict, period: str, name: str):
    m = rec.get(f"{period}_metrics") or {}
    v = m.get(name)
    return v if isinstance(v, (int, float)) else None


def _tok(rec: dict, field: str) -> int:
    t = rec.get("llm_tokens") or {}
    return t.get(field) or 0


def main() -> None:
    rows = []
    for label, root, sub, mode_letter in METHODS:
        path = root / sub / "trials.jsonl"
        if not path.exists():
            continue
        records = [json.loads(l) for l in open(path, encoding="utf-8")]
        # trial_idx may be None in older M2 records; sort by record order then.
        for ord_idx, r in enumerate(records, start=1):
            dec = r.get("decision") or {}
            ap = r.get("algorithm_params") or {}
            rows.append({
                "method": label,
                "mode": mode_letter,
                "basin_id": r.get("basin_id"),
                "model": r.get("model"),
                "trial_idx": r.get("trial_idx") or ord_idx,
                "objective": dec.get("objective"),
                "budget_level": dec.get("budget_level"),
                "range_policy": dec.get("range_policy"),
                "rep":    ap.get("rep"),
                "ngs":    ap.get("ngs"),
                "kstop":  ap.get("kstop"),
                "peps":   ap.get("peps"),
                "pcento": ap.get("pcento"),
                "stop_flag": dec.get("stop"),
                "notes": (dec.get("notes") or "")[:120],
                "train_NSE": _metric(r, "train", "NSE"),
                "train_KGE": _metric(r, "train", "KGE"),
                "test_NSE":  _metric(r, "test",  "NSE"),
                "test_KGE":  _metric(r, "test",  "KGE"),
                "prompt_tokens":     _tok(r, "prompt_tokens"),
                "completion_tokens": _tok(r, "completion_tokens"),
                "cached_tokens":     _tok(r, "cached_tokens"),
                "total_tokens":      _tok(r, "total_tokens"),
                "llm_decision_time_s": (r.get("llm_tokens") or {}).get("decision_elapsed_s") or 0,
                "wall_time_s":         r.get("wall_time_s") or 0,
                "active_seconds":      r.get("active_seconds") or 0,
                "boundary_hits":       ";".join(
                    (h.get("name", str(h)) if isinstance(h, dict) else str(h))
                    for h in (r.get("boundary_hits") or [])
                ),
                "error":               r.get("error") or "",
            })
    rows.sort(key=lambda r: (r["method"], r["basin_id"], r["model"], r["trial_idx"]))
    if not rows:
        print("No exp1 trials found.")
        return
    TABLES.mkdir(parents=True, exist_ok=True)
    out = TABLES / "table_exp1_per_trial.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} per-trial rows -> {out}")
    # quick summary
    from collections import defaultdict
    by_m = defaultdict(int)
    tok_m = defaultdict(int)
    wall_m = defaultdict(float)
    for r in rows:
        by_m[r["method"]] += 1
        tok_m[r["method"]] += r["total_tokens"]
        wall_m[r["method"]] += r["wall_time_s"]
    for m in by_m:
        print(f"  {m}: {by_m[m]} trials | total_tokens={tok_m[m]} | total_wall_s={wall_m[m]:.0f}")


if __name__ == "__main__":
    main()
