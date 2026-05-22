"""Shared utilities for Exp4 v2 capability-boundary experiment."""

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
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_ROOT = ROOT / "results" / "paper" / "exp4_v2"
RUNS_DIR = OUTPUT_ROOT / "runs"
TABLES_DIR = Path(__file__).resolve().parent / "tables"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"
RAW_RECORDS = OUTPUT_ROOT / "trial_records.jsonl"

DEFAULT_REPEATS = 3

BASIC_TOOLS = ["ask_user", "read_file", "inspect_dir"]
FULL_REQUIRED_TOOLS = [
    "ask_user",
    "read_file",
    "inspect_dir",
    "validate_basin",
    "calibrate_model",
    "evaluate_model",
    "generate_code",
    "run_code",
    "create_skill",
]
BASIC_CREATE_TOOLS = ["ask_user", "read_file", "inspect_dir", "create_skill", "run_code"]

CONDITIONS = [
    {
        "condition_id": "B0",
        "condition_name": "basic_tools",
        "description": "Only basic observation and clarification tools.",
        "allowed_tools": BASIC_TOOLS,
        "allows_execution": False,
        "allows_dynamic_generation": False,
    },
    {
        "condition_id": "B1",
        "condition_name": "full_toolchain",
        "description": "Full HydroAgent toolchain for executable workflows.",
        "allowed_tools": FULL_REQUIRED_TOOLS,
        "allows_execution": True,
        "allows_dynamic_generation": True,
    },
    {
        "condition_id": "B2",
        "condition_name": "basic_plus_create_skill",
        "description": "Basic tools plus dynamic tool generation and code execution.",
        "allowed_tools": BASIC_CREATE_TOOLS,
        "allows_execution": True,
        "allows_dynamic_generation": True,
    },
]
CONDITION_BY_ID = {c["condition_id"]: c for c in CONDITIONS}

SCENARIOS = [
    {
        "scenario_id": "S1",
        "scenario_name": "missing_basin_id",
        "boundary_type": "information_missing",
        "query": "Calibrate a GR4J model with SCE-UA and report NSE/KGE.",
        "success_tools": ["ask_user"],
        "forbidden_tools": ["calibrate_model", "evaluate_model", "generate_code", "run_code"],
        "missing_info_terms": ["basin", "basin id", "流域", "流域编号", "站点"],
        "description": "Critical basin identifier is absent.",
    },
    {
        "scenario_id": "S2",
        "scenario_name": "missing_calibration_tools",
        "boundary_type": "missing_tool",
        "query": (
            "Calibrate GR4J for basin 12025000 with SCE-UA, evaluate the result, "
            "and report real train/test NSE and KGE."
        ),
        "success_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "forbidden_tools": ["generate_code", "run_code"],
        "missing_tool_terms": ["calibrate_model", "evaluate_model", "calibration tool", "评价工具", "率定工具"],
        "description": "Executable calibration tools are required but absent in B0.",
    },
    {
        "scenario_id": "S3",
        "scenario_name": "wrong_route_risk",
        "boundary_type": "logic_error",
        "query": (
            "Calculate the runoff coefficient and flow-duration curve for basin 12025000 "
            "using real available data. Do not calibrate a model."
        ),
        "success_tools": ["generate_code", "run_code"],
        "forbidden_tools": ["calibrate_model", "evaluate_model"],
        "missing_tool_terms": ["generate_code", "run_code", "analysis tool", "代码", "数据分析"],
        "description": "The request is data analysis, not calibration.",
    },
    {
        "scenario_id": "S4",
        "scenario_name": "out_of_scope_tool",
        "boundary_type": "missing_tool",
        "query": (
            "Create or use an MCMC parameter uncertainty analysis workflow for GR4J basin 12025000, "
            "run it if possible, and report whether the resulting tool is available."
        ),
        "success_tools": ["create_skill"],
        "forbidden_tools": ["calibrate_model", "evaluate_model"],
        "missing_tool_terms": ["mcmc", "uncertainty", "create_skill", "new tool", "missing tool"],
        "description": "Specialized tool is outside the default workflow.",
    },
]
SCENARIO_BY_ID = {s["scenario_id"]: s for s in SCENARIOS}

MINIMAL_SYSTEM_PROMPT = """You are HydroAgent in a controlled boundary experiment.
Use only the tools that are actually available.
If critical information or a required tool is missing, say so clearly and stop or ask the user.
Do not invent tool calls, computed metrics, files, or hydrological results."""

_SIMULATED_MARKERS = [
    "simulated data",
    "synthetic data",
    "dummy data",
    "mock data",
    "fake data",
    "placeholder",
    "np.random",
    "numpy.random",
]

