# 开发指南

> 版本：v2.6 | 日期：2026-03-25

---

## 项目结构（v2.6）

```
HydroAgent/
├── hydroagent/                     # 核心包
│   ├── agent.py                   # Agentic Loop（ReAct + CC-2/CC-4）
│   ├── llm.py                     # LLM 客户端（Function Calling + Prompt 降级）
│   ├── memory.py                  # 记忆系统（会话 / MEMORY.md / 流域档案）
│   ├── config.py                  # 配置加载 + hydromodel 配置构建
│   ├── skill_registry.py          # Skill 自动扫描与关键词匹配
│   ├── skill_states.py            # Skill 生命周期状态（draft/active/deprecated）
│   ├── __main__.py                # python -m hydroagent 入口
│   │
│   ├── adapters/                  # PackageAdapter 插件层（v2.5）
│   │   ├── __init__.py            # reload_adapters() + get_adapter() 路由
│   │   ├── base.py                # PackageAdapter 抽象接口
│   │   ├── hydromodel/
│   │   │   ├── adapter.py         # HydromodelAdapter（priority=10）
│   │   │   └── skills/hydromodel.md
│   │   ├── hydrodatasource/
│   │   │   ├── adapter.py         # HydrodatasourceAdapter（priority=15）
│   │   │   └── skills/hydrodatasource.md
│   │   └── generic/
│   │       └── adapter.py         # GenericAdapter（priority=0，兜底）
│   │
│   ├── agents/                    # 子代理定义（v2.6）
│   │   ├── __init__.py            # AgentRegistry
│   │   ├── calibrate_worker.md
│   │   └── basin_explorer.md
│   │
│   ├── skills/                    # Skill 包（工作流指引 + 工具实现）
│   │   ├── system.md              # 系统基础 prompt（每次都注入）
│   │   ├── calibration/
│   │   ├── evaluation/
│   │   ├── llm_calibration/
│   │   ├── batch_calibration/
│   │   ├── code_analysis/
│   │   ├── model_comparison/
│   │   ├── visualization/
│   │   ├── hydrodatasource/       # 自定义数据集工具
│   │   └── hydrodataset/          # 公开数据集工具
│   │
│   ├── tools/                     # 核心工具（priority=20）
│   │   ├── __init__.py            # 工具发现引擎（fn_to_schema + 优先级注册）
│   │   ├── validate.py            # validate_basin()
│   │   ├── simulate.py            # run_simulation()
│   │   ├── observe.py             # read_file() / inspect_dir()
│   │   ├── task_tools.py          # create_task_list / get_pending_tasks / update_task / add_task
│   │   ├── memory_tools.py        # search_memory / save_basin_profile / record_error_solution
│   │   ├── ask_user.py            # ask_user()
│   │   ├── create_skill.py        # 元工具：动态生成 Skill
│   │   ├── create_adapter.py      # 元工具：动态生成 PackageAdapter 骨架
│   │   ├── install_package.py     # 受控包安装
│   │   ├── register_package.py    # PyPI 自动适配器生成
│   │   ├── add_local_package.py   # 注册本地目录包
│   │   ├── add_local_tool.py      # 注册单文件工具
│   │   └── spawn_agent.py         # 委派子代理
│   │
│   ├── knowledge/                 # 领域知识库（按关键词注入）
│   │   ├── model_parameters.md
│   │   └── calibration_guide.md
│   │
│   ├── utils/                     # 辅助模块
│   │   ├── context_utils.py       # truncate_tool_result()（字段级 8K + 整体 16K）
│   │   ├── task_state.py          # TaskState（任务状态 JSON 持久化）
│   │   ├── plugin_registry.py     # PluginRegistry（读写 plugins.json）
│   │   ├── basin_validator.py     # 流域验证
│   │   ├── error_kb.py            # 错误知识库
│   │   └── setup_wizard.py        # 首次启动向导
│   │
│   └── interface/                 # 界面层
│       ├── cli.py                 # CLI 入口 + 交互 REPL
│       ├── ui.py                  # Rich 终端 UI
│       ├── server.py              # FastAPI + WebSocket
│       └── static/                # Web 前端（6 模块）
│
├── configs/
│   ├── model_config.py            # 用户自定义参数（算法、时段、目标函数）
│   ├── private.py                 # 私密配置（API Key、路径，已 gitignore）
│   └── example_private.py        # 模板
│
├── experiment/                    # 论文实验脚本
│   ├── exp1_standard_calibration.py
│   ├── exp2_llm_calibration.py
│   ├── exp4_capability_boundaries.py
│   ├── exp3_knowledge_ablation.py
│   ├── plot_paper_figures.py      # 生成论文图（待写）
│   └── README.md                  # 实验设计说明
│
└── docs/                          # 项目文档
```

