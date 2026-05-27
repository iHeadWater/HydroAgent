# Experiment 3 paper text

## Tables and files (paper-section -> source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.6 (knowledge input conditions) | `experiment/exp3/tables/table_exp3_condition_design.csv` | One row per condition (K0/K1/K2). |
| Table 4.7 (core results) | `experiment/exp3/tables/table_exp3_core_results.csv` | One row per condition (n=20 per condition: 4 tasks x 5 repeats). |
| Task-level breakdown | `experiment/exp3/tables/table_exp3_task_level.csv` | One row per (condition, task). |
| Every individual run | `experiment/exp3/tables/tableS_exp3_trial_records.csv` | 60 rows (3 conditions x 4 tasks x 5 repeats). |
| Fig 4.5 success vs tokens | `experiment/exp3/figures/fig_exp3_success_vs_tokens.png` | Scatter with arrows showing K0->K1 (tools) and K1->K2 (knowledge) gains. |
| Fig 4.6 task-level heatmap | `experiment/exp3/figures/fig_exp3_task_heatmap.png` | 3-condition x 4-task heatmap; task groups labelled on y-axis. |
| Raw records | `results/paper/exp3_v2/trial_records.jsonl` |

## 3.2.3 Tool grounding and knowledge-on-demand experiment

This experiment asks whether HydroAgent's reliability comes primarily from executable tool grounding, and when additional system-specific knowledge provides enough marginal value to justify its token cost.

We define three input conditions while keeping the tool set fixed across K1 and K2. In K0, the model receives only a minimal instruction prompt and no callable tools, representing a plain LLM baseline. In K1, the model receives the same tool schemas as the full system but no skill descriptions, hydrological knowledge files, adapter documentation, or memory. In K2, the model receives the same tools as K1 together with the complete HydroAgent knowledge input: skill workflow guides, parameter knowledge, calibration strategy guides, and cross-session memory hooks. The comparison K0 to K1 isolates the effect of executable tool access; K1 to K2 measures the marginal value of system-specific knowledge.

The task set contains four workflows spanning two capability types:

- **Execution tasks** (T1, T2): T1 is a standard single-basin GR4J calibration (validate -> calibrate -> evaluate). T2 is a two-model comparison (GR4J vs XAJ). Both require real tool execution to succeed.
- **Reasoning tasks** (T3, T4): T3 is a diagnostic reasoning case where the agent must interpret XAJ parameter boundary-hitting and recommend next steps without running tools. T4 is a calibration workflow knowledge task where the agent must describe HydroAgent-specific SCE-UA hyperparameter recommendations (rep/ngs for quick, standard, and precision runs) and GR4J parameter diagnostics -- information available only in the knowledge pack.

For each condition and task, we repeat the run five times with independent workspaces, producing 60 total records (3 conditions x 4 tasks x 5 repeats).

## Table 4.6. Knowledge input conditions

| Condition | Tool schemas | Skill/Knowledge/Memory | Est. knowledge tokens | Purpose |
|---|---:|---:|---:|---|
| K0 Plain LLM | 0 | None | 0 | Language-only baseline |
| K1 Tools only | same as K2 | None | 0 | Isolate executable tool grounding |
| K2 Tools + full knowledge | same as K1 | All | ~3 152 | Measure marginal knowledge value |

## Table 4.7. Core results (n = 20 per condition, 4 tasks x 5 repeats)

| Condition | Success | Hallucination | LLM calls | Tool calls | Total tokens | Wall (s) | Tokens/success |
|---|---:|---:|---:|---:|---:|---:|---:|
| K0 Plain LLM | 25% | 10% | 1.0 | 0.0 | 1 496 | ~17 | -- |
| K1 Tools only | **75%** | 0% | 5.2 | 5.3 | 11 640 | ~120 | 15 520 |
| K2 Full knowledge | **90%** | 0% | 5.7 | 5.9 | 62 116 | ~142 | 69 018 |

