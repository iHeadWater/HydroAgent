"""M2 HydroAgent/LLM menu controller for Exp1 v2.

The LLM does not calculate parameters or metrics. It only selects the next
menu item from a controlled hyperparameter space; hydromodel executes every
calibration/evaluation trial.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path

from common import (
    BUDGET_LEVELS,
    MAX_TRIALS,
    OBJECTIVES,
    RANGE_POLICIES,
    MenuDecision,
    append_jsonl,
    best_record,
    ensure_dirs,
    flatten_metric,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the controlled menu controller for a hydrological calibration experiment.
You must choose only from the allowed menu. Numerical calibration will be done by hydromodel,
not by you. Your goal is to reduce human diagnostic effort while keeping test NSE/KGE non-inferior.

Return exactly one JSON object with:
{"objective": "NSE|KGE|LOGNSE", "budget_level": "quick|default|deep",
 "range_policy": "default|climate_prior|wide|boundary_expand",
 "stop": true|false, "notes": "short evidence-based reason"}
No markdown, no extra text."""


def _json_from_text(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _build_user_prompt(task: dict, attrs: dict, history: list[dict]) -> str:
    compact_history = []
    for record in history:
        compact_history.append({
            "trial_idx": record.get("trial_idx"),
            "decision": record.get("decision"),
            "train_NSE": flatten_metric(record, "train", "NSE"),
            "test_NSE": flatten_metric(record, "test", "NSE"),
            "train_KGE": flatten_metric(record, "train", "KGE"),
            "test_KGE": flatten_metric(record, "test", "KGE"),
            "boundary_hits": record.get("boundary_hits", []),
        })
    return json.dumps({
        "task": {
            "task_id": task["task_id"],
            "basin_id": task["basin_id"],
            "model": task["model"],
            "climate_zone": task["climate_zone"],
        },
        "basin_attributes": {
            k: attrs.get(k)
            for k in ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
            if attrs.get(k) is not None
        },
        "allowed_menu": {
            "objective": OBJECTIVES,
            "budget_level": BUDGET_LEVELS,
            "range_policy": RANGE_POLICIES,
            "max_trials": MAX_TRIALS,
        },
        "history": compact_history,
        "decision_guidance": [
            "Use climate_prior on the first trial when basin attributes are informative.",
            "Use boundary_expand only when previous best has boundary_hits.",
            "Use deep only when metrics are poor or previous improvement is still plausible.",
            "Set stop=true when the best result is already satisfactory or additional trials are unlikely to help.",
        ],
    }, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing LLM trial log")
    parser.add_argument("--max-trials", type=int, default=MAX_TRIALS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("hydroagent_menu")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    all_records = read_jsonl(trial_log)
    new_records = []

    for task in iter_tasks(smoke=args.smoke):
        task_history = [r for r in all_records if r.get("task_id") == task["task_id"]]
        attrs = get_basin_attrs(task["basin_id"], cfg)
        workspace = out_dir / "controller_sessions" / task["task_id"]
        agent = HydroAgent(
            workspace=workspace,
            ui=ConsoleUI(mode="dev"),
            prompt_mode="minimal",
            config_override={"max_turns": 1},
        )

        for trial_idx in range(len(task_history) + 1, min(args.max_trials, MAX_TRIALS) + 1):
            # Trial 1 is forced to the default menu so that M2's best-of-N is
            # always >= M0 (default baseline). This eliminates the failure mode
            # observed in v1 where the LLM picked climate_prior on trial 1 and
            # the basin's best NSE stayed below default for the rest of the
            # budget (e.g. 06885500 stuck at 0.458 < M0 0.505).
            if trial_idx == 1:
                decision = MenuDecision(
                    objective="NSE",
                    budget_level="default",
                    range_policy="default",
                    stop=False,
                    notes="Trial 1 forced to default as baseline anchor (M2 v2 policy).",
                ).normalized()
                token_delta = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "total_tokens": 0,
                    "decision_elapsed_s": 0.0,
                }
                raw = "[trial 1 forced to default; no LLM call]"
            else:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(task, attrs, task_history)},
                ]
                before = agent.llm.tokens.summary()
                t_decision = time.time()
                response = agent.llm.chat(messages)
                decision_elapsed = time.time() - t_decision
                after = agent.llm.tokens.summary()
                raw = response.text or ""
                data = _json_from_text(raw)
                decision = MenuDecision(
                    objective=data.get("objective", "NSE"),
                    budget_level=data.get("budget_level", "default"),
                    range_policy=data.get("range_policy", "default"),
                    stop=bool(data.get("stop", False)),
                    notes=data.get("notes", raw[:200]),
                ).normalized()
                token_delta = {
                    "calls": after.get("calls", 0) - before.get("calls", 0),
                    "prompt_tokens": after.get("prompt_tokens", 0) - before.get("prompt_tokens", 0),
                    "completion_tokens": after.get("completion_tokens", 0) - before.get("completion_tokens", 0),
                    "cached_tokens": after.get("cached_tokens", 0) - before.get("cached_tokens", 0),
                    "total_tokens": after.get("total_tokens", 0) - before.get("total_tokens", 0),
                    "decision_elapsed_s": round(decision_elapsed, 3),
                }
            previous_best = best_record(task_history)
            record = run_trial(
                method="M2",
                task=task,
                trial_idx=trial_idx,
                decision=decision,
                cfg=cfg,
                run_dir=out_dir,
                active_seconds=0.0,
                llm_tokens=token_delta,
                previous_best=previous_best,
            )
            record["controller_response"] = raw[:2000]
            append_jsonl(trial_log, record)
            all_records.append(record)
            task_history.append(record)
            new_records.append(record)
            LOGGER.info(
                "M2 %s trial %d: test NSE=%s tokens=%s",
                task["task_id"], trial_idx, flatten_metric(record, "test", "NSE"), token_delta.get("total_tokens"),
            )
            if decision.stop and trial_idx > 1:
                break

    write_json(out_dir / "summary.json", {"method": "M2", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} new M2 trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
