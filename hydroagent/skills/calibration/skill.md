---
name: Standard Calibration
description: 使用 SCE-UA/GA/scipy 对单个或多个流域进行标准水文模型率定
keywords: [率定, calibrat, 优化参数, 参数优化, SCE_UA, GA, scipy]
tools: [calibrate_model, validate_basin, evaluate_model, visualize, inspect_dir, read_file]
when_to_use: 单流域或多流域，使用传统优化算法，首选工作流
---

## Goal

获得指定流域在指定模型上的有效率定结果，输出：
1. 最优参数（保存至 `calibration_dir`）
2. 训练期 NSE / KGE / RMSE（拟合质量）
3. 测试期 NSE / KGE / RMSE（泛化能力）
4. 基于指标和参数边界情况的专业改进建议

---

## Decision Rules

**任务开始时（第一步：检索历史记录）：**

调用 `validate_basin` 之前，先检索历史：
```
search_memory(query="<basin_id>")
```
- 有历史记录 → 告知用户上次率定结果（模型、NSE/KGE、时间），询问是否复用或重新率定
- 无历史记录 → 继续正常流程
- 用户已提供 `calibration_dir` 且只需评估 → 跳过率定，直接调用 `evaluate_model`

**率定完成后（`calibrate_model` 返回 `success: True`）：**
`calibrate_model` **只返回参数，不返回任何指标**。必须显式调用评估：
```
evaluate_model(calibration_dir, eval_period=train_period)   # 训练期
evaluate_model(calibration_dir, eval_period=test_period)    # 测试期
```
`train_period` 和 `test_period` 在 `calibrate_model` 的返回值中已给出，直接使用。

**参数边界判断（对照下表，直接推理，无需额外工具）：**

| 模型 | 参数 | 典型范围 |
|------|------|---------|
| GR4J | x1 (产流库容) | [1, 2000] mm |
| GR4J | x2 (地下水交换) | [-5, 3] mm/d |
| GR4J | x3 (汇流库容) | [1, 500] mm |
| GR4J | x4 (单位线时基) | [0.5, 4] d |

距边界 < 5%（如 x1=1980，接近上界 2000）→ 视为**触边界**。
触边界且 NSE < 0.65 → 推荐改用 `llm_calibrate` 扩展搜索范围。
多轮触边界 → 考虑模型不适配，而不是无限扩范围。

**观测文件的使用时机：**

| 情况 | 操作 |
|------|------|
| 返回了 calibration_dir 但不确定文件是否完整 | `inspect_dir(calibration_dir)` |
| `evaluate_model` 失败，报 config 不存在 | `inspect_dir(calibration_dir)` 诊断根因 |
| 想验证最优参数的具体值 | `read_file(observable_files['calibration_results.json'])` |
| 指标异常（NSE < 0 或极低） | 先读 calibration_results.json，对照边界表判断 |

---

## Failure Recovery

**数据相关（Class A）：**
- `validate_basin` 失败：检查流域 ID 格式（8位）、DATASET_DIR 配置；告知用户并给示例
- 指定变量不全：提示缺失变量，给出最小修复建议

**流程相关（Class B）：**
- 缺结果文件：`inspect_dir(calibration_dir)` 判断是率定未完成还是评估路径错误
- 指标文件不存在：重新执行 `evaluate_model`，不重新率定
- `calibrate_model` 失败，HDF error：再试一次（工具内部已自动重试）
- `calibrate_model` 失败，dataset path：提示用户检查 `configs/definitions_private.py`

**参数相关（Class C）：**
- 多次率定 NSE 无改进：换算法（SCE_UA -> GA），不无限重复

**模型相关（Class D）：**
- 训练期 NSE 合格但测试期差：报告"泛化不足 / 过拟合"，不能宣称成功
- NSE 持续 < 0.4：考虑换模型，参考 `knowledge/model_parameters.md`

**遇到不确定情况时，主动查阅知识库：**

| 情况 | 操作 |
|------|------|
| 报错原因不明，无法判断是哪类失败 | `read_file("hydroagent/knowledge/failure_modes.md")` |
| 同一工具报错反复出现 | `read_file("hydroagent/knowledge/tool_error_kb.md")` |
| 不确定数据集支持的流域或变量 | `read_file("hydroagent/knowledge/datasets.md")` |
| 不确定模型参数的物理含义 | `read_file("hydroagent/knowledge/model_parameters.md")` |

---

## Stop Conditions

**完成条件（满足其一即可停止）：**
- 已获得训练期 + 测试期 NSE/KGE，已记录参数和 `calibration_dir`
- 已确认当前数据/模型/工具条件下无法继续，并输出失败类型和具体建议

**禁止条件：**
- 不能因为"calibrate_model 跑完了"就停止——必须还有完整评估结果
- 不能因为循环超过 3 次就继续重复相同操作——改策略或停止并报告

**完成后必做：**
1. 确认已获得训练期 + 测试期双期指标
2. 用一句话解释本次结果的水文含义（如"KG 接近上界说明地下水出流强，适合换用含地下水模块的模型"）
3. 如果发现了值得记录的流域特征或参数规律，明确提示用户（方便纳入长期记忆）

---

## 报告格式（中文输出）

- 模型名称、流域 ID、算法
- 训练期指标：NSE / KGE / RMSE（含时段日期）
- 测试期指标：NSE / KGE / RMSE（含时段日期）
- 最优参数值及边界情况分析
- 质量等级：NSE ≥ 0.75 优秀 / ≥ 0.65 良好 / ≥ 0.50 一般 / < 0.50 较差
- 改进建议（如触边界 → llm_calibrate；如 NSE 过低 → 换算法或换模型）

---

## 关键配置参考

- `algorithm_params`: 算法参数 dict，如 `{"rep": 500, "ngs": 200}`（不是字符串）
- `param_range_file`: 自定义参数范围 YAML，迭代扩展边界时使用
- 默认训练期：2000-01-01 ~ 2009-12-31 | 默认测试期：2010-01-01 ~ 2014-12-31
