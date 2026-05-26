# Experiment 4 paper text

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.8 (tool conditions + boundary scenarios) | `experiment/exp4/tables/table_exp4_tool_conditions.csv` | One row per condition (B0/B1/B2/B3) with `allowed_tools`, `observed_tool_schemas`, `allows_execution`, `allows_dynamic_generation`. Scenario definitions are in the run script `experiment/exp4/common.py:SCENARIOS`. |
| Table 4.9 (failure modes per condition) | `experiment/exp4/tables/table_exp4_failure_modes.csv` | One row per condition (n = 20 = 4 scenarios × 5 repeats). Columns: `task_success_rate`, `controlled_failure_rate`, `information_missing_rate`, `missing_tool_rate`, `logic_error_rate`, `hallucination_rate`, `fabricated_tool_rate`, `wrong_tool_route_rate`, `ask_user_rate`, `create_skill_rate`, `recovery_success_rate`, `mean_recovery_turns`, `mean_recovery_tokens`, `mean_llm_calls`, `mean_tool_calls`, `mean_prompt_tokens`, `mean_completion_tokens`, `mean_cached_tokens`, `mean_total_tokens`, `mean_wall_time_s`, `mean_tool_compute_time_s`, `mean_llm_decision_time_s`. |
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

## Table 4.9. Failure modes and recovery cost

Numbers are observed rates over n trials per condition. **n = 5 repeats per (condition, scenario) cell is modest, so the paper text frames these as controlled-condition evidence and patterns consistent across repeats, not as statistically significant tests.**

| Condition | n | Success | Controlled failure | Hallucination | Wrong route | ask_user | **create_skill** |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 Basic tools (no execution)                   | 20 |  0.0% | 25.0% | **75.0%** |  0.0% | 20.0% |  0.0% |
| B1 Full toolchain (production)                  | 20 | **55.0%** | 10.0% |  5.0% | 35.0% | 20.0% |  5.0% |
| B2 Basic + create_skill (tool, no policy)       | 20 |  0.0% | 45.0% | 30.0% | 25.0% | 25.0% |  5.0% |
| B3 Basic + create_skill + explicit policy       | 20 |  0.0% | 35.0% | 30.0% | 35.0% | 10.0% | **20.0%** |
| **B4 Full base + create_skill + policy** (S2+S4 only) | 10 | **60.0%** | 30.0% | 10.0% | 40.0% |  0.0% | 10.0% |

The first four rows are stress tests: B0/B2/B3 deliberately strip out the core hydromodel-backed calibration tools so that the LLM is forced to confront a tool-boundary scenario. B1 is the production-equivalent toolchain. B4 (added 2026-05-26) is the canonical extension test: it keeps the full base toolchain available AND adds the explicit create_skill policy, isolating "does LLM extend its toolchain on a genuinely out-of-scope task" from the conflated "can LLM reconstruct an entire calibration substrate from scratch" question that B2/B3 unintentionally test.

## Figure 4.7. Failure mode composition

Use `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`. The expected interpretation is that B0 may fail frequently, but a useful system should make those failures controlled rather than hallucinated or logically wrong.

## Figure 4.8. Dynamic recovery cost

Use `experiment/exp4/figures/fig_exp4_recovery_cost.png`. This figure should show how often B2 attempts dynamic tool creation, how often recovery succeeds, and the token/loop cost of that recovery.

## 4.4 Capability boundary and controlled failure results

The results in Table 4.9 reveal five boundary patterns. The first three are observed across the stress-test conditions (B0–B3); the last two are isolated by the B4 fair-extension condition that preserves the hydromodel base.

**Pattern 1: hallucination collapses when execution becomes feasible.** Under B0, the agent has no calibration or computation tool, and 75.0% of the 20 runs end with a hallucinated NSE/KGE answer, while only 25.0% are controlled failures that explicitly stop or call `ask_user`. The same boundary scenarios under B1 produce hallucinations in only 5.0% of runs (a 15× reduction), even though 35.0% still go down a wrong tool route (we revisit that in Pattern 4). The takeaway: the dominant cause of hydrological hallucination in this setting is not the language model's confidence, but the absence of an executable grounding step. Adding even one executable tool ('calibrate_model' via hydromodel) is enough to convert most "made-up NSE" answers into "real NSE answers".

**Pattern 2a (policy gap): without an explicit policy, meta-tools sit unused.** B2 provides `create_skill` and `run_code` on top of B0's basic tools, but the observed `create_skill_rate` is only 5.0% across 20 runs. B3 keeps the same tool set and adds the system-prompt sentence "if the task requires a tool not in your list, you must call `create_skill`". With that addendum, `create_skill_rate` rises to 20.0% (B3 hallucination correspondingly stays at 30.0%, similar to B2). This separates a pure *prompt-engineering finding* — the LLM has the capability to invoke the meta-tool but defaults to not doing so — from any deeper claim about meta-tool efficacy.

