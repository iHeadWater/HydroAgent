# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

> HydroAgent — LLM-driven agentic loop for hydrological model calibration | Updated 2026-06-12

## Goal

One-sentence natural language drives the full calibration workflow (data validation → calibration → evaluation). Supports multi-model × multi-basin batch tasks with cross-session memory.

## Commands

```bash
# Install (editable, with hydromodel from OuyangWenyu/hydromodel@dev)
pip install -e .

# Run
python -m hydroagent                                          # Interactive REPL
python -m hydroagent "Calibrate GR4J for basin 12025000"      # Single query
python -m hydroagent --server                                 # Web UI (FastAPI, port 7860)
python -m hydroagent -w results/my_experiment                 # Custom workspace

# Experiments (from repo root)
python experiment/exp1/exp1_hydroagent.py       # Method D: HydroAgent feedback calibration
python experiment/exp1/exp1_llm_direct.py       # Method B: LLM direct parameter proposal
python experiment/exp1/exp1_llm_localsearch.py  # Method C: LLM proposal + local search

# Tests
pytest
```

## Five-Layer Architecture

```
Brain        agent.py            LLM reasoning & tool dispatch (ReAct loop)
Cerebellum   skills/*/skill.md   Skill workflow guides, injected into system prompt
Spine        adapters/           PackageAdapter — bidirectional intent<->package translation
Nerve        tools/*.py          Thin tool-routing functions (auto-discovered)
Muscle       hydromodel pkg      Numerical work: SCE-UA optimization, GR4J/XAJ simulation
```

Key insight: **tools are thin shells.** Real logic lives in `skills/*/` (each skill = `skill.md` workflow guide + tool implementation). `tools/*.py` are auto-discovered routing wrappers. `adapters/` translate between natural-language intent and package-specific API surfaces (hydromodel, hydrodatasource, generic fallback).

## Secondary execution paths

- **`pipeline.py`** — Plan-and-Execute mode. Single LLM call generates a JSON execution plan, then runs locally with 0 further LLM involvement (unless a tool fails). ~10K tokens vs ~80K for ReAct.
- **`tools/spawn_agent.py`** — Spawns an isolated sub-agent with restricted tool allowlist and independent context. Role definitions in `agents/*.md`. Depth-limited to prevent recursion.

## Dynamic system prompt assembly

Every `agent.run()` assembles the system prompt from 7 sections:

| § | Source | Content |
|---|--------|---------|
| §1 | `skills/system.md` | Identity and behavioral principles |
| §1.5 | `policy/*.md` | Behavioral constraints (when to stop, when to ask) |
| §1.7 | `skills/expert_hydrologist/skill.md` | Hydrologist cognitive framework (always injected) |
| §2 | `skill_registry.py` | Index of available skills |
| §3 | `adapters/` | PackageAdapter capability docs |
| §4 | `knowledge/*.md` | Domain knowledge (parameter meanings, failure modes, calibration guide) |
| §5 | `basin_profiles/` + `MEMORY.md` | Basin history and cross-session memory |

## Key files to know

- `hydroagent/agent.py` — HydroAgent class: ReAct loop, tool dispatch, system prompt assembly
- `hydroagent/llm.py` — LLM client wrapper (function-calling with OpenAI-compatible API)
- `hydroagent/adapters/base.py` — PackageAdapter base class (priority-based routing, capability listing)
- `hydroagent/skills/calibration/calibrate.py` — `calibrate_model()` calls hydromodel SCE-UA/GA/scipy
- `hydroagent/skills/llm_calibration/llm_calibrate.py` — LLM-guided calibration (parameter range iteration)
- `hydroagent/memory.py` — Basin profiles + cross-session MEMORY.md
- `experiment/exp1/_common.py` — Shared experiment utilities (Task, run_calibration, evaluate_parameter_set)

## Configuration

Copy `configs/example_private.py` → `configs/private.py`. Required: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `DATASET_DIR`, `RESULT_DIR`. Any OpenAI-compatible endpoint works (Qwen, DeepSeek, OpenAI, Ollama).

## Critical dependency

`hydromodel` must come from `OuyangWenyu/hydromodel@dev` (the `dev` branch), NOT PyPI. The `dev` branch has a parameter-range denormalization bug fix and a ~290× GR4J speed-up via JIT. PyPI version silently produces wrong calibration results.
