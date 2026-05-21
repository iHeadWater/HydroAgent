"""
Author: HydroAgent Team
Date: 2026-02-08
Description: Agentic Loop core - the heart of HydroAgent.
             LLM decides what to do, code only executes.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from hydroagent.config import load_config
from hydroagent.llm import LLMClient, LLMResponse
from hydroagent.memory import Memory
from hydroagent.skill_registry import SkillRegistry
from hydroagent.skill_states import SkillStateManager
from hydroagent.tools import discover_tools, get_tool_schemas
from hydroagent.utils.context_utils import estimate_tokens, truncate_tool_result, semantic_truncate
from hydroagent.interface.ui import ConsoleUI

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


class HydroAgent:
    """LLM-driven hydrological model calibration agent.

    Core loop: Query → LLM reasons → calls tools → LLM reasons → ... → final answer.
    No state machine, no if-else routing, no multi-agent orchestration.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        workspace: Path | None = None,
        ui: ConsoleUI | None = None,
        config_override: dict | None = None,
        prompt_mode: str = "full",
    ):
        self.cfg = load_config(config_path)
        if config_override:
            _deep_merge(self.cfg, config_override)

        # Config validation: fail early with a clear message instead of KeyError
        if "llm" not in self.cfg:
            raise ValueError(
                "Configuration error: missing required key 'llm'. "
                "Check your config file or configs/private.py."
            )
        for _k in ("model", "base_url"):
            if _k not in self.cfg["llm"]:
                raise ValueError(
                    f"Configuration error: missing required LLM config key '{_k}'. "
                    f"Check the [llm] section of your config."
                )

        self.llm = LLMClient(self.cfg["llm"])
        self.memory = Memory(workspace or Path("."))
        self.tools = discover_tools()
        self.tool_schemas = get_tool_schemas()
        self.max_turns = self.cfg.get("max_turns", 30)
        self.workspace = workspace or Path(".")
        self.ui = ui or ConsoleUI(mode="user")
        self._pause_requested = False   # set by request_pause(); checked between turns
        self._stop_requested  = False   # set by request_stop(); stops after current tool
        # Prompt mode: "full" injects domain knowledge + memory + basin profiles.
        # "minimal" keeps only core system prompt + skills + adapter docs — faster
        # and cheaper for sub-agent / batch scenarios where domain context isn't needed.
        self._prompt_mode = prompt_mode

        skills_dir = Path(__file__).parent / "skills"
        self.skill_registry = SkillRegistry(skills_dir)
        self.skill_states = SkillStateManager(skills_dir)

        # CC-3: Subagent registry
        from hydroagent.agents import AgentRegistry
        self.agent_registry = AgentRegistry(self.workspace)

        # CC-4: PostToolUse hook registry. Maps tool_name -> list of callables.
        # Each hook: fn(tool_name: str, arguments: dict, result: Any) -> None
        # External plugins / tests can add hooks via register_post_hook().
        self._post_tool_hooks: dict[str, list] = {}
        self._register_builtin_post_hooks()

        logger.info(
            f"HydroAgent initialized: {len(self.tools)} tools, "
            f"{len(self.skill_registry.skills)} skills, "
            f"model={self.cfg['llm']['model']}, max_turns={self.max_turns}"
        )

    def register_post_hook(self, tool_name: str, fn) -> None:
        """Register a PostToolUse hook for the given tool name.

        Hook signature: fn(tool_name: str, arguments: dict, result: Any) -> None
        Hooks are called after the tool executes, in registration order.
        Exceptions are caught and logged; they do not abort the agent loop.
        """
        self._post_tool_hooks.setdefault(tool_name, []).append(fn)

    def _register_builtin_post_hooks(self) -> None:
        """Register built-in PostToolUse hooks (replaces the if-chain in _execute_tool)."""
        # Auto-save basin profile after successful calibration
        for tool in ("calibrate_model", "llm_calibrate"):
            self.register_post_hook(tool, self._hook_save_basin_profile)
        # Show task progress in UI after task-state-mutating tools
        for tool in ("create_task_list", "update_task", "add_task"):
            self.register_post_hook(tool, self._hook_task_progress)
        # Refresh tool/skill registries after dynamic tool/skill/adapter creation
        self.register_post_hook("create_skill",   self._hook_refresh_registries)
        self.register_post_hook("create_adapter", self._hook_reload_adapters)

    def _hook_save_basin_profile(self, name: str, arguments: dict, result: Any) -> None:
        if not (isinstance(result, dict) and result.get("success")):
            return
        basin_ids = arguments.get("basin_ids", [])
        model_name = arguments.get("model_name", "")
        algorithm = arguments.get("algorithm", "SCE_UA")
        best_params = result.get("best_params", {})
        if name == "calibrate_model":
            metrics = result.get("metrics", {})
        else:
            nse = result.get("best_nse")
            metrics = {"NSE": nse} if nse is not None else {}
        for basin_id in basin_ids:
            self.memory.save_basin_profile(basin_id, model_name, best_params, metrics, algorithm)

    def _hook_task_progress(self, name: str, arguments: dict, result: Any) -> None:
        if isinstance(result, dict) and result.get("success"):
            self.ui.on_task_progress(self.workspace)

    def _hook_refresh_registries(self, name: str, arguments: dict, result: Any) -> None:
        if not (isinstance(result, dict) and result.get("success")):
            return
        self.tools = discover_tools()
        self.tool_schemas = get_tool_schemas()
        self.skill_registry = SkillRegistry(Path(__file__).parent / "skills")
        logger.info("Registries refreshed: %d tools, %d skills", len(self.tools), len(self.skill_registry.skills))
        self.ui.dev_log(f"Registry refreshed: {len(self.tools)} tools, {len(self.skill_registry.skills)} skills")

    def _hook_reload_adapters(self, name: str, arguments: dict, result: Any) -> None:
        if isinstance(result, dict) and result.get("success"):
            from hydroagent.adapters import reload_adapters
            reload_adapters()
            self.ui.dev_log("Adapter registry reloaded after create_adapter.")

    def request_stop(self):
        """Request immediate stop after current tool completes."""
        self._stop_requested = True

    def run(self, query: str, prior_messages: list[dict] | None = None) -> str:
        """Run the agentic loop for a user query.

        Args:
            query: Natural language query (Chinese or English).

        Returns:
            Final text response from the LLM.
        """
        messages = self._build_context(query, prior_messages=prior_messages)
        self.llm.tokens.reset()   # reset per-session counter
        _run_start = time.time()

        # Token budget (0 = unlimited). If set, agent is informed at start
        # and receives progressive warnings as it approaches the limit.
        self._session_budget = self.cfg.get("session_budget_tokens", 0)
        if self._session_budget:
            budget_note = (
                f"\n\n[System] Token budget for this session: {self._session_budget:,} tokens. "
                f"Monitor your usage. When approaching the limit, prioritize wrapping up "
                f"completed work over starting new sub-tasks."
            )
            messages[0]["content"] += budget_note
            logger.info(f"Session budget: {self._session_budget:,} tokens")

        logger.info(f"Starting agentic loop for: {query[:80]}...")
        self.ui.on_query(query)

        _consecutive: dict[str, int] = {}   # tool_name -> consecutive call count
        _MAX_CONSECUTIVE = 4                 # stop loop if same tool called >4 times in a row
        _recent_tools: list[str] = []        # sliding window for alternating-loop detection

        _total_calls: dict[str, int] = {}    # tool_name -> total calls this session
        # When a tool has been called this many times total without resolving the task,
        # inject a system nudge to use ask_user or stop instead of keep retrying.
        _TOTAL_WARN_AT = {
            "generate_code": 3,
            "run_code":       5,
            "inspect_dir":    4,
        }
        _total_warned: set[str] = set()      # tools already warned about (once per session)

        for turn in range(self.max_turns):
            logger.debug(f"Turn {turn + 1}/{self.max_turns}")

            # Check stop/pause flag (set externally, e.g. web UI Stop button)
            if self._stop_requested:
                self._stop_requested = False
                msg = "已停止。"
                self.memory.save_session(query, msg)
                self.ui.on_answer(msg, turn)
                return msg

            if self._pause_requested:
                self._pause_requested = False
                msg = "已暂停。任务状态已保存，输入 /resume 继续批量任务。"
                self.memory.save_session(query, msg)
                self.ui.on_answer(msg, turn)
                return msg

            messages = self._maybe_compress_history(messages)

            # Per-turn token budget awareness
            est_tokens = estimate_tokens(messages)
            tok_so_far = self.llm.tokens.summary()
            used = tok_so_far["total_tokens"]
            logger.debug(
                "Turn %d | context ~%d est. tokens | session used: %d tokens",
                turn + 1, est_tokens, used,
            )

            if self._session_budget and self._session_budget > 0:
                ratio = used / self._session_budget
                remaining = self._session_budget - used
                if ratio >= 1.0:
                    # Over budget — inject stop signal, let agent give final answer
                    stop_msg = (
                        f"[System] Token budget exhausted: {used:,}/{self._session_budget:,} tokens used. "
                        f"Do NOT call any more tools. Immediately summarize all completed work "
                        f"and give your final answer now."
                    )
                    logger.warning("Token budget exhausted (%d/%d). Injecting stop signal.", used, self._session_budget)
                    self.ui.dev_log(f"Token budget exhausted: {used:,}/{self._session_budget:,}")
                    messages.append({"role": "user", "content": stop_msg})
                elif ratio >= 0.8:
                    # 80%+ used — warn agent, let it decide
                    warn_msg = (
                        f"[System] Token budget warning: {used:,}/{self._session_budget:,} tokens used "
                        f"({ratio*100:.0f}%, ~{remaining:,} remaining). "
                        f"Prioritize completing in-progress tasks over starting new ones. "
                        f"If the current task cannot be finished within the budget, summarize progress and stop."
                    )
                    logger.warning("Token budget at %.0f%% (%d/%d).", ratio * 100, used, self._session_budget)
                    self.ui.dev_log(f"Token budget: {ratio*100:.0f}% ({used:,}/{self._session_budget:,})")
                    messages.append({"role": "user", "content": warn_msg})
                elif ratio >= 0.6:
                    logger.info("Token budget: %.0f%% used (%d/%d).", ratio * 100, used, self._session_budget)
                    self.ui.dev_log(f"Token budget: {ratio*100:.0f}% ({used:,}/{self._session_budget:,})")

            with self.ui.thinking(turn + 1):
                response = self.llm.chat(messages, tools=self.tool_schemas)

            # Emit reasoning/thinking content if present (reasoning models only).
            # Only show text that accompanies tool calls if the model explicitly produced it
            # (e.g. extended thinking or a dialogue model that writes reasoning inline).
            # Do NOT synthesise fallback notes — an empty block is better than noise.
            thought = response.thinking or (response.text if response.tool_calls else None)
            if thought and hasattr(self.ui, "on_thought"):
                self.ui.on_thought(thought, turn + 1)

            if response.is_text():
                tok = self.llm.tokens.summary()
                logger.info(
                    f"Completed in {turn + 1} turns | "
                    f"tokens: prompt={tok['prompt_tokens']:,} "
                    f"completion={tok['completion_tokens']:,} "
                    f"total={tok['total_tokens']:,} "
                    f"calls={tok['calls']}"
                )
                self.memory.save_session(query, response.text)
                self.ui.on_answer(response.text, turn + 1)
                if hasattr(self.ui, "on_session_summary"):
                    self.ui.on_session_summary(
                        total_turns=turn + 1,
                        elapsed_s=time.time() - _run_start,
                        tokens=tok,
                    )
                return response.text

            # LLM wants to call tools
            if self.llm.supports_function_calling:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                # DeepSeek V4+ thinking mode requires reasoning_content echoed back.
                if self.llm.needs_reasoning_echo and response.thinking:
                    assistant_msg["reasoning_content"] = response.thinking
                messages.append(assistant_msg)

                # Attach LLM metadata (tokens, thinking) only to the FIRST tool
                # call of this turn — subsequent tool calls in the same turn
                # share the same LLM invocation, so don't double-count.
                _llm_meta_attached_this_turn = False

                for tc in response.tool_calls:
                    # Stop check before executing each tool
                    if self._stop_requested:
                        self._stop_requested = False
                        stop_msg = "已停止。"
                        self.ui.on_answer(stop_msg, turn)
                        return stop_msg

                    # Consecutive-call guard: abort if same tool is stuck in a loop
                    _consecutive[tc.name] = _consecutive.get(tc.name, 0) + 1
                    for other in list(_consecutive):
                        if other != tc.name:
                            _consecutive[other] = 0
                    if _consecutive[tc.name] > _MAX_CONSECUTIVE:
                        loop_msg = (
                            f"Tool `{tc.name}` has been called {_consecutive[tc.name]} times "
                            f"consecutively. Stopping to avoid a runaway loop. "
                            "Please summarize what you have accomplished so far and stop."
                        )
                        logger.warning(loop_msg)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"error": loop_msg, "success": False}),
                        })
                        break

                    # Alternating-loop guard: catch A->B->A->B patterns missed by consecutive counter
                    _recent_tools.append(tc.name)
                    if len(_recent_tools) > 6:
                        _recent_tools.pop(0)
                    if len(_recent_tools) >= 4:
                        last4 = _recent_tools[-4:]
                        if (last4[0] == last4[2] and last4[1] == last4[3]
                                and last4[0] != last4[1]):
                            loop_msg = (
                                f"Alternating loop detected: {'->'.join(last4)}. "
                                "Stopping to avoid a runaway loop. "
                                "Please summarize what you have accomplished so far and stop."
                            )
                            logger.warning(loop_msg)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps({"error": loop_msg, "success": False}),
                            })
                            break

                    self.ui.on_tool_start(tc.name, tc.arguments)
                    t0 = time.time()
                    result = {"error": "execution failed", "success": False}
                    try:
                        with self.ui.suppress_tool_output(tc.name):
                            result = self._execute_tool(tc.name, tc.arguments)
                    finally:
                        _elapsed = time.time() - t0
                        self.ui.on_tool_end(tc.name, result, _elapsed)

                    # Attach per-turn LLM metadata only on first tool of this turn
                    _first = not _llm_meta_attached_this_turn
                    _llm_meta_attached_this_turn = True
                    self.memory.log_tool_call(
                        tc.name, tc.arguments, result,
                        turn_id=turn,
                        elapsed_s=_elapsed,
                        llm_tokens=(self.llm.tokens.last_call() if _first else None),
                        llm_thinking_excerpt=(response.thinking if _first else None),
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": truncate_tool_result(tc.name, result),
                    })

                    # Total-call guard: catch alternating loops (e.g. generate_code->run_code->...)
                    _total_calls[tc.name] = _total_calls.get(tc.name, 0) + 1
                    warn_at = _TOTAL_WARN_AT.get(tc.name)
                    if (
                        warn_at
                        and _total_calls[tc.name] >= warn_at
                        and tc.name not in _total_warned
                    ):
                        _total_warned.add(tc.name)
                        nudge = (
                            f"[System] `{tc.name}` has been called {_total_calls[tc.name]} times "
                            f"this session without fully resolving the task. "
                            f"Repeating the same approach is unlikely to help. "
                            f"If critical information is missing, use `ask_user` to get it from the user. "
                            f"If the task cannot be completed, stop and report what went wrong."
                        )
                        logger.warning(
                            "Total-call nudge: %s called %d times.", tc.name, _total_calls[tc.name]
                        )
                        messages.append({"role": "user", "content": nudge})

                # Reconcile: every tool_call_id MUST have a tool response or strict
                # APIs (DeepSeek) reject the next request with 400. Loop guards above
                # may `break` mid-turn, leaving later parallel tool_calls unanswered.
                _answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
                for tc in response.tool_calls:
                    if tc.id not in _answered:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {"error": "skipped due to loop guard", "success": False}
                            ),
                        })

                # CC-2: inject task status once after ALL tool results for this turn
                # (must be after all tool messages to avoid breaking the API message order)
                task_note = self._get_task_status_note()
                if task_note:
                    messages.append({"role": "user", "content": task_note})

            else:
                # Prompt-based fallback
                if response.text:
                    messages.append({"role": "assistant", "content": response.text})

                _llm_meta_attached_this_turn = False
                for tc in response.tool_calls:
                    # Consecutive-call guard (same logic as function-calling branch)
                    _consecutive[tc.name] = _consecutive.get(tc.name, 0) + 1
                    for other in list(_consecutive):
                        if other != tc.name:
                            _consecutive[other] = 0
                    if _consecutive[tc.name] > _MAX_CONSECUTIVE:
                        loop_msg = (
                            f"Tool `{tc.name}` called {_consecutive[tc.name]} times "
                            "consecutively. Stopping loop. Summarize and stop."
                        )
                        logger.warning(loop_msg)
                        messages.append({
                            "role": "user",
                            "content": f"SYSTEM: {loop_msg}",
                        })
                        break

                    # Alternating-loop guard (shared _recent_tools with function-calling branch)
                    _recent_tools.append(tc.name)
                    if len(_recent_tools) > 6:
                        _recent_tools.pop(0)
                    if len(_recent_tools) >= 4:
                        last4 = _recent_tools[-4:]
                        if (last4[0] == last4[2] and last4[1] == last4[3]
                                and last4[0] != last4[1]):
                            loop_msg = (
                                f"Alternating loop detected: {'->'.join(last4)}. "
                                "Stopping loop. Summarize and stop."
                            )
                            logger.warning(loop_msg)
                            messages.append({
                                "role": "user",
                                "content": f"SYSTEM: {loop_msg}",
                            })
                            break

                    self.ui.on_tool_start(tc.name, tc.arguments)
                    t0 = time.time()
                    result = {"error": "execution failed", "success": False}
                    try:
                        with self.ui.suppress_tool_output(tc.name):
                            result = self._execute_tool(tc.name, tc.arguments)
                    finally:
                        _elapsed = time.time() - t0
                        self.ui.on_tool_end(tc.name, result, _elapsed)

                    _first = not _llm_meta_attached_this_turn
                    _llm_meta_attached_this_turn = True
                    self.memory.log_tool_call(
                        tc.name, tc.arguments, result,
                        turn_id=turn,
                        elapsed_s=_elapsed,
                        llm_tokens=(self.llm.tokens.last_call() if _first else None),
                        llm_thinking_excerpt=(response.thinking if _first else None),
                    )

                    tool_result_content = f"Tool `{tc.name}` returned:\n```json\n{truncate_tool_result(tc.name, result)}\n```\nContinue with the next step."
                    task_note = self._get_task_status_note()
                    if task_note:
                        tool_result_content += f"\n\n{task_note}"
                    messages.append({"role": "user", "content": tool_result_content})

                    # Total-call guard (prompt-based branch)
                    _total_calls[tc.name] = _total_calls.get(tc.name, 0) + 1
                    warn_at = _TOTAL_WARN_AT.get(tc.name)
                    if (
                        warn_at
                        and _total_calls[tc.name] >= warn_at
                        and tc.name not in _total_warned
                    ):
                        _total_warned.add(tc.name)
                        nudge = (
                            f"[System] `{tc.name}` has been called {_total_calls[tc.name]} times "
                            f"this session without fully resolving the task. "
                            f"Repeating the same approach is unlikely to help. "
                            f"If critical information is missing, use `ask_user` to get it from the user. "
                            f"If the task cannot be completed, stop and report what went wrong."
                        )
                        logger.warning(
                            "Total-call nudge: %s called %d times.", tc.name, _total_calls[tc.name]
                        )
                        messages.append({"role": "user", "content": nudge})

        logger.warning(f"Reached max turns ({self.max_turns})")
        self.ui.on_max_turns()
        final = "已达到最大步骤数，请检查已有结果。"
        self.memory.save_session(query, final)
        return final

    # Hard limits for context injection (chars). Prevents runaway memory from
    # bloating the system prompt with accumulated session data.
    _MAX_MEMORY_CHARS   = 4_000   # load_knowledge() cap
    _MAX_PROFILE_CHARS  = 3_000   # basin profiles cap
    _MAX_SYSTEM_CHARS   = 20_000  # total system prompt cap — warn if exceeded
    _WARN_CONTEXT_TOKENS = 30_000 # warn if initial context already exceeds this

    def _build_system_prompt(self, query: str) -> str:
        """Compose the system prompt from modular sections.

        Prompt modes
        ------------
        full    -- all sections: core + skills + adapters + domain + basin + memory.
                   Use for interactive sessions and single-basin tasks.
        minimal -- core + skills + adapters only.
                   Use for sub-agent calls, batch inner loops, or token-budget runs
                   where domain context is already embedded in the task description.
        """
        parts: list[str] = []

        # ── Section 1: Core identity & instructions (always included) ──────────
        parts.append(self._load_system_prompt())

        # ── Section 1.5: Behavior policies (always included, even in minimal mode) ─
        # Gateable for ablation experiments (default on -> normal behaviour).
        _policy_dir = Path(__file__).parent / "policy"
        if getattr(self, "_inject_policies", True) and _policy_dir.exists():
            _policy_parts = [
                pf.read_text(encoding="utf-8").strip()
                for pf in sorted(_policy_dir.glob("*.md"))
            ]
            if _policy_parts:
                _policy_text = "\n\n".join(_policy_parts)
                _MAX_POLICY_CHARS = 2_000
                if len(_policy_text) > _MAX_POLICY_CHARS:
                    _policy_text = _policy_text[:_MAX_POLICY_CHARS] + "\n...(policy truncated)"
                parts.append("## Behavior Policies\n\n" + _policy_text)

        # ── Section 1.7: Cognitive skills — always-injected domain expert framework ─
        cognitive_prompt = self.skill_registry.get_cognitive_prompt()
        if cognitive_prompt:
            parts.append(cognitive_prompt)

        # ── Section 2: Available skills index (always included) ─────────────────
        available_skills = self.skill_registry.available_skills_prompt(self.skill_states)
        if available_skills:
            parts.append(available_skills)

        # ── Section 2.5: Available subagents (always included) ───────────────────
        available_agents = self.agent_registry.available_agents_prompt()
        if available_agents:
            parts.append(available_agents)

        # ── Section 3: Package adapter skill docs (always included) ─────────────
        # Gateable for ablation experiments (default on -> normal behaviour).
        if getattr(self, "_inject_adapter_docs", True):
            from hydroagent.adapters import get_all_skill_docs
            adapter_docs = get_all_skill_docs()
            if adapter_docs:
                parts.append("## Package Adapter Skills\n" + "\n---\n".join(adapter_docs))

        if self._prompt_mode == "minimal":
            logger.info("[agent] prompt_mode=minimal: skipping domain/basin/memory sections")
        else:
            # ── Section 4: Domain knowledge ──────────────────────────────────────
            # Knowledge files are NOT auto-injected here.
            # Agent consults them on-demand via read_file when needed.
            # Skill.md guides the Agent on which file to read in which situation.

            # ── Section 5: Basin profiles (full mode only) ────────────────────────
            basin_ids_in_query = re.findall(r'\b\d{8}\b', query)
            basin_profiles = self.memory.format_basin_profiles_for_context(basin_ids_in_query)
            if basin_profiles:
                parts.append(
                    semantic_truncate(basin_profiles, self._MAX_PROFILE_CHARS, "basin profiles")
                )

            # ── Section 6: Cross-session memory (full mode only) ──────────────────
            memory = self.memory.load_knowledge()
            if memory:
                parts.append(
                    "## Memory (from previous sessions)\n"
                    + semantic_truncate(memory, self._MAX_MEMORY_CHARS, "memory")
                )

        system_content = "\n\n".join(p for p in parts if p)

        if len(system_content) > self._MAX_SYSTEM_CHARS:
            logger.error(
                "System prompt is abnormally large: %d chars (~%d est. tokens). "
                "This will consume excessive API quota. Check memory/profile injection.",
                len(system_content), len(system_content) // 3,
            )
            self.ui.dev_log(
                f"WARNING: system prompt = {len(system_content):,} chars "
                f"(~{len(system_content)//3:,} est. tokens). May hit API limits."
            )

        return system_content

    def _build_context(self, query: str, prior_messages: list[dict] | None = None) -> list[dict]:
        """Build initial message context from the modular system prompt + conversation history."""
        system_content = self._build_system_prompt(query)
        messages = [{"role": "system", "content": system_content}]
        if prior_messages:
            messages.extend(prior_messages)
        messages.append({"role": "user", "content": query})

        est = estimate_tokens(messages)
        if est > self._WARN_CONTEXT_TOKENS:
            logger.warning(
                "Initial context already ~%d est. tokens before any tool calls. "
                "Consider reducing memory or knowledge injection.",
                est,
            )

        return messages

    def _load_domain_knowledge(self, query: str) -> str:
        """Load relevant domain knowledge files based on query keywords."""
        knowledge_dir = Path(__file__).parent / "knowledge"
        if not knowledge_dir.exists():
            return ""

        query_lower = query.lower()
        loaded = []

        calib_keywords = ["率定", "calibrat", "优化", "参数", "nse", "算法", "边界"]
        if any(kw in query_lower for kw in calib_keywords):
            guide = knowledge_dir / "calibration_guide.md"
            if guide.exists():
                loaded.append(guide.read_text(encoding="utf-8"))

        model_keywords = ["gr4j", "gr5j", "gr6j", "xaj", "参数含义", "模型选择"]
        if any(kw in query_lower for kw in model_keywords):
            params = knowledge_dir / "model_parameters.md"
            if params.exists():
                loaded.append(params.read_text(encoding="utf-8"))

        if not loaded:
            return ""

        result = []
        for text in loaded:
            if len(text) > 2000:
                text = text[:2000] + "\n...(truncated)"
            result.append(text)

        return "\n\n---\n\n".join(result)

    def _load_system_prompt(self) -> str:
        """Load the system prompt.

        When running as a subagent, _subagent_system_prompt overrides the
        default system.md so the subagent uses its own focused instructions.
        """
        # Experiment override: assemble a custom core system prompt (e.g. exp3
        # knowledge-ablation builds a tools-only K0 prompt). Takes precedence.
        if getattr(self, "_system_prompt_override", ""):
            return self._system_prompt_override
        # CC-3: subagent custom prompt override
        if getattr(self, "_subagent_system_prompt", ""):
            return self._subagent_system_prompt
        skill_path = Path(__file__).parent / "skills" / "system.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")
        return _DEFAULT_SYSTEM_PROMPT

    def request_pause(self):
        """Request the agent to pause after the current turn completes."""
        self._pause_requested = True

    # ── Context compression ──────────────────────────────────────────

    def _maybe_compress_history(self, messages: list[dict]) -> list[dict]:
        """Compress conversation history when approaching context limit.

        Keeps: system message, original user query, last 4 messages.
        Summarizes everything in between into a single assistant message.
        Triggered when estimated tokens exceed context_compress_threshold
        (default 60,000 tokens, ~180k chars).
        """
        threshold = self.cfg.get("context_compress_threshold", 60_000)
        est = estimate_tokens(messages)
        if est < threshold:
            return messages

        # Safety: if estimated tokens are impossibly large (likely a bug in
        # memory/knowledge injection), try a forced aggressive compression first
        # rather than aborting immediately and losing the entire session.
        _HARD_LIMIT = 500_000  # ~1.5M chars — no legitimate context exceeds this
        if est > _HARD_LIMIT:
            logger.error(
                "Context far exceeds HARD_LIMIT (~%d est. tokens). "
                "Attempting forced compression to system+query+last-2.",
                est,
            )
            if len(messages) > 4:
                compressed = [messages[0], messages[1]] + messages[-2:]
                logger.warning(
                    "Forced compression: %d messages -> %d", len(messages), len(compressed)
                )
                return compressed
            raise RuntimeError(
                f"Context size is abnormally large: ~{est:,} est. tokens "
                f"({est * 3:,} chars). Forced compression did not help. "
                f"Check memory.load_knowledge() and basin profiles."
            )

        # Need at least system + user + some history to compress
        # Structure: [system(0), user_query(1), ...history..., tail(-4):]
        keep_tail = 4
        if len(messages) <= 2 + keep_tail:
            return messages

        system_msg    = messages[0]
        user_query    = messages[1]
        middle        = messages[2: -keep_tail]
        tail          = messages[-keep_tail:]

        if not middle:
            return messages

        logger.info(
            "Context approaching limit (%d est. tokens), compressing %d messages...",
            estimate_tokens(messages), len(middle),
        )

        middle_text = json.dumps(middle, ensure_ascii=False)
        summary_response = self.llm.chat([
            {
                "role": "system",
                "content": (
                    "You are a concise summarizer. "
                    "Summarize the following conversation history in a few bullet points. "
                    "Focus on: which tools were called, what results were obtained, "
                    "what decisions were made. Keep it under 300 words."
                ),
            },
            {"role": "user", "content": middle_text},
        ])

        summary_msg = {
            "role": "assistant",
            "content": "[Earlier conversation summary]\n" + summary_response.text,
        }

        compressed = [system_msg, user_query, summary_msg] + tail
        logger.info(
            "History compressed: %d -> %d est. tokens",
            estimate_tokens(messages),
            estimate_tokens(compressed),
        )
        self.ui.dev_log(
            f"Context compressed: ~{estimate_tokens(messages):,} tokens "
            f"-> ~{estimate_tokens(compressed):,} tokens"
        )
        return compressed

    def _get_task_status_note(self) -> str:
        """Return a compact task-status message to inject after tool calls.

        Mirrors Claude Code's behavior: after every tool result, inject the
        current TODO list so the agent always knows what remains.
        Returns empty string if no active task list or all tasks done.
        """
        from hydroagent.utils.task_state import TaskState, PENDING, RUNNING
        try:
            ts = TaskState(self.workspace)
            if not ts.all_tasks():
                return ""
            pending = ts.pending_tasks()
            running = [t for t in ts.all_tasks() if t["status"] == RUNNING]
            if not pending and not running:
                return ""  # all done or all failed, no need to remind
            summary = ts.summary()
            return f"[任务状态]\n{summary}"
        except Exception:
            return ""

    def _execute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool function by name."""
        fn = self.tools.get(name)
        if fn is None:
            return {"error": f"Unknown tool: {name}"}

        import inspect
        sig = inspect.signature(fn)
        if "_workspace" in sig.parameters:
            arguments["_workspace"] = self.workspace
        if "_cfg" in sig.parameters:
            arguments["_cfg"] = self.cfg
        if "_llm" in sig.parameters:
            arguments["_llm"] = self.llm
        if "_ui" in sig.parameters:
            arguments["_ui"] = self.ui

        try:
            result = fn(**arguments)

            # CC-4: run registered PostToolUse hooks (decoupled from tool functions)
            for hook in self._post_tool_hooks.get(name, []):
                try:
                    hook(name, arguments, result)
                except Exception as hook_err:
                    logger.warning("PostToolUse hook failed for %s: %s", name, hook_err)

            # Update skill lifecycle state for generated skills (not a hook; tightly coupled to agent)
            if self.skill_states.is_generated(name):
                success = isinstance(result, dict) and result.get("success", False)
                err = result.get("error") if isinstance(result, dict) else None
                self.skill_states.record_execution(name, success=success, error=err)

            return result
        except TypeError as e:
            logger.warning(f"Tool {name} argument error: {e}")
            if self.skill_states.is_generated(name):
                self.skill_states.record_execution(name, success=False, error=str(e))
            return {"error": f"Invalid arguments for {name}: {e}"}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            if self.skill_states.is_generated(name):
                self.skill_states.record_execution(name, success=False, error=str(e))
            return {"error": f"Tool {name} failed: {e}"}



# ── Default system prompt ────────────────────────────────────────────

_DEFAULT_SYSTEM_PROMPT = """You are HydroAgent, an expert hydrological model calibration assistant.

You help users calibrate, evaluate, and analyze hydrological models using the CAMELS dataset.
You can understand both Chinese and English queries.

Choose tools flexibly based on the user's intent. Do NOT apply a fixed workflow to every task:
- Calibration tasks: validate_basin → calibrate_model → evaluate_model → visualize
- Evaluation only: evaluate_model
- Custom analysis: generate_code → run_code
- New capability needed: create_skill

Only call validate_basin when the task involves basin data. Skip it for pure analysis or skill creation.
Always provide professional analysis in the user's language.
"""
