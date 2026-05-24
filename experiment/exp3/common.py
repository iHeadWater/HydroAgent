"""Shared utilities for Exp3 v2 knowledge-input ablation."""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_ROOT = ROOT / "results" / "paper" / "exp3_v2"
RUNS_DIR = OUTPUT_ROOT / "runs"
TABLES_DIR = Path(__file__).resolve().parent / "tables"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"
RAW_RECORDS = OUTPUT_ROOT / "trial_records.jsonl"

DEFAULT_REPEATS = 3

ALLOWED_TOOLS = [
    "validate_basin",
    "calibrate_model",
    "evaluate_model",
    "generate_code",
    "run_code",
    "inspect_dir",
    "read_file",
    "ask_user",
]

CONDITIONS = [
    {
        "condition_id": "K0",
        "condition_name": "plain_llm",
        "description": "No tools, no skill index, no knowledge base, no memory.",
        "tools_enabled": False,
        "knowledge_level": "none",
    },
    {
        "condition_id": "K1",
        "condition_name": "tools_only",
        "description": "Same required tools as K2, but no skill/domain/adapter/memory knowledge.",
        "tools_enabled": True,
        "knowledge_level": "none",
    },
    {
        "condition_id": "K2",
        "condition_name": "full_knowledge",
        "description": "Same required tools as K1 plus full HydroAgent knowledge inputs.",
        "tools_enabled": True,
        "knowledge_level": "full",
    },
]
CONDITION_BY_ID = {c["condition_id"]: c for c in CONDITIONS}

TASKS = [
    {
        "task_id": "T1",
        "task_name": "standard_calibration",
        "query": (
            "Calibrate the GR4J model for CAMELS basin 12025000 using SCE-UA. "
            "Validate the basin first, then report train and test NSE/KGE from real tool outputs."
        ),
        "expected_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "expected_first": "validate_basin",
        "forbidden_tools": [],
        "success_type": "calibration",
        "description": "Basic hydrological execution chain.",
    },
    {
        "task_id": "T2",
        "task_name": "model_comparison",
        "query": (
            "For basin 03439000, compare GR4J and XAJ calibration performance. "
            "Run real calibration/evaluation for both models and choose the better model based on NSE/KGE."
        ),
        "expected_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "expected_first": "validate_basin",
        "forbidden_tools": [],
        "success_type": "model_comparison",
        "description": "Two-model workflow and metric-based synthesis.",
    },
    {
        "task_id": "T3",
        "task_name": "code_analysis",
        "query": (
            "Generate and run Python code to calculate the runoff coefficient and flow-duration "
            "curve for basin 12025000 using real available basin data. Do not calibrate a model."
        ),
        "expected_tools": ["generate_code", "run_code"],
        "expected_first": "generate_code",
        "expected_first_alt": "validate_basin",
        "forbidden_tools": ["calibrate_model", "evaluate_model"],
        "success_type": "code_analysis",
        "description": "Route to code/data analysis rather than calibration.",
    },
    {
        "task_id": "T4",
        "task_name": "failure_diagnosis",
        "query": (
            "A previous XAJ calibration for basin 03439000 ended with train NSE=0.105. "
            "Four parameters were near upper bounds: CS=0.98 of [0,1], L=9.8 of [1,10], "
            "CI=0.89 of [0,0.9], EX=1.49 of [1,1.5]. Explain what this implies physically, "
            "whether simply expanding ranges is likely to help, and what the next calibration step should be."
        ),
        "expected_tools": [],
        "expected_first": None,
        "forbidden_tools": ["calibrate_model", "evaluate_model", "generate_code", "run_code"],
        "success_type": "diagnosis",
        "description": "Knowledge-sensitive reasoning without unnecessary computation.",
    },
]
TASK_BY_ID = {t["task_id"]: t for t in TASKS}

MINIMAL_SYSTEM_PROMPT = """You are HydroAgent in a controlled ablation experiment.
Answer the user's hydrological task as accurately as possible.
If tools are available, use real tool outputs for executable claims.
If tools are unavailable, do not pretend that computations were executed."""

_BLOCKED_READ_PATTERNS = [
    "hydroagent/knowledge/",
    "hydroagent\\knowledge\\",
    "hydroagent/skills/",
    "hydroagent\\skills\\",
    "hydroagent/adapters/",
    "hydroagent\\adapters\\",
]

_SIMULATED_MARKERS = [
    "simulated data",
    "synthetic data",
    "dummy data",
    "random data",
    "mock data",
    "placeholder data",
    "fake data",
    "np.random",
    "numpy.random",
]

