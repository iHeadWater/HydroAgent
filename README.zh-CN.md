
# HydroAgent：LLM 驱动的水文模型率定智能体

<div align="center">

**[English](README.md)** | **简体中文**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![HydroModel](https://img.shields.io/badge/hydromodel-0.3+-orange.svg)](https://github.com/OuyangWenyu/hydromodel)
[![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-green.svg)](LICENSE)

**一句自然语言，完成从数据验证到模型评估的完整水文率定流程**

</div>

---

## 演示视频

<div align="center">

https://github.com/user-attachments/assets/95648c65-c6e1-4832-ba69-783933747682

<sub><i>演示视频（约 50 秒）</i></sub>

</div>

---

## 项目简介

HydroAgent 是一个基于大语言模型（LLM）Agentic Loop 的水文模型率定系统。用户只需用自然语言描述任务，Agent 自主决定调用哪些工具、以何种顺序执行，最终输出率定参数、评估指标和分析报告。

系统支持 GR4J、XAJ 等概念性水文模型，使用 CAMELS-US 数据集，率定算法包括传统 SCE-UA/GA 和 LLM 智能率定两种模式。

---

## 系统架构

HydroAgent 采用**五层架构**，每层职责明确：

```
大脑 (Brain)         agent.py            LLM 推理与工具调度（ReAct Loop）
小脑 (Cerebellum)    skills/*/skill.md   Skill 工作流说明书，注入 system prompt
脊椎 (Spine)         adapters/           PackageAdapter，双向翻译任务意图与包调用
神经末梢 (Nerve)     tools/*.py          工具路由函数，薄包装
肌肉 (Muscle)        hydromodel pkg      数值计算：SCE-UA 优化、GR4J/XAJ 模拟
```

除默认的 ReAct Loop（`agent.py`）外，系统还提供 `pipeline.py` 的 **Plan-and-Execute** 流水线模式，以及通过 `tools/spawn_agent.py` + `agents/*.md` 派生子 Agent（如流域探查、率定工人）的能力。

**System Prompt 七段式动态拼装**（每次 `agent.run()` 时按需组装）：

| 段 | 来源 | 内容 |
|----|------|------|
| §1 | `skills/system.md` | 身份与行为原则 |
| §1.5 | `policy/*.md` | 行为约束（何时停止、何时询问）|
| §1.7 | `skills/expert_hydrologist/skill.md` | 水文学家认知框架（始终注入）|
| §2 | `skill_registry.py` | 可用 Skill 索引与读取路径 |
| §3 | `adapters/` | PackageAdapter 能力文档 |
| §4 | `knowledge/*.md` | 领域知识（参数含义、故障诊断）|
| §5 | `basin_profiles/` + `MEMORY.md` | 流域历史档案与跨会话记忆 |

---

## 快速开始

### 安装

```bash
git clone https://github.com/zhuanglaihong/HydroAgent.git
cd HydroAgent

python -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

### 配置

```bash
cp configs/example_private.py configs/private.py
```

编辑 `configs/private.py`，填写以下必填项：

```python
OPENAI_API_KEY  = "sk-your-api-key"
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 或 DeepSeek / OpenAI 端点
DATASET_DIR     = r"/path/to/CAMELS_US_parent"   # CAMELS_US/ 的父目录
RESULT_DIR      = r"/path/to/results"
```

支持任何 OpenAI 兼容接口（Qwen、DeepSeek、OpenAI、本地 Ollama）。

### 运行

HydroAgent 有两种面向用户的交互模式，以及一种面向开发者的脚本模式：

**终端交互模式**（精简输出，适合日常使用）：

```bash
python -m hydroagent                                          # 进入交互 REPL
python -m hydroagent "率定 GR4J 模型，流域 12025000"          # 单次查询后退出
python -m hydroagent -w results/my_experiment                 # 指定工作目录
```

**Web 前端模式**（浏览器界面，FastAPI + WebSocket）：

```bash
python -m hydroagent --server           # 默认 http://localhost:7860
python -m hydroagent --server --port 8080
```

**开发者脚本模式**（论文实验 / 系统测试）：

直接在 Python 脚本中实例化 `HydroAgent`，完整记录工具调用序列和中间结果：

```python
from hydroagent.agent import HydroAgent
from hydroagent.interface.ui import ConsoleUI

agent = HydroAgent(workspace=Path("results/exp1"), ui=ConsoleUI(mode="dev"))
agent.run("率定 GR4J 模型，流域 12025000，SCE-UA 算法")
```

论文实验脚本均采用此模式，详见 `experiment/` 目录。

---

## 主要功能

### 标准率定

```
用户> 率定 GR4J 模型，流域 12025000

Agent:
  [工具] validate_basin(["12025000"])        -> 数据完整
  [工具] calibrate_model("gr4j", "SCE_UA")  -> train NSE=0.783
  [工具] evaluate_model(period="test")      -> test  NSE=0.747

  流域 12025000 的 GR4J 率定完成。
  最优参数：x1=1180.6 mm, x2=-3.94, x3=36.9 mm, x4=1.22 days
  训练期 NSE=0.783，测试期 NSE=0.747，结果已保存至 results/gr4j_12025000/
```

### LLM 智能率定

LLM 不直接提议参数值，而是分析参数是否触边界，动态调整搜索范围，配合 SCE-UA 迭代优化：

```
Round 1: 默认范围 -> SCE-UA -> NSE=0.65, x1=1998（触上界 2000）
         LLM 诊断："x1 持续触上界，说明流域蓄水容量被低估，建议扩展至 [1, 3000]"
Round 2: 新范围  -> SCE-UA -> NSE=0.74，无触界参数
         LLM 诊断："NSE 达标且参数未触界，收敛，结束"
```

### 跨会话记忆

每次率定成功后自动保存流域档案（`basin_profiles/<basin_id>.json`）。下次对同一流域发起任务时，历史档案注入 LLM 上下文，支持先验初始化和对比分析。

### 认知框架（Expert Hydrologist Skill）

`skills/expert_hydrologist/skill.md` 是一个始终注入的认知型 Skill，编码了资深水文学家的思维模式：三种心智模型（参数即假设、先分类再搜索、误差三层剥洋葱）、五条决策启发式和四个诚实边界。

### 动态扩展（元工具）

当所需功能或数据源不在现有能力范围内时，Agent 可调用元工具自行扩展：`create_skill` 生成新的 Skill 包（skill.md + 工具实现，写入后立即可用），`create_adapter` 生成新的 PackageAdapter 骨架并自动重载。

---

## 项目结构

```
HydroAgent/
├── hydroagent/
│   ├── agent.py                  # Agentic Loop 核心（ReAct 模式）
│   ├── pipeline.py               # Plan-and-Execute 流水线模式（备选执行路径）
│   ├── llm.py                    # LLM 客户端（Function Calling）
│   ├── memory.py                 # 跨会话记忆（会话日志 + MEMORY.md + 流域档案）
│   ├── skill_registry.py         # Skill 自动扫描、关键词匹配、认知 Skill 注入
│   ├── skill_states.py           # Skill 生命周期状态管理
│   ├── config.py                 # 配置加载
│   ├── adapters/                 # PackageAdapter 插件层（按 priority 路由）
│   │   ├── base.py               # PackageAdapter 基类
│   │   ├── hydromodel/           # hydromodel 适配器（GR4J / XAJ / HBV 等）
│   │   ├── hydrodatasource/      # 数据源适配器（CAMELS-US）
│   │   └── generic/              # 兜底适配器（priority=0）
│   ├── agents/                   # 子 Agent 角色定义（spawn_agent 派生）
│   ├── interface/
│   │   ├── cli.py                # CLI 入口 + 交互 REPL
│   │   ├── ui.py                 # Rich 终端 UI（user / dev 模式）
│   │   └── server.py             # FastAPI Web 服务
│   ├── tools/                    # 工具集（自动发现注册）
│   │   ├── validate.py           # validate_basin
│   │   ├── simulate.py           # run_simulation
│   │   ├── search_memory.py      # search_memory
│   │   ├── observe.py            # inspect_dir / read_file 现场观测
│   │   ├── ask_user.py           # 主动澄清
│   │   ├── task_tools.py         # 批量任务管理
│   │   ├── spawn_agent.py        # 派生子 Agent
│   │   ├── create_skill.py       # 动态生成新 Skill（元工具）
│   │   └── create_adapter.py     # 动态生成新 Adapter（元工具）
│   ├── skills/                   # Skill 包（工作流说明书 + 工具实现）
│   │   ├── calibration/          # 标准率定（SCE-UA / GA / scipy）
│   │   ├── llm_calibration/      # LLM 智能率定
│   │   ├── evaluation/           # 模型评估
│   │   ├── batch_calibration/    # 批量率定
│   │   ├── model_comparison/     # 多模型对比
│   │   ├── code_analysis/        # 代码生成与执行
│   │   ├── visualization/        # 可视化
│   │   └── expert_hydrologist/   # 水文学家认知框架（始终注入）
│   ├── policy/                   # 行为约束层（agent_behavior / calibration_policy 等）
│   ├── knowledge/                # 结构化领域知识
│   │   ├── model_parameters.md   # 参数物理含义与边界
│   │   ├── failure_modes.md      # 水文故障分类与诊断
│   │   ├── calibration_guide.md  # 率定经验
│   │   └── datasets.md           # 数据集说明
│   └── utils/
│       ├── context_utils.py      # Token 估算与上下文截断
│       ├── task_state.py         # 批量任务状态持久化
│       └── basin_validator.py    # 流域数据验证
├── configs/
│   ├── example_private.py        # 配置模板（提交到仓库）
│   └── private.py                # 实际配置（gitignore）
├── experiment/                   # 论文实验脚本
│   ├── exp1_standard_calibration.py   # Agent 驱动标准率定基线
│   ├── exp1_scripted_baseline.py      # 脚本基线（无 Agent 层，数值对照）
│   ├── exp2_llm_calibration.py        # LLM 率定三路对比
│   ├── exp3_knowledge_ablation.py     # 结构化知识层消融
│   └── exp4_capability_boundaries.py  # Agent 能力边界
├── results/paper/                # 实验结果
└── plot/                         # 论文配图脚本与输出
```

---

## 复现论文实验

所有实验结果保存在 `results/paper/`，配图脚本在 `plot/`。

```bash
# 运行实验（各约 2-4 小时）
python experiment/exp1_standard_calibration.py   # Exp1：Agent 驱动标准率定基线
python experiment/exp1_scripted_baseline.py      # Exp1：脚本基线（数值对照）
python experiment/exp2_llm_calibration.py        # Exp2：LLM 率定三路对比
python experiment/exp3_knowledge_ablation.py     # §4.3：结构化知识层消融
python experiment/exp4_capability_boundaries.py  # §4.4：Agent 能力边界

# 生成论文配图
python plot/exp1_figures.py
python plot/exp2_figures.py
python plot/exp3_figures.py
python plot/exp4_figures.py
```

详见 `experiment/README.md` 和 `plot/README.md`。

---

## 技术依赖

| 类别 | 组件 |
|------|------|
| LLM | 任意 OpenAI 兼容接口（Qwen / DeepSeek / GPT-4o / 本地 Ollama）|
| 水文建模 | [hydromodel](https://github.com/OuyangWenyu/hydromodel)（GR4J / XAJ / SACSMA）|
| 数据集 | CAMELS-US（671 流域，[aquaFetch](https://github.com/AtrCheema/aquaFetch) 下载）|
| 终端 UI | [Rich](https://github.com/Textualize/rich) |
| Web 服务 | FastAPI + WebSocket |
| Python | 3.11+ |

---

## 参考文献

> Zhu, S. et al. (2026). Large Language Models as Virtual Hydrologists. *Geophysical Research Letters*.

HydroAgent 与 Zhu et al. 方法的核心区别：LLM 调整参数**搜索范围**（而非直接提议参数值），配合 SCE-UA 全局优化，LLM 调用次数减少约 100 倍，同时保持等价的率定精度。

---

## 许可证

本项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE) 授权，允许非商业用途的使用、修改与分发。商业用途请联系作者。