---

## 添加新工具

### 方式 1：独立工具（tools/ 目录，priority=20）

适用于通用的、不属于特定工作流的工具：

```python
# hydroagent/tools/my_tool.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def my_tool(
    basin_id: str,
    param_a: str = "default",
    _workspace: Path | None = None,
    _cfg: dict | None = None,
) -> dict:
    """一行描述，LLM 据此理解工具用途。

    Args:
        basin_id: CAMELS 流域 ID（8位数字）
        param_a: 参数 A 的说明

    Returns:
        {"result": ..., "success": bool}
    """
    try:
        return {"result": "done", "success": True}
    except Exception as e:
        logger.error("my_tool failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}

# 可选：附加隐性约束知识（__agent_hint__）
my_tool.__agent_hint__ = (
    "Returns X not Y — call another_tool() separately to get Y."
)
```

### 方式 2：创建新 Skill（skills/ 目录，priority=10）

适用于有明确工作流场景的功能，工作流说明书 + 工具实现自包含：

```
hydroagent/skills/my_skill/
├── skill.md      # 工作流指引（关键词匹配时注入 system prompt）
└── my_tool.py    # 工具实现（自动发现注册）
```

`skill.md` 格式（v2.6，目标+判断框架，非步骤序列）：

```markdown
---
keywords: [my_keyword, 我的功能]
priority: 10
---

## My Skill 工作流

### 目标
当用户需要 XXX 时使用此 Skill，目标是得到 YYY。

### 判断框架
- 前置条件：先调用 validate_basin 确认数据可用
- my_tool 返回 A，不含 B -> 需要再调用 another_tool 取 B
- 若 my_tool 失败 -> 调用 inspect_dir 诊断目录状态

### 异常处理
| 情况 | 处理方式 |
|------|---------|
| 数据缺失 | ask_user 询问路径 |
| 结果异常 | read_file 查看原始输出，主动诊断 |
```

### 方式 3：添加 PackageAdapter（adapters/ 目录）

适用于接入新的水文计算包：

```python
# hydroagent/adapters/my_package/adapter.py
from hydroagent.adapters.base import PackageAdapter
from pathlib import Path

class Adapter(PackageAdapter):
    name = "my_package"
    priority = 12  # 高于 hydromodel(10) 则优先匹配

    def can_handle(self, data_source: str, model_name: str) -> bool:
        return model_name in ("my_model_v1", "my_model_v2")

    def supported_operations(self) -> list[str]:
        return ["calibrate", "simulate"]

    def calibrate(self, workspace: Path, **kw) -> dict:
        try:
            import my_package  # lazy import
            # ... 实现率定逻辑
            return {"success": True, "calibration_dir": str(workspace / "results")}
        except ImportError:
            return {"success": False, "error": "my_package not installed"}
```

同时在 `adapters/my_package/skills/skill.md` 中写包的调用约定（注入 system prompt）。

调用 `reload_adapters()` 后立即生效，或使用 `create_adapter` 元工具自动生成骨架。

### 方式 4：注册本地包（运行时，无需修改代码）

```
# 在本地包根目录放 hydroagent_adapter.py（与方式 3 同结构）
# 然后 Agent 调用：
add_local_package(path="D:/project/my_hydro_package", name="my_pkg")
```

---

## 工具编写规范

### 函数规范

1. 每个文件一个公开入口函数（辅助函数以 `_` 开头，不暴露给 LLM）
2. 必须有完整类型注解（工具发现依赖此生成 Schema）
3. 必须有 Google-style docstring（首行 + Args + Returns）
4. 返回 `dict`，包含 `success: bool` 键
5. 捕获异常返回 `{"error": "...", "success": False}`，不要 raise
6. 外部包在函数体内 lazy import（避免启动时 ImportError）

```python
# 正确：lazy import
def my_tool(...):
    try:
        import spotpy
    except ImportError:
        return {"error": "spotpy not installed. Run: install_package('spotpy')", "success": False}
```

7. 需要表达隐性约束时，附加 `__agent_hint__`（见工具自描述协议）

### 工具自描述协议（__agent_hint__）

三类适合写入 `__agent_hint__` 的内容：