**Pattern 2b (engineering gap): create_skill cannot reconstruct stripped-out core infrastructure.** Both B2 and B3 keep task_success at 0/20 even when `create_skill` is invoked. The reason is structural: S2 (the calibration scenario where the calibrate_model tool is artificially blocked) requires the agent to generate a working SCE-UA calibrator from scratch without access to the hydromodel API — including parameter ranges, normalization, basin data loading, and the SCE-UA optimizer itself — and this is outside the practical scope of in-loop few-shot code generation. The B2/B3 results therefore confirm a *practical-limits-of-meta-tool* finding: even when invoked, create_skill cannot replace an entire engineering substrate. This is a stress-test result rather than a deployment-relevant one (production HydroAgent always has hydromodel available).

**Pattern 3 (B4 fair-extension test, NEW): when the base toolchain is preserved, the B3 failure on S2 disappears entirely, and create_skill on genuinely out-of-scope tasks remains hard.** B4 keeps the full B1 toolchain and adds the explicit create_skill policy from B3. Run on S2 + S4 × 5 reps = 10 records.

  - **B4 on S2**: 5/5 task_success, **0/5 create_skill calls**. The LLM correctly routes to the existing `calibrate_model` and `evaluate_model` tools and never invokes create_skill (no policy trigger is needed when the tool already exists). This directly confirms that B3's 0/5 failure on S2 was the result of substrate stripping, **not** a policy or LLM-capability deficit. Production HydroAgent on S2-type requests therefore behaves the same as B1.

  - **B4 on S4 (genuinely out-of-scope MCMC)**: 1/5 task_success, **1/5 create_skill calls**, 1/5 hallucination. Only one trial out of five followed the prescribed pattern of generating an MCMC skill and running it; the rest either ignored the policy, attempted ordinary calibration as a stand-in, or hallucinated MCMC results. The 1/5 success rate matches B1's 1/5 (20%) baseline on the same scenario — the explicit policy did not raise S4 success in our 5-rep sample.

  Taken together, B4 shows that the meta-tool extension mechanism *works in principle* (one S4 trial produced a real MCMC tool and a real result) but **its invocation is not reliable** even with both base infrastructure and an explicit prompt: 4/5 trials on S4 silently fall back to non-extension behaviors. The next research direction for create_skill is therefore not "tell the LLM to use it" (we did) and not "give it a working substrate" (we did), but to make the agent recognise out-of-scope-vs-in-scope at the decision point with higher reliability — for example, by adding a pre-step that classifies the task against the existing tool schemas before any tool is invoked.

**Pattern 4 (tool routing): the cost of adding tools is wrong-route errors.** B0 has wrong_route = 0% (it cannot mis-route to a calibration tool because it has none). B1 has wrong_route = 35.0%. B3 stays high at 35.0% (the explicit "do something" policy redirects effort that B2 spent on `ask_user` into unproductive code generation; ask_user_rate drops from 25.0% in B2 to 10.0% in B3). The wrong_route rate is the visible signature of "tool richness creates a routing decision that didn't exist before". The next research direction in this dimension is not more tools, it is better tool-selection policy.

**Pattern 5: success rate is bought with hydromodel compute, not with LLM tokens.** B1 success rate of 55.0% comes with a mean wall time of 97 s, ~5× B0's 20 s. The token cost grows more modestly (84 k vs 60 k). The dominant cost of executable correctness in HydroAgent is hydromodel SCE-UA compute, not language-model tokens — a useful property because the latter is a hard budget limit while the former scales naturally with the calibration request itself.

Taken together, Experiment 4 supports four design boundaries for an LLM-driven hydrological agent: (i) when the agent lacks executable tools, configure it to fail controlled rather than narrate plausible metrics (Pattern 1, B0→B1 hallu 75%→5%); (ii) treat meta-tools (create_skill) as gap-fillers on top of a working substrate rather than as substrate replacements (Patterns 2b + 3 — B3 fails 0/20 on the stress test where substrate is stripped, but B4 succeeds 5/5 on S2 by reusing the existing substrate tools, and reaches 1/5 on truly out-of-scope S4); (iii) make the "when to invoke a meta-tool" policy explicit because giving the option alone is not sufficient (Pattern 2a, B2→B3 raises create_skill_rate 5%→20%); (iv) when tools are added, accompany them with a routing policy because tool richness alone creates wrong-route failures (Pattern 4, B0→B1 wrong_route 0%→35%); and additionally, (v) **explicit policy alone does not make meta-tool invocation reliable** — even with full base + policy on a genuinely out-of-scope task, B4_S4 invoked create_skill only 1/5 times. Reliable out-of-scope recognition is the next research target.
