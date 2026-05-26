# Experiment 3 paper text

## Tables and files (paper-section -> source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.6 (knowledge input conditions) | `experiment/exp3/tables/table_exp3_condition_design.csv` | One row per condition (K0/K1/K2). Columns describe what is or is not injected (tool schemas, skill index, knowledge files, adapter docs, memory/profile) and the estimated knowledge tokens. |
| Table 4.7 (core results) | `experiment/exp3/tables/table_exp3_core_results.csv` | One row per condition (n=25 per condition: 5 tasks x 5 repeats). Columns: `task_success_rate`, `tool_route_success_rate`, `first_tool_accuracy`, `forbidden_tool_rate`, `hallucination_rate`, `mean_llm_calls`, `mean_tool_calls`, `mean_total_tokens`, etc. |
| Task-level breakdown | `experiment/exp3/tables/table_exp3_task_level.csv` | One row per (condition, task). Used for the T5 knowledge-gradient finding. |
| Every individual run | `experiment/exp3/tables/tableS_exp3_trial_records.csv` | 75 rows (3 conditions x 5 tasks x 5 repeats). Per-trial booleans + tokens + tools-called list. |
| Fig 4.5 success vs tokens | `experiment/exp3/figures/fig_exp3_success_vs_tokens.png` | Scatter of success rate vs total tokens, one point per condition. |
| Fig 4.6 task-level heatmap | `experiment/exp3/figures/fig_exp3_task_heatmap.png` | 3-condition x 5-task heatmap of success rate; the T5 knowledge gradient (0.40 -> 0.80 -> 1.00) is visible in the bottom row. |
| Raw records | `results/paper/exp3_v2/trial_records.jsonl`, per-run dirs in `results/paper/exp3_v2/runs/<condition>_<task>_<repeat>/`. |

## 3.2.3 Knowledge input ablation experiment

After evaluating HydroAgent's calibration behavior in the previous experiments, we further examine where the system's execution ability comes from. A hydrological agent may appear effective either because the language model has been given extensive domain knowledge, or because it can call the right tools and ground its answer in executable results. These two sources are easy to mix in a full system, so this experiment separates them with a controlled knowledge-input ablation.

We define three input conditions while keeping the task set and, where tools are available, the tool set fixed. In the first condition, K0, the model receives only a minimal instruction prompt and no callable tools. This setting represents a plain LLM baseline: it may explain what should be done, but it cannot actually validate data, calibrate a model, or compute metrics. In the second condition, K1, the model receives the same necessary tool schemas used by the full system, but all skill descriptions, hydrological knowledge files, adapter documentation, basin profiles, and cross-session memory are removed from the prompt. In the third condition, K2, the model receives the same tool set as K1, together with the complete HydroAgent knowledge input. Therefore, the comparison between K0 and K1 isolates the effect of tool availability, while the comparison between K1 and K2 measures the marginal value of additional knowledge.

The task set contains five representative workflows that span different capability requirements. Tasks T1-T3 test executable tool use: T1 is a standard single-basin calibration (validate, calibrate, evaluate), T2 is a two-model comparison (GR4J vs XAJ), and T3 is a code-based hydrological analysis (routing to generate_code/run_code instead of calibration). Task T4 is a diagnostic reasoning case built from a low-NSE XAJ calibration with several parameters near their upper bounds, where the agent must interpret the failure physically without running additional tools. Task T5 tests calibration workflow knowledge specific to HydroAgent: given a successful calibrate_model result, the agent must describe the correct evaluation sequence, recommend specific SCE-UA hyperparameters (rep/ngs) for different calibration scenarios, and diagnose parameter boundary-hitting patterns for GR4J. The answers to T5 require information from the calibration guide and model parameter knowledge files that are injected only under K2.

For each condition and task, we repeat the run five times with independent workspaces, producing 75 total records (3 conditions x 5 tasks x 5 repeats).

## Table 4.6. Knowledge input conditions and fairness constraints

| Condition | Tool schemas | Skill index | Knowledge files | Adapter docs | Memory/profile | Est. knowledge tokens | Purpose |
|---|---:|---:|---:|---:|---:|---:|---|
| K0 Plain LLM | 0 | No | No | No | No | 0 | Plain language-only baseline |
| K1 Tools only | same as K2 | No | No | No | No | 0 | Isolate the contribution of executable tools |
| K2 Full knowledge | same as K1 | Yes | Yes | Yes | Yes | ~3 152 | Measure marginal value of full knowledge input |

## Table 4.7. Core results of Experiment 3 (n = 25 per condition, 5 repeats x 5 tasks)

