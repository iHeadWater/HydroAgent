---
name: Param Distribution Comparison
description: 对比两个率定结果目录的参数分布，生成箱线图可视化。
keywords: [parameter distribution, calibration comparison, boxplot, visualization, hydrology]
tools: [param_distribution_comparison]
when_to_use: 需要直观对比不同模型或算法的率定参数分布差异时
---

## Param Distribution Comparison 工作流

### 功能概述
本技能用于对比两个水文模型率定结果目录中的参数分布情况。通过自动提取参数值并绘制箱线图（Boxplot），直观展示不同模型、算法或流域间的参数敏感性差异。相比仅返回文本表格的工具，本技能提供可视化支持，便于快速识别参数分布的中心趋势和离散程度。

### 适用场景
- **模型对比**：比较 GR4J 与 XAJ 等不同结构模型的参数分布。
- **算法对比**：评估不同优化算法（如 SCE-UA vs PSO）对参数收敛的影响。
- **流域分析**：对比不同流域同一模型参数的空间分布特征。

### 工作流程
1. **准备数据**：确保两个输入目录 (`dir1`, `dir2`) 中包含格式一致的率定参数文件（通常为 CSV 或 JSON）。
2. **调用工具**：传入两个目录路径，工具将自动扫描并解析参数文件。
3. **数据处理**：使用 `pandas` 合并数据，清洗缺失值，按参数名称分组。
4. **可视化生成**：利用 `seaborn` 和 `matplotlib` 绘制双组箱线图。
5. **结果输出**：返回参数统计表格及生成的图片文件路径。

### 参数说明
| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `dir1` | str | 是 | 第一个率定结果目录路径 |
| `dir2` | str | 是 | 第二个率定结果目录路径 |
| `output_path` | str | 否 | 保存箱线图的输出路径，默认为当前工作目录 |
| `figsize` | tuple | 否 | 图像尺寸，默认 `(10, 6)` |

### 注意事项
- 两个目录下的参数文件名需保持一致或能被工具自动匹配。
- 若参数文件中包含非数值列，工具会自动忽略。
- 生成的图片为 PNG 格式，分辨率适中，适合报告插入。

### 使用示例
```python
# 对比 GR4J 和 XAJ 模型的率定参数分布
result = param_distribution_comparison(
    dir1="/path/to/gr4j_results", 
    dir2="/path/to/xaj_results"
)

# result 包含统计表格和图表路径
print(result['chart_path'])
```