_DIAGNOSIS_KEYWORDS = [
    "boundary",
    "upper bound",
    "range",
    "expand",
    "model structure",
    "structure",
    "mismatch",
    "switch model",
    "parameter",
    "recession",
    "routing",
    "runoff",
    "baseflow",
    "边界",
    "上界",
    "参数",
    "模型结构",
    "换模型",
    "扩展",
    "汇流",
    "退水",
]


@dataclass(frozen=True)
class TrialKey:
    condition_id: str
    task_id: str
    repeat: int

    @property
    def run_id(self) -> str:
        return f"{self.condition_id}_{self.task_id}_r{self.repeat:02d}"


def ensure_dirs() -> None:
    for path in (OUTPUT_ROOT, RUNS_DIR, TABLES_DIR, FIGURES_DIR):
        path.mkdir(parents=True, exist_ok=True)


def estimate_text_tokens(text: str) -> int:
    return max(0, len(json.dumps(text or "", ensure_ascii=False)) // 3)


def estimate_json_tokens(data: Any) -> int:
    return max(0, len(json.dumps(data, ensure_ascii=False, default=str)) // 3)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def iter_trial_keys(
    *,
    conditions: list[str] | None = None,
    task_ids: list[str] | None = None,
    repeats: int = DEFAULT_REPEATS,
    smoke: bool = False,
) -> list[TrialKey]:
    selected_conditions = conditions or [c["condition_id"] for c in CONDITIONS]
    selected_tasks = task_ids or [t["task_id"] for t in TASKS]
    if smoke:
        selected_conditions = selected_conditions[: min(3, len(selected_conditions))]
        selected_tasks = selected_tasks[:1]
        repeats = 1
    return [
        TrialKey(condition_id=cid, task_id=tid, repeat=rep)
        for cid in selected_conditions
        for tid in selected_tasks
        for rep in range(1, repeats + 1)
    ]


def schema_name(schema: dict[str, Any]) -> str:
    return ((schema.get("function") or {}).get("name") or schema.get("name") or "")


def filter_tool_schemas(schemas: list[dict[str, Any]], allowed: list[str] = ALLOWED_TOOLS) -> list[dict[str, Any]]:
    allowed_set = set(allowed)
    return [s for s in schemas if schema_name(s) in allowed_set]


def load_knowledge_pack(max_chars_per_file: int = 900, max_total_chars: int = 9000) -> str:
    sections = []
    for folder in [ROOT / "hydroagent" / "knowledge", ROOT / "hydroagent" / "skills"]:
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                continue
            if not text:
                continue
            if len(text) > max_chars_per_file:
                text = text[:max_chars_per_file] + "\n...(truncated for Exp3 prompt budget)"
            rel = path.relative_to(ROOT).as_posix()
            sections.append(f"### {rel}\n{text}")
    pack = "\n\n---\n\n".join(sections)
    if len(pack) > max_total_chars:
        pack = pack[:max_total_chars] + "\n...(Exp3 knowledge pack truncated to prompt budget)"
    return pack


def _blocked_read_file(original: Callable) -> Callable:
    def read_file_guard(path: str, limit: int = 200) -> dict:
        normalized = str(path).replace("\\", "/").lower()
        if any(p.replace("\\", "/").lower() in normalized for p in _BLOCKED_READ_PATTERNS):
            return {
                "success": False,
                "error": "blocked_by_exp3_tools_only_condition",
                "path": path,
                "hint": "K1 tools-only condition blocks skill, adapter, and knowledge files.",
            }
        return original(path=path, limit=limit)

    return read_file_guard


@contextmanager
def apply_condition(agent, condition_id: str) -> Iterator[dict[str, Any]]:
    """Temporarily apply a controlled knowledge-input condition to a HydroAgent."""
    condition = CONDITION_BY_ID[condition_id]
    original = {
        "tools": agent.tools,
        "tool_schemas": agent.tool_schemas,
        "system_prompt_override": getattr(agent, "_system_prompt_override", ""),
        "prompt_mode": getattr(agent, "_prompt_mode", "full"),
        "inject_adapter_docs": getattr(agent, "_inject_adapter_docs", True),
        "inject_policies": getattr(agent, "_inject_policies", True),
        "load_domain": agent._load_domain_knowledge,
        "available_skills": agent.skill_registry.available_skills_prompt,
        "get_cognitive": agent.skill_registry.get_cognitive_prompt,
        "profile_ctx": agent.memory.format_basin_profiles_for_context,
        "load_mem": agent.memory.load_knowledge,
        "available_agents": agent.agent_registry.available_agents_prompt,
    }
    original_tools = dict(agent.tools)
    original_schemas = list(agent.tool_schemas)
    knowledge_pack = load_knowledge_pack() if condition_id == "K2" else ""
    allowed_tools = {k: v for k, v in original_tools.items() if k in ALLOWED_TOOLS}
    allowed_schemas = filter_tool_schemas(original_schemas)

    try:
        agent._system_prompt_override = MINIMAL_SYSTEM_PROMPT
        agent._inject_policies = False
        agent._inject_adapter_docs = False
        agent._prompt_mode = "minimal"
        agent.skill_registry.available_skills_prompt = lambda *a, **kw: ""
        agent.skill_registry.get_cognitive_prompt = lambda: ""
        agent._load_domain_knowledge = lambda q: ""
        agent.memory.format_basin_profiles_for_context = lambda ids: ""
        agent.memory.load_knowledge = lambda: ""
        agent.agent_registry.available_agents_prompt = lambda: ""

        if condition_id == "K0":
            agent.tools = {}
            agent.tool_schemas = []
        elif condition_id == "K1":
            guarded_tools = dict(allowed_tools)
            if "read_file" in guarded_tools:
                guarded_tools["read_file"] = _blocked_read_file(guarded_tools["read_file"])
            agent.tools = guarded_tools
            agent.tool_schemas = allowed_schemas
        elif condition_id == "K2":
            agent.tools = allowed_tools
            agent.tool_schemas = allowed_schemas
            agent._system_prompt_override = (
                MINIMAL_SYSTEM_PROMPT
                + "\n\n## Exp3 Full Knowledge Pack\n"
                + knowledge_pack
            )
            agent._inject_policies = True
            agent._inject_adapter_docs = True
            agent._prompt_mode = "full"
            agent.skill_registry.available_skills_prompt = original["available_skills"]
            agent.skill_registry.get_cognitive_prompt = original["get_cognitive"]
            agent._load_domain_knowledge = original["load_domain"]
            agent.memory.format_basin_profiles_for_context = original["profile_ctx"]
            agent.memory.load_knowledge = original["load_mem"]
            agent.agent_registry.available_agents_prompt = original["available_agents"]
        else:
            raise ValueError(f"Unknown Exp3 condition: {condition_id}")

        prompt_preview = agent._build_system_prompt("exp3 prompt measurement")
        metadata = {
            **condition,
            "active_tool_names": sorted(agent.tools.keys()),
            "tool_schema_names": sorted(schema_name(s) for s in agent.tool_schemas),
            "system_prompt_tokens_est": estimate_text_tokens(prompt_preview),
            "tool_schema_tokens_est": estimate_json_tokens(agent.tool_schemas),
            "knowledge_input_tokens_est": estimate_text_tokens(knowledge_pack),
            "knowledge_pack_chars": len(knowledge_pack),
        }
        yield metadata
    finally:
        agent.tools = original["tools"]
        agent.tool_schemas = original["tool_schemas"]
        agent._system_prompt_override = original["system_prompt_override"]
        agent._prompt_mode = original["prompt_mode"]
        agent._inject_adapter_docs = original["inject_adapter_docs"]
        agent._inject_policies = original["inject_policies"]
        agent._load_domain_knowledge = original["load_domain"]
        agent.skill_registry.available_skills_prompt = original["available_skills"]
        agent.skill_registry.get_cognitive_prompt = original["get_cognitive"]
        agent.memory.format_basin_profiles_for_context = original["profile_ctx"]
        agent.memory.load_knowledge = original["load_mem"]
        agent.agent_registry.available_agents_prompt = original["available_agents"]


def tool_sequence(tool_log: list[dict[str, Any]]) -> list[str]:
    return [str(entry.get("tool", "")) for entry in tool_log if entry.get("tool")]


def first_meaningful_tool(tools: list[str]) -> str | None:
    for name in tools:
        if name != "read_file":
            return name
    return tools[0] if tools else None


def contains_required_tools(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return True
    remaining = list(actual)
    for name in expected:
        if name not in remaining:
            return False
        remaining.remove(name)
    return True


def _text_from_record(record: dict[str, Any], final_response: str) -> str:
    texts = [final_response or ""]
    for entry in record.get("tool_log", []):
        texts.append(str(entry.get("result_summary", "")))
    return "\n".join(texts).lower()


def detect_hallucination(record: dict[str, Any], final_response: str) -> bool:
    # NEW: honest-disclaimer escape — if the agent clearly states it has no
    # access to tools and provides NO concrete fabricated metric values, this
    # is a controlled failure, not hallucination. Without this guard, K0's
    # honest "I do not have access to tools" responses get flagged as
    # hallucination just because they mention 'calibration' or 'NSE' as
    # context-explaining keywords.
    fr_lower = (final_response or "").lower()
    honest_phrases = [
        "do not have access", "cannot provide", "tools are unavailable",
        "tools.{0,20}not available", "unable to execute", "cannot execute",
        "无法访问", "没有工具", "工具不可用", "无法执行", "无法获取",
    ]
    is_honest = any(re.search(p, fr_lower) for p in honest_phrases)
    has_fabricated_value = bool(re.search(
        r"\b(nse|kge|rmse)\s*[=:]\s*-?\d+\.?\d*", fr_lower
    ))
    if is_honest and not has_fabricated_value:
        return False  # Honest "no access" statement without fake numbers

    text = _text_from_record(record, final_response)
    actual = record.get("actual_tools", [])
    if any(marker in text for marker in _SIMULATED_MARKERS):
        return True

    # For diagnosis tasks (T4), the prompt itself supplies the NSE/parameter
    # facts and explicitly forbids calibrate/evaluate tools. The agent
    # discussing those facts is the requested behavior, not hallucination.
    task_id = record.get("task_id")
    task = TASK_BY_ID.get(task_id, {}) if task_id else {}
    if task.get("success_type") == "diagnosis":
        return False

    claims_metrics = any(k in text for k in ["nse", "kge", "rmse", "calibrat", "率定", "评价"])
    if claims_metrics and not any(t in actual for t in ["calibrate_model", "evaluate_model", "run_code"]):
        return True
    claims_done = any(k in text for k in ["completed", "finished", "完成", "已完成", "得到结果"])
    if claims_done and record["condition_id"] == "K0" and record["task_id"] in ("T1", "T2", "T3"):
        return True
    return False


def _count_successful_tool(tool_log: list[dict[str, Any]], tool_name: str) -> int:
    count = 0
    for entry in tool_log:
        if entry.get("tool") != tool_name:
            continue
        summary = str(entry.get("result_summary", "")).lower()
        if "success" in summary and "false" in summary:
            continue
        count += 1
    return count


def evaluate_trial_record(record: dict[str, Any], final_response: str) -> dict[str, Any]:
    task = TASK_BY_ID[record["task_id"]]
    actual = record.get("actual_tools", [])
    first = first_meaningful_tool(actual)
    expected_first = task.get("expected_first")
    expected_first_alt = task.get("expected_first_alt")
    forbidden = task.get("forbidden_tools", [])
    forbidden_hit = any(t in actual for t in forbidden)
    tool_route_success = contains_required_tools(task["expected_tools"], actual) and not forbidden_hit
    if expected_first:
        first_tool_accuracy = first == expected_first or (expected_first_alt and first == expected_first_alt)
    else:
        first_tool_accuracy = True
    hallucination = detect_hallucination(record, final_response)

    success_type = task["success_type"]
    if record["condition_id"] == "K0" and success_type in ("calibration", "model_comparison", "code_analysis"):
        task_success = False
    elif success_type == "calibration":
        task_success = (
            tool_route_success
            and _count_successful_tool(record["tool_log"], "calibrate_model") >= 1
            and _count_successful_tool(record["tool_log"], "evaluate_model") >= 1
            and not hallucination
        )
    elif success_type == "model_comparison":
        task_success = (
            tool_route_success
            and _count_successful_tool(record["tool_log"], "calibrate_model") >= 2
            and _count_successful_tool(record["tool_log"], "evaluate_model") >= 2
            and not hallucination
        )
    elif success_type == "code_analysis":
        task_success = (
            tool_route_success
            and "generate_code" in actual
            and "run_code" in actual
            and not hallucination
        )
    elif success_type == "diagnosis":
        text = _text_from_record(record, final_response)
        keyword_hits = [kw for kw in _DIAGNOSIS_KEYWORDS if kw.lower() in text]
        task_success = len(keyword_hits) >= 3 and not forbidden_hit and not hallucination
    else:
        task_success = tool_route_success and not hallucination

    return {
        "task_success": bool(task_success),
        "tool_route_success": bool(tool_route_success),
        "first_tool_accuracy": bool(first_tool_accuracy),
        "forbidden_tool_hit": bool(forbidden_hit),
        "hallucination": bool(hallucination),
        "first_meaningful_tool": first or "",
    }


def summarize_times(tool_log: list[dict[str, Any]], wall_time_s: float) -> dict[str, float]:
    tool_compute = round(sum(float(e.get("elapsed_s") or 0.0) for e in tool_log), 3)
    return {
        "tool_compute_time_s": tool_compute,
        "llm_decision_time_s": round(max(0.0, wall_time_s - tool_compute), 3),
    }


def token_summary(agent) -> dict[str, int]:
    try:
        return agent.llm.tokens.summary()
    except Exception:
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "total_tokens": 0}


def mean(values: list[Any]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return round(statistics.mean(clean), 6) if clean else None


def rate(values: list[Any]) -> float | None:
    if not values:
        return None
    return round(sum(1 for v in values if bool(v)) / len(values), 6)


def run_wall_clock() -> float:
    return time.time()
