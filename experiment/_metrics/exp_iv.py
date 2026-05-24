"""Capability-boundary metrics (Exp 4 / paper §4.4).

Provides:
  Group A:
    - semantic_consistency(): task-level equivalence vs reference
    - clarification_handling(): did agent invoke ask_user when needed?

  Group C:
    - planning_scale_ratio(): planned_subtasks / expected_subtasks
    - completion_ratio(): completed_subtasks / expected_subtasks
    - classify_failure(): 7-class label
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import efficiency, workflow


# ── Group A ───────────────────────────────────────────────────────────────────

def semantic_consistency(
    observed_state: dict,
    reference_state: dict,
    nse_tolerance: float = 0.05,
) -> bool:
    """Task-level equivalence: same (basin, model) AND |ΔNSE|<tol vs reference.

    Args:
        observed_state: agent's final state (must contain basin_id, model_name,
                        and a metrics.NSE or test_metrics.NSE)
        reference_state: gold-standard final state
        nse_tolerance: how much NSE may differ (default 0.05)
    """
    def _nse(s: dict) -> float | None:
        for path in (("test_metrics", "NSE"), ("metrics", "NSE")):
            cur = s
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    cur = None
                    break
            if isinstance(cur, (int, float)):
                return float(cur)
        return None

    if observed_state.get("basin_id") != reference_state.get("basin_id"):
        return False
    if observed_state.get("model_name") != reference_state.get("model_name"):
        return False
    nse_obs = _nse(observed_state)
    nse_ref = _nse(reference_state)
    if nse_obs is None or nse_ref is None:
        return False
    return abs(nse_obs - nse_ref) < nse_tolerance


def clarification_handling(session_jsonl: str | Path) -> int:
    """3-level rating: 0=missed (no ask_user), 1=guessed silently, 2=asked properly.

    Heuristic auto-rating: if `ask_user` tool was invoked at all → 2;
    if completion succeeded without it → 1 (silent default);
    if neither → 0 (no resolution attempt).

    For finer rating, override with human inspection.
    """
    tools = workflow.tool_set(session_jsonl)
    if "ask_user" in tools:
        return 2
    # If session completed at all (>0 tool calls) treat as silent guess
    if efficiency.tool_call_count(session_jsonl) > 0:
        return 1
    return 0


# ── Group C ───────────────────────────────────────────────────────────────────

def planning_scale_ratio(planned_subtasks: int, expected_subtasks: int) -> float | None:
    """planned / expected. Returns None if expected is 0."""
    if expected_subtasks <= 0:
        return None
    return round(planned_subtasks / expected_subtasks, 2)


def completion_ratio(completed_subtasks: int, expected_subtasks: int) -> float | None:
    if expected_subtasks <= 0:
        return None
    return round(min(completed_subtasks, expected_subtasks) / expected_subtasks, 2)


# Failure class labels (7-class)
FAILURE_CLASSES = (
    "task_explosion",          # planning_scale_ratio > 1.5
    "under_planning",          # planning_scale_ratio < 0.7
    "missing_dependency",      # ImportError not handled
    "unregistered_tool",       # called tool not in registry
    "semantic_inconsistency",  # claimed completed but state invalid
    "incomplete_recovery",     # recovery branch tried but did not fix
    "silent_drift",            # never acknowledged failure, ran out of turns
)


def classify_failure(
    *,
    planning_ratio: float | None = None,
    completion: float | None = None,
    saw_import_error: bool = False,
    handled_import_error: bool = False,
    saw_unregistered_tool: bool = False,
    final_state_valid: bool = True,
    claimed_completed: bool = False,
    recovery_attempted: bool = False,
    recovery_succeeded: bool = False,
    used_all_turns: bool = False,
) -> str | None:
    """Return a failure-class label or None if no failure detected.

    Order of evaluation matters (most specific first). Caller passes in
    signals extracted from session JSONL + state.json + agent log.
    """
    if planning_ratio is not None and planning_ratio > 1.5:
        return "task_explosion"
    if planning_ratio is not None and planning_ratio < 0.7:
        return "under_planning"
    if saw_import_error and not handled_import_error:
        return "missing_dependency"
    if saw_unregistered_tool:
        return "unregistered_tool"
    if claimed_completed and not final_state_valid:
        return "semantic_inconsistency"
    if recovery_attempted and not recovery_succeeded:
        return "incomplete_recovery"
    if used_all_turns and not claimed_completed:
        return "silent_drift"
    if completion is not None and completion < 1.0 and not recovery_attempted:
        return "silent_drift"
    return None  # no failure
