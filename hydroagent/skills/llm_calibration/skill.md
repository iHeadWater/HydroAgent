---
name: LLM Calibration
description: LLM 智能率定：先获取流域属性 → 推理先验参数范围 → 迭代自适应调整，模拟人类水文专家经验
keywords: [ai率定, 智能率定, 专家模式, llm率定, ai calibrat, llm calibrat]
tools: [get_basin_attributes, llm_calibrate, validate_basin, evaluate_model, inspect_dir, read_file]
when_to_use: 传统率定 NSE 偏低时，或用户明确要求 AI/智能率定
---

## 目标

LLM 智能率定的本质是**模拟人类水文专家的两步经验**：

1. **先验知识**：专家在看到任何率定结果之前，先根据流域气候特征判断哪些参数范围合理
2. **自适应调整**：专家根据率定结果（参数是否触边界、NSE 是否合理）主动缩窄或扩展搜索空间

Agent 的任务：像人类专家一样，先查流域属性、推理合理范围，再驱动迭代率定。

---

## 三步工作流（必须按顺序执行）

### Step 1: 获取流域气候属性

```
get_basin_attributes(basin_id=<id>, data_source=<dataset>)
```

重点关注返回值：
- `aridity`：干旱度（PET/P）。< 0.6 湿润，0.6-1.0 半湿润，> 1.0 干旱
- `runoff_ratio`：产流比（Q/P）
- `baseflow_index`：基流指数（BFI）。高 BFI = 地下水调蓄能力强
- `frac_snow`：降雪比例
- `climate_zone`：自动判断的气候区（humid_cold / humid_warm / sub_humid_mediterranean / semiarid_arid）

### Step 2: 推理参数范围（根据下表 + 流域属性）

根据气候区推理 XAJ 各参数的初始范围，传入 `llm_calibrate`。
参考下方 **XAJ 参数气候区对照表**，结合 `aridity`、`frac_snow`、`baseflow_index` 做出判断。

关键推理逻辑：
- 湿润流域（aridity < 0.6）：产流充分，K 偏高，SM 较大，CG 接近 1.0（慢速基流）
- 干旱流域（aridity > 1.0）：产流少，K 偏低，SM 较小，CS 较大（地表径流快）
- 积雪流域（frac_snow > 0.15）：可能存在融雪贡献，L（滞后时间）偏大
- 高 BFI（> 0.6）：地下出流占主导，KG 偏高，CG 接近 1.0

### Step 3: 调用 LLM 率定（传入先验范围）

```python
llm_calibrate(
    basin_ids=[<basin_id>],
    model_name="xaj",
    param_ranges=<Step 2 推理出的范围>,   # 关键：传入先验约束
    max_rounds=5,
)
```

工具内部会以此为起点进行多轮迭代，每轮检测边界触碰、固定收敛参数、调整未收敛参数的范围。

---

## XAJ 参数气候区对照表

| 参数 | 物理含义 | 湿润寒冷 | 湿润温暖 | 地中海型 | 干旱半干旱 |
|------|---------|---------|---------|---------|---------|
| K | 蒸散发折减系数 | 0.7 – 1.0 | 0.6 – 0.9 | 0.5 – 0.8 | 0.3 – 0.7 |
| B | 张力水蓄水容量分布指数 | 0.1 – 0.3 | 0.1 – 0.3 | 0.2 – 0.4 | 0.2 – 0.4 |
| IM | 不透水面积比例 | 0.01 – 0.05 | 0.01 – 0.05 | 0.01 – 0.08 | 0.01 – 0.10 |
| UM | 上层张力水容量（mm）| 15 – 30 | 10 – 25 | 10 – 30 | 5 – 20 |
| LM | 下层张力水容量（mm）| 70 – 90 | 60 – 85 | 60 – 90 | 60 – 90 |
| DM | 深层张力水容量（mm）| 80 – 120 | 70 – 110 | 60 – 100 | 60 – 100 |
| C | 深层蒸散发系数 | 0.12 – 0.20 | 0.10 – 0.18 | 0.08 – 0.16 | 0.05 – 0.15 |
| SM | 自由水蓄水容量（mm）| 30 – 80 | 20 – 70 | 20 – 60 | 10 – 50 |
| EX | 自由水分布指数 | 1.0 – 1.5 | 1.0 – 1.5 | 1.0 – 1.5 | 1.0 – 1.5 |
| KI | 壤中流出流系数 | 0.3 – 0.7 | 0.3 – 0.6 | 0.2 – 0.6 | 0.1 – 0.5 |
| KG | 地下径流出流系数 | 0.2 – 0.5 | 0.2 – 0.5 | 0.3 – 0.6 | 0.1 – 0.4 |
| CS | 地表径流消退系数 | 0.2 – 0.6 | 0.2 – 0.6 | 0.3 – 0.7 | 0.3 – 0.8 |
| L | 河网滞后时间（时段数）| 2 – 6 | 1 – 4 | 1 – 3 | 1 – 3 |
| CI | 壤中流消退系数 | 0.5 – 0.9 | 0.5 – 0.9 | 0.4 – 0.8 | 0.3 – 0.7 |
| CG | 地下径流消退系数 | 0.980 – 0.998 | 0.970 – 0.998 | 0.960 – 0.998 | 0.950 – 0.998 |

