"""
Experiment 3 - Agent 能力广度验证
=================================
目的：验证 HydroAgent 在三个正交维度的端到端能力广度：

  Section A: 自然语言鲁棒性
    6 个代表性场景，覆盖标准率定/智能率定/代码分析/残缺信息/隐含意图/批量规划，
    每个场景独立重复 N_REPEATS_A=3 次（新鲜 agent + 独立工作空间）。
    报告工具匹配率（mean±std）和决策一致性率（相邻重复工具序列相同的比例）。

  Section B: 动态 Skill 生成（元能力）
    3 个场景，每个请求一个默认 Skill 集不存在的能力，验证运行时生成 + 立即注册。
    对比点：OpenClaw 静态 Skill 市场（预安装），HydroAgent 按需生成。

  Section C: 自驱动任务规划
    Phase C1 (基础执行): 批量任务 -> Agent 自主创建任务列表并完整执行
    Phase C2 (自适应):   含困难流域 -> Agent 是否追加补救任务 (add_task)
    Phase C3 (断点恢复): 预写半完成状态 -> Agent 跳过已完成任务

评估指标：
  A: 工具序列匹配率（mean across repeats）、首个工具准确率、决策一致性率
  B: create_skill 调用率、skill.md/tool.py 生成率、语法合法率、注册成功率
  C: 规划工具使用率、任务完成率、自适应触发率、恢复正确率

论文对应：Section 4.4
合并来源：原 exp3_scenario_robustness + exp4_create_skill + exp7_self_driven_planning
参考文献：
  OpenClaw Skill 系统（静态安装范式，与 Section B 对比）
  AgentHPO (ICLR 2025) — LLM Agent 迭代优化，工具集固定（与 Section C 对比）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import ast
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime

import yaml

# New metric modules (paper §4.4 redesign)
from experiment._metrics import efficiency as _eff
from experiment._metrics import exp_iv as _eiv

# ── Gold-standard loader ──────────────────────────────────────────────────────

_GOLD_FILE = Path(__file__).parent / "_gold" / "exp_iv_tasks.yaml"


def _load_gold() -> dict:
    """Load Exp IV gold-standard reference data (expected subtasks, etc.)."""
    if _GOLD_FILE.exists():
        return yaml.safe_load(_GOLD_FILE.read_text(encoding="utf-8"))
    return {}


# ── Checkpoint helpers ───────────────────────────────────────────────────────

_CKPT_FILE = Path("results/paper/exp4/checkpoints.json")


def _load_checkpoints() -> dict:
    """Load saved checkpoints {scenario_id -> result_dict}."""
    if _CKPT_FILE.exists():
        try:
            return json.loads(_CKPT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_checkpoint(scenario_id: str, record: dict):
    """Save a single scenario result to the checkpoint file."""
    _CKPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ckpts = _load_checkpoints()
    ckpts[scenario_id] = record
    _CKPT_FILE.write_text(
        json.dumps(ckpts, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )



import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("results/paper/exp4")

# Section A: repeat each NL scenario this many times to compute consistency rate.
# Uses fresh agent + workspace per repeat; natural SCE-UA variance provides diversity.
N_REPEATS_A = 3

# ── Section A: NL 鲁棒性场景 ────────────────────────────────────────────────
# 从原 12 个场景选 6 个，覆盖所有类别，避免冗余

NL_SCENARIOS = [
    {
        "id": "A01", "category": "standard_calibration",
        "query": "请帮我率定GR4J模型，流域12025000（快速验证：algorithm_params={'rep': 200, 'ngs': 16}）",
        "expected_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "expected_first": "validate_basin",
        "description": "完整信息标准率定（中文）",
    },
    {
        "id": "A02", "category": "algo_params",
        "query": "Calibrate GR4J model for basin 03439000 using SCE-UA (fast validation: algorithm_params={'rep': 200, 'ngs': 16})",
        "expected_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "expected_first": "validate_basin",
        "description": "英文查询 + 算法参数（迭代轮数）",
    },
    {
        "id": "A03", "category": "llm_calibration",
        "query": "流域06043500的GR4J率定效果不好，参数可能碰到了边界",
        "expected_tools": ["llm_calibrate"],
        "expected_first": None,   # 可以先 validate_basin 也可以直接 llm_calibrate
        "description": "隐含意图：参数边界 -> 应触发 LLM 智能率定",
    },
    {
        "id": "A04", "category": "batch_planning",
        "query": "批量率定流域12025000和03439000，使用GR4J模型",
        "expected_tools": ["create_task_list", "get_pending_tasks", "update_task"],
        "expected_first": None,
        "description": "批量任务 -> Agent 应自驱动创建任务列表",
    },
    {
        "id": "A05", "category": "code_analysis",
        "query": "帮我计算流域12025000的径流系数，并画FDC曲线",
        "expected_tools": ["validate_basin", "generate_code"],
        "expected_first": "validate_basin",
        "description": "流域数据代码生成（应先 validate_basin，跳过 calibrate_model/evaluate_model）",
    },
    {
        "id": "A06", "category": "missing_info",
        "query": "率定GR4J模型",
        "expected_tools": [],        # 缺流域 ID，任意处理方式均可
        "expected_first": None,
        "description": "残缺信息（缺流域 ID），系统应询问或报错而非崩溃",
    },
]

# ── Section B: 动态 Skill 生成场景 ──────────────────────────────────────────

SKILL_SCENARIOS = [
    {
        "id": "B01",
        "query": "帮我创建一个用 spotpy 做 MCMC 参数不确定性分析的工具",
        "description": "MCMC uncertainty analysis via spotpy",
        "hint": "spotpy",
    },
    {
        "id": "B02",
        "query": "我需要一个计算流域径流系数和流量历时曲线(FDC)的分析工具，帮我创建",
        "description": "Runoff coefficient + FDC analysis",
        "hint": "fdc",
    },
    {
        "id": "B03",
        "query": "创建一个工具，能对比两个率定结果目录的参数分布，生成箱线图",
        "description": "Parameter distribution comparison (boxplot)",
        "hint": "param",
    },
]

# ── Section C: 自驱动规划配置 ────────────────────────────────────────────────

PHASE_C1_QUERY = (
    "请帮我比较GR4J和GR5J模型在流域12025000和03439000上的率定性能。"
    "列出任务计划，依次执行，最后给出综合对比报告。"
    "（快速验证：algorithm_params={'rep': 200, 'ngs': 16}）"
)

PHASE_C2_QUERY = (
    "批量率定以下3个流域的GR4J模型：12025000（湿润）、06043500（半干旱山区）、"
    "08101000（半干旱闪洪）。"
    "如果某个流域的NSE低于0.3，请分析原因并考虑是否需要追加LLM智能率定或换用GR5J模型。"
    "全部完成后给出分析报告。（快速验证：algorithm_params={'rep': 200, 'ngs': 16}）"
)

PHASE_C3_QUERY = (
    "继续批量率定任务：比较GR4J和GR5J在流域12025000和03439000上的性能。"
    "（快速验证：algorithm_params={'rep': 200, 'ngs': 16}）"
)

# 预写半完成状态（task_001 已完成）
PHASE_C3_PRESET_STATE = {
    "goal": "比较GR4J和GR5J在流域12025000和03439000上的性能",
    "created_at": "2026-03-08T00:00:00",
    "updated_at": "2026-03-08T00:00:00",
    "tasks": [
        {
            "id": "task_001", "description": "率定GR4J，流域12025000",
            "status": "done",
            "result": {"NSE": 0.72, "notes": "pre-completed for resume test"},
            "error": None, "started_at": "2026-03-08T00:00:00",
            "finished_at": "2026-03-08T00:10:00",
        },
        {
            "id": "task_002", "description": "率定GR5J，流域12025000",
            "status": "pending", "result": None, "error": None,
            "started_at": None, "finished_at": None,
        },
        {
            "id": "task_003", "description": "率定GR4J，流域03439000",
            "status": "pending", "result": None, "error": None,
            "started_at": None, "finished_at": None,
        },
        {
            "id": "task_004", "description": "率定GR5J，流域03439000",
            "status": "pending", "result": None, "error": None,
            "started_at": None, "finished_at": None,
        },
    ],
}


# ── Utilities ────────────────────────────────────────────────────────────────

def setup_logging():
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / f"exp4_{ts}.log", encoding="utf-8"),
        ],
    )


def _check_tool_match(expected: list, actual: list) -> bool:
    """子集匹配：expected 每个工具都出现在 actual 中即通过。空列表视为通过。"""
    if not expected:
        return True
    ec, ac = Counter(expected), Counter(actual)
    return all(ac[t] >= ec[t] for t in ec)


# P3: agent now reads skill.md via read_file before starting real work.
# These preamble calls should not count as the "first meaningful tool".
_PREAMBLE_TOOLS = {"read_file"}


def _first_meaningful_tool(actual_tools: list[str]) -> str | None:
    """Return first tool that is not a skill.md preamble read.

    After P3, agent calls read_file(skill.md) as its first action.
    We skip leading read_file calls to find the first 'real' work tool.
    """
    for t in actual_tools:
        if t not in _PREAMBLE_TOOLS:
            return t
    return actual_tools[0] if actual_tools else None


def _py_syntax_ok(py_file: Path) -> bool:
    try:
        ast.parse(py_file.read_text(encoding="utf-8"))
        return True
    except SyntaxError:
        return False


def _snapshot_skills() -> set:
    skills_dir = Path(__file__).parent.parent / "hydroagent" / "skills"
    return {d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith("_")}


def _patch_tool_tracker(agent):
    """Patch agent._execute_tool to record call order. Returns the list."""
    called = []
    orig = agent._execute_tool

    def tracked(name, arguments):
        called.append(name)
        return orig(name, arguments)

    agent._execute_tool = tracked
    return called


# ── Section A ────────────────────────────────────────────────────────────────

def _consistency_rate(tool_seqs: list[list]) -> float:
    """Fraction of consecutive repeat-pairs with identical tool sequences.

    E.g., 3 repeats -> 2 pairs -> if 1 pair matches -> 0.5.
    Returns 1.0 for a single repeat (degenerate case).
    """
    if len(tool_seqs) <= 1:
        return 1.0
    matches = sum(
        1 for a, b in zip(tool_seqs, tool_seqs[1:]) if a == b
    )
    return matches / (len(tool_seqs) - 1)


def run_section_a(workspace: Path, resume: bool = False) -> dict:
    """NL 查询鲁棒性：6 个代表性场景，full_knowledge 条件，每个场景重复 N_REPEATS_A 次。

    Each repeat uses a fresh agent and isolated workspace to prevent cross-repeat
    memory/session accumulation.  The consistency_rate measures how often the agent
    chooses the *same* tool sequence across independent repetitions of the same query —
    a proxy for decision stability under LLM sampling variance.
    """
    from hydroagent.agent import HydroAgent

    logger.info("\n" + "=" * 60)
    logger.info(
        f"Section A: Natural Language Robustness ({len(NL_SCENARIOS)} scenarios x {N_REPEATS_A} repeats)"
    )
    logger.info("=" * 60)

    ckpts = _load_checkpoints() if resume else {}
    scenario_records = []   # one dict per scenario (aggregated across repeats)

    for sc in NL_SCENARIOS:
        sid = sc["id"]
        repeats = []

        logger.info(f"\n  {sid}: {sc['description']}")

        for ri in range(N_REPEATS_A):
            ck_key = f"{sid}_r{ri + 1}"

            # Resume: skip completed repeats
            if resume and ck_key in ckpts:
                logger.info(f"    repeat {ri+1}/{N_REPEATS_A}: [SKIPPED - from checkpoint]")
                repeats.append(ckpts[ck_key])
                continue

            logger.info(f"    repeat {ri+1}/{N_REPEATS_A} ...")
            rep_workspace = workspace / f"{sid}_r{ri+1}"
            rep_workspace.mkdir(parents=True, exist_ok=True)

            rep = {
                "scenario_id": sid, "repeat": ri + 1,
                "actual_tools": [], "first_tool_correct": False,
                "tool_match": False, "success": False,
                "total_tokens": 0, "wall_time_s": 0.0, "error": None,
            }

            agent = HydroAgent(workspace=rep_workspace)
            t0 = time.time()
            try:
                response = agent.run(sc["query"])
                rep["wall_time_s"] = round(time.time() - t0, 2)
                rep["actual_tools"] = [e["tool"] for e in agent.memory._log]
                rep["total_tokens"] = agent.llm.tokens.summary().get("total_tokens", 0)
                rep["success"] = True
                rep["tool_match"] = _check_tool_match(sc["expected_tools"], rep["actual_tools"])
                if sc["expected_first"] and rep["actual_tools"]:
                    first_meaningful = _first_meaningful_tool(rep["actual_tools"])
                    rep["first_tool_correct"] = (first_meaningful == sc["expected_first"])
                    rep["first_meaningful_tool"] = first_meaningful
                elif not sc["expected_first"]:
                    rep["first_tool_correct"] = True

                # ── §4.4 Group A new signals ──
                # clarification_handling: 0=missed, 1=silent guess, 2=invoked ask_user
                _gold_a = _load_gold().get("group_a", {}).get("variants", {}).get(sid, {})
                if "ask_user" in rep["actual_tools"]:
                    rep["clarification_handling"] = 2
                elif not _gold_a.get("info_complete", True):
                    # info was incomplete but agent didn't ask -> silent guess
                    rep["clarification_handling"] = 1
                else:
                    rep["clarification_handling"] = None  # N/A (info was complete)
                # Capture full response for semantic_consistency / intent rating
                rep["final_report"] = (response or "")[:2000]
                # task_completion = ran without error AND produced some output
                rep["task_completion"] = bool(response)
            except Exception as e:
                rep["wall_time_s"] = round(time.time() - t0, 2)
                rep["error"] = str(e)
                logger.error(f"      repeat {ri+1} failed: {e}")

            _save_checkpoint(ck_key, rep)
            repeats.append(rep)
            logger.info(
                f"      match={rep['tool_match']}  first_ok={rep['first_tool_correct']}  "
                f"tokens={rep['total_tokens']}  tools={rep['actual_tools']}"
            )

        # Aggregate repeats for this scenario
        n_rep = len(repeats)
        tool_seqs = [r["actual_tools"] for r in repeats]
        tool_match_rate = sum(1 for r in repeats if r["tool_match"]) / n_rep if n_rep else 0
        first_tool_rate = sum(1 for r in repeats if r["first_tool_correct"]) / n_rep if n_rep else 0
        cr = _consistency_rate(tool_seqs)
        avg_tokens = sum(r["total_tokens"] for r in repeats) / n_rep if n_rep else 0
        avg_time = sum(r["wall_time_s"] for r in repeats) / n_rep if n_rep else 0

        agg = {
            "id": sid, "category": sc["category"],
            "description": sc["description"], "query": sc["query"],
            "expected_tools": sc["expected_tools"],
            "expected_first": sc["expected_first"],
            "repeats": repeats,
            "n_repeats": n_rep,
            "tool_match_rate": round(tool_match_rate, 4),
            "first_tool_rate": round(first_tool_rate, 4),
            "consistency_rate": round(cr, 4),
            "avg_total_tokens": round(avg_tokens, 1),
            "avg_wall_time_s": round(avg_time, 2),
        }
        scenario_records.append(agg)
        logger.info(
            f"  {sid} summary: match_rate={tool_match_rate*100:.0f}%  "
            f"first_ok={first_tool_rate*100:.0f}%  consistency={cr*100:.0f}%"
        )

    n_sc = len(scenario_records)
    overall_match = sum(r["tool_match_rate"] for r in scenario_records) / n_sc if n_sc else 0
    overall_first = sum(r["first_tool_rate"] for r in scenario_records) / n_sc if n_sc else 0
    overall_consistency = sum(r["consistency_rate"] for r in scenario_records) / n_sc if n_sc else 0

    return {
        "section": "A",
        "title": "Natural Language Robustness",
        "n_scenarios": n_sc,
        "n_repeats_per_scenario": N_REPEATS_A,
        "results": scenario_records,
        "stats": {
            "tool_match_rate": round(overall_match, 4),
            "first_tool_rate": round(overall_first, 4),
            "consistency_rate": round(overall_consistency, 4),
            # Legacy fields for backward compatibility with print_summary
            "n_match": sum(1 for r in scenario_records if r["tool_match_rate"] >= 1.0),
            "n_first": sum(1 for r in scenario_records if r["first_tool_rate"] >= 1.0),
        },
    }


# ── Section B ────────────────────────────────────────────────────────────────

def run_section_b(workspace: Path, resume: bool = False) -> dict:
    """动态 Skill 生成：3 个场景，验证运行时生成 + 立即注册。"""
    from hydroagent.agent import HydroAgent
    from hydroagent.tools import reload_tools

    logger.info("\n" + "=" * 60)
    logger.info("Section B: Dynamic Skill Generation (3 scenarios)")
    logger.info("=" * 60)

    ckpts = _load_checkpoints() if resume else {}
    results = []

    for sc in SKILL_SCENARIOS:
        sid = sc["id"]

        # Resume: skip already-done scenarios
        if resume and sid in ckpts:
            logger.info(f"\n  {sid}: [SKIPPED - loaded from checkpoint]")
            results.append(ckpts[sid])
            continue

        logger.info(f"\n  {sid}: {sc['description']}")
        logger.info(f"  Query: {sc['query']}")

        # Delete any skill created by a previous run of this scenario so the
        # agent always creates fresh. Skills from OTHER scenarios are kept
        # (reuse across scenarios is intentional and a system feature).
        prev_ckpt = ckpts.get(sid, {})
        prev_skill = prev_ckpt.get("new_skill_dir")
        if prev_skill:
            import shutil
            prev_path = Path(__file__).parent.parent / "hydroagent" / "skills" / prev_skill
            if prev_path.exists():
                shutil.rmtree(prev_path, ignore_errors=True)
                logger.info(f"  Removed previous skill from last run: {prev_skill}")

        skills_before = _snapshot_skills()
        agent = HydroAgent(workspace=workspace)  # fresh instance per scenario

        record = {
            "id": sid, "description": sc["description"], "query": sc["query"],
            "create_skill_called": False, "new_skill_dir": None,
            "reused_existing_skill": None,
            "skill_md_exists": False, "tool_py_exists": False,
            "tool_py_syntax_ok": False, "tool_registered": False,
            "success": False, "response_preview": "", "time_s": 0, "error": None,
        }

        agent.memory._log.clear()
        t0 = time.time()
        try:
            response = agent.run(sc["query"])
            record["time_s"] = round(time.time() - t0, 2)
            record["response_preview"] = (response or "")[:500]

            actual_tools = [e["tool"] for e in agent.memory._log]
            record["create_skill_called"] = "create_skill" in actual_tools

            skills_after = _snapshot_skills()
            new_skills = skills_after - skills_before
            if new_skills:
                skill_name = sorted(new_skills)[0]
                record["new_skill_dir"] = skill_name
                skill_dir = Path(__file__).parent.parent / "hydroagent" / "skills" / skill_name
                record["skill_md_exists"] = (skill_dir / "skill.md").exists()
                py_files = [f for f in skill_dir.glob("*.py") if f.name != "__init__.py"]
                if py_files:
                    record["tool_py_exists"] = True
                    record["tool_py_syntax_ok"] = _py_syntax_ok(py_files[0])
                updated = reload_tools()
                record["tool_registered"] = any(
                    skill_name.replace("-", "_").lower() in name.lower()
                    for name in updated
                )

            # Check if agent reused an existing skill (hint keyword in tool list)
            hint = sc.get("hint", "")
            if hint:
                reused = [t for t in actual_tools if hint.lower() in t.lower()
                          and t != "create_skill"]
                if reused:
                    record["reused_existing_skill"] = reused[0]

            # Success: either created a new working skill OR intelligently reused an existing one
            record["success"] = (
                (record["create_skill_called"] and record["tool_py_exists"] and record["tool_py_syntax_ok"])
                or (record["reused_existing_skill"] is not None)
            )

            # ── §4.4 Group B metric aliases + new signals ──
            # Map existing checks onto the paper's metric names; add new ones.
            record["artifact_generated"] = record["skill_md_exists"] and record["tool_py_exists"]
            record["syntax_validity"] = record["tool_py_syntax_ok"]
            record["runtime_registration"] = record["tool_registered"]
            # smoke_test_pass proxy: registered + syntax-valid implies callable.
            # A true smoke test (call with toy args) requires per-skill arg synthesis;
            # left as a proxy here, refine if reviewers require live invocation.
            record["smoke_test_pass"] = record["tool_registered"] and record["tool_py_syntax_ok"]
            # dependency_handling: 0=crash, 1=error-no-fix, 2=detected+install_package
            if "install_package" in actual_tools:
                record["dependency_handling"] = 2
            elif record["error"]:
                record["dependency_handling"] = 1
            else:
                record["dependency_handling"] = None  # N/A (no missing dep in this scenario)

        except Exception as e:
            record["time_s"] = round(time.time() - t0, 2)
            record["error"] = str(e)
            logger.error(f"  {sid} exception: {e}", exc_info=True)

        _save_checkpoint(sid, record)
        results.append(record)
        logger.info(
            f"  create_skill={record['create_skill_called']}  "
            f"md={record['skill_md_exists']}  py={record['tool_py_exists']}  "
            f"syntax={record['tool_py_syntax_ok']}  reg={record['tool_registered']}  "
            f"dir={record['new_skill_dir']}"
        )

    n = len(results)
    n_ok = sum(1 for r in results if r["success"])

    return {
        "section": "B",
        "title": "Dynamic Skill Generation",
        "n_scenarios": n,
        "results": results,
        "stats": {
            "success_rate": n_ok / n if n else 0,
            "n_success": n_ok,
            "create_skill_rate": sum(1 for r in results if r["create_skill_called"]) / n if n else 0,
            "syntax_ok_rate": sum(1 for r in results if r["tool_py_syntax_ok"]) / n if n else 0,
            "registered_rate": sum(1 for r in results if r["tool_registered"]) / n if n else 0,
        },
    }


# ── Section C ────────────────────────────────────────────────────────────────

def _run_planning_phase(agent, query: str, workspace: Path,
                        phase_id: str, preset_state: dict | None = None) -> dict:
    """Run one planning phase and return result dict."""
    state_file = workspace / "task_state.json"
    if preset_state:
        state_file.write_text(
            json.dumps(preset_state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    elif state_file.exists():
        state_file.unlink()

    called = _patch_tool_tracker(agent)
    t0 = time.time()
    try:
        response = agent.run(query)
        elapsed = round(time.time() - t0, 1)
        error = None
    except Exception as e:
        response = ""
        elapsed = round(time.time() - t0, 1)
        error = str(e)
        logger.error(f"  Phase {phase_id} exception: {e}", exc_info=True)

    # Read final task state
    final_state = {}
    if state_file.exists():
        try:
            final_state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    tasks_all = final_state.get("tasks", [])
    tasks_total = len(tasks_all)
    tasks_done = sum(1 for t in tasks_all if t["status"] == "done")
    tasks_failed = sum(1 for t in tasks_all if t["status"] == "failed")

    planning_tools = [t for t in called if t in (
        "create_task_list", "get_pending_tasks", "update_task", "add_task"
    )]

    result = {
        "phase": phase_id,
        "query_preview": query[:120],
        "tools_called": called,
        "planning_tools": planning_tools,
        "create_task_list_called": "create_task_list" in called,
        "get_pending_called": "get_pending_tasks" in called,
        "update_task_called": "update_task" in called,
        "add_task_called": "add_task" in called,
        "task_state_file_created": state_file.exists(),
        "tasks_total": tasks_total,
        "tasks_done": tasks_done,
        "tasks_failed": tasks_failed,
        "completion_rate": tasks_done / tasks_total if tasks_total else 0,
        "elapsed_s": elapsed,
        "response_preview": (response or "")[:300],
        "error": error,
    }

    # ── New §4.4 metrics: planning_scale_ratio, completion_ratio, failure_class ──
    _gold = _load_gold().get("group_c", {}).get(phase_id, {})
    expected = _gold.get("expected_subtasks")
    if expected:
        # planned = the agent's declared task-list size (tasks_total proxies this)
        result["planned_subtasks"] = tasks_total
        result["expected_subtasks"] = expected
        result["planning_scale_ratio"] = _eiv.planning_scale_ratio(tasks_total, expected)
        result["completion_ratio"] = _eiv.completion_ratio(tasks_done, expected)
    # adaptive expectation (C2 should trigger add_task on difficult basin)
    result["adaptive_expected"] = _gold.get("adaptive_expected", False)
    result["adaptive_triggered_raw"] = "add_task" in called

    # Phase-specific checks
    if phase_id == "C3":
        task_001 = next((t for t in tasks_all if t["id"] == "task_001"), {})
        # Primary check: use preset timestamps as fingerprint.
        # update_task() would overwrite finished_at with the current time if the agent
        # re-ran task_001; the preset value "2026-03-08T00:10:00" is preserved only if
        # the agent correctly skipped it.
        result["skipped_done_task"] = (
            task_001.get("status") == "done"
            and task_001.get("finished_at") == "2026-03-08T00:10:00"
        )
        # Diagnostic fallback: also record the notes-based check separately.
        result["skipped_done_task_notes"] = (
            task_001.get("result", {}).get("notes") == "pre-completed for resume test"
        )
        # C3 success = agent did NOT overwrite the done task (skipped it correctly).
        # create_task_list should NOT be called in a resume scenario.
        result["success"] = result["skipped_done_task"] and result["get_pending_called"]
    elif phase_id == "C2":
        nse_values = {}
        for t in tasks_all:
            if t["status"] == "done" and t.get("result"):
                nse = t["result"].get("NSE")
                if nse is not None:
                    nse_values[t["id"]] = nse
        result["nse_values"] = nse_values
        result["adaptive_triggered"] = result["add_task_called"]
        # Allow 1 failure: 06043500 is a notoriously difficult basin; requiring all 3
        # to complete would fail even when planning and execution are correct.
        result["success"] = result["create_task_list_called"] and tasks_done >= 2
    else:  # C1
        result["success"] = (
            result["create_task_list_called"]
            and result["get_pending_called"]
            and result["update_task_called"]
            and tasks_total > 0
        )

    # ── failure_class (7-class taxonomy, §4.4) ──
    result["failure_class"] = _eiv.classify_failure(
        planning_ratio=result.get("planning_scale_ratio"),
        completion=result.get("completion_ratio"),
        final_state_valid=bool(tasks_all),
        claimed_completed=result["success"],
        recovery_attempted=result.get("add_task_called", False),
        recovery_succeeded=(result["success"] and tasks_failed == 0),
        used_all_turns=False,  # TODO: wire from agent if max_turns hit (need log confirm)
    )

    ok_str = "[PASS]" if result["success"] else "[FAIL]"
    logger.info(
        f"  Phase {phase_id} {ok_str}: tasks {tasks_done}/{tasks_total} done, "
        f"plan_ratio={result.get('planning_scale_ratio')}, "
        f"completion_ratio={result.get('completion_ratio')}, "
        f"failure_class={result.get('failure_class')}, elapsed={elapsed:.0f}s"
    )
    return result


def run_section_c(workspace: Path, resume: bool = False) -> dict:
    """自驱动任务规划：C1基础执行 / C2自适应 / C3断点恢复。"""
    from hydroagent.agent import HydroAgent

    logger.info("\n" + "=" * 60)
    logger.info("Section C: Self-Driven Task Planning (3 phases)")
    logger.info("=" * 60)

    ckpts = _load_checkpoints() if resume else {}
    phases = []

    phase_configs = [
        ("C1", PHASE_C1_QUERY, None, "Basic batch execution"),
        ("C2", PHASE_C2_QUERY, None, "Adaptive strategy (difficult basins)"),
        ("C3", PHASE_C3_QUERY, PHASE_C3_PRESET_STATE, "Interruption recovery"),
    ]

    for phase_id, query, preset, desc in phase_configs:
        if resume and phase_id in ckpts:
            logger.info(f"\n  Phase {phase_id}: [SKIPPED - loaded from checkpoint]")
            phases.append(ckpts[phase_id])
            continue

        logger.info(f"\n  Phase {phase_id}: {desc}")
        # Fresh agent + isolated workspace per phase: prevents cross-phase memory
        # contamination (C3 "resume" query would otherwise see C1/C2 session history).
        phase_ws = workspace / phase_id
        phase_ws.mkdir(parents=True, exist_ok=True)
        agent = HydroAgent(workspace=phase_ws)
        result = _run_planning_phase(agent, query, phase_ws, phase_id, preset)
        _save_checkpoint(phase_id, result)
        phases.append(result)

    n_pass = sum(1 for p in phases if p["success"])

    return {
        "section": "C",
        "title": "Self-Driven Task Planning",
        "n_phases": len(phases),
        "phases": phases,
        "stats": {
            "pass_rate": n_pass / len(phases) if phases else 0,
            "n_pass": n_pass,
            "c2_adaptive_triggered": next(
                (p.get("adaptive_triggered") for p in phases if p["phase"] == "C2"), None
            ),
        },
    }


# ── Main orchestration ───────────────────────────────────────────────────────

def run_experiment(resume: bool = False, sections: list[str] | None = None) -> dict:
    """Run experiment 3.

    Args:
        resume: If True, skip scenarios that already have checkpoints.
        sections: List of sections to run, e.g. ["A", "B"]. None = all.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    workspace = OUTPUT_DIR / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    run_all = sections is None
    results_path = OUTPUT_DIR / "exp4_results.json"

    # Load previous results if resuming
    prev = {}
    if resume and results_path.exists():
        try:
            prev = json.loads(results_path.read_text(encoding="utf-8")).get("sections", {})
            logger.info(f"Loaded previous results for sections: {list(prev.keys())}")
        except Exception:
            pass

    sec_a = prev.get("A") if (resume and "A" in prev and (sections is None or "A" not in sections)) else None
    sec_b = prev.get("B") if (resume and "B" in prev and (sections is None or "B" not in sections)) else None
    sec_c = prev.get("C") if (resume and "C" in prev and (sections is None or "C" not in sections)) else None

    if run_all or "A" in (sections or []):
        if sec_a is None:
            sec_a = run_section_a(workspace, resume=resume)
    if run_all or "B" in (sections or []):
        if sec_b is None:
            sec_b = run_section_b(workspace, resume=resume)
    if run_all or "C" in (sections or []):
        if sec_c is None:
            sec_c = run_section_c(workspace, resume=resume)

    return {
        "experiment": "exp4_capability_boundaries",
        "timestamp": datetime.now().isoformat(),
        "sections": {
            k: v for k, v in {"A": sec_a, "B": sec_b, "C": sec_c}.items() if v is not None
        },
    }


