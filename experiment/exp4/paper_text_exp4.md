# Experiment 4 paper text template

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

| Condition | Success | Controlled failure | Info-missing | Missing-tool | Logic-error | Hallucination | Fabricated tool | ask_user | create_skill | Mean tokens | Mean wall (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 Basic tools | 0.0% | 25.0% | 25.0% | 8.3% | 8.3% | **75.0%** | 8.3% | 8.3% | 0.0% | 59 660 | 20.2 |
| B1 Full toolchain | **58.3%** | 8.3% | 25.0% | 41.7% | 33.3% | 8.3% | 0.0% | 25.0% | **8.3%** | 84 311 | 97.0 |
| B2 Basic + create_skill | 0.0% | 33.3% | 25.0% | 33.3% | 25.0% | 41.7% | 0.0% | 33.3% | **0.0%** | 93 909 | 21.3 |

## Figure 4.7. Failure mode composition

Use `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`. The expected interpretation is that B0 may fail frequently, but a useful system should make those failures controlled rather than hallucinated or logically wrong.

## Figure 4.8. Dynamic recovery cost

Use `experiment/exp4/figures/fig_exp4_recovery_cost.png`. This figure should show how often B2 attempts dynamic tool creation, how often recovery succeeds, and the token/loop cost of that recovery.

## 4.4 Capability boundary and controlled failure results

The results in Table 4.9 reveal three boundary patterns that are not visible from the success rate alone.

**Pattern 1: hallucination collapses when execution becomes feasible.** Under B0, the agent has no calibration or computation tool, and 75.0% of the 12 runs end with a hallucinated NSE/KGE answer, while only 25.0% are controlled failures that explicitly stop or call `ask_user`. The same boundary scenarios under B1 produce hallucinations in only 8.3% of runs, even though 41.7% still fail because the calibration step itself does not finish (for example when the tool path is intentionally blocked for S2). This 9× reduction in fabricated metrics suggests that the dominant cause of hydrological hallucination in this setting is not the language model's confidence, but the absence of an executable grounding step.

**Pattern 2: adding a recovery primitive does not by itself trigger recovery.** B2 provides `create_skill` and `run_code` on top of the basic tool set. If the agent recognized "missing capability" as a trigger for tool generation, S4 (out-of-scope MCMC workflow) and S2 (missing calibration tool) should show non-zero `create_skill` use. The observed `create_skill_rate` for B2 is exactly 0% across all 12 runs, while the hallucination rate remains 41.7%. In other words, dynamic tool generation is available but never selected: the agent prefers to keep narrating partial answers from the basic toolset. This is direct evidence that giving an agent a meta-tool is not the same as giving it the policy to use that meta-tool, and it identifies dynamic-tool selection as the next behavioural gap to address.

**Pattern 3: success rate is bought with execution time but not with cleaner failure.** The B1 success rate of 58.3% comes with a mean wall-clock time of 97.0 s, an order of magnitude higher than the 20.2 s of B0. The token cost grows more modestly (84 k vs 60 k tokens). This indicates that the main cost of executable correctness in HydroAgent is hydromodel compute time, not language-model token consumption — a useful property because the latter is a hard budget limit while the former scales naturally with the calibration request itself.

Taken together, Experiment 4 supports treating failure as a measurable behavior with three actionable boundaries: (i) when the agent lacks tools, it should be configured to fail controlled rather than narrate plausible metrics; (ii) when the agent has tools, a high enough fraction of remaining failures are routing errors (`wrong_tool_route_rate` is 0% in B0 but 33.3% in B1) that the next improvement direction is tool-selection policy rather than additional tools; (iii) when the agent has a meta-tool, the policy that decides "I am out of capability, I should create a new skill" must be made explicit, because giving the option is not sufficient. These three boundaries define the failure modes that an LLM-based hydrological agent should make legible to its user, and they motivate the design directions discussed in Section 5.
