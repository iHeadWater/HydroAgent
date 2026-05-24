# Experiment 4 paper text

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.8 (tool conditions + boundary scenarios) | `experiment/exp4/tables/table_exp4_tool_conditions.csv` | One row per condition (B0/B1/B2/B3) with `allowed_tools`, `observed_tool_schemas`, `allows_execution`, `allows_dynamic_generation`. Scenario definitions are in the run script `experiment/exp4/common.py:SCENARIOS`. |
| Table 4.9 (failure modes per condition) | `experiment/exp4/tables/table_exp4_failure_modes.csv` | One row per condition (n=12 = 4 scenarios × 3 repeats). Columns: `task_success_rate`, `controlled_failure_rate`, `information_missing_rate`, `missing_tool_rate`, `logic_error_rate`, `hallucination_rate`, `fabricated_tool_rate`, `wrong_tool_route_rate`, `ask_user_rate`, `create_skill_rate`, `recovery_success_rate`, `mean_recovery_turns`, `mean_recovery_tokens`, `mean_llm_calls`, `mean_tool_calls`, `mean_prompt_tokens`, `mean_completion_tokens`, `mean_cached_tokens`, `mean_total_tokens`, `mean_wall_time_s`, `mean_tool_compute_time_s`, `mean_llm_decision_time_s`. |
| Scenario × condition breakdown | `experiment/exp4/tables/table_exp4_recovery_cost.csv` | One row per (scenario, condition). Use when discussing scenario-specific aversion such as "S2 is 0/3 for B2 and B3". |
| Every individual run | `experiment/exp4/tables/tableS_exp4_trial_records.csv` | 48 rows. Per-trial fields including `prompt_tokens`, `completion_tokens`, `cached_tokens`, `total_tokens`, `wall_time_s`, `tool_compute_time_s`, `llm_decision_time_s`, `actual_tools`, all failure-mode booleans. **Each row is one complete agent run**; there is no per-iteration table because each boundary scenario is one agent invocation, not an iterated calibration loop. |
| Fig 4.7 failure mode composition | `experiment/exp4/figures/fig_exp4_failure_mode_stack.png` | Stacked bar of failure modes per condition; the 75% B0 hallucination band and the B3 wrong-route climb are visible. |
| Fig 4.8 recovery cost | `experiment/exp4/figures/fig_exp4_recovery_cost.png` | Token/turn cost of B2/B3 create_skill attempts (most slots empty because B2 never invoked it and B3 invoked it 4/12 times). |
| Raw records | `results/paper/exp4_v2/trial_records.jsonl`, per-run dirs in `results/paper/exp4_v2/runs/<condition>_<scenario>_<repeat>/`. Dynamically generated skills under `hydroagent/skills/check_environment/`, `explore_environment/`, `write_script_file/` are paper artifacts of B3's `create_skill` invocations. |

## 3.2.4 Capability boundary and controlled failure experiment

The previous experiments evaluate HydroAgent under conditions where the required tools and task information are largely available. In practice, however, an agentic hydrological system also needs to behave predictably when this assumption is violated. The central question of Experiment 4 is therefore not whether the agent can solve every task, but whether its failure mode is controlled when the task lies outside the current tool or information boundary.

We define controlled failure as a response in which the agent explicitly identifies the missing information or missing tool, asks the user for clarification when appropriate, or stops without fabricating results. This is contrasted with uncontrolled failure, where the agent calls an irrelevant tool, claims that an unavailable tool was used, reports numerical metrics without executable evidence, or substitutes simulated data for real hydrological output. This distinction is important because a hydrological agent can be useful even when it cannot complete a task, provided that the reason for failure is visible and recoverable.

