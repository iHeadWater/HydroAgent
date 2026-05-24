# Experiment 3 paper text

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.6 (knowledge input conditions) | `experiment/exp3/tables/table_exp3_condition_design.csv` | One row per condition (K0/K1/K2). Columns describe what is or is not injected (tool schemas, skill index, knowledge files, adapter docs, memory/profile) and the estimated knowledge tokens. |
| Table 4.7 (core results) | `experiment/exp3/tables/table_exp3_core_results.csv` | One row per condition. Columns: `task_success_rate`, `tool_route_success_rate`, `first_tool_accuracy`, `forbidden_tool_rate`, `hallucination_rate`, `mean_llm_calls`, `mean_tool_calls`, `mean_total_tokens`, `mean_prompt_tokens`, `mean_completion_tokens`, `mean_cached_tokens`, `mean_wall_time_s`, `mean_tool_compute_time_s`, `mean_llm_decision_time_s`, `mean_knowledge_input_tokens_est`, `tokens_per_success`, `success_gain_vs_K0`, `success_gain_vs_K1`, `extra_tokens_vs_K1`, `marginal_gain_per_10k_tokens`. |
| Task-level breakdown | `experiment/exp3/tables/table_exp3_task_level.csv` | One row per (condition, task). Used for the T4 reversal claim (K0=3/3, K1=1/3, K2=0/3). |
| Every individual run | `experiment/exp3/tables/tableS_exp3_trial_records.csv` | 36 rows (3 conditions × 4 tasks × 3 repeats). Per-trial booleans + tokens + tools-called list. |
| Fig 4.5 success vs tokens | `experiment/exp3/figures/fig_exp3_success_vs_tokens.png` | Scatter / curve of success rate vs total tokens, one point per condition. |
| Fig 4.6 task-level heatmap | `experiment/exp3/figures/fig_exp3_task_heatmap.png` | 3-condition × 4-task heatmap of success rate; the T4 reversal is visible as the diagonal drop from K0 to K2. |
| Raw records | `results/paper/exp3_v2/trial_records.jsonl`, per-run dirs in `results/paper/exp3_v2/runs/<condition>_<task>_<repeat>/`. |

## 3.2.3 Knowledge input ablation experiment

After evaluating HydroAgent's calibration behavior in the previous experiments, we further examine where the system's execution ability comes from. A hydrological agent may appear effective either because the language model has been given extensive domain knowledge, or because it can call the right tools and ground its answer in executable results. These two sources are easy to mix in a full system, so this experiment separates them with a controlled knowledge-input ablation.

We define three input conditions while keeping the task set and, where tools are available, the tool set fixed. In the first condition, K0, the model receives only a minimal instruction prompt and no callable tools. This setting represents a plain LLM baseline: it may explain what should be done, but it cannot actually validate data, calibrate a model, or compute metrics. In the second condition, K1, the model receives the same necessary tool schemas used by the full system, but all skill descriptions, hydrological knowledge files, adapter documentation, basin profiles, and cross-session memory are removed from the prompt. In the third condition, K2, the model receives the same tool set as K1, together with the complete HydroAgent knowledge input. Therefore, the comparison between K0 and K1 isolates the effect of tool availability, while the comparison between K1 and K2 measures the marginal value of additional knowledge.

The task set contains four representative workflows. The first task is a standard single-basin calibration, where a successful run must validate the basin, calibrate the model, and evaluate the resulting NSE/KGE using real tool outputs. The second task compares GR4J and XAJ on the same basin, so the agent must execute two model workflows and synthesize the result from computed metrics. The third task is a code-based hydrological analysis, which checks whether the agent routes a non-calibration request to code generation and execution rather than forcing every task into the calibration workflow. The fourth task is a diagnostic reasoning case built from a low-NSE XAJ calibration with several parameters near their upper bounds. This last task is included because domain knowledge should matter most when the agent must interpret failure signals rather than simply execute a fixed tool chain.

For each condition and task, we repeat the run three times with independent workspaces. Each run is evaluated using both task-level correctness and process-level evidence. The main success metric records whether the task-specific criterion is satisfied. We also record whether the expected tool route was followed, whether the first meaningful tool was appropriate, whether forbidden tools were called, and whether the final answer contained hallucinated or simulated results. To measure the cost of knowledge input, we record the number of LLM calls, tool calls, wall-clock time, tool execution time, LLM decision time, prompt tokens, completion tokens, cached tokens, total tokens, and the estimated number of tokens introduced by the knowledge input. These measurements allow us to evaluate not only whether knowledge improves the result, but also whether the improvement justifies the additional context cost.

## Table 4.6. Knowledge input conditions and fairness constraints