| Condition | Success | Hallucination | LLM calls | Tool calls | Total tokens | Wall (s) | Tokens/success | Gain vs previous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| K0 Plain LLM (no tools)        | 28% | 12% | 1.0 | 0.0 | 1 862 | ~23 | 6 650 | -- |
| K1 Tools only (no knowledge)   | **96%** | 0% | 5.0 | 4.6 | 29 987 | ~128 | 31 236 | **+68 pp** vs K0 |
| K2 Full knowledge + tools      | **100%** | 0% | 5.8 | 5.8 | 78 099 | ~161 | 78 099 | **+4 pp** vs K1 |

## Task-level breakdown

| Task | K0 | K1 | K2 | What is tested |
|---|---:|---:|---:|---|
| T1 standard calibration | 0/5 | 5/5 | 5/5 | Tool-driven execution chain |
| T2 model comparison     | 0/5 | 5/5 | 5/5 | Multi-model execution + synthesis |
| T3 code analysis        | 0/5 | 5/5 | 5/5 | Non-calibration routing |
| T4 failure diagnosis    | 5/5 | 5/5 | 5/5 | Physical reasoning (LLM suffices) |
| T5 calibration knowledge| **2/5** | **4/5** | **5/5** | HydroAgent-specific workflow knowledge |

## Figure 4.5. Success rate versus token cost

Use `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`. K0 is at the lower left (28%, ~1.9k tokens), K1 jumps to upper middle (96%, ~30k tokens), K2 reaches the upper right (100%, ~78k tokens). The main takeaway: the large vertical jump is K0->K1 (tools), and K1->K2 adds the last 4 pp at 2.6x token cost.

## Figure 4.6. Task-level success heatmap

Use `experiment/exp3/figures/fig_exp3_task_heatmap.png`. The heatmap now has five rows (T1-T5). T1-T3 show a clean binary split: K0=0, K1=K2=1.00. T4 is uniformly 1.00 across all conditions (general LLM reasoning suffices). The bottom row T5 shows the knowledge gradient: 0.40 (K0) -> 0.80 (K1) -> 1.00 (K2), the only task where K2 strictly outperforms K1.

## 4.3 Knowledge input ablation results

The aggregated numbers in Table 4.7 show that executable tooling is the dominant factor, with domain knowledge providing a small but directionally consistent marginal gain. The task-level breakdown in Figure 4.6 reveals where each source of capability matters.

**Executable tools account for the decisive success jump.** Going from K0 (no tools) to K1 (tools, no knowledge) raises overall success from 28% to 96% (+68 pp). On T1-T3 (execution-type tasks), K0 scores 0/5 on every task while K1 scores 5/5 on every task: the entire deficit is closed by tool access alone. Hallucination drops from 12% to 0%, confirming that fabricated NSE/KGE values under K0 are caused by the absence of an executable grounding step, not by the model lacking hydrological vocabulary.

**Domain knowledge produces a small positive marginal gain on the knowledge-sensitive task.** K1 and K2 are identical on T1-T4 (both 100% success). The difference appears only on T5, where the agent must describe HydroAgent-specific calibration workflow details: recommended SCE-UA hyperparameters (rep/ngs values for quick, standard, and precision runs), the post-calibration evaluation sequence, and parameter boundary-hitting diagnostics for GR4J. K0 scores 2/5 (occasional lucky guesses from LLM pre-training), K1 scores 4/5 (partial inference from tool schema descriptions), and K2 scores 5/5 (the calibration guide and model parameter files provide the exact answers). The K1->K2 gap is +4 pp overall, or +1/5 on T5 specifically, at a cost of +48k extra tokens per run.

**T4 (physical diagnosis) does not differentiate the conditions.** All three conditions achieve 5/5 on T4, which asks the agent to interpret XAJ parameter boundary-hitting and recommend next steps. The LLM's pre-training already contains sufficient hydrological knowledge for this level of diagnostic reasoning. This confirms that domain knowledge injection is not needed for tasks that stay within the LLM's existing training distribution.

**Design implication: tools first, knowledge on demand.** The combined evidence supports a layered strategy that matches the architecture diagram: (1) executable tools are the non-negotiable foundation (K0->K1 closes 68 pp); (2) domain knowledge adds marginal reliability on workflow-knowledge tasks (K1->K2 closes the final 4 pp) but at 2.6x token cost; (3) for routine execution and general diagnosis, tool schemas alone carry the agent to near-perfect performance. This supports a knowledge-on-demand policy: keep the default prompt lean (tools + procedural rules) and load domain knowledge files only when the task requires system-specific workflow information.
