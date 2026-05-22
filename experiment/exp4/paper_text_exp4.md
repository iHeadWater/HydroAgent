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

## Table 4.9. Failure modes and recovery cost

| Condition | Success rate | Controlled failure rate | Info-missing rate | Missing-tool rate | Logic-error rate | Hallucination rate | Token cost | Recovery turns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 Basic tools | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] |
| B1 Full toolchain | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] |
| B2 Basic + create_skill | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] |

## Figure 4.7. Failure mode composition

Use `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`. The expected interpretation is that B0 may fail frequently, but a useful system should make those failures controlled rather than hallucinated or logically wrong.

## Figure 4.8. Dynamic recovery cost

Use `experiment/exp4/figures/fig_exp4_recovery_cost.png`. This figure should show how often B2 attempts dynamic tool creation, how often recovery succeeds, and the token/loop cost of that recovery.

## 4.4 Capability boundary and controlled failure results

The results in Table 4.9 show that tool boundaries are visible in the agent's behavior. Under B0, the task success rate is expectedly limited because the agent does not have access to calibration, evaluation, or code execution tools. The important observation is whether these failures are controlled. In cases where the basin identifier is missing or the calibration tool is unavailable, a controlled response should ask for the missing basin or explicitly state that the required tool is not available. Such behavior indicates that the system can recognize its execution boundary instead of pretending that the computation has been completed.

The full-toolchain condition B1 provides the complementary evidence. When the required tools are available, the same class of requests can be converted into executable workflows. A higher success rate in B1 therefore supports the conclusion that reliable hydrological execution depends on explicit tools rather than on the language model's parametric knowledge alone. At the same time, any remaining B1 failures are informative: they indicate tasks that are not solved simply by adding tools, such as ambiguous user intent, unsuitable data, or limitations in the current workflow design.

The recovery condition B2 evaluates a different aspect of the boundary. For tasks that request a capability outside the existing tool set, dynamic tool creation may allow the agent to extend itself. However, this recovery is not free. It consumes additional LLM calls, code-generation tokens, and validation loops. Therefore, B2 should be interpreted as an extension mechanism rather than a replacement for a well-designed core toolchain.

Overall, Experiment 4 reframes failure as a measurable behavior. HydroAgent is not expected to solve every task automatically. Its reliability comes from making the boundary explicit: when information is missing, it should ask; when a tool is missing, it should say so or create one if allowed; when execution is impossible, it should not fabricate results. This supports the broader design principle that an LLM-based hydrological agent should use tools to ground action, and use controlled failure to prevent hallucinated scientific claims.
