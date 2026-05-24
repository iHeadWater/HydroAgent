---
name: MCMC参数不确定性分析
description: 使用spotpy对GR4J/XAJ等水文模型进行MCMC参数不确定性分析，生成后验参数分布、轨迹图及流模拟不确定性区间。
keywords: [MCMC, uncertainty, spotpy, hydrological model, parameter estimation, posterior distribution, prediction intervals]
tools: [mcmc_uncertainty_analysis]
when_to_use: 当需要评估已校准水文模型参数的不确定性，并生成基于MCMC的预测区间（如5th-95th百分位数）时使用。
---

## MCMC参数不确定性分析工作流

### 适用范围
- 模型类型：GR4J、XAJ等支持spotpy的水文模型。
- 前置条件：已完成模型校准，校准结果存放于 `calibration_dir` 目录。
- 输入参数：
  - `calibration_dir`：校准模型输出目录，包含模型文件及校准参数等。
  - `basin_ids`：流域ID列表（字符串列表）。
  - `model_name`：模型名称（如"GR4J"、"XAJ"），用于加载对应的spotpy设置。
  - `n_samples`：MCMC采样迭代次数（例如10000）。
- 输出：
  - 后验参数文件（CSV格式，包含所有后验样本）。
  - 轨迹诊断图及后验参数分布直方图。
  - 预测区间文件：基于后验参数模拟的5th-95th百分位流序列。

### 工作流步骤

1. **加载校准模型和参数**
   - 从 `calibration_dir` 读取已校准的参数（如最优参数向量）及模型结构。
   - 基于 `model_name` 实例化 spotpy 的 `spotpy_setup` 对象（需自定义实现，继承 `spotypy.setup`）。

2. **配置MCMC采样器**
   - 根据需求选择算法（推荐 DE-MCz，即 `demcz`）。
   - 初始化采样器：`sampler = demcz(spotpy_setup, dbname='MCMC', dbformat='csv')`

3. **运行MCMC采样**
   - 调用 `sampler.sample(iterations=n_samples)`。
   - 可设置并行参数（如 `nchain`）以获得更高效率。

4. **后处理与诊断**
   - 使用 `spotpy.analyser` 加载结果：`results = spotpy.analyser.load_csv_results('MCMC')`
   - 生成参数轨迹图（trace plots）和后验分布直方图（`plot_posterior_parameter_histogram`）。
   - 计算Gelman-Rubin收敛诊断（`gelman_rubin`）并保存。

5. **生成预测区间**
   - 用后验参数样本（如随机选取1000组）运行模型模拟，对每个时间步计算5th和95th百分位数。
   - 输出区间结果至CSV文件（包含日期、观测值、模拟中位数、下限、上限）。

### 注意事项
- 确保 `spotpy_setup` 中的 `parameters` 定义与模型参数一一对应。
- 对于大型模型，可调整 `n_samples` 和并行核心数以平衡计算时间与收敛质量。
- 默认数据库格式为CSV（`dbformat='csv'`），也可改用SQLite。
- 若陷入局部后验，尝试调整提议步长或链数。

### 示例（Python伪代码）
```python
import spotpy
from spotpy.algorithms import demcz
# 假设已有自定义 spotpy_setup
sampler = demcz(spotpy_setup, dbname='MCMC', dbformat='csv')
sampler.sample(iterations=n_samples)
results = spotpy.analyser.load_csv_results('MCMC')
spotpy.analyser.plot_posterior_parameter_histogram(results)
# 后续预测区间计算略
```