```python
# 1. 必填约束（type hint 表达不了的隐性规则）
validate_basin.__agent_hint__ = "Call this before calibrate_model to avoid mid-run failures."

# 2. 输出->输入关系
calibrate_model.__agent_hint__ = (
    "Returns calibration_dir, NOT metrics. "
    "Pass calibration_dir to evaluate_model() to get NSE/KGE."
)

# 3. 最常见错误的一句话预防
generate_code.__agent_hint__ = (
    "After 3 code execution failures, use ask_user instead of regenerating."
)
```

### PostToolUse Hook

工具成功执行后需要触发副作用，使用 hook 注册而非修改 `_execute_tool`：

```python
# 在 agent 初始化后注册（通常在 Skill 加载时）
agent.register_post_hook("my_tool", lambda name, args, result: do_something(result))
```

内置 hook（在 `_register_builtin_post_hooks` 中注册）：
- `calibrate_model` / `llm_calibrate` -> 自动保存流域档案
- `create_task_list` / `update_task` / `add_task` -> 刷新 UI 任务进度
- `create_skill` -> 重扫工具注册表
- `create_adapter` -> 重载适配器

---

## 添加子代理

在 `hydroagent/agents/` 或 `<workspace>/.hydroagent/agents/` 下新建 `.md` 文件：

```markdown
---
name: my-agent
description: 执行 XXX 任务的专用代理（在 spawn_agent 的 name 参数中使用此名称）
tools: [tool_a, tool_b, validate_basin]
prompt_mode: minimal   # minimal（子代理默认）或 full
max_turns: 10
---
你是一个专注于 XXX 的代理。

工作流：
1. 调用 tool_a 完成第一步
2. 调用 tool_b 完成第二步
3. 返回结构化结论：key1, key2, key3

约束：
- 不要发起新的批量任务
- 最终回复只包含核心数字，不需要冗长解释
```

重启或工作区重加载后，`AgentRegistry` 自动扫描注册，主代理 system prompt 中会列出该代理供选择。

---

## 代码规范

### 类型注解

所有公开函数必须完整注解（Schema 生成依赖此）：

```python
# 正确
def my_func(name: str, count: int = 10, ids: list[str] | None = None) -> dict: ...

# 错误（Schema 类型推断失败，会被当作 string）
def my_func(name, count=10): ...
```

### 日志

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Normal operation")
logger.warning("Unexpected but recoverable")
logger.error("Error occurred", exc_info=True)  # 附带堆栈
```

### 跨平台路径

项目同时支持 Windows / Linux / macOS，始终使用 `pathlib.Path`：

```python
# 正确
path = Path(_workspace) / "results" / f"{basin_id}.json"

# 错误
path = _workspace + "\\results\\" + basin_id + ".json"
```

---

## 测试

### 验证工具发现

```python
from hydroagent.tools import reload_tools, get_tool_schemas

tools = reload_tools()
print("Registered:", sorted(tools.keys()))

for s in get_tool_schemas():
    print(f"  {s['function']['name']}")
```

### 单工具测试

```python
from hydroagent.tools.validate import validate_basin
result = validate_basin(basin_id="12025000")
print(result)
```

### 完整流程测试

```bash
python -m hydroagent "验证流域12025000是否存在"
```

---

## 调试

### 查看工具注册状态

```bash
python -c "from hydroagent.tools import reload_tools; t = reload_tools(); print(sorted(t.keys()))"
```

### 查看当前适配器

```bash
python -c "from hydroagent.adapters import get_loaded_adapters; [print(a.name, a.priority) for a in get_loaded_adapters()]"
```

### 常见问题

**工具未被发现**：
- 函数名或文件名不能以 `_` 开头
- 检查 import 是否报错：`python -c "from hydroagent.skills.xxx.yyy import zzz"`

**Schema 参数类型错误**：
- `list[str]` -> `"array"`，`dict` -> `"object"`，`str | None` -> `"string"`
- 未注解的参数会被推断为 `"string"`

**Skill 未匹配**：
- 检查 `skill.md` 头部 `keywords` 字段是否包含查询中出现的关键词
- 关键词匹配区分大小写，建议用小写

**适配器未加载**：
- 检查 `adapters/<name>/adapter.py` 中是否有 `class Adapter(PackageAdapter)` 定义
- 确认 `can_handle()` 在预期输入下返回 True
- 手动 reload：`from hydroagent.adapters import reload_adapters; reload_adapters()`

**uv 崩溃（此机器专属）**：
- 此机器上 uv 会 EXCEPTION_ACCESS_VIOLATION，不要用 `uv pip install`
- 统一用：`.venv/Scripts/python.exe -m pip install <包名>`
