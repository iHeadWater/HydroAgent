---
name: compare_calibration_distributions
description: 对比两个水文模型率定结果目录的参数分布，生成箱线图可视化
keywords: [hydrology, calibration, distribution, visualization, boxplot, comparison]
tools: [compare_calibration_distributions]
when_to_use: 需要直观对比不同模型或不同优化算法的率定参数分布差异时
---

## compare_calibration_distributions 工作流

### 功能概述
本技能用于对比两个水文模型率定结果目录中的参数分布情况。通过读取 `calibration_results.json` 文件，提取各参数的最优值、归一化值和物理值，并使用 matplotlib/seaborn 绘制并排箱线图。与仅进行统计对比的 `compare_calibration_params` 不同，本工具侧重于**可视化展示**参数分布的差异（如离散度、中位数偏移等），帮助评估不同模型结构或优化算法对参数敏感性的影响。

### 适用场景
- 对比不同水文模型（如 GR4J vs XAJ）在同一流域的率定参数分布。
- 对比同一模型使用不同优化算法（如 SCE-UA vs GA）的率定结果稳定性。
- 分析参数在多次率定运行中的波动范围及异常值。

### 输入参数
| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `calibration_dir_1` | str | 是 | 第一个率定结果目录路径，需包含 `calibration_results.json` |
| `calibration_dir_2` | str | 是 | 第二个率定结果目录路径，需包含 `calibration_results.json` |

### 工作流程
1. **数据加载**：自动扫描指定目录下的 `calibration_results.json` 文件。
2. **数据解析**：提取 JSON 中的参数信息，包括参数名称、最优物理值、归一化值及对应的目标函数值。
3. **统计分析**：计算各参数的均值、中位数、标准差及四分位距（IQR）。
4. **可视化生成**：使用 Seaborn 绘制并排箱线图（Side-by-Side Boxplot），X 轴为参数名称，Y 轴为参数值（可选择物理值或归一化值），两组数据分别用不同颜色区分。
5. **结果输出**：返回统计摘要文本及生成的图表图像。

### 注意事项
- 确保两个目录下的 `calibration_results.json` 格式一致，包含相同的参数键名。
- 若参数单位差异巨大，建议优先查看归一化值分布以消除量纲影响。
- 依赖库：`matplotlib`, `seaborn`, `pandas`, `numpy`。

### 示例代码

```python
# 对比 GR4J 和 XAJ 在同一流域的率定参数分布
compare_calibration_distributions(
    calibration_dir_1="/path/to/gr4j_calibration",
    calibration_dir_2="/path/to/xaj_calibration"
)

# 对比同一模型不同算法的率定结果
compare_calibration_distributions(
    calibration_dir_1="/path/to/sce_ua_results",
    calibration_dir_2="/path/to/ga_results"
)
```

### 输出说明
- **统计摘要**：控制台打印各参数的关键统计指标（Min, Max, Mean, Median, Std）。
- **可视化图表**：生成包含参数分布箱线图的 PNG 图片，直观展示两组数据的分布重叠程度及离散性。