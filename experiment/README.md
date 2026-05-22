# HydroAgent 实验脚本说明

> 论文 Section 4: Experiments | 更新：2026-04-09

---

## 一、实验总览

| 脚本 | 实验 | 核心论证 | 状态 |
|------|------|---------|------|
| `exp1_standard_calibration.py` | 标准率定基线 | Agent 自主规划工作流的可靠性 | 已完成 |
| `exp2_llm_calibration.py` | LLM 率定 A/B/C 三路对比 | 自动化等价：C ≈ A，零人工干预 | 已完成 |
| `exp4_capability_boundaries.py` | Agent 能力广度 | NL 鲁棒性 + 动态 Skill + 批量自治 | 已完成 |
| `exp3_knowledge_ablation.py` | 知识层消融 K0-K3 | 结构化知识注入的量化贡献 | 已完成 |

整体论证逻辑：

```
Exp1 -> 系统"能做"               Agent 自主执行完整率定，tool_sequence 可验证
Exp2 -> 系统"做得一样好，不需要人"  C ≈ A（NSE），但 C 自主多轮决策
Exp3 -> 系统"足够通用"            6种自然语言表达全部正确，跨任务类型自适应规划
Exp4 -> 结构"有必要"              K0-K3逐层消融，量化每层知识的贡献
```

---

## 二、Exp1：标准率定基线

**目的**：验证 HydroAgent Agent 能从自然语言自主规划并执行完整水文率定工作流。

**设计**：5 流域 x XAJ 模型 x SCE-UA x 3 次独立运行
（单模型：XAJ 为湿润区代表性概念模型；GR4J 对比移至 Exp2）

| 流域 | 气候区 | KGE_test | 说明 |
|------|--------|---------|------|
| 12025000 Fish River, ME | 湿润寒冷 | 0.679 | 拟合良好，参照流域 |
| 11532500 Smith River, CA | 地中海 | 0.581 | 强季节性，表现中等 |
| 03439000 French Broad, NC | 湿润暖 | -0.110 | 模型适配性不足 |
| 06043500 Gallatin R., MT | 半干旱山区 | -0.047 | 积雪融雪主导，XAJ 不适配 |
| 08101000 Cowhouse Creek, TX | 半干旱闪洪 | -8.696 | 超渗产流，概念模型结构局限 |

**关键证据**：
- `tool_sequence`：全部 15 次运行均自主调用 validate_basin -> calibrate_model -> evaluate_model（full_seq_ok = 15/15）
- 半干旱流域的负 KGE 是有价值的负面结果，说明 XAJ 的适用边界

**Token 对比子实验**（附加，basin 12025000，1 次运行）：

| 模式 | API 调用次数 | 总 token | 节省 |
|------|------------|---------|------|
| ReAct | 4 | 52,333 | — |
| Pipeline | 1 | 7,304 | 86% |

**绘图**：`plot/exp1_figures.py` -> `plot/exp1/`

---

## 三、Exp2：LLM 率定 A/B/C 三路对比

**目的**：验证 HydroAgent 自主 LLM 率定工作流（方法C）达到与传统 SCE-UA（方法A）等价的精度，同时实现零人工干预。

**模型**：GR4J | **流域**：3 个气候区

### 三路方法定义

| 方法 | 名称 | 执行方式 | 核心特点 |
|------|------|---------|---------|
| A | SCE-UA 基线 | Agent 驱动 | 默认参数范围，1 次运行 |
| B | Zhu et al. 风格 | 脚本复现（非 Agent） | LLM 直接提议参数值，极窄范围 +-3%，<=15 轮 |
| C | HydroAgent LLM 率定 | Agent 驱动 | Agent 自主触发 llm_calibrate，最多 5 轮，每轮不同种子 |

> 方法 B 用脚本而非 Agent：Zhu 方法需精确控制 prompt 格式和 +-3% 窄范围约定，自然语言无法准确表达，脚本复现更忠实原始方法。

### 实际结果

| 流域 | A test NSE | B test NSE | C test NSE | C train NSE 轨迹 |
|------|-----------|-----------|-----------|----------------|
| 12025000 | 0.748 | 0.758 | 0.748 | 平稳（5 轮无变化）|
| 11532500 | 0.741 | 0.748 | 0.741 | 平稳（5 轮无变化）|
| 06043500 | -0.181 | -0.120 | -0.149 | 有改善（-0.116 -> -0.097）|

### Exp2 验证什么

**核心论点**：LLM 参与率定的价值在于**自动化等价**，而非 NSE 超越。

1. **精度等价**（C ≈ A）：方法 C 与 SCE-UA 基线 NSE 基本持平，引入 LLM 不损失精度
2. **零人工干预自主多轮**：Agent 完整执行 5 轮迭代，每轮自主决定是否继续，无用户介入
3. **LLM 对难流域有实质作用**：06043500 方法 C 的 train NSE 有改善（-0.116 -> -0.097），固定参数范围的方法 A 无法自适应
4. **与 Zhu 2026 共同结论**：两项研究均发现 LLM 参与不能突破模型-流域的 NSE 上限（由水文模型结构决定），价值在于减少人工干预

