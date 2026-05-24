"""Workflow-route metrics: did the agent take a reasonable tool path?

All metrics are computed from a session JSONL (written by
`hydroagent.memory.Memory.log_tool_call`) plus optional task gold standards.

These metrics deliberately DO NOT require the tool sequence to match
exactly — the paper's claim is that knowledge layers influence behavior
at the dispatch/interpretation layer, not at sequence-rigidity level.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import efficiency


def _tool_names(session_jsonl: str | Path) -> list[str]:
    return [e.get("tool", "") for e in efficiency._iter_entries(session_jsonl)]


def tool_set(session_jsonl: str | Path) -> set[str]:
    """Distinct tool names invoked, ignoring order and arguments."""
    return {t for t in _tool_names(session_jsonl) if t}


def core_tool_coverage(
    session_jsonl: str | Path,
    expected_tools: Iterable[str],
) -> float:
    """|observed ∩ expected| / |expected|.

    Args:
        session_jsonl: path to session JSONL
        expected_tools: gold-standard core tools the task ought to use

    Returns 1.0 = full coverage; 0.0 = none. Bounded in [0,1].
    """
    expected = set(expected_tools)
    if not expected:
        return 1.0
    observed = tool_set(session_jsonl)
    return round(len(expected & observed) / len(expected), 3)


def detour_count(
    session_jsonl: str | Path,
    expected_tools: Iterable[str],
) -> int:
    """Number of tool calls beyond what the gold standard requires.

    detour = total_tool_calls − |expected ∩ observed|.
    A negative would mean the agent skipped expected tools (we still
    report the raw difference; caller can interpret).
    """
    total = efficiency.tool_call_count(session_jsonl)
    expected = set(expected_tools)
    observed = tool_set(session_jsonl)
    return total - len(expected & observed)


def repeat_call_count(session_jsonl: str | Path) -> int:
    """Re-export from efficiency for convenience."""
    return efficiency.repeat_call_count(session_jsonl)


def terminal_state_validity(
    state_json: str | Path,
    required_fields: Iterable[str],
) -> bool:
    """Did the agent reach a valid terminal state?

    Args:
        state_json: path to the agent's state.json (or any JSON
                    capturing final state); for calibration tasks
                    this is typically the agent workspace state.
        required_fields: keys that MUST exist (and be truthy)
                         e.g. ["calibration_dir"] or
                         ["calibration_dir", "metrics.NSE"]
                         Nested fields supported via dot notation.

    Returns True iff all required fields present and truthy.
    """
    p = Path(state_json)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    for field in required_fields:
        cur = data
        for key in field.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return False
        if not cur:  # None / 0 / empty string / empty dict all fail
            return False
    return True


def summary(
    session_jsonl: str | Path,
    expected_tools: Iterable[str],
    state_json: str | Path | None = None,
    state_required: Iterable[str] | None = None,
) -> dict:
    """Compact workflow-metric report for one session."""
    out = {
        "core_tool_coverage": core_tool_coverage(session_jsonl, expected_tools),
        "detour_count": detour_count(session_jsonl, expected_tools),
        "repeat_call_count": repeat_call_count(session_jsonl),
        "tools_observed": sorted(tool_set(session_jsonl)),
    }
    if state_json and state_required:
        out["terminal_state_valid"] = terminal_state_validity(state_json, state_required)
    return out
