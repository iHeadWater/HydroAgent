---
name: 径流系数与流量历时曲线分析
description: 计算流域径流系数和流量历时曲线（FDC），评估水文特征和水资源可利用性。
keywords: [hydrology, runoff, fdc, camels, water resource analysis]
tools: [runoff_fdc_analysis]
when_to_use: 需要评估流域产水效率或分析不同超越概率下的流量特征时
---

## 径流系数与流量历时曲线分析工作流

本技能用于基于 CAMELS 数据集分析特定流域的水文特性，主要包含两个核心指标：**径流系数**（Runoff Coefficient）和**流量历时曲线**（Flow Duration Curve, FDC）。

### 功能概述
1.  **径流系数计算**：通过年径流量除以年降水量，反映流域的产水效率及水分转化能力。
2.  **流量历时曲线 (FDC)**：生成流量超过特定概率的频率分布曲线，提取关键分位数（Q90, Q75, Q50, Q25, Q10），用于评估枯水期、丰水期及水资源可利用性。

### 使用流程
1.  **输入参数**：指定流域 ID（gage_id）和分析的时间范围（start_date, end_date）。
2.  **数据读取**：系统自动调用 `hydrodataset.camels_us.CamelsUs` 接口，获取该流域对应的 `streamflow`（径流）和 `precipitation`（降水）时间序列数据。
3.  **数据处理**：
    *   将 Xarray Dataset 转换为 DataFrame。
    *   按年份聚合计算年总径流量和年总降水量。
    *   计算径流系数 = 年径流量 / 年降水量。
    *   对日径流数据进行排序，构建 FDC 并计算各分位点流量值。
4.  **结果输出**：返回径流系数数值表、FDC 关键统计量表格以及可视化图表。

### 参数说明
| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `basin_id` | String | 是 | 流域站点 ID (例如：05082000)，需符合 CAMELS-US 命名规范 |
| `start_date` | String | 是 | 开始日期，格式 YYYY-MM-DD |
| `end_date` | String | 是 | 结束日期，格式 YYYY-MM-DD |

### 输出示例
*   **径流系数表**：包含年份、年径流量、年降水量、径流系数。
*   **FDC 统计量**：
    *   Q90 (低流量基准): XX m³/s
    *   Q75: XX m³/s
    *   Q50 (中值): XX m³/s
    *   Q25: XX m³/s
    *   Q10 (高流量基准): XX m³/s
*   **图表**：FDC 曲线图（横轴为超越概率%，纵轴为流量）。

### 注意事项
*   **数据来源**：默认使用 `hydrodataset.camels_us.CamelsUs` 加载 CAMELS-US 数据，请确保本地已配置好 `DATA_PATH` 或网络访问权限。
*   **单位一致性**：计算前会自动处理单位，通常径流单位为 mm/day 或 m³/s，降水单位为 mm/day，计算系数时需统一量纲（代码内部已处理求和逻辑）。
*   **缺失值**：若时间范围内存在数据缺失，计算结果可能受影响，建议检查数据完整性。
*   **适用性**：此技能专为美国大陆流域（CONUS）设计，不适用于其他区域数据集。