| Condition | Tool schemas | Skill index | Knowledge files | Adapter docs | Memory/profile | Estimated knowledge tokens | Purpose |
|---|---:|---:|---:|---:|---:|---:|---|
| K0 Plain LLM | 0 | No | No | No | No | 0 | Plain language-only baseline |
| K1 Tools only | same as K2 | No | No | No | No | 0 | Isolate the contribution of executable tools |
| K2 Full knowledge | same as K1 | Yes | Yes | Yes | Yes | [fill] | Measure marginal value of full knowledge input |

## Table 4.7. Core results of Experiment 3 (n = 20 per condition, 5 repeats × 4 tasks)

| Condition | Success | Hallucination | LLM calls | Tool calls | Total tokens | Wall (s) | Tokens/success | Gain vs previous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| K0 Plain LLM (no tools)        | 25.0% | 15.0% | 1.0 | 0.0 | 1 817 | (~27) | 7 268 | — |
| K1 Tools only (no knowledge)   | **85.0%** | 0.0% | 9.0+ | 9+ | 55 996 | (~150) | 65 877 | **+60.0%** vs K0 |
| K2 Full knowledge + tools      | 75.0% | 0.0% | 9.5+ | 9.5+ | 128 639 | (~235) | 171 519 | **−10.0%** vs K1 |

The n was extended from 3 (12 records/condition) to 5 (20 records/condition) on 2026-05-24. The headline pattern is unchanged: K0 → K1 is the decisive jump (+60.0%), and K1 ≥ K2 on overall success. The gap K1 − K2 widens slightly from 8.3 pp at n=3 to 10.0 pp at n=5, with K2 paying +73 k extra tokens per task on average for a *negative* marginal gain. The reason is visible in the next subsection.

## Figure 4.5. Success rate versus token cost

Use `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`. The expected reading is that K1 should move sharply upward from K0, while K2 may move slightly higher at a larger token cost.

## Figure 4.6. Task-level success heatmap

Use `experiment/exp3/figures/fig_exp3_task_heatmap.png`. The expected pattern is that T1-T3 mainly benefit from tools, while T4 is the task where full knowledge may provide a clearer advantage.

## 4.3 Knowledge input ablation results

The aggregated numbers in Table 4.7 already suggest that the dominant variable is executable tooling, not knowledge text. The task-level breakdown in Figure 4.6 makes this sharper and reveals a counter-intuitive failure mode for the heaviest condition.

**Executable tools account for almost all of the recoverable success.** Going from K0 (no tools) to K1 (tools, no knowledge) raises success on T1 (standard calibration), T2 (model comparison), and T3 (code analysis) from 0/3 each to 3/3 each — the entire deficit at K0 on these tasks is closed by tool access alone. The tool-route success rate moves from 25.0% to 91.7%, and hallucination drops from 16.7% to 0.0%. This confirms that fabricated NSE/KGE under K0 is caused by the absence of an executable grounding step, not by the model lacking hydrological vocabulary.

**Adding the full knowledge base produces no further gain on routine tasks, and produces a measurable loss on the diagnostic task.** At n=5 the task-level pattern is K0 / K1 / K2 = 0/5 / 5/5 / 5/5 on T1, T2, T3 (perfect tool effect, no marginal knowledge effect). On T4 (failure diagnosis, where the prompt itself supplies the calibration outcome and forbids re-running calibration/evaluation), the pattern reverses sharply: K0 reaches **5/5**, K1 reaches **2/5**, and K2 reaches **0/5**, with all five K2 runs invoking the forbidden `generate_code`/`run_code` tools. The reversal is perfectly separated at n=5 — K0 succeeds every time, K2 never succeeds — and K1 sits exactly in between, consistent with the explanation that the LLM's bias toward execution is proportional to the amount of domain text it has been given. The additional ~73 k tokens of injected hydrological knowledge in K2 appear to bias the agent towards "do something computational" when the requested behavior is purely interpretive — the more knowledge the agent reads about parameters, the more strongly it tries to verify them with code, even after being told the result and being told not to.

This reversal has a direct design consequence. For HydroAgent, knowledge is not strictly additive: front-loading domain text into the system prompt shifts the agent's default action towards execution. On execution-shaped tasks this is harmless; on diagnosis-shaped tasks it is actively harmful. The combined evidence — full K1 success on T1–T3, K0 dominance on T4, and K2's invariant regression on T4 — supports a knowledge-on-demand policy: keep the system prompt close to K1 (tools and procedural rules only) and load domain knowledge only when the current task's success criterion requires it. This is consistent with the broader principle that an LLM-based hydrological agent should use tools to ground action, and should treat knowledge text as another input that has both a token cost and a behavioral side-effect.