**KI + KG 约束**：两者之和必须 < 0.7。推理范围时注意使 KI_max + KG_max ≤ 0.65。

---

## 任务开始前的准备

**第一步：检索历史记录**
```
search_memory(query="<basin_id>")
```
- 有历史 LLM 率定记录 → 告知用户上次的初始参数范围和 NSE 轨迹，询问是否复用或重跑
- 无历史记录 → 继续三步工作流

**第二步：验证数据并告知耗时**
- 调用 `validate_basin` 确认流域数据可用（时段、变量齐全）
- 告知用户：共最多 `max_rounds` 轮（默认 5），每轮完整 SCE-UA，总耗时较长

---

## 如何解读 `llm_calibrate` 返回结果

`llm_calibrate` 内部已计算每轮训练期 NSE，但**测试期评估需手动调用**：

```
evaluate_model(calibration_dir=result['calibration_dir'], eval_period=test_period)
```

检查 `history`（每轮含 `round`, `nse`, `boundary_hits`, `param_ranges`）：

| 观察到的情况 | 判断 |
|------------|------|
| NSE 逐轮上升，最终达到目标 | 先验范围有效，迭代改善成功 |
| NSE 无变化，`boundary_hits` 为空 | 模型在当前范围内已收敛，考虑换模型或诊断数据 |
| `final_boundary_hits` 非空 | 最终参数仍触边界，可扩展 `param_ranges` 对应参数再试 |
| 某轮失败（`error` 字段存在）| 跳过该轮，看其余轮次趋势 |

---

## 异常处理

| 异常 | 处理方式 |
|------|---------|
| `get_basin_attributes` 找不到缓存文件 | 跳过先验推理，用默认范围调用 `llm_calibrate`；在报告中注明 |
| `llm_calibrate` 返回 `success: False` | 检查 `error` 字段；若为 LLM 未连接，检查 API key |
| 所有轮次 NSE 均 < 0.5 | 检查参数文件，诊断是否为数据问题（而非范围问题）|
| `nse_target` 始终未达到 | 报告最优 NSE，分析原因，给出后续建议 |

**遇到不确定情况时，主动查阅知识库：**

| 情况 | 操作 |
|------|------|
| 报错原因不明，无法判断失败类型 | `read_file("hydroagent/knowledge/failure_modes.md")` |
| 同一工具报错反复出现 | `read_file("hydroagent/knowledge/tool_error_kb.md")` |
| 不确定流域属性归类方法 | `read_file("hydroagent/knowledge/datasets.md")` |
| 不确定 XAJ/GR4J 参数物理含义 | `read_file("hydroagent/knowledge/model_parameters.md")` |

---

## 报告格式

最终报告必须包含：
- **流域特征摘要**：climate_zone、aridity、runoff_ratio、baseflow_index
- **先验范围决策**：Agent 推理得到的初始 `param_ranges`（与默认范围对比说明收窄原因）
- **收敛轨迹**：每轮 NSE（表格形式）
- **参数固定记录**：哪些参数在哪轮被固定（`fixed_params_by_round`）
- **最优参数及边界状态**：`final_boundary_hits` 分析
- **测试期泛化指标**：NSE / KGE
- **与标准 SCE-UA 对比**：若已知单轮结果，说明先验知识带来的改善

---

## 完成后必做

1. 确认已获得训练期 + 测试期双期指标
2. 对比 `initial_param_ranges_llm` 与默认范围，解释先验收窄的水文依据
3. 如果 `fixed_params_by_round` 非空，说明哪些参数在几轮后收敛及其含义
4. 用一句话总结"本次 LLM 率定相比标准 SCE-UA 做了什么不同"
5. 如发现流域特殊行为或参数规律，明确提示用户（方便纳入长期记忆）

---

## 参考

Zhu et al. (2026), GRL, doi:10.1029/2025GL120043
HydroAgent 扩展：LLM 不直接搜索参数，而是通过范围调整指导 SCE-UA 跳出局部最优。
