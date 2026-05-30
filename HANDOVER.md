# HydroAgent 交接说明

给新接手的开发者一份从零到能跑通的最小路径。整体流程:**装环境 → 填配置 → 起 CLI / 前端 → 跑入口示例脚本**。

---

## 1. 装环境

```bash
git clone <仓库地址> HydroAgent
cd HydroAgent
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

**装包期间会自动从 github 拉 hydromodel 的 dev 分支**(`OuyangWenyu/hydromodel @ dev`)。这一步很关键 — 项目用的是修了 `param_range` 反归一化 bug、并把 GR4J 加速了 290 倍的 dev 分支版本,不是 PyPI 上的 `hydromodel==0.3.2`。如果你后续看到率定时"参数范围调了也不影响 NSE",八成是装到了 PyPI 版本,要重装。

**验证 hydromodel 装对了**:

```bash
python -c "import hydromodel, os; print(os.path.dirname(hydromodel.__file__))"
python -c "import os, hydromodel; print(os.path.exists(os.path.join(os.path.dirname(hydromodel.__file__), 'models', 'SMS_3.py')))"
```

第二条命令应该输出 `True`(`SMS_3.py` 是 fork 独有,PyPI 版没有)。输出 `False` = 装错了。

要避开的坑:**不要用 `uv pip install`**(这台机器上会崩,MEMORY 里记着)。统一用 `.venv\Scripts\python.exe -m pip install`。

---

## 2. 填配置

```bash
copy configs\example_private.py configs\private.py
```

编辑 `configs/private.py`,填这几个字段:

| 字段 | 值 |
|---|---|
| `OPENAI_API_KEY` | 你的 LLM 密钥(DeepSeek / Qwen / OpenAI 兼容均可) |
| `OPENAI_BASE_URL` | 比如 `https://api.deepseek.com/v1` |
| `DATASET_DIR` | **CAMELS_US/ 的父目录**(注意不是 CAMELS_US 本身,是它上一级) |
| `RESULT_DIR` | 率定结果输出目录 |
| `PROJECT_DIR` | 留空就好,会自动推断 |

**CAMELS-US 数据(~14.6 GB)需要你自己准备**,放到 `DATASET_DIR/CAMELS_US/` 下面。这不在交接范围内 — 项目代码不打包数据。CAMELS 官方下载或 aquaFetch 都可以。

如果 `private.py` 字段不全,首次 `python -m hydroagent` 会进交互式 setup wizard 引导你填。

---

## 3. 起 CLI / 前端

```bash
# CLI 交互式(终端)
python -m hydroagent

# CLI 一次性查询
python -m hydroagent "率定 GR4J 模型,流域 12025000"

# 前端 Web UI(默认端口 7860,可加 --port 8080)
python -m hydroagent --server
```

前端是裸 HTML/JS(在 `hydroagent/interface/static/`),不需要 npm/webpack 编译。打开浏览器 `http://localhost:7860` 直接用。

要避开的坑:

- **Windows + VPN(尤其 Astrill)**:`cli.py` 已经加了 `WindowsSelectorEventLoopPolicy()` 守卫,不要删那段代码。
- **Windows GBK 编码**:跑 Python 脚本前 `set PYTHONUTF8=1`(cmd)或 `$env:PYTHONUTF8="1"`(PowerShell)。

---

## 4. 跑示范脚本

`experiment/exp1/` 下有三个示范脚本,对应论文里的三个 LLM 率定办法。共享一个本地依赖 `_common.py`(从 exp2 复制过来的工具函数,自包含)。

### 办法 B:HydroAgent(真实 agent loop)

```bash
PYTHONUTF8=1 python experiment/exp1/exp1_hydroagent.py
```

**唯一一个真实调 `HydroAgent.run(自然语言查询)` 的脚本**,~70 行。3 个示范流域(易/中/难),自然语言驱动 `validate_basin → calibrate_model → evaluate_model`。跑完产物在 `experiment/exp1/results/exp1_hydroagent_results.json`,字段 `tool_sequence` 应该含这三个工具。**了解 HydroAgent 怎么用的最快路径**。

### 办法 C:LLM-Direct(Zhu 直接猜参数)

```bash
PYTHONUTF8=1 python experiment/exp1/exp1_llm_direct.py
```

每代 LLM 直接吐一组参数,as-is 评估(无任何数值优化)。靠多代独立提议形成的多样性做隐式正则化。3 流域、min50/max200 迭代、按 train NSE 早停。产物:`experiment/exp1/results_llm_direct/trials.jsonl`。

### 办法 D:LLM-LocalSearch

```bash
PYTHONUTF8=1 python experiment/exp1/exp1_llm_localsearch.py
```

每代 LLM 提议 + scipy SLSQP 在 ±3% 窗口里精修(目标:train NSE)。比 C 多了"局部优化"那一步。3 流域、同样的 min/max/patience。产物:`experiment/exp1/results_llm_localsearch/trials.jsonl`。

### 注意

C 和 D **故意绕过 agent loop**(直接用 LLMClient + hydromodel skills),因为每代是紧密数值循环,走完整 agent loop 太重。只有 B (`exp1_hydroagent.py`) 是 ReAct 全循环的示范。三个脚本结构平行,逻辑都很短,适合并列对比阅读。

快速 smoke(各跑 1 流域、小迭代验证脚本通):
```bash
python experiment/exp1/exp1_llm_direct.py      --basins 08101000 --max-iters 6 --overwrite
python experiment/exp1/exp1_llm_localsearch.py --basins 12025000 --max-iters 3 --overwrite
```

---

## 5. 其他你可能想了解的

- **核心代码在 `hydroagent/`**:`agent.py` 是 Agentic Loop 核心,`llm.py` 是 LLM 客户端,`tools/` 是工具集(`calibrate.py` / `evaluate.py` / 等),`skills/` 是工作流指引,`interface/` 是 CLI + 前端入口。
- **`configs/` 是配置层**:`private.py` 是你填的密钥/路径,`definitions.py` 和 `model_config.py` 是不需要改的内置配置。
- **跨平台**:项目目标 Windows / Linux / macOS 都能跑,用 `pathlib.Path`,平台特定代码都有 `if sys.platform == "win32":` 守卫。
- **`.venv` 没 pip**:跑 `.venv\Scripts\python.exe -m ensurepip --upgrade` 即可。

---

## 验证交接成功(干净机器上跑一遍)

1. `git clone` 仓库到新目录
2. `python -m venv .venv && .venv\Scripts\python.exe -m pip install -e .`(看到 pip 自动 `git clone` `OuyangWenyu/hydromodel`,分支 dev)
3. `python -c "import os, hydromodel; print(os.path.exists(os.path.join(os.path.dirname(hydromodel.__file__), 'models', 'SMS_3.py')))"` 输出 `True`
4. 复制 `configs\example_private.py` 为 `private.py`,填上 LLM 密钥和真实 `DATASET_DIR`
5. `python -m hydroagent` 起 REPL,能聊
6. `python -m hydroagent --server`,浏览器 7860 端口能聊
7. `PYTHONUTF8=1 python experiment/exp1/exp1_hydroagent.py` 跑完看到 3 行 `OK`

**5–7 都过 = 交接成功**。第 3 步是关键校验 — 装错 hydromodel 时,5–7 表面上能过,但率定结果是错的(参数范围被忽略),只有这个版本检查能发现。
