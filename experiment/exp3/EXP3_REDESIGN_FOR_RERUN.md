# Experiment 3 redesign for rerun

本文档用于指导下一轮 Experiment 3 的代码、README、paper text、表格和图件重构。当前实验 3 的基本设计仍然可用，但叙事需要从宽泛的 “knowledge input ablation” 调整为更清楚的：

> tool grounding and knowledge-on-demand experiment

实验 3 不应被写成“知识越多是否越好”的测试，而应回答：

1. HydroAgent 的执行成功主要来自可执行工具，还是来自 prompt 中额外注入的知识？
2. 当工具已经可用时，额外知识在哪类任务上仍有边际价值？
3. 这种边际价值是否值得默认全量注入，还是更适合按需加载？

## 1. 当前设计是否偏离原始目的

当前 K0/K1/K2 三条件设计是合理的：

| 条件 | 含义 | 主要比较 |
|---|---|---|
| K0 | plain LLM, no tools, no knowledge | 语言模型本身能否完成任务 |
| K1 | tools only, no extra knowledge | 可执行工具的贡献 |
| K2 | same tools + full knowledge input | 额外知识的边际贡献 |

这个结构没有根本偏离。需要修正的是叙事方式和任务解释。

当前新增 T5 后，实验不再只是“工具 vs 知识”的单一平均成功率比较，而是包含两类任务：

- execution-shaped tasks：T1, T2, T3，主要测试工具 grounding；
- knowledge-sensitive tasks：T4, T5，测试一般水文知识和 HydroAgent-specific workflow knowledge。

因此，不能只用总成功率解释实验 3。必须按任务类型解释：K0->K1 的大跃迁来自工具；K1->K2 的小收益只出现在知识敏感任务。

## 2. 新的实验主张

建议论文中的 Experiment 3 主张写成：

> Executable tools are the foundation of HydroAgent's reliability, while additional knowledge should be loaded on demand for workflow-specific reasoning tasks.

中文主张：

> HydroAgent 的可靠性首先来自可执行工具；额外知识只在系统特定工作流知识任务上提供边际收益，因此更适合按需加载，而不是默认全量注入。

当前数据支持这个主张：

- K0 -> K1：success 28% -> 96%，+68 percentage points；
- hallucination 12% -> 0%，说明工具 grounding 抑制无证据输出；
- K1 -> K2：success 96% -> 100%，+4 percentage points；
- K2 token 约 78k，K1 约 30k，约 2.6x；
- K2 的唯一严格增益来自 T5：K0 2/5，K1 4/5，K2 5/5。

## 3. 建议保留的条件

保留 K0/K1/K2，不建议再增加更多条件。实验 3 的价值在于简单清楚：

| 条件 | 建议名称 | 解释 |
|---|---|---|
| K0 | language-only baseline | 没有工具、没有知识；测试语言模型是否会凭空完成执行任务 |
| K1 | tools-only grounding | 有同 K2 相同的工具，但无额外知识；测试工具是否足以完成多数任务 |
| K2 | tools + full knowledge | 工具同 K1，加 skills/knowledge/adapter docs/memory；测试知识边际收益 |

注意：K2 不应被简称为 “domain knowledge only”。它包含 skills、knowledge files、adapter docs、memory/profile hooks。因此论文和表格中建议写：

- `Full knowledge input`
- `Tools + full knowledge input`
- `system-specific knowledge input`

避免写：

- `More hydrological knowledge`
- `Knowledge makes the model better`

## 4. 任务分组建议

当前 T1-T5 可以保留，但 README 和 paper text 必须重新解释每个任务的角色。

| 任务 | 建议类型 | 保留理由 | 预期解释 |
|---|---|---|---|
| T1 standard calibration | executable workflow | 基础水文执行链 | K0 应失败；K1/K2 应成功 |
| T2 model comparison | executable workflow | 多模型执行和指标综合 | K0 应失败；K1/K2 应成功 |
| T3 code analysis | routing / non-calibration execution | 测试工具路由，而不是率定 | K1/K2 应避免 calibrate/evaluate |
| T4 failure diagnosis | general hydrological reasoning | 测试 LLM 预训练知识是否已足够 | 三组都可能成功，不应作为 K2 优势证据 |
| T5 calibration workflow knowledge | system-specific knowledge | 测试知识包是否有边际价值 | K2 应优于 K1，但要报告 token 成本 |

