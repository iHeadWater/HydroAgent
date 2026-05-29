---
name: 检查CAMELS数据
description: 检查原始CAMELS数据集的变量、单位、属性和数据质量，读取xarray数据集并打印变量属性、描述统计，检查负值或异常值，计算基本诊断以理解数据结构。
keywords: [CAMELS, 数据检查, 变量属性, 数据质量, 诊断]
tools: [inspect_camels_data]
when_to_use: 当用户需要对CAMELS数据集中的特定流域进行初步探索和数据质量评估时。
---

## 检查CAMELS数据 工作流

### 适用场景
- 用户需要快速了解指定流域CAMELS数据集的结构（变量、单位、缺失情况）。
- 在建模或分析前进行数据质量初筛（如负值、异常值、缺失率）。
- 对比不同流域的数据可用性。

### 前置依赖
- 已安装 `hydrodataset` 包（`pip install hydrodataset`）。
- 本地已下载CAMELS数据集，且目录结构符合 `hydrodataset` 默认约定（通常为 `/data/camels` 或用户指定路径）。

### 逐步工作流

1. **初始化CAMELS数据源**
   - 导入 `hydrodataset` 的 `Camels` 类。
   - 指定 `data_dir` 参数（默认路径为 `~/camels`，可通过 `CAMELS_DATA_DIR` 环境变量覆盖）。
   - 示例：`from hydrodataset import Camels; camels = Camels(data_dir="/path/to/camels")`

2. **读取指定流域的数据**
   - 调用 `camels.read_data(basin=basin_id, start_date=start, end_date=end)` 返回 `xarray.Dataset`。
   - 参数说明：
     - `basin_id`：流域编号（字符串，如 `"01013500"`）。
     - `start_date` 和 `end_date`：可选，默认读取全部可用时段。
   - 若数据不存在或参数无效，会抛出异常，需捕获并提示用户。

3. **打印数据集概览**
   - 输出 `ds` 的基本信息（维度、坐标、变量列表）。
   - 使用 `print(ds)` 或 `ds.info()`（xarray 0.19+ 可用）。

4. **遍历每个变量并输出属性**
   - 对 `ds.data_vars` 中的每个变量：
     - 打印变量名。
     - 若存在 `units` 和 `long_name` 属性，则输出；否则标注“属性缺失”。
   - 检查 `ds.attrs` 中的全局属性（如 `CAMELS_version`、`basin` 等），一并输出。

5. **计算描述性统计**
   - 使用 `ds.describe()` 获得 DataFrame 形式的统计表（count, mean, std, min, 25%, 50%, 75%, max）。
   - 输出该统计表，注意处理 NaN 值。

6. **检查缺失值**
   - 对每个变量计算 `ds[var].isnull().sum()` 和缺失比例。
   - 若缺失比例 > 阈值（如 5%），给出警告。

7. **检查负值（针对非负变量）**
   - 对常见的非负变量（如 `prcp`、`q_mean`、`pet` 等），统计负值个数。
   - 若存在负值，列出具体时间步（前几个示例）并建议数据清洗。

8. **异常值诊断（可选）**
   - 对每个变量，计算 Z-score（`(x - mean) / std`），标记 |Z|>3 的点为潜在异常值。
   - 输出异常值数量及对应时间戳（若超过阈值可警告）。

9. **汇总诊断报告**
   - 将上述结果格式化为清晰文本（可使用 Markdown 或纯文本）。
   - 包含：数据时段、变量数量、缺失率最高的变量、负值变量列表、异常值占比等。

### 参数说明
| 参数 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| `data_dir` | str | 否 | `~/camels` 或环境变量 `CAMELS_DATA_DIR` | CAMELS 数据根目录 |
| `basin_id` | str | 是 | 无 | 流域编号（如 `"01013500"`） |
| `start_date` | str / datetime | 否 | 数据集最早日期 | 开始日期（`"YYYY-MM-DD"`） |
| `end_date` | str / datetime | 否 | 数据集最晚日期 | 结束日期（`"YYYY-MM-DD"`） |

### 注意事项
- 确保 `hydrodataset` ≥ 0.2.0，否则 `read_data` 接口可能不同。
- CAMELS 数据集变量名可能因版本略有差异，检查时建议先打印完整变量列表。
- 对于大型数据集（如 40+ 变量、数十年逐日数据），描述统计和异常值诊断可能较慢，可提示用户先降采样或选择变量子集。
- 负值检查默认认为降水、径流、PET、温度（若单位为 °C，负值正常，需特殊处理）。可根据 `units` 属性判断：若单位包含 `mm`、`m^3/s` 等，则不允许负值；温度允许负值。
- 若用户需要保存诊断结果，可额外提供导出为 CSV 或 JSON 的功能（可选扩展）。