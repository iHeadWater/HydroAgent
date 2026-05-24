---
name: Check Environment
description: Check Python environment: installed packages, data files for basin 12025000, and directory structure
keywords: [environment, python, packages, data files, directory structure, basin 12025000]
tools: [check_environment]
when_to_use: 当需要验证Python环境、已安装的包、特定流域数据文件是否存在以及项目目录结构时使用。
---

## Check Environment 工作流

### 概述
`check_environment` 技能用于检查当前Python环境的基本配置，包括已安装的软件包列表、特定流域（12025000）的数据文件完整性以及项目的目录结构。该技能不接收任何参数，直接运行即可输出环境信息。

### 使用场景
- 在新环境中部署项目时，快速验证依赖是否齐全。
- 数据文件丢失或目录结构变化后，诊断问题。
- 定期审计环境一致性。

### 工作流
1. **调用函数**：直接调用 `check_environment()`。
2. **执行检查**：
   - 使用 `subprocess` 运行 `pip list` 获取已安装包列表。
   - 使用 `pathlib` 检查特定路径下是否存在流域12025000的数据文件（如 `data/12025000/` 目录下的文件）。
   - 使用 `os` 和 `pathlib` 遍历项目目录，输出结构摘要。
3. **输出结果**：将检查结果打印到控制台，包括：
   - 已安装包的数量和名称（或异常信息）。
   - 数据文件的存在状态（缺失或完整）。
   - 目录结构的树状预览（仅显示前两级或指定深度）。

### 注意事项
- 该技能假设数据文件位于 `./data/12025000/` 路径下，可根据实际项目调整。
- 需要 `pip` 命令可用，且Python环境已激活。
- 输出信息较多时，建议重定向到文件或使用日志记录。

### 示例
```python
from hydro_agent.skills import check_environment
check_environment()
```

执行后控制台会显示类似信息：
```
===== 环境检查报告 =====
已安装包：numpy, pandas, matplotlib, ... 共12个。
流域12025000数据文件：存在 (文件数: 5)
目录结构：
├── README.md
├── data
│   └── 12025000
│       ├── flow.csv
│       └── precip.csv
├── notebooks
├── scripts
└── skill.md
```

注意：示例输出仅供示意，实际内容取决于环境。