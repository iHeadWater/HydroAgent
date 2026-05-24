"""
Experiment 3 (paper §4.3) — Structured Knowledge Layer Ablation
================================================================

Goal: quantify how each structured knowledge layer (K0..K4) affects
HydroAgent's BEHAVIOR — workflow route, efficiency, and diagnostic
reasoning quality. The paper's thesis is that knowledge layers shape
HOW the LLM reasons over hydrological evidence, NOT the numerical
calibration outputs (which come from hydromodel/SCE-UA regardless).

Knowledge conditions (cumulative):
  K0 (no_knowledge):     no skill index, no domain knowledge, no profile, no memory, no cognitive
  K1 (skills_only):      +procedural skill docs (skills/*/skill.md, read on demand)
  K2 (skills_domain):    +domain knowledge (hydrological/parameters/failures), read on demand
  K3 (full):             +cross-session basin profile + MEMORY.md
  K4 (full_cognitive):   +expert_hydrologist cognitive framework (always-inject)

For paper §4.3 the user chose to run K0 / K2 / K4 × T1-T4 = 12 instances
(sufficient contrast: no-knowledge baseline / domain-knowledge / full cognitive).
K1 / K3 can be added later if reviewers ask for full ablation curve.

Tasks (T1-T4, adversarial-difficulty increasing):
  T1 standard_calibration   — baseline: all conditions should complete
  T2 boundary_diagnosis     — params engineered to hit boundaries; needs K2
  T3 output_inspection      — needs K2+K4 to interpret FHV/FLV sub-metrics
  T4 poor_performance_diag  — structurally infeasible basin; tests K4 limit-acknowledgment

Three metric categories (computed via experiment/_metrics/):
  1. Workflow route        — core_tool_coverage, detour_count, repeat_call_count
  2. Efficiency            — llm_call_count, tokens (prompt/completion/cached),
                              tokens_per_useful_step, wall_clock_time
  3. Diagnostic reasoning  — DiagScore (5-dim rubric on final_report, rated by
                              user + LLM-as-2nd-rater, agreement reported via Cohen's κ)

Output structure:
  results/paper/exp3/
    checkpoints/<K>_<T>.json        — per-instance checkpoint for resume
    final_reports/<K>_<T>.txt       — agent's final report text (input for DiagScore)
    workspaces/<K>_<T>/             — per-instance HydroAgent workspace
      sessions/*.jsonl              — tool-call log (input for workflow/efficiency)
      state.json                    — if agent maintained one
    exp3_results.json               — aggregated metrics for all instances

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp3_knowledge_ablation.py
  # Add --conditions K0,K2,K4 to override default
  # Add --tasks T1,T2 to run subset
  # Add --resume to continue from checkpoints
"""

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib  # noqa: E402
matplotlib.use("Agg")

from experiment._metrics import efficiency, workflow  # noqa: E402

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("results/paper/exp3")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
REPORTS_DIR = OUTPUT_DIR / "final_reports"
WORKSPACES_DIR = OUTPUT_DIR / "workspaces"

# ── Knowledge conditions (subset chosen for paper §4.3) ───────────────────────

CONDITIONS = [
    # (id,  key,          description) — 4-level threshold ladder (true-zero K0)
    ("K0", "tools_only",  "bare identity + tool schema only; NO model/param/workflow/policy"),
    ("K1", "procedural",  "+procedural: skill rules, workflow, policies, adapter docs, skill index"),
    ("K2", "domain",      "+domain: hydro identity, model/param meanings, algorithms, NSE rules"),
    ("K3", "full",        "+experiential+cognitive: basin profiles, memory, expert framework"),
]


# ── Task definitions ──────────────────────────────────────────────────────────

