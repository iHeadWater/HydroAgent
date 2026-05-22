# Experiment 3 paper text template

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

## Table 4.7. Core results of Experiment 3

| Condition | Success rate | Tool route success | Hallucination rate | LLM calls | Tool calls | Total tokens | Wall time (s) | Tokens per success | Gain vs previous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| K0 Plain LLM | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | - |
| K1 Tools only | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [K1-K0] |
| K2 Full knowledge | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [fill] | [K2-K1] |

## Figure 4.5. Success rate versus token cost

Use `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`. The expected reading is that K1 should move sharply upward from K0, while K2 may move slightly higher at a larger token cost.

## Figure 4.6. Task-level success heatmap

Use `experiment/exp3/figures/fig_exp3_task_heatmap.png`. The expected pattern is that T1-T3 mainly benefit from tools, while T4 is the task where full knowledge may provide a clearer advantage.

## 4.3 Knowledge input ablation results

The results in Table 4.7 show a clear separation between executable capability and additional knowledge input. Under K0, the model can describe a plausible calibration procedure, but it cannot ground the answer in real basin validation, calibration output, or evaluation metrics. This leads to a low task success rate of [fill] and a hallucination rate of [fill], especially in tasks that require computed NSE/KGE or real data analysis.

Adding the necessary tools in K1 changes the behavior more substantially than adding any other input. The success rate increases from [K0 fill] to [K1 fill], and the tool-route success rate reaches [fill]. This indicates that the decisive step is giving the model executable access to hydrological operations. Once the model can call validation, calibration, evaluation, and code execution tools, most standard workflows can be completed without loading the full knowledge base into the initial context.

The full-knowledge condition K2 provides a more selective improvement. Compared with K1, its overall success rate changes by [fill], while the mean token cost increases by [fill]. The largest qualitative difference appears in the diagnostic task, where the additional knowledge helps the agent interpret parameter boundary signals and distinguish between range expansion, optimizer budget, and possible model-structure mismatch. In contrast, for standard calibration and model comparison, the improvement over K1 is limited because the necessary procedure is already encoded by the available tools and their schemas.

These results support a tool-first interpretation of HydroAgent. Knowledge is useful, but its value is not proportional to the amount of context injected. For routine executable workflows, a compact tool-only context can reach most of the full system's performance at a lower token cost. The full knowledge base is most valuable when the agent must diagnose failures or recover from ambiguous model behavior. This suggests that HydroAgent should prefer a knowledge-on-demand strategy rather than always placing all available knowledge in the prompt.