### 关于 T5 的风险

T5 容易被读者看成“专门为 K2 设计的知识题”。为了避免这个问题，建议：

1. 在实验设计中明确声明 T5 是 knowledge-sensitive control task；
2. 不把 T5 和 T1-T3 混在一起讲平均成功率；
3. 在 Results 中说清楚 K2 的收益只集中在 T5；
4. 讨论中承认 T5 测的是 HydroAgent-specific workflow knowledge，而不是一般水文能力。

如果要让 T5 更自然，可以把用户 query 改成真实操作后的诊断请求，而不是直接问知识点。例如：

```text
After a GR4J calibration run for basin 12025000, the result reports test NSE=0.45.
The selected parameters are x1=98 near the lower bound and x2=-2.95 near the lower bound.
The user asks what evaluation should be run next, whether the search budget should be quick,
standard, or precision, and which parameter ranges should be adjusted before the next run.
Do not run tools; answer from the available workflow knowledge.
```

这样 T5 更像真实率定后的 workflow decision，而不是考试式知识问答。

## 5. 成功判定建议

当前成功判定大体可用，但建议做以下清理。

### T1: standard calibration

成功条件：

- 调用 `validate_basin`；
- 调用 `calibrate_model`；
- 调用 `evaluate_model`；
- 最终答案引用真实 NSE/KGE 或工具输出；
- 无 hallucination。

K0 没有工具时，如果只解释流程但没有真实指标，不应算成功。可以单独记录为 `procedural_answer`，但 `task_success=False`。

### T2: model comparison

成功条件：

- 两个模型都运行 calibration/evaluation；
- 选择结果基于真实 NSE/KGE；
- 无 hallucination。

需要防止只跑一个模型就给结论。

### T3: code analysis

成功条件：

- 使用 `generate_code` 和 `run_code`；
- 避免 `calibrate_model` 和 `evaluate_model`；
- 输出来自真实可用数据；
- 不使用 simulated/random/dummy data。

T3 的主指标应是 routing success，而不是水文指标。

### T4: failure diagnosis

成功条件：

- 不调用工具；
- 解释参数触边的物理意义；
- 提醒不要机械扩展所有范围，或指出可能存在模型结构/数据/参数可辨识问题；
- 给出合理下一步。

T4 不应要求 K2 特有事实。它的作用是证明：一般诊断任务不一定需要 full knowledge input。

### T5: calibration workflow knowledge

成功条件建议从“关键词命中”改成更结构化：

- 正确说明 post-calibration evaluation sequence；
- 给出合理的 SCE-UA budget choice 或 rep/ngs 建议；
- 正确解释 GR4J 参数触边含义；
- 给出具体 range adjustment 或 rerun strategy；
- 不调用工具。

如果保留 exact required facts，例如 `500`、`rep`、`ngs`，要确保这些事实确实来自当前知识文件，并且在 paper 中说明 T5 专门测试 system-specific workflow knowledge。

## 6. 指标设计建议

正文主表不要放太多字段。建议保留：

| 指标 | 用途 |
|---|---|
| Task success | 总体任务完成 |
| Execution-task success | T1-T3 平均；体现工具 grounding |
| Knowledge-task success | T4-T5 或仅 T5；体现知识边际 |
| Tool-route success | 是否选对工具路径 |
| Hallucination | 是否编造执行结果 |
| Forbidden-tool rate | 是否在不应运行工具时运行工具 |
| Mean tokens per run | 成本 |
| Tokens per success | 成本效率 |

建议新增两个聚合字段：

- `execution_success_rate`: T1-T3 的成功率；
- `knowledge_sensitive_success_rate`: T5 的成功率，或 T4-T5 分开统计。

不要只报总成功率，因为 K2 的总成功率 100% 容易掩盖“收益只来自 T5”的事实。

## 7. 图件建议

### Figure 4.5: success-cost frontier

保留成功率 vs token 图，但图注要强调：

- K0 -> K1 是大幅垂直提升；
- K1 -> K2 是小幅成功率提升和较大 token 增量；
- 结论是 knowledge-on-demand，而不是 full knowledge by default。

