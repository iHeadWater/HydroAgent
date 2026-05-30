
# HydroAgent: An LLM-Powered Agent for Hydrological Model Calibration

<div align="center">

**English** | **[简体中文](README.zh-CN.md)**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![HydroModel](https://img.shields.io/badge/hydromodel-0.3+-orange.svg)](https://github.com/OuyangWenyu/hydromodel)
[![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-green.svg)](LICENSE)

**One sentence in natural language drives the full calibration workflow — from data validation to model evaluation.**

</div>

---

## Demo

<div align="center">

https://github.com/user-attachments/assets/95648c65-c6e1-4832-ba69-783933747682

<sub><i>Demo video (~50 s)</i></sub>

</div>

---

## Overview

HydroAgent is a hydrological model calibration system built on a Large Language Model (LLM) agentic loop. The user describes a task in plain natural language; the agent autonomously decides which tools to call and in what order, and finally returns calibrated parameters, evaluation metrics, and an analysis report.

It supports conceptual hydrological models such as GR4J and XAJ over the CAMELS-US dataset, with two calibration modes: classical SCE-UA / GA optimization and LLM-guided calibration.

---

## Architecture

HydroAgent uses a **five-layer architecture** with clearly separated responsibilities:

```
Brain        agent.py            LLM reasoning & tool dispatch (ReAct loop)
Cerebellum   skills/*/skill.md   Skill workflow guides, injected into the system prompt
Spine        adapters/           PackageAdapter — bidirectional intent <-> package translation
Nerve        tools/*.py          Thin tool-routing functions
Muscle       hydromodel pkg      Numerical work: SCE-UA optimization, GR4J/XAJ simulation
```

Beyond the default ReAct loop (`agent.py`), the system also offers a **Plan-and-Execute** pipeline mode (`pipeline.py`), and the ability to spawn sub-agents (e.g. basin explorer, calibration worker) via `tools/spawn_agent.py` + `agents/*.md`.

**The system prompt is assembled dynamically from seven sections** on every `agent.run()`:

| Section | Source | Content |
|---------|--------|---------|
| §1 | `skills/system.md` | Identity and behavioral principles |
| §1.5 | `policy/*.md` | Behavioral constraints (when to stop, when to ask) |
| §1.7 | `skills/expert_hydrologist/skill.md` | Hydrologist cognitive framework (always injected) |
| §2 | `skill_registry.py` | Index of available skills and their read paths |
| §3 | `adapters/` | PackageAdapter capability docs |
| §4 | `knowledge/*.md` | Domain knowledge (parameter meanings, failure diagnosis) |
| §5 | `basin_profiles/` + `MEMORY.md` | Basin history and cross-session memory |

---

## Quick Start

### Install

```bash
git clone https://github.com/zhuanglaihong/HydroAgent.git
cd HydroAgent

python -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -e .

# Linux / macOS
.venv/bin/python -m pip install -e .
```

> **Note on `hydromodel`.** `pip install` will automatically pull the `dev`
> branch of [`OuyangWenyu/hydromodel`](https://github.com/OuyangWenyu/hydromodel)
> from GitHub, not the PyPI release. The `dev` branch contains a fix for a
> silent parameter-range bug and an ~290× GR4J speed-up that the experiments
> rely on. If you ever see "changing the parameter range has no effect on the
> NSE", you have somehow ended up on the PyPI version — reinstall.

### Configure

```bash
cp configs/example_private.py configs/private.py
```

Edit `configs/private.py` and fill in the required fields:

```python
OPENAI_API_KEY  = "sk-your-api-key"
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # or DeepSeek / OpenAI endpoint
DATASET_DIR     = r"/path/to/CAMELS_US_parent"   # parent directory of CAMELS_US/
RESULT_DIR      = r"/path/to/results"
```

Any OpenAI-compatible endpoint works (Qwen, DeepSeek, OpenAI, local Ollama).

### Run

HydroAgent offers two user-facing interactive modes and one developer-facing scripting mode:

**Terminal mode** (concise output, for daily use):

```bash
python -m hydroagent                                          # interactive REPL
python -m hydroagent "Calibrate GR4J for basin 12025000"      # single query, then exit
python -m hydroagent -w results/my_experiment                 # set the workspace
```

**Web mode** (browser UI, FastAPI + WebSocket):

```bash
python -m hydroagent --server           # default http://localhost:7860
python -m hydroagent --server --port 8080
```

**Developer scripting mode** (paper experiments / system tests):

Instantiate `HydroAgent` directly in a Python script, recording the full tool-call
sequence and intermediate results:

```python
from hydroagent.agent import HydroAgent
from hydroagent.interface.ui import ConsoleUI

agent = HydroAgent(workspace=Path("results/exp1"), ui=ConsoleUI(mode="dev"))
agent.run("Calibrate GR4J for basin 12025000 with SCE-UA")
```

This is also the path used by the paper experiments.

---

## Features

### Standard calibration

```
User> Calibrate GR4J for basin 12025000

Agent:
  [tool] validate_basin(["12025000"])        -> data complete
  [tool] calibrate_model("gr4j", "SCE_UA")   -> train NSE=0.783
  [tool] evaluate_model(period="test")       -> test  NSE=0.747

  GR4J calibration for basin 12025000 is complete.
  Best parameters: x1=1180.6 mm, x2=-3.94, x3=36.9 mm, x4=1.22 days
  Train NSE=0.783, test NSE=0.747; results saved to results/gr4j_12025000/
```

### LLM-guided calibration

Rather than proposing parameter values directly, the LLM analyzes whether parameters
hit their bounds, dynamically adjusts the search range, and lets SCE-UA iterate:

```
Round 1: default range -> SCE-UA -> NSE=0.65, x1=1998 (hits upper bound 2000)
         LLM diagnosis: "x1 keeps hitting the upper bound; basin storage capacity is
                         underestimated. Suggest extending to [1, 3000]."
Round 2: new range     -> SCE-UA -> NSE=0.74, no boundary-hitting parameters
         LLM diagnosis: "NSE acceptable and no parameter at its bound. Converged."
```

### Cross-session memory

After every successful calibration a basin profile is saved automatically
(`basin_profiles/<basin_id>.json`). On the next task for the same basin, the profile is
injected into the LLM context to support prior initialization and comparative analysis.

### Cognitive framework (Expert Hydrologist skill)

`skills/expert_hydrologist/skill.md` is an always-injected cognitive skill that encodes a
senior hydrologist's reasoning patterns: three mental models (parameters as hypotheses,
classify-before-search, three-layer error onion), five decision heuristics, and four
honesty boundaries.

### Dynamic extension (meta-tools)

When a required capability or data source is outside the current scope, the agent can
extend itself: `create_skill` generates a new skill package (skill.md + tool
implementation, usable immediately), and `create_adapter` generates a new PackageAdapter
skeleton and reloads it automatically.

---

## Project Structure

```
HydroAgent/
├── hydroagent/
│   ├── agent.py                  # Agentic loop core (ReAct)
│   ├── pipeline.py               # Plan-and-Execute pipeline mode (alternative path)
│   ├── llm.py                    # LLM client (function calling)
│   ├── memory.py                 # Cross-session memory (session log + MEMORY.md + basin profiles)
│   ├── skill_registry.py         # Skill scan, keyword match, cognitive-skill injection
│   ├── skill_states.py           # Skill lifecycle state management
│   ├── config.py                 # Configuration loading
│   ├── adapters/                 # PackageAdapter plugin layer (priority-based routing)
│   │   ├── base.py               # PackageAdapter base class
│   │   ├── hydromodel/           # hydromodel adapter (GR4J / XAJ / HBV ...)
│   │   ├── hydrodatasource/      # data-source adapter (CAMELS-US)
│   │   └── generic/              # fallback adapter (priority=0)
│   ├── agents/                   # sub-agent role definitions (spawned via spawn_agent)
│   ├── interface/
│   │   ├── cli.py                # CLI entry + interactive REPL
│   │   ├── ui.py                 # Rich terminal UI (user / dev modes)
│   │   └── server.py             # FastAPI web service
│   ├── tools/                    # tool set (auto-discovered & registered)
│   │   ├── validate.py           # validate_basin
│   │   ├── simulate.py           # run_simulation
│   │   ├── search_memory.py      # search_memory
│   │   ├── observe.py            # inspect_dir / read_file on-site observation
│   │   ├── ask_user.py           # proactive clarification
│   │   ├── task_tools.py         # batch task management
│   │   ├── spawn_agent.py        # spawn a sub-agent
│   │   ├── create_skill.py       # generate a new skill (meta-tool)
│   │   └── create_adapter.py     # generate a new adapter (meta-tool)
│   ├── skills/                   # skill packages (workflow guide + tool impl)
│   │   ├── calibration/          # standard calibration (SCE-UA / GA / scipy)
│   │   ├── llm_calibration/      # LLM-guided calibration
│   │   ├── evaluation/           # model evaluation
│   │   ├── batch_calibration/    # batch calibration
│   │   ├── model_comparison/     # multi-model comparison
│   │   ├── code_analysis/        # code generation & execution
│   │   ├── visualization/        # visualization
│   │   └── expert_hydrologist/   # hydrologist cognitive framework (always injected)
│   ├── policy/                   # behavioral-constraint layer (agent_behavior / calibration_policy ...)
│   ├── knowledge/                # structured domain knowledge
│   │   ├── model_parameters.md   # parameter physics & bounds
│   │   ├── failure_modes.md      # hydrological failure taxonomy & diagnosis
│   │   ├── calibration_guide.md  # calibration experience
│   │   └── datasets.md           # dataset notes
│   └── utils/
│       ├── context_utils.py      # token estimation & context truncation
│       ├── task_state.py         # batch-task state persistence
│       └── basin_validator.py    # basin data validation
└── configs/
    ├── example_private.py        # config template (committed)
    └── private.py                # actual config (gitignored)
```

---

## Dependencies

| Category | Component |
|----------|-----------|
| LLM | Any OpenAI-compatible endpoint (Qwen / DeepSeek / GPT-4o / local Ollama) |
| Hydrological modeling | [hydromodel](https://github.com/OuyangWenyu/hydromodel) (GR4J / XAJ / SACSMA) |
| Dataset | CAMELS-US (671 basins, downloaded via [aquaFetch](https://github.com/AtrCheema/aquaFetch)) |
| Terminal UI | [Rich](https://github.com/Textualize/rich) |
| Web service | FastAPI + WebSocket |
| Python | 3.11+ |

---

## Reference

> Zhu, S. et al. (2026). Large Language Models as Virtual Hydrologists. *Geophysical Research Letters*.

The key difference from Zhu et al.: HydroAgent has the LLM adjust the parameter **search
range** (rather than proposing parameter values directly) and pairs it with SCE-UA global
optimization, reducing the number of LLM calls by roughly 100x while maintaining
equivalent calibration accuracy.

---

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE), which
permits use, modification, and distribution for noncommercial purposes. For commercial use,
please contact the author.