The experiment compares two primary tool conditions and one recovery condition. In B0, the agent is given only basic observation and clarification tools: `ask_user`, `read_file`, and `inspect_dir`. This condition simulates a boundary setting where the model can inspect context and ask questions but cannot perform hydrological computation. In B1, the full HydroAgent toolchain is available, including basin validation, calibration, evaluation, code execution, and dynamic skill creation. This condition tests whether the complete toolchain converts boundary cases into executable workflows. Finally, B2 adds `create_skill` and `run_code` to the basic tool set. It is not the main baseline, but it tests whether the system can recover when the requested operation is outside the existing tool set.

Four boundary scenarios are used. The first removes a required basin identifier from a calibration request, so the correct behavior is to ask for the missing basin or stop clearly. The second asks for a real calibration and evaluation under a condition where the calibration tools may be unavailable, testing whether the agent reports the tool boundary rather than inventing NSE/KGE values. The third is a data-analysis request that should not trigger calibration tools, so it probes wrong-route errors. The fourth asks for an MCMC-style parameter uncertainty workflow, which is outside the default calibration path and therefore tests whether the agent can recognize a missing capability or use dynamic tool creation.

For each run, we record both the outcome and the process by which it was reached. The outcome metrics include task success, controlled failure, information-missing failure, missing-tool failure, logic-error failure, hallucinated result, fabricated tool, and wrong tool route. The process metrics include LLM calls, tool calls, token usage, wall-clock time, whether `ask_user` was used, whether `create_skill` was called, and the token and loop cost of recovery. This allows Experiment 4 to measure not only whether the task succeeded, but also whether failure remained interpretable and recoverable.

## Table 4.8. Tool conditions and boundary scenarios

| Condition | Tool set | Execution allowed | Dynamic generation allowed | Intended role |
|---|---|---:|---:|---|
| B0 Basic tools | ask_user, read_file, inspect_dir | No | No | Boundary baseline |
| B1 Full toolchain | Full HydroAgent toolchain | Yes | Yes | Main executable system |
| B2 Basic + create_skill | B0 + create_skill + run_code | Partial | Yes | Recovery condition |

| Scenario | Boundary type | Expected controlled behavior |
|---|---|---|
| S1 Missing basin id | Information missing | Ask for basin id or stop clearly |
| S2 Missing calibration tools | Missing tool | Report missing tool rather than fabricate NSE/KGE |
| S3 Wrong-route risk | Logic error risk | Avoid unrelated calibration tools |
| S4 Out-of-scope MCMC workflow | Missing specialized tool | Admit missing capability or create a new skill |

## Table 4.9. Failure modes and recovery cost (n = 12 per condition, 3 repeats × 4 scenarios)

| Condition | Success | Controlled failure | Hallucination | Fabricated tool | Wrong route | ask_user | **create_skill** |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 Basic tools                                   |  0.0% | 25.0% | **75.0%** | 8.3% |  0.0% |  8.3% |  0.0% |
| B1 Full toolchain                                | **58.3%** | 8.3% |  8.3% | 0.0% | 33.3% | 25.0% |  8.3% |
| B2 Basic + create_skill (tool, no policy hint)   |  0.0% | 33.3% | 41.7% | 0.0% | 25.0% | 33.3% | **0.0%** |
| B3 Basic + create_skill + explicit policy        |  0.0% | 33.3% | 25.0% | 0.0% | **41.7%** |  0.0% | **33.3%** |

B3 has the same tool set as B2 but adds a system-prompt sentence stating "if the task requires a tool not in your list, call create_skill". This is the policy-gap test: does telling the agent to use the meta-tool close the gap that B2 left open?

## Figure 4.7. Failure mode composition

Use `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`. The expected interpretation is that B0 may fail frequently, but a useful system should make those failures controlled rather than hallucinated or logically wrong.

## Figure 4.8. Dynamic recovery cost

Use `experiment/exp4/figures/fig_exp4_recovery_cost.png`. This figure should show how often B2 attempts dynamic tool creation, how often recovery succeeds, and the token/loop cost of that recovery.

## 4.4 Capability boundary and controlled failure results

