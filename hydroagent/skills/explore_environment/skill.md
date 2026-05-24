---
name: Explore Environment
description: A utility skill to explore the Python environment and check what packages and modules are available for calibration work.
keywords: [environment, packages, modules, calibration, os]
tools: [explore_environment]
when_to_use: When you need to inspect the current Python environment, installed packages, or system paths.
---

## Explore Environment 工作流

### 何时使用
当需要快速了解当前 Python 环境中可用的包、模块、环境变量或文件系统结构以进行校准相关工作时使用。

### 工作流
1. 确定探索范围：指定 `target` 参数为 `'packages'`（列出 Python 的 site-packages 目录中的包）、`'env_vars'`（获取环境变量）、`'all'`（返回全部信息）。
2. 调用工具函数 `explore_environment(target)`。
3. 根据返回结果进行分析。

### 参数
- `target` (string): 可选值 `'packages'`、`'env_vars'`、`'all'`，默认 `'all'`。

### 返回值
- 当 `target='all'` 时，返回一个包含以下键的字典：
  - `packages`: site-packages 目录下的包列表（基于 `os.listdir`）
  - `env_vars`: 当前操作系统环境变量（`os.environ` 的快照）
  - `cwd`: 当前工作目录
  - `sys_path`: Python 模块搜索路径（通过 `os` 相关函数获取）
- 当 `target='packages'` 时，仅返回 `packages` 列表。
- 当 `target='env_vars'` 时，仅返回 `env_vars` 字典。

### 注意事项
- 本技能基于 `os` 模块实现，部分功能受限：包列表仅扫描标准 site-packages 路径，无法检测通过其他方式安装的包。
- 环境变量是操作系统的当前快照，不会包含 Python 运行时内部变量。
- 调用结果可能根据操作系统和 Python 安装方式有所差异。

### 示例
```python
# 获取所有环境信息
info = explore_environment('all')
print(info['packages'][:5])   # 显示前5个包
print(info['env_vars']['PATH'])  # 显示 PATH 环境变量
```