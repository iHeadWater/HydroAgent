"""Efficiency metrics: tokens, calls, wall-clock time.

All functions take a path to a session JSONL file (one line per tool call,
as written by `hydroagent.memory.Memory.log_tool_call`). New JSONL entries
contain optional `turn_id`, `elapsed_s`, `llm_tokens` fields (added 2026-05);
this module degrades gracefully for older sessions that lack them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator


def _iter_entries(session_jsonl: str | Path) -> Iterator[dict]:
    """Yield each tool-call entry from a session JSONL file."""
    p = Path(session_jsonl)
    if not p.exists():
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def tool_call_count(session_jsonl: str | Path) -> int:
    """Total tool calls in the session (including repeats)."""
    return sum(1 for _ in _iter_entries(session_jsonl))


def _arg_hash(arguments) -> str:
    """Stable hash of tool arguments for repeat detection."""
    try:
        canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        canonical = repr(arguments)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:16]


def useful_tool_count(session_jsonl: str | Path) -> int:
    """Count of distinct (tool_name, args_hash) pairs.

    Two calls to validate_basin with the same basin list count as ONE
    useful tool call (the second is a repeat).
    """
    seen: set[tuple[str, str]] = set()
    for e in _iter_entries(session_jsonl):
        seen.add((e.get("tool", ""), _arg_hash(e.get("arguments", {}))))
    return len(seen)


def repeat_call_count(session_jsonl: str | Path) -> int:
    """Number of redundant repeats = total - useful."""
    return tool_call_count(session_jsonl) - useful_tool_count(session_jsonl)


def llm_call_count(session_jsonl: str | Path) -> int:
    """Number of distinct LLM API calls (turns).

    Counted as the number of entries that carry a `llm_tokens` field
    (which is attached only to the first tool of each turn). For older
    JSONL without this field, falls back to distinct `turn_id` count,
    and finally to total tool_call_count as last-resort.
    """
    n_with_tokens = sum(1 for e in _iter_entries(session_jsonl) if e.get("llm_tokens"))
    if n_with_tokens > 0:
        return n_with_tokens
    turn_ids = {e["turn_id"] for e in _iter_entries(session_jsonl) if "turn_id" in e}
    if turn_ids:
        return len(turn_ids)
    # Last resort: very crude (treats each tool call as a turn)
    return tool_call_count(session_jsonl)


def total_tokens(session_jsonl: str | Path) -> dict:
    """Sum prompt/completion/cached tokens across all turns.

    Returns dict with keys: prompt, completion, cached, total. Returns zeros
    if the JSONL lacks llm_tokens fields.
    """
    p = c = cache = 0
    for e in _iter_entries(session_jsonl):
        tk = e.get("llm_tokens") or {}
        p += tk.get("prompt", 0) or 0
        c += tk.get("completion", 0) or 0
        cache += tk.get("cached", 0) or 0
    return {"prompt": p, "completion": c, "cached": cache, "total": p + c}


def cached_tokens(session_jsonl: str | Path) -> int:
    """Total cached prompt tokens across the session."""
    return total_tokens(session_jsonl)["cached"]


def tokens_per_useful_step(session_jsonl: str | Path) -> float | None:
    """total_tokens / useful_tool_count.

    Returns None if useful_tool_count is 0 OR if no token data is recorded.
    """
    tot = total_tokens(session_jsonl)["total"]
    useful = useful_tool_count(session_jsonl)
    if tot == 0 or useful == 0:
        return None
    return round(tot / useful, 1)


def wall_clock_time(session_jsonl: str | Path) -> float | None:
    """Sum of per-tool elapsed_s across the session.

    Returns None if no entries have elapsed_s (older JSONL).
    Note: this is sum-of-tool-times, NOT end_ts − start_ts. For
    end-to-end wall-clock, prefer the experiment driver's outer timer.
    """
    total = 0.0
    found_any = False
    for e in _iter_entries(session_jsonl):
        if "elapsed_s" in e:
            total += float(e["elapsed_s"])
            found_any = True
    return round(total, 2) if found_any else None


def summary(session_jsonl: str | Path) -> dict:
    """One-stop summary for a session."""
    tt = total_tokens(session_jsonl)
    return {
        "tool_calls": tool_call_count(session_jsonl),
        "useful_tools": useful_tool_count(session_jsonl),
        "repeats": repeat_call_count(session_jsonl),
        "llm_calls": llm_call_count(session_jsonl),
        "tokens": tt,
        "tokens_per_useful_step": tokens_per_useful_step(session_jsonl),
        "wall_clock_s": wall_clock_time(session_jsonl),
    }
