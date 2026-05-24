---
name: Explore Calibration Environment
description: Quick exploration of the Python environment to check available packages, calibration tools, and dataset configuration
keywords: [environment, calibration, packages, dataset, exploration]
tools: [list_installed_packages, find_calibration_tools, inspect_dataset_config]
when_to_use: When you need to quickly assess the current Python environment for calibration capabilities, available libraries, and dataset setup.
---

## Explore Calibration Environment 工作流

**用途**：当需要快速了解当前 Python 环境中关于校准（calibration）相关的包、工具和数据集配置时使用。

**步骤**：
1. **检查已安装的包**：调用 `list_installed_packages`（来自 hydroagent）来列出所有已安装的 Python 包，并特别筛选出与校准相关的包（如 `openCV`、`scipy`、`matplotlib`、`pycalib` 等）。
2. **查找校准工具**：调用 `find_calibration_tools`（来自 hydroagent）来搜索环境中可以用于校准的模块或独立工具（例如棋盘格检测、相机标定、IMU 校准等）。
3. **检查数据集配置**：调用 `inspect_dataset_config`（来自 hydroagent）来读取当前项目或默认路径下的数据集配置文件（如 `dataset.yaml`），检查数据集的结构、路径、标签等是否正确。
4. **汇总报告**：将以上三步的结果整合，输出环境快照，包括可用包版本、校准工具列表和数据集配置摘要。

**参数**：无（自动检测当前环境）。

**注意事项**：
- 该技能假设 hydroagent 已安装且包含上述工具函数。
- 如果某些工具找不到，会返回相应的错误信息。
- 建议在校准任务开始前先运行此技能，以确保环境满足要求。