**负面结果的科学价值**：
- 12025000 和 11532500 的 C 轨迹全平——参数范围已近最优，诚实报告
- 半干旱流域 NSE 仍为负——模型结构不适配，超出 Agent 能力边界，Discussion 需明确

**绘图**：`plot/exp2_figures.py` -> `plot/exp2/`

---

## 四、Exp3：Agent 能力广度

**目的**：验证系统通用性——正确响应多样化自然语言、不同任务类型和批量规划场景。

**Section A：自然语言鲁棒性（6 场景，全部 tool_match = True）**

| ID | 类别 | 工具调用数 | 规划特点 |
|----|------|----------|---------|
| A01 | 标准率定 | 8 | 标准 validate->calibrate->evaluate 序列 |
| A02 | 含算法参数 | 8 | 正确解析 rep=500 等具体参数 |
| A03 | 隐含意图（LLM率定）| 19 | 自动选 llm_calibrate，多轮迭代调整 |
| A04 | 批量规划 | 13 | 调用 create/get/update_task 任务管理工具链 |
| A05 | 代码分析 | 29 | generate_code + run_code 多轮循环 |
| A06 | 残缺信息 | 8 | 自主执行并给出改进建议 |

**Section B**：动态 Skill 生成（`create_skill` 元工具验证）

**Section C**：自驱动批量任务规划（断点续传 + 自适应追加）

**绘图**：`plot/exp3_figures.py` -> `plot/exp3/`

---

## 五、Exp4：知识层消融 K0-K4 + 认知框架评估

**目的**：量化系统提示中四层知识注入的独立贡献，特别评估专家认知框架（K4）对推理质量的影响。

**实现**：monkey-patch 临时屏蔽对应知识层，相同 LLM 后端保证公平对比。

| 条件 | 注入内容 | 说明 |
|------|---------|------|
| K0 | 仅角色描述 | 基线 |
| K1 | +Skill 说明书 | 工作流步骤 + 工具调用顺序 |
| K2 | +领域知识库 | 参数物理含义（按需 read_file） |
| K3 | +跨会话记忆 | 流域档案先验（三层完整系统）|
| K4 | +认知框架 | 水文学家.skill 始终注入（四层完整系统）★新增 |

**核心发现**：
- 所有条件 tool_match = 1.0：知识注入不影响工具选择准确率
- **K2 < K1 token（反直觉）**：领域知识引导更直接的推理路径，减少无效工具调用轮次
- **K3 token 激增 4.2x**：跨会话记忆注入代价高，但不提升准确率——记忆是个性化/持久化功能，非准确率功能

| 场景 | 类型 | 评估指标 | 核心问题 |
|------|------|---------|---------|
| T1 | 标准率定 | tool_match / first_tool | 工作流规划能力 |
| T2 | 参数边界感知 | tool_match | 领域知识应用 |
| T3 | 代码分析 | tool_match（需排除率定工具）| 任务类型路由 |
| T4 | 认知诊断 ★新增 | physical_reasoning_score / correct_conclusion | 专家直觉推理 |

**T4 设计**：给定 03439000 流域 4 个参数同时触上界（CS/L/CI/EX），要求 Agent 从物理角度解释原因并给出建议。K0-K3 禁用认知框架，K4 启用，对比物理推理词命中率和正确结论比率。

**历史结果（K0-K3，T1-T3）**：
- 所有条件 tool_match = 1.0：知识注入不影响工具选择准确率
- K2 比 K1 少 14% token（领域知识引导更直接的推理路径）
- K3 token 激增 4.2x（记忆注入代价高，但不提升准确率）

**绘图**：`plot/exp4_figures.py` -> `plot/exp4/`

---

## 六、运行说明

```bash
python experiment/exp1_standard_calibration.py   # ~3h
python experiment/exp2_llm_calibration.py        # ~4h
python experiment/exp4_capability_boundaries.py     # ~2h
python experiment/exp3_knowledge_ablation.py     # ~2h
```

注意：
- Exp1 为 XAJ 单模型，附带 ReAct vs Pipeline token 对比子实验
- Exp2 方法 B 为脚本复现（非 Agent），方法 A/C 为 Agent 驱动
- Exp4 monkey-patch 不修改源文件，可安全重复运行

---

## 七、结果与绘图索引

```
results/paper/
├── exp1/exp1_results.json
├── exp2/exp2_results.json
├── exp3/exp3_results.json
└── exp4/exp4_results.json

plot/
├── exp1_figures.py  ->  exp1/fig2_performance_heatmap.png
│                        exp1/fig3_hydrograph.png
│                        exp1/figS1_token_comparison.png
├── exp2_figures.py  ->  exp2/fig4_method_comparison.png
│                        exp2/fig5_nse_trajectory.png
├── exp3_figures.py  ->  exp3/fig6_tool_sequence_gantt.png
└── exp4_figures.py  ->  exp4/fig7_knowledge_ablation.png
                         exp4/fig8_per_task_tokens.png
```