# Curated execution-focused subset (TE1-TE4). Primary success is automatable:
# workflow completed + valid test-period NSE computed + NSE >= nse_floor +
# converged within turn_budget. nse_floor=None -> only require NSE computed
# (used for the structurally-hard under-specified task, where the point is
# workflow self-organization, not achieving good NSE).
TASKS = {
    "TE1": {
        "name": "standard_calibration",
        "query": (
            "请率定 GR4J 模型，流域 12025000，使用 SCE-UA 算法"
            "（快速验证设置：algorithm_params={'rep': 200, 'ngs': 16}）。"
            "完成后报告训练期与测试期的 NSE/KGE。"
        ),
        "expected_core_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "nse_floor": 0.0,
        "turn_budget": 8,
        "difficulty": "low",
        "tests": "baseline execution — can tools alone (K0) run validate->calibrate->evaluate?",
    },
    "TE2": {
        "name": "harder_basin_calibration",
        "query": (
            "请率定 GR4J 模型，流域 06043500（半干旱山区），使用 SCE-UA 算法"
            "（快速验证设置：algorithm_params={'rep': 200, 'ngs': 16}）。"
            "完成后报告训练期与测试期的 NSE/KGE。"
        ),
        "expected_core_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "nse_floor": 0.0,
        "turn_budget": 10,
        "difficulty": "medium",
        "tests": "harder basin — does knowledge help reach a valid (NSE>0) result?",
    },
    "TE3": {
        "name": "boundary_recovery",
        "query": (
            "请率定 GR4J 模型，流域 11532500，使用 SCE-UA 算法"
            "（快速验证设置：algorithm_params={'rep': 200, 'ngs': 16}，最多 2 轮）。"
            "如果有参数触及范围边界，请诊断并调整范围重新率定，最终给出有效的率定结果。"
        ),
        "expected_core_tools": [
            "validate_basin", "calibrate_model", "llm_calibrate", "evaluate_model"
        ],
        "nse_floor": 0.0,
        "turn_budget": 12,
        "difficulty": "medium-high",
        "tests": "recovery — does procedural/domain knowledge enable boundary recovery to a valid result?",
    },
    "TE4": {
        "name": "underspecified_diagnosis",
        "query": (
            "流域 03439000 用 GR4J 模型总是效果不好，帮我搞清楚原因，能不能改善。"
            "（如需率定，用快速设置 algorithm_params={'rep': 200, 'ngs': 16}）"
        ),
        "expected_core_tools": ["validate_basin", "calibrate_model", "evaluate_model"],
        "nse_floor": None,
        "turn_budget": 10,
        "difficulty": "high",
        "tests": "under-specified — does knowledge curb spiraling and self-organize the workflow?",
    },
}


# ── Layered system-prompt assembly (true-zero K0) ─────────────────────────────

_SKILLS_DIR = Path(__file__).parent.parent / "hydroagent" / "skills"


def _frag(name: str) -> str:
    p = _SKILLS_DIR / name
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _layered_system_prompt(condition_key: str) -> str:
    """Assemble the Section-1 system prompt for a knowledge level.

    K0 tools_only -> core only (bare identity, no hydro/workflow/policy).
    K1 procedural -> core + procedural (skill rules, workflow, tool-calling).
    K2 domain     -> core + procedural + domain (model/param meanings, NSE rules).
    K3 full       -> same prompt as K2 (K3's extra = basin profiles + memory +
                      cognitive, injected by separate sections).
    """
    parts = [_frag("system_core.md")]
    if condition_key in ("procedural", "domain", "full"):
        parts.append(_frag("system_procedural.md"))
    if condition_key in ("domain", "full"):
        parts.append(_frag("system_domain.md"))
    return "\n\n".join(p for p in parts if p)


# ── Knowledge condition toggle (true-zero ladder) ─────────────────────────────

def _apply_condition(agent, condition_key: str) -> dict:
    """Configure the agent's injected context to enforce a knowledge level.

    Layer matrix (on/off per section):
                   sys_prompt   policies adapter skills_idx domain_kb profile memory cognitive
    K0 tools_only  core           off      off     off       off      off     off    off
    K1 procedural  +procedural    on       on      on        off      off     off    off
    K2 domain      +domain        on       on      on        on       off     off    off
    K3 full        +domain        on       on      on        on       on      on     on
    """
    backup = {
        "load_domain":       agent._load_domain_knowledge,
        "available_skills":  agent.skill_registry.available_skills_prompt,
        "get_cognitive":     agent.skill_registry.get_cognitive_prompt,
        "profile_ctx":       agent.memory.format_basin_profiles_for_context,
        "load_mem":          agent.memory.load_knowledge,
        "sys_override":      getattr(agent, "_system_prompt_override", ""),
        "inject_policies":   getattr(agent, "_inject_policies", True),
        "inject_adapter":    getattr(agent, "_inject_adapter_docs", True),
    }

    # Section 1: replace the base system prompt with the layered assembly.
    agent._system_prompt_override = _layered_system_prompt(condition_key)

    procedural_on = condition_key in ("procedural", "domain", "full")
    domain_on = condition_key in ("domain", "full")
    full_on = condition_key == "full"

    # Procedural-layer sections: policies, adapter docs, skill index.
    agent._inject_policies = procedural_on
    agent._inject_adapter_docs = procedural_on
    if not procedural_on:
        agent.skill_registry.available_skills_prompt = lambda *a, **kw: ""

    # Domain-layer: on-demand knowledge/*.md files.
    if not domain_on:
        agent._load_domain_knowledge = lambda q: ""

    # Experiential + cognitive layer (K3 only).
    if not full_on:
        agent.skill_registry.get_cognitive_prompt = lambda: ""
        agent.memory.format_basin_profiles_for_context = lambda ids: ""
        agent.memory.load_knowledge = lambda: ""

    return backup