The results in Table 4.9 reveal three boundary patterns that are not visible from the success rate alone.

**Pattern 1: hallucination collapses when execution becomes feasible.** Under B0, the agent has no calibration or computation tool, and 75.0% of the 12 runs end with a hallucinated NSE/KGE answer, while only 25.0% are controlled failures that explicitly stop or call `ask_user`. The same boundary scenarios under B1 produce hallucinations in only 8.3% of runs, even though 41.7% still fail because the calibration step itself does not finish (for example when the tool path is intentionally blocked for S2). This 9× reduction in fabricated metrics suggests that the dominant cause of hydrological hallucination in this setting is not the language model's confidence, but the absence of an executable grounding step.

**Pattern 2: adding a recovery primitive does not by itself trigger recovery, and adding the policy on top only partially closes the gap — the underlying gap is that the created skill cannot complete the blocked task.** B2 provides `create_skill` and `run_code` on top of the basic tool set, but the observed `create_skill_rate` is exactly 0% across all 12 runs. B3 keeps the same tool set as B2 but adds an explicit system-prompt instruction "if the task requires a tool not in your list, you must call `create_skill`". With that addendum, `create_skill_rate` rises from 0/12 to 4/12 (33.3%) and the hallucination rate drops from 41.7% to 25.0%. So far the policy-gap explanation is correct: the agent does have a willingness to use the meta-tool when told to, and it does substitute create_skill for hallucination some of the time. But **task_success_rate stays at 0/12 across both B2 and B3**, and the `create_skill` use in B3 is scenario-asymmetric: S2 (missing calibration tool) is the scenario most obviously in need of a generated tool, yet it is **0/3 in both B2 and B3** even with the explicit prompt. The S1/S3/S4 scenarios are where B3's create_skill use concentrates (S1 1/3, S3 2/3, S4 1/3), and in those scenarios the agent does try to generate a tool but cannot reconstruct the blocked capability — for instance, on S2 the agent would have to generate a working SCE-UA calibrator from scratch without the hydromodel API, which is outside the practical scope of in-loop code generation. The full finding is therefore three layers: (i) without a policy hint the meta-tool sits unused (B2); (ii) with an explicit policy the meta-tool is used about 1/3 of the time (B3); (iii) even when used, the meta-tool does not recover the task in any of the 12 runs, because the missing capability in these boundary scenarios is not the kind a few-shot generated skill can replace. Wrong-route rate also climbs in B3 (41.7% vs B2's 25.0%) — the agent, now told to "do something" rather than ask the user, redirects its effort into unproductive code generation. The corollary for paper-grade claims is that "give the agent a meta-tool" is necessary but very far from sufficient: the next research direction is not more meta-tools, it is a calibrated decision boundary for when create_skill can plausibly succeed.

**Pattern 3: success rate is bought with execution time but not with cleaner failure.** The B1 success rate of 58.3% comes with a mean wall-clock time of 97.0 s, an order of magnitude higher than the 20.2 s of B0. The token cost grows more modestly (84 k vs 60 k tokens). This indicates that the main cost of executable correctness in HydroAgent is hydromodel compute time, not language-model token consumption — a useful property because the latter is a hard budget limit while the former scales naturally with the calibration request itself.

Taken together, Experiment 4 supports treating failure as a measurable behavior with three actionable boundaries: (i) when the agent lacks tools, it should be configured to fail controlled rather than narrate plausible metrics; (ii) when the agent has tools, a high enough fraction of remaining failures are routing errors (`wrong_tool_route_rate` is 0% in B0 but 33.3% in B1) that the next improvement direction is tool-selection policy rather than additional tools; (iii) when the agent has a meta-tool, the policy that decides "I am out of capability, I should create a new skill" must be made explicit, because giving the option is not sufficient. These three boundaries define the failure modes that an LLM-based hydrological agent should make legible to its user, and they motivate the design directions discussed in Section 5.