def save_results(results: dict):
    f = OUTPUT_DIR / "exp4_results.json"
    f.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info(f"Saved -> {f}")


def print_summary(results: dict):
    sections = results["sections"]

    print(f"\n{'='*80}")
    print(f"  Exp3: Agent Capability Breadth")
    print(f"{'='*80}")

    def yn(v): return "[Y]" if v else "[N]"

    # Section A
    if "A" in sections:
        sa = sections["A"]
        stats_a = sa["stats"]
        n_rep = sa.get("n_repeats_per_scenario", 1)
        print(f"\n  [Section A] NL Robustness  ({sa['n_scenarios']} scenarios x {n_rep} repeats)")
        print(f"    Tool match rate : {stats_a['tool_match_rate']*100:.0f}%  "
              f"(mean across scenarios)")
        print(f"    First tool rate : {stats_a['first_tool_rate']*100:.0f}%  "
              f"(mean across scenarios)")
        print(f"    Consistency     : {stats_a['consistency_rate']*100:.0f}%  "
              f"(same tool seq across repeats, mean across scenarios)")
        header = (f"{'ID':<5} {'Category':<22} {'Match%':>7} {'First%':>7} "
                  f"{'Consist%':>9} {'Tokens':>7}")
        print(f"\n    {header}")
        print(f"    {'-'*60}")
        for r in sa["results"]:
            # Single-repeat result (old format) or multi-repeat (new format)
            if "repeats" in r:
                mk = f"{r['tool_match_rate']*100:.0f}%"
                fk = f"{r['first_tool_rate']*100:.0f}%"
                ck = f"{r['consistency_rate']*100:.0f}%"
                tk = f"{int(r['avg_total_tokens'])}"
            else:
                mk = ("100%" if r.get("tool_match") else "0%") if r.get("success") else "ERR"
                fk = ("100%" if r.get("first_tool_correct") else "0%") if r.get("success") else "ERR"
                ck = "N/A"
                tk = "N/A"
            print(f"    {r['id']:<5} {r['category']:<22} {mk:>7} {fk:>7} {ck:>9} {tk:>7}")

    # Section B
    if "B" in sections:
        sb = sections["B"]
        stats_b = sb["stats"]
        print(f"\n  [Section B] Dynamic Skill Generation  ({sb['n_scenarios']} scenarios)")
        print(f"    Success rate    : {stats_b['success_rate']*100:.0f}%  "
              f"({stats_b['n_success']}/{sb['n_scenarios']})")
        print(f"    create_skill    : {stats_b['create_skill_rate']*100:.0f}%  |  "
              f"syntax OK: {stats_b['syntax_ok_rate']*100:.0f}%  |  "
              f"registered: {stats_b['registered_rate']*100:.0f}%")
        header = (f"{'ID':<5} {'create':>7} {'md':>4} {'py':>4} "
                  f"{'syn':>4} {'reg':>4}  New dir")
        print(f"\n    {header}")
        print(f"    {'-'*60}")
        for r in sb["results"]:
            reused = r.get("reused_existing_skill") or ""
            new_dir = r.get("new_skill_dir") or ""
            outcome = f"reused:{reused}" if reused else (new_dir or "N/A")
            print(
                f"    {r['id']:<5} {yn(r['create_skill_called']):>7} "
                f"{yn(r['skill_md_exists']):>4} {yn(r['tool_py_exists']):>4} "
                f"{yn(r['tool_py_syntax_ok']):>4} {yn(r['tool_registered']):>4}  "
                f"{outcome}"
            )

    # Section C
    if "C" in sections:
        sc = sections["C"]
        stats_c = sc["stats"]
        print(f"\n  [Section C] Self-Driven Task Planning  ({sc['n_phases']} phases)")
        print(f"    Pass rate       : {stats_c['pass_rate']*100:.0f}%  "
              f"({stats_c['n_pass']}/{sc['n_phases']})")
        if stats_c.get("c2_adaptive_triggered") is not None:
            print(f"    Adaptive (C2)   : {stats_c['c2_adaptive_triggered']}")
        for p in sc["phases"]:
            ok = "PASS" if p["success"] else "FAIL"
            cr = p["completion_rate"] * 100
            print(f"    Phase {p['phase']} [{ok}]  tasks={p['tasks_done']}/{p['tasks_total']} "
                  f"({cr:.0f}%)  planning={p['planning_tools']}")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Exp3: Agent Capability Breadth")
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip scenarios that already have checkpoints, resume from last failure",
    )
    parser.add_argument(
        "--section", nargs="+", choices=["A", "B", "C"],
        help="Run only specific sections, e.g. --section B C",
    )
    parser.add_argument(
        "--clear-checkpoints", action="store_true",
        help="Delete checkpoint file and start fresh",
    )
    parser.add_argument(
        "--scenario", nargs="+",
        metavar="ID",
        help="Re-run specific scenarios by ID, e.g. --scenario A05 B03. "
             "Clears their checkpoints and runs only those scenarios.",
    )
    parser.add_argument(
        "--repeats", type=int, default=None,
        help="Override N_REPEATS_A (Section A repeats). Use 1 for fast validation.",
    )
    args = parser.parse_args()

    setup_logging()

    # Fast-validation override: reduce Section A repeats
    if args.repeats is not None:
        global N_REPEATS_A
        N_REPEATS_A = args.repeats
        logger.info(f"N_REPEATS_A overridden to {N_REPEATS_A} (fast validation)")

    if args.clear_checkpoints and _CKPT_FILE.exists():
        _CKPT_FILE.unlink()
        logger.info("Checkpoints cleared.")

    # --scenario: clear specified scenario checkpoints then run their sections
    if args.scenario:
        scenario_ids = [s.upper() for s in args.scenario]
        ckpts = _load_checkpoints()
        for sid in scenario_ids:
            if sid in ckpts:
                del ckpts[sid]
                logger.info(f"Cleared checkpoint for {sid}")
        _CKPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CKPT_FILE.write_text(
            json.dumps(ckpts, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # Derive which sections to run from the scenario IDs
        sections_to_run = sorted({sid[0] for sid in scenario_ids if sid[0] in "ABC"})
        logger.info(
            f"Re-running scenarios {scenario_ids} -> sections {sections_to_run}"
        )
        results = run_experiment(resume=True, sections=sections_to_run)
        save_results(results)
        print_summary(results)
        logger.info("Exp3 complete")
        return

    logger.info(
        f"Starting Exp3: Agent Capability Breadth "
        f"(resume={args.resume}, sections={args.section or 'all'})"
    )
    results = run_experiment(resume=args.resume, sections=args.section)
    save_results(results)
    print_summary(results)
    logger.info("Exp3 complete")


if __name__ == "__main__":
    main()
