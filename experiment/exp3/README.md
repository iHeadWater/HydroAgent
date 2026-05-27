# Exp3 v2: Tool grounding and knowledge-on-demand

This experiment asks whether HydroAgent's reliability comes primarily from executable tool grounding, and when additional system-specific knowledge provides enough marginal value to justify its token cost.

## Question

Does HydroAgent's reliability come primarily from executable tool grounding, and when does additional system-specific knowledge provide enough marginal value to justify its token cost?

| Condition | Name | Input | Purpose |
|---|---|---|---|
| K0 | Plain LLM | No tools, no skills, no knowledge, no memory | Test whether a plain LLM can complete executable hydrological tasks |
| K1 | Tools only | Same required tools as K2, but no knowledge input | Test whether tools are the decisive factor |
| K2 | Full knowledge | Same tools as K1 plus skills, knowledge pack, adapter docs, memory/profile hooks | Test marginal gains from extra knowledge |

K1 and K2 must expose the same tool schemas. This keeps the comparison focused on knowledge input rather than tool availability.

## Tasks

| Task | Focus | Success criterion |
|---|---|---|
| T1 standard calibration | Basic hydrological execution | Calls `validate_basin`, `calibrate_model`, and `evaluate_model`; returns real NSE/KGE evidence |
| T2 model comparison | Multi-model execution and synthesis | Runs/evaluates GR4J and XAJ and chooses based on NSE/KGE |
| T3 code analysis | Non-calibration routing | Calls `generate_code` and `run_code`, avoids calibration tools, and does not use simulated data |
| T4 failure diagnosis | General diagnostic reasoning | Explains low NSE and boundary-hit evidence for XAJ without running tools; tests LLM's pre-trained hydrology knowledge |
| T5 calibration knowledge | HydroAgent-specific workflow knowledge | Describes correct post-calibration evaluation sequence, recommends specific SCE-UA rep/ngs values, and diagnoses GR4J parameter boundary-hitting patterns; requires information from the calibration guide and model parameter knowledge files |

Default run size:

```text
3 conditions x 5 tasks x 5 repeats = 75 runs
```

## Metrics

The primary metrics are:

- `task_success_rate`
- `tool_route_success_rate`
- `first_tool_accuracy`
- `forbidden_tool_rate`
- `hallucination_rate`
- `llm_calls`
- `tool_calls`
- `wall_time_s`
- `tool_compute_time_s`
- `llm_decision_time_s`
- `prompt_tokens`, `completion_tokens`, `cached_tokens`, `total_tokens`
- `knowledge_input_tokens_est`
- `tokens_per_success`
- `marginal_gain_per_10k_tokens`

The intended interpretation is:

- `K1 - K0` measures the effect of tool availability.
- `K2 - K1` measures the marginal effect of full knowledge input.
- T5 is the main place where K2 should outperform K1, since it requires calibration workflow knowledge only available in the knowledge pack.
- T4 tests general diagnostic reasoning where the LLM's pre-training is expected to suffice regardless of knowledge injection.

## Run Order

Use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe experiment\exp3\run_knowledge_ablation.py
.\.venv\Scripts\python.exe experiment\exp3\compile_results.py
.\.venv\Scripts\python.exe experiment\exp3\plot_results.py
```

Quick check:

```powershell
.\.venv\Scripts\python.exe experiment\exp3\run_knowledge_ablation.py --smoke --repeats 1 --overwrite
.\.venv\Scripts\python.exe experiment\exp3\compile_results.py
.\.venv\Scripts\python.exe experiment\exp3\plot_results.py
```

The current local environment previously showed a hydromodel import blocker caused by a missing transitive dependency, `pytz`, inside `.venv`. Fix that environment issue before expecting T1/T2 hydrological evaluations to complete.

## Outputs

Raw records:

- `results/paper/exp3_v2/trial_records.jsonl`
- `results/paper/exp3_v2/runs/<condition>_<task>_<repeat>/trial_record.json`
- `results/paper/exp3_v2/compiled_results.json`

Tables:

- `experiment/exp3/tables/table_exp3_condition_design.csv`
- `experiment/exp3/tables/table_exp3_core_results.csv`
- `experiment/exp3/tables/table_exp3_task_level.csv`
- `experiment/exp3/tables/tableS_exp3_trial_records.csv`

Figures:

- `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`
- `experiment/exp3/figures/fig_exp3_task_heatmap.png`

## Paper Logic

The conclusion is tool-first, knowledge-on-demand:

1. Executable tools are the non-negotiable foundation (K0->K1 closes the execution deficit).
2. General diagnostic reasoning does not require the full knowledge pack (T3 is 5/5 for all conditions).
3. System-specific workflow knowledge adds marginal reliability on T4, but at 5.3x token cost.
4. The default prompt should stay lean (K1 level); load knowledge files only when the task requires system-specific workflow information.