def _restore_condition(agent, backup: dict):
    agent._load_domain_knowledge = backup["load_domain"]
    agent.skill_registry.available_skills_prompt = backup["available_skills"]
    agent.skill_registry.get_cognitive_prompt = backup["get_cognitive"]
    agent.memory.format_basin_profiles_for_context = backup["profile_ctx"]
    agent.memory.load_knowledge = backup["load_mem"]
    agent._system_prompt_override = backup["sys_override"]
    agent._inject_policies = backup["inject_policies"]
    agent._inject_adapter_docs = backup["inject_adapter"]


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _ckpt_path(cond_id: str, task_id: str) -> Path:
    return CHECKPOINT_DIR / f"{cond_id}_{task_id}.json"


def _load_ckpt(cond_id: str, task_id: str) -> dict | None:
    p = _ckpt_path(cond_id, task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_ckpt(cond_id: str, task_id: str, data: dict):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _ckpt_path(cond_id, task_id).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ── Single-instance runner ────────────────────────────────────────────────────

def run_instance(cond_id: str, cond_key: str, task_id: str, task: dict, resume: bool = True) -> dict:
    """Execute a single (condition, task) instance and compute metrics.

    Returns a dict with: condition, task, success, workflow{...},
    efficiency{...}, final_report_path, session_jsonl_path, error.
    Auto-skipped if a checkpoint with success=True exists and resume=True.
    """
    if resume:
        existing = _load_ckpt(cond_id, task_id)
        if existing and existing.get("success"):
            logger.info(f"[skip] {cond_id} × {task_id} (cached)")
            return existing

    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    workspace = WORKSPACES_DIR / f"{cond_id}_{task_id}"
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info(f"  {cond_id} ({cond_key}) × {task_id} ({task['name']})")
    logger.info(f"  Query: {task['query'][:100]}...")
    logger.info("=" * 70)

    agent = HydroAgent(workspace=workspace, ui=ConsoleUI(mode="dev"))
    backup = _apply_condition(agent, cond_key)

    # Turn cap = task budget: bounds spiraling and defines convergence
    # (hitting the cap == did not converge within budget == failure).
    turn_budget = task.get("turn_budget", 12)
    agent.max_turns = turn_budget

    t0 = time.time()
    final_report = ""
    error_msg = None
    try:
        final_report = agent.run(task["query"])
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Instance failed: {error_msg}")
        logger.error(traceback.format_exc())
    finally:
        _restore_condition(agent, backup)
    wall_time_s = round(time.time() - t0, 2)

    # Save final report to disk for DiagScore rating
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"{cond_id}_{task_id}.txt"
    report_file.write_text(
        f"# Condition: {cond_id} ({cond_key})\n"
        f"# Task: {task_id} — {task['name']}\n"
        f"# Query: {task['query']}\n"
        f"# Wall-clock: {wall_time_s}s\n"
        f"# Generated: {datetime.now().isoformat()}\n"
        f"# Error: {error_msg or '(none)'}\n"
        f"# {'=' * 60}\n\n"
        f"{final_report}\n",
        encoding="utf-8",
    )

    # Locate the session JSONL just written
    sessions = sorted((workspace / "sessions").glob("*.jsonl"))
    session_path = str(sessions[-1]) if sessions else None

    # Compute workflow + efficiency metrics
    wf = workflow.summary(
        session_path or "",
        expected_tools=task["expected_core_tools"],
    ) if session_path else {}
    eff = efficiency.summary(session_path or "") if session_path else {}

    # ── Strict, quantitative task-success gate ──────────────────────────────
    # Primary success = workflow executed (valid test-period NSE computed)
    # AND NSE >= nse_floor (None -> only require NSE computed)
    # AND converged within turn budget (did not hit the turn cap).
    test_nse = None
    try:
        from experiment.exp2_llm_calibration import _extract_from_log, _evaluate_from_disk
        extracted = _extract_from_log(agent.memory._log)
        cal_dir = extracted.get("calibration_dir")
        if cal_dir:
            _, test_m = _evaluate_from_disk(cal_dir, agent.cfg)
            v = test_m.get("NSE")
            test_nse = float(v) if isinstance(v, (int, float)) else None
    except Exception as e:
        logger.warning(f"NSE extraction failed: {e}")

    llm_calls = eff.get("llm_calls") or 0
    nse_floor = task.get("nse_floor", 0.0)
    hit_cap = llm_calls >= turn_budget
    converged = (error_msg is None) and (not hit_cap)
    nse_ok = (test_nse is not None) and (nse_floor is None or test_nse >= nse_floor)
    task_success = bool(converged and nse_ok)

    record = {
        "condition_id": cond_id,
        "condition_key": cond_key,
        "task_id": task_id,
        "task_name": task["name"],
        "difficulty": task["difficulty"],
        "tests": task["tests"],
        "success": error_msg is None,          # ran without crashing
        "task_success": task_success,          # strict gate (converged + valid NSE)
        "test_nse": test_nse,
        "nse_floor": nse_floor,
        "turn_budget": turn_budget,
        "hit_cap": hit_cap,
        "converged": converged,
        "error": error_msg,
        "wall_clock_total_s": wall_time_s,
        "final_report_chars": len(final_report or ""),
        "workflow": wf,
        "efficiency": eff,
        "final_report_path": str(report_file),
        "session_jsonl_path": session_path,
        "workspace": str(workspace),
        "timestamp": datetime.now().isoformat(),
    }
    _save_ckpt(cond_id, task_id, record)
    logger.info(
        f"  -> done in {wall_time_s}s | "
        f"task_success={task_success} | test_nse={test_nse} | "
        f"turns={llm_calls}/{turn_budget}{' (HIT CAP)' if hit_cap else ''} | "
        f"coverage={wf.get('core_tool_coverage')} | "
        f"tokens={eff.get('tokens', {}).get('total')}"
    )
    return record


# ── Main ──────────────────────────────────────────────────────────────────────

def setup_logging():
    log_file = Path("logs") / f"exp3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def main():
    ap = argparse.ArgumentParser(description="Exp 3 — Knowledge Layer Ablation")
    ap.add_argument(
        "--conditions", default="K0,K1,K2,K3",
        help="Comma-separated condition IDs (default: K0,K1,K2,K3 — true-zero ladder)"
    )
    ap.add_argument(
        "--tasks", default="TE1,TE2,TE3,TE4",
        help="Comma-separated task IDs (default: TE1,TE2,TE3,TE4)"
    )
    ap.add_argument(
        "--no-resume", action="store_true",
        help="Force re-run even if checkpoint exists"
    )
    args = ap.parse_args()

    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cond_filter = set(args.conditions.split(","))
    task_filter = [t for t in args.tasks.split(",") if t in TASKS]
    conds = [c for c in CONDITIONS if c[0] in cond_filter]

    logger.info(f"Conditions: {[c[0] for c in conds]}")
    logger.info(f"Tasks: {task_filter}")
    logger.info(f"Total instances: {len(conds) * len(task_filter)}")
    logger.info(f"Resume: {not args.no_resume}")

    results = []
    for cond_id, cond_key, cond_desc in conds:
        for task_id in task_filter:
            task = TASKS[task_id]
            rec = run_instance(cond_id, cond_key, task_id, task, resume=not args.no_resume)
            results.append(rec)

    # Aggregate
    out = OUTPUT_DIR / "exp3_results.json"
    out.write_text(
        json.dumps({
            "experiment": "exp3_knowledge_ablation",
            "timestamp": datetime.now().isoformat(),
            "conditions": [{"id": c[0], "key": c[1], "desc": c[2]} for c in conds],
            "tasks": {k: {"name": v["name"], "difficulty": v["difficulty"]}
                      for k, v in TASKS.items() if k in task_filter},
            "n_instances": len(results),
            "results": results,
        }, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info(f"Saved aggregated results: {out}")
    logger.info("Next steps:")
    logger.info(f"  1. User rates final_reports/*.txt manually -> _annot/human_template.csv")
    logger.info(f"  2. Run: python experiment/_annot/llm_rater.py results/paper/exp3/final_reports/")
    logger.info(f"  3. Run: python experiment/_annot/aggregate_diag.py")


if __name__ == "__main__":
    main()