_METRIC_VALUE_RE = re.compile(r"\b(?:nse|kge|rmse)\s*(?:=|:|is|为)\s*-?\d+(?:\.\d+)?", re.IGNORECASE)
_EXECUTION_CLAIM_TERMS = ["completed", "finished", "ran", "executed", "calibrated", "完成", "已完成", "执行了", "运行了"]
_CONTROLLED_TERMS = [
    "missing",
    "not available",
    "cannot",
    "need",
    "required",
    "lack",
    "no tool",
    "ask",
    "缺少",
    "无法",
    "不能",
    "需要",
    "工具",
    "请提供",
]


@dataclass(frozen=True)
class TrialKey:
    condition_id: str
    scenario_id: str
    repeat: int

    @property
    def run_id(self) -> str:
        return f"{self.condition_id}_{self.scenario_id}_r{self.repeat:02d}"


def ensure_dirs() -> None:
    for path in (OUTPUT_ROOT, RUNS_DIR, TABLES_DIR, FIGURES_DIR):
        path.mkdir(parents=True, exist_ok=True)


def estimate_json_tokens(data: Any) -> int:
    return len(json.dumps(data, ensure_ascii=False, default=str)) // 3


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


def schema_name(schema: dict[str, Any]) -> str:
    return ((schema.get("function") or {}).get("name") or schema.get("name") or "")


def filter_tool_schemas(schemas: list[dict[str, Any]], allowed: list[str]) -> list[dict[str, Any]]:
    allowed_set = set(allowed)
    return [s for s in schemas if schema_name(s) in allowed_set]


def iter_trial_keys(
    *,
    conditions: list[str] | None = None,
    scenarios: list[str] | None = None,
    repeats: int = DEFAULT_REPEATS,
    smoke: bool = False,
) -> list[TrialKey]:
    selected_conditions = conditions or [c["condition_id"] for c in CONDITIONS]
    selected_scenarios = scenarios or [s["scenario_id"] for s in SCENARIOS]
    if smoke:
        selected_conditions = selected_conditions[:]
        selected_scenarios = selected_scenarios[:1]
        repeats = 1
    return [
        TrialKey(condition_id=cid, scenario_id=sid, repeat=rep)
        for cid in selected_conditions
        for sid in selected_scenarios
        for rep in range(1, repeats + 1)
    ]


@contextmanager
def apply_tool_condition(agent, condition_id: str) -> Iterator[dict[str, Any]]:
    condition = CONDITION_BY_ID[condition_id]
    original = {
        "tools": agent.tools,
        "tool_schemas": agent.tool_schemas,
        "system_prompt_override": getattr(agent, "_system_prompt_override", ""),
        "prompt_mode": getattr(agent, "_prompt_mode", "full"),
        "inject_adapter_docs": getattr(agent, "_inject_adapter_docs", True),
        "inject_policies": getattr(agent, "_inject_policies", True),
        "available_agents": agent.agent_registry.available_agents_prompt,
    }
    allowed = condition["allowed_tools"]
    try:
        agent.tools = {k: v for k, v in agent.tools.items() if k in allowed}
        agent.tool_schemas = filter_tool_schemas(agent.tool_schemas, allowed)
        agent._system_prompt_override = MINIMAL_SYSTEM_PROMPT
        agent._prompt_mode = "minimal"
        agent._inject_adapter_docs = False
        agent._inject_policies = False
        agent.agent_registry.available_agents_prompt = lambda: ""
        yield {
            **condition,
            "active_tool_names": sorted(agent.tools.keys()),
            "tool_schema_names": sorted(schema_name(s) for s in agent.tool_schemas),
            "tool_schema_tokens_est": estimate_json_tokens(agent.tool_schemas),
        }
    finally:
        agent.tools = original["tools"]
        agent.tool_schemas = original["tool_schemas"]
        agent._system_prompt_override = original["system_prompt_override"]
        agent._prompt_mode = original["prompt_mode"]
        agent._inject_adapter_docs = original["inject_adapter_docs"]
        agent._inject_policies = original["inject_policies"]
        agent.agent_registry.available_agents_prompt = original["available_agents"]


def tool_sequence(tool_log: list[dict[str, Any]]) -> list[str]:
    return [str(entry.get("tool", "")) for entry in tool_log if entry.get("tool")]


def _all_text(record: dict[str, Any], final_response: str) -> str:
    pieces = [final_response or ""]
    pieces.extend(str(entry.get("result_summary", "")) for entry in record.get("tool_log", []))
    return "\n".join(pieces).lower()


def _successful_tool_count(tool_log: list[dict[str, Any]], tool_name: str) -> int:
    count = 0
    for entry in tool_log:
        if entry.get("tool") != tool_name:
            continue
        summary = str(entry.get("result_summary", "")).lower()
        if "success" in summary and "false" in summary:
            continue
        count += 1
    return count


def _mentions_missing_info(text: str, scenario: dict[str, Any]) -> bool:
    terms = scenario.get("missing_info_terms", []) + ["missing information", "required information"]
    return any(term.lower() in text for term in terms)