### Figure 4.6: task-type heatmap

建议把热图按任务类型分组，或者在 y 轴标签中标出：

- Execution: T1, T2
- Routing: T3
- General diagnosis: T4
- System-specific knowledge: T5

图注应直接点明：

> K2 only strictly improves over K1 on T5.

### 可选新增 Figure/Table

如果另一个 agent 有时间，可以新增一个小表或小图：

| Comparison | Success gain | Extra tokens | Marginal gain per 10k tokens |
|---|---:|---:|---:|
| K0 -> K1 | +68 pp | +28k | high |
| K1 -> K2 | +4 pp | +48k | low |

这能直接支撑 “knowledge-on-demand”。

## 8. 表格、图件和预期指标清单

这一节给执行 agent 作为产物验收清单。不要只重新生成旧表；表格必须直接服务论文论点。

### 正文 Table A: condition-level evidence

文件建议：

- `experiment/exp3/tables/table_exp3_condition_summary.csv`

建议字段：

| Column | Meaning |
|---|---|
| Condition | K0/K1/K2 |
| Input setting | language only / tools only / tools + full knowledge |
| Number of runs | 每个条件总运行数 |
| Overall task success | T1-T5 总成功率 |
| Execution-task success | T1-T3 成功率 |
| General-diagnosis success | T4 成功率 |
| System-specific-knowledge success | T5 成功率 |
| Tool-route success | 工具路径正确率 |
| Hallucination | 无执行依据结果率 |
| Forbidden-tool use | 不应调用工具时的调用率 |
| Mean tokens per run | 平均 token |
| Tokens per success | 每成功任务 token |
| Extra tokens vs tools-only | K2 相对 K1 的额外 token |
| Marginal gain per 10k tokens | K1->K2 每 10k token 的成功率增益 |

预期最容易写论文的模式：

- K0 overall success 明显低，最好低于 40%；
- K1 overall success 接近 K2，最好达到 90% 以上；
- K2 overall success 可略高于 K1，但增益应小，预期约 0-10 percentage points；
- K0 hallucination 高于 K1/K2，K1/K2 最好接近 0；
- K2 mean tokens 显著高于 K1，预期至少 2x；
- K1->K2 的 marginal gain per 10k tokens 明显低于 K0->K1。

这些不是强制“调结果”的目标，而是判断这组实验是否能支持 `tool-first, knowledge-on-demand` 论文主张的预期模式。

### 正文 Table B: task-type evidence

文件建议：

- `experiment/exp3/tables/table_exp3_task_group_summary.csv`

建议字段：

| Column | Meaning |
|---|---|
| Task group | execution / routing / general diagnosis / system-specific knowledge |
| Tasks included | T1-T5 对应关系 |
| K0 success | 该组 K0 成功率 |
| K1 success | 该组 K1 成功率 |
| K2 success | 该组 K2 成功率 |
| Main interpretation | 工具贡献 / 知识边际 / LLM 预训练足够 |

预期模式：

- Execution group: K0 低，K1=K2 高；
- Routing group: K1=K2 高，且 forbidden-tool rate 低；
- General diagnosis: K0/K1/K2 都高，说明 full knowledge 不必要；
- System-specific knowledge: K2 > K1 >= K0，说明知识包只在这类任务上有边际价值。

### Supplementary Table: trial-level audit

文件保留：

- `experiment/exp3/tables/tableS_exp3_trial_records.csv`

必须保留字段：

- `condition_id`
- `task_id`
- `repeat`
- `task_success`
- `tool_route_success`
- `first_tool_accuracy`
- `forbidden_tool_hit`
- `hallucination`
- `total_tokens`
- `wall_time_s`
- `tool_compute_time_s`
- `llm_decision_time_s`
- `actual_tools`
- `error`

用途：支撑可追溯性，不建议放正文。

### Figure 4.5: success-cost frontier

文件建议：

- `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`

图内容：

- x-axis: mean tokens per run；
- y-axis: overall task success；
- points: K0, K1, K2；
- 用箭头标出 K0->K1 和 K1->K2；
- 可在点旁标注 success 和 mean tokens。

预期视觉效果：