## Task-level breakdown

| Task | Group | K0 | K1 | K2 | Interpretation |
|---|---|---:|---:|---:|---|
| T1 standard calibration | execution | 0/5 | 5/5 | 5/5 | Tool grounding closes the gap |
| T2 model comparison | execution | 0/5 | 5/5 | 5/5 | Tool grounding closes the gap |
| T3 failure diagnosis | general diagnosis | 5/5 | 5/5 | 5/5 | LLM pre-training suffices |
| T4 calibration knowledge | system-specific | **0/5** | **0/5** | **3/5** | Knowledge pack provides the answer |

## Figure 4.5. Success rate versus token cost

`experiment/exp3/figures/fig_exp3_success_vs_tokens.png`. K0 (25%, ~1.5k tokens) -> K1 (75%, ~12k) -> K2 (90%, ~62k). Arrows annotate the +50 pp tool-grounding gain and the +15 pp knowledge gain at 5.3x token cost.

## Figure 4.6. Task-level success heatmap

`experiment/exp3/figures/fig_exp3_task_heatmap.png`. Four rows labelled by task group. T1-T2 show a binary split (K0=0, K1=K2=1.00). T3 is uniformly 1.00. T4 shows 0.00 / 0.00 / 0.60 -- the only row where K2 strictly outperforms K1.

## 4.3 Tool grounding and knowledge-on-demand results

The aggregated numbers in Table 4.7 show that executable tool grounding is the dominant factor, with system-specific knowledge providing a meaningful but task-specific marginal gain.

**Executable tools are the decisive factor.** K0 to K1 raises overall success from 25% to 75% (+50 pp). On T1 and T2 (execution tasks), K0 scores 0/5 on each while K1 scores 5/5 on each: tool access alone closes the entire execution deficit. Hallucination drops from 10% to 0%, confirming that fabricated metrics under K0 are caused by the absence of executable grounding, not by the model lacking hydrological vocabulary.

**General diagnostic reasoning does not require knowledge injection.** T3 (failure diagnosis) achieves 5/5 across all three conditions. The LLM's pre-training contains sufficient hydrological knowledge to interpret XAJ parameter boundary-hitting patterns and recommend physically grounded next steps. This confirms that the full knowledge pack is not needed for tasks within the LLM's training distribution.

**System-specific workflow knowledge provides marginal gain on the knowledge-sensitive task.** T4 requires HydroAgent-specific information: SCE-UA rep/ngs recommendations from `calibration_guide.md` and GR4J parameter diagnostics from `model_parameters.md`. K0 and K1 both score 0/5 -- neither can produce the system-specific hyperparameter values. K2 scores 3/5, with the successful trials correctly citing the recommended rep=500, ngs=200 for standard calibration. The 2/5 failures are due to K2 mentioning rep/ngs but not the exact recommended values, suggesting that even with the knowledge pack, retrieval from a ~9k-token context is not perfectly reliable.

**Cost-benefit assessment.** K1 to K2 adds +15 pp success at 5.3x token cost (12k -> 62k per run). The marginal gain is concentrated entirely on T4. For the execution tasks (T1-T2) and general diagnosis (T3), the additional knowledge tokens produce zero incremental success. This supports a knowledge-on-demand design: keep the default prompt lean with tool schemas and procedural rules (K1 level), and load domain-specific knowledge files only when the task requires system-specific workflow information.

| Comparison | Success gain | Extra tokens/run | Interpretation |
|---|---:|---:|---|
| K0 -> K1 | +50 pp | +10k | Executable tool grounding (decisive) |
| K1 -> K2 | +15 pp | +50k | System-specific knowledge (marginal, task-confined) |

**Design implication.** These results support a tool-first, knowledge-on-demand architecture aligned with the layered design in Section 2: the Tool Layer provides the non-negotiable execution foundation, while the Skills/Knowledge Layer should be loaded selectively based on task type rather than injected by default into every prompt.
