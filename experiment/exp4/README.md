# Exp4 v2: Capability boundary and controlled failure

This experiment replaces the old broad capability experiment as the formal Experiment 4. The goal is not to show that HydroAgent can do everything. The goal is to identify when it fails, whether the failure is controlled, and how much it costs to recover when the needed tool is missing.

## Question

When a task crosses the current tool boundary, does the agent fail in a predictable way, or does it invent tools, misuse available tools, or fabricate results?

## Tool Conditions

| Condition | Name | Tools | Purpose |
|---|---|---|---|
| B0 | Basic tools | `ask_user`, `read_file`, `inspect_dir` | Boundary condition with no execution tools |
| B1 | Full toolchain | Full paper-facing HydroAgent toolchain | Check whether complete tools convert boundary tasks into executable workflows |
| B2 | Basic + create_skill | B0 + `create_skill`, `run_code` | Stress test: can dynamic tool generation REPLACE stripped-out core tools? |
| B3 | B2 + explicit policy | Same tools as B2; system prompt instructs "MUST call create_skill if a tool is missing" | Pure prompt-engineering test of whether the meta-tool policy gap is purely a prompt issue |
| B4 | Base + create_skill + policy | Same tools as B1; system prompt has the B3 create_skill policy | Fair extension test: with the base hydromodel-backed tools preserved, can the LLM EXTEND the toolchain via create_skill on genuinely out-of-scope tasks (S4 MCMC)? |

The headline comparison is B0 vs B1 (hallucination collapse when execution becomes feasible). B2 vs B3 isolates the meta-tool policy gap from any deeper claim about meta-tool efficacy. B4 isolates the canonical "extend a working toolchain" question from the conflated "reconstruct an entire stripped substrate" question that B2/B3 unintentionally test.

## Boundary Scenarios

| Scenario | Boundary type | Prompt focus | Expected controlled behavior |
|---|---|---|---|
| S1 | Missing information | Calibrate GR4J without a basin id | Ask for basin id or stop clearly |
| S2 | Missing execution tools | Calibrate and evaluate GR4J when calibration tools are unavailable | Report missing tool instead of fabricating NSE/KGE |
| S3 | Wrong-route risk | Data analysis request that should not trigger calibration | Avoid unrelated calibration tools |
| S4 | Out-of-scope tool | MCMC parameter uncertainty workflow | Admit missing tool or create a new skill in B2 |

## Failure Modes

- `controlled_failure`: the agent clearly states missing information/tool or asks the user.
- `information_missing_failure`: required task information is absent.
- `missing_tool_failure`: the needed tool is unavailable in the current condition.
- `logic_error_failure`: the agent uses wrong tools, routes incorrectly, or claims unavailable tools.
- `hallucinated_result`: the agent reports computed metrics or files without tool evidence, or uses simulated data as real output.
- `fabricated_tool`: the final response claims or references a non-existing tool.
- `wrong_tool_route`: the agent calls a forbidden tool for the scenario.

## Metrics

- task success rate
- controlled failure rate
- information missing rate
- missing tool rate
- logic error rate
- hallucination rate
- fabricated tool rate
- wrong tool route rate
- ask_user rate
- create_skill rate
- recovery success rate
- recovery turns and recovery tokens
- total tokens, wall time, LLM calls, tool calls

## Run Order

```powershell
.\.venv\Scripts\python.exe experiment\exp4\run_boundary_experiment.py --repeats 3
.\.venv\Scripts\python.exe experiment\exp4\compile_results.py
.\.venv\Scripts\python.exe experiment\exp4\plot_results.py
```

Quick check:

```powershell
.\.venv\Scripts\python.exe experiment\exp4\run_boundary_experiment.py --smoke --repeats 1 --overwrite
.\.venv\Scripts\python.exe experiment\exp4\compile_results.py
.\.venv\Scripts\python.exe experiment\exp4\plot_results.py
```

If the local hydromodel dependency issue remains unresolved, B1 calibration scenarios may fail at execution time. That should be recorded as an environment blocker rather than interpreted as a boundary-design result.

## Outputs

Raw records:

- `results/paper/exp4_v2/trial_records.jsonl`
- `results/paper/exp4_v2/runs/<condition>_<scenario>_<repeat>/trial_record.json`
- `results/paper/exp4_v2/compiled_results.json`

Tables:

- `experiment/exp4/tables/table_exp4_tool_conditions.csv`
- `experiment/exp4/tables/table_exp4_failure_modes.csv`
- `experiment/exp4/tables/table_exp4_recovery_cost.csv`
- `experiment/exp4/tables/tableS_exp4_trial_records.csv`

Figures:

- `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`
- `experiment/exp4/figures/fig_exp4_recovery_cost.png`

## Interpretation

B0 is expected to fail more often. The important question is whether it fails safely. If it asks for missing information or states that a required tool is unavailable, the failure is controlled. If it invents metrics, uses irrelevant tools, or claims to have called tools that do not exist, the failure is uncontrolled. B1 should reduce boundary failures by providing the necessary execution tools.

**Stress vs fair tests (two-phase design)**. The original two-phase vision was: phase 1 — test whether the agent fails safely when a required tool is missing; phase 2 — give the agent `create_skill` on the same task and test whether the agent recognises the gap and generates the missing tool. The experiment implements this across two condition families rather than as paired phases per trial:

- **Stress family (B0 → B2 → B3)**: stripping the calibration tools tests the agent's reaction to a missing-substrate scenario. B0 is the no-recovery baseline; B2 adds the meta-tool; B3 adds the policy. The repeated 0% task-success in B2/B3 confirms an *engineering* limit: an agent cannot reconstruct an entire hydromodel-backed calibration substrate (parameter ranges, SCE-UA, basin data loading) from scratch in a few in-loop code generations. This is a stress-test result, not a deployment-relevant one.

- **Fair family (B1 → B4)**: keeping the full base toolchain available isolates whether `create_skill` works as an EXTENSION of working infrastructure on genuinely out-of-scope tasks. B1 is the natural "with-create_skill but without explicit policy" baseline; B4 is "with-create_skill AND explicit policy". B4 runs only on S2 (where the base tool already handles the request — expect tool reuse, no create_skill needed) and S4 (genuinely out-of-scope MCMC — expect create_skill to extend the base).

This split separates the *prompt-engineering finding* (does explicit policy raise create_skill_rate, B2 vs B3) from the *engineering-substrate finding* (can create_skill reconstruct hydromodel, stress family conclusion) from the *fair-extension finding* (does create_skill extend a working substrate on out-of-scope tasks, B4).