- K0->K1 是大幅向上移动；
- K1->K2 是小幅向上但明显向右移动；
- 图注直接写明：large tool-grounding gain, small knowledge gain at high token cost。

### Figure 4.6: task-type heatmap

文件建议：

- `experiment/exp3/figures/fig_exp3_task_heatmap.png`

图内容：

- rows: T1-T5，按任务类型排序；
- columns: K0/K1/K2；
- cell value: task success rate；
- y-axis label 建议写成 `T1 execution: standard calibration` 这种带类型的短标签；
- 在图注中点明 T5 是唯一 K2 严格优于 K1 的任务。

预期视觉效果：

- T1-T3: K0 冷色，K1/K2 热色；
- T4: 三列都热色；
- T5: 从 K0 到 K1 到 K2 递增。

### 可选 Figure 4.6b 或正文小表: marginal value

如果版面允许，可增加一张小表而不是新图：

| Comparison | Success gain | Extra tokens per run | Interpretation |
|---|---:|---:|---|
| K0 -> K1 | large | moderate | executable grounding |
| K1 -> K2 | small | large | knowledge-on-demand |

这个表非常适合放 Discussion 前作为 Results 的收束证据。

## 9. README / paper text 改写建议

### README 标题

建议从：

```text
Exp3 v2: Knowledge input ablation
```

改为：

```text
Exp3 v2: Tool grounding and knowledge-on-demand
```

### Experiment question

建议改为：

```text
Does HydroAgent's reliability come primarily from executable tool grounding,
and when does additional system-specific knowledge provide enough marginal value
to justify its token cost?
```

### Results 主句

建议写：

```text
The decisive improvement is tool grounding: adding executable tools raises
success from 28% to 96% and removes hallucinated numerical results. Full
knowledge input adds the final 4 percentage points, but the gain is confined
to a system-specific workflow-knowledge task and costs about 2.6 times more
tokens than tools alone.
```

### Discussion 主句

建议写：

```text
These results support a tool-first, knowledge-on-demand design. Routine
execution and general diagnosis do not require the full knowledge pack in
every run, but workflow-specific questions benefit from loading the relevant
knowledge files when needed.
```

## 10. 建议代码修改清单

### `common.py`

1. 保留 K0/K1/K2。
2. 保留 T1-T5，但重新标注每个 task 的 `task_group`：
   - `execution`
   - `routing`
   - `general_diagnosis`
   - `system_specific_knowledge`
3. 可考虑重写 T5 query，使其更像真实率定后的 workflow decision，而不是显式问答。
4. 将 T5 的成功判定从纯关键词匹配改为结构化 checklist。
5. 对 K0 的 procedural answer 单独标记，不计入 execution success。

### `compile_results.py`

1. 新增 task-group 聚合表：
   - `table_exp3_task_group_summary.csv`
2. 在 condition summary 中新增：
   - `execution_success_rate`
   - `routing_success_rate`
   - `general_diagnosis_success_rate`
   - `system_specific_knowledge_success_rate`
3. 继续保留 `tokens_per_success` 和 `marginal_gain_per_10k_tokens`。
4. 表头使用完整词，避免缩写。

### `plot_results.py`

1. 热图按 task group 排序。
2. 在图中或图注中突出 T5 是唯一 K2 > K1 的任务。
3. 成功率-token 图中标注 K0->K1 和 K1->K2 两条增量箭头。

### `README.md` 和 `paper_text_exp3.md`

1. 改标题和主问题。
2. 把 T5 明确写成 knowledge-sensitive control task。
3. 结果章不要写“K2 最好所以知识有效”这种粗结论。
4. 写成“工具决定大部分成功，知识提供小幅且任务特定的边际收益”。

## 11. 给执行 agent 的最低验收标准

下一轮修改至少要满足：

- K0/K1/K2 条件保持公平：K1 和 K2 工具集相同。
- T1-T3 明确作为工具 grounding 任务解释。
- T4 不作为 K2 优势证据。
- T5 明确作为 system-specific knowledge task。
- 输出表中能直接读出：
  - K0 -> K1 的工具贡献；
  - K1 -> K2 的知识边际收益；
  - K2 相对 K1 的额外 token 成本。
- 正文或 paper text 明确使用 “knowledge-on-demand” 结论。