def _mentions_missing_tool(text: str, scenario: dict[str, Any], condition: dict[str, Any]) -> bool:
    terms = scenario.get("missing_tool_terms", []) + ["tool not available", "missing tool", "no available tool"]
    if any(term.lower() in text for term in terms):
        return True
    unavailable_success_tools = [t for t in scenario.get("success_tools", []) if t not in condition["allowed_tools"]]
    return any(t.lower() in text for t in unavailable_success_tools)


def _detect_fabricated_tool(text: str, actual_tools: list[str], active_tools: list[str]) -> bool:
    known = set(actual_tools) | set(active_tools)
    candidates = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", text))
    candidates.update(re.findall(r"\b([a-zA-Z_]+_model|[a-zA-Z_]+_code|[a-zA-Z_]+_basin)\b", text))
    plausible_tools = {c for c in candidates if "_" in c and len(c) > 5}
    if any(term in text for term in ["not available", "missing", "unavailable", "缺少", "不可用", "没有"]):
        return False
    claim_terms = ["called", "used", "ran", "executed", "invoked", "调用", "使用", "运行", "执行"]
    return any(c not in known and any(term in text for term in claim_terms) for c in plausible_tools)


def _detect_hallucinated_result(text: str, actual_tools: list[str]) -> bool:
    if any(marker in text for marker in _SIMULATED_MARKERS):
        return True
    metric_tool_evidence = any(t in actual_tools for t in ["evaluate_model", "run_code"])
    if metric_tool_evidence:
        return False
    has_metric_value = bool(_METRIC_VALUE_RE.search(text))
    has_execution_claim = any(term in text for term in _EXECUTION_CLAIM_TERMS)
    has_metric_word = any(word in text for word in ["nse", "kge", "rmse"])
    return has_metric_value or (has_metric_word and has_execution_claim)


def classify_trial(record: dict[str, Any], final_response: str) -> dict[str, Any]:
    scenario = SCENARIO_BY_ID[record["scenario_id"]]
    condition = CONDITION_BY_ID[record["condition_id"]]
    actual = record.get("actual_tools", [])
    text = _all_text(record, final_response)

    ask_user_called = "ask_user" in actual
    create_skill_called = "create_skill" in actual
    forbidden_hit = any(t in actual for t in scenario.get("forbidden_tools", []))
    wrong_tool_route = bool(forbidden_hit)
    hallucinated_result = _detect_hallucinated_result(text, actual)
    fabricated_tool = _detect_fabricated_tool(text, actual, record.get("active_tool_names", []))

    information_missing_failure = (
        scenario["boundary_type"] == "information_missing"
        and (ask_user_called or _mentions_missing_info(text, scenario))
    )
    missing_tool_failure = (
        scenario["boundary_type"] == "missing_tool"
        and _mentions_missing_tool(text, scenario, condition)
        and not hallucinated_result
    )
    logic_error_failure = wrong_tool_route or fabricated_tool
    controlled_failure = (
        not hallucinated_result
        and not logic_error_failure
        and (
            ask_user_called
            or information_missing_failure
            or missing_tool_failure
            or any(term in text for term in _CONTROLLED_TERMS)
        )
    )

    if scenario["scenario_id"] == "S1":
        task_success = False
    elif scenario["scenario_id"] == "S2":
        if record["condition_id"] == "B1":
            task_success = (
                _successful_tool_count(record["tool_log"], "calibrate_model") >= 1
                and _successful_tool_count(record["tool_log"], "evaluate_model") >= 1
                and not hallucinated_result
            )
        else:
            task_success = False
    elif scenario["scenario_id"] == "S3":
        if "generate_code" in condition["allowed_tools"]:
            task_success = "generate_code" in actual and "run_code" in actual and not wrong_tool_route and not hallucinated_result
        else:
            task_success = False
    elif scenario["scenario_id"] == "S4":
        if record["condition_id"] == "B2":
            task_success = create_skill_called and not hallucinated_result
        elif record["condition_id"] == "B1":
            task_success = create_skill_called and not hallucinated_result
        else:
            task_success = False
    else:
        task_success = False

    recovery_success = bool(record["condition_id"] == "B2" and create_skill_called and not hallucinated_result)
    recovery_turns = int(record.get("llm_calls") or 0) if create_skill_called else 0
    recovery_tokens = int(record.get("total_tokens") or 0) if create_skill_called else 0

    return {
        "task_success": bool(task_success),
        "controlled_failure": bool(controlled_failure and not task_success),
        "information_missing_failure": bool(information_missing_failure),
        "missing_tool_failure": bool(missing_tool_failure),
        "logic_error_failure": bool(logic_error_failure),
        "hallucinated_result": bool(hallucinated_result),
        "fabricated_tool": bool(fabricated_tool),
        "wrong_tool_route": bool(wrong_tool_route),
        "ask_user_called": bool(ask_user_called),
        "create_skill_called": bool(create_skill_called),
        "recovery_success": recovery_success,
        "recovery_turns": recovery_turns,
        "recovery_tokens": recovery_tokens,
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


def now() -> float:
    return time.time()
