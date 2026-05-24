# HydroAgent paper data index

**Updated 2026-05-24 09:35.** This file is the single entry point for the paper-writing agent. Each section below lists, per experiment, (a) what the experiment claims in its `README.md`, (b) what the actual data supports, (c) where to find tables, figures, raw records, and the per-experiment paper-text draft.

The drafts in `paper_text_exp{2,3,4}.md` are aligned to the *actual evidence*, not always to the original `README.md`. When the two disagree, the paper-text draft is the source of truth; README mismatches are flagged explicitly in the "Evidence vs README" rows below.

LLM backend: DeepSeek `deepseek-v4-flash` for every agent run. DiagScore rater (where used) is Qwen, configured in `configs/private.py` (`RATER_*`). Train period `2000-01-01` to `2009-12-31`, test `2010-01-01` to `2014-12-31` for every hydrological experiment.

---

## Experiment 1 — Token-for-time calibration (`experiment/exp1/`)

**Question.** Can HydroAgent preserve hydrological performance while replacing human active tuning time with LLM token cost, and does it choose menu hyperparameters more directionally than random search?

**Tasks.** 5 GR4J basins × 4 methods (M0 default-script / M1 human / M2 HydroAgent menu / M3 random menu). The 5 basins were selected on 2026-05-24 from a 60-basin screen of CAMELS-US (`results/paper/exp1_v2/screen/screen_trials.jsonl`) by filtering for GR4J test-NSE in [0.40, 0.65] (so range tuning has room to help) and taking one basin per USGS HUC region for geographic diversity:

| Basin id  | HUC | Default-range GR4J test NSE |
|-----------|----:|---:|
| 01543000 | 01 | 0.473 |
| 03574500 | 03 | 0.560 |
| 05495000 | 05 | 0.584 |
| 06885500 | 06 | 0.441 |
| 07197000 | 07 | 0.475 |

Basin list is in `experiment/exp1/common.py:BASINS`. XAJ is excluded because the screen produced only one XAJ medium-difficulty candidate.

**Current data status (in-progress, started 2026-05-24 09:34).**

| Method | Status | Records expected | Notes |
|---|---|---:|---|
| M0 default_script         | running in background, ETA ~5 min  | 5 | `results/paper/logs/exp1_M0.log` |
| M1 human_runner           | not started — operator-driven      | 5 | user will run manually |
| M2 hydroagent_menu        | running in background, ETA ~25 min | 25 (5 trials × 5 basins) | `results/paper/logs/exp1_M2.log` |
| M3 random_menu            | not started                        | (5 × n_repeats) | optional, run after M0/M2 finish |

Stale pre-screen records (single 12025000/xaj entry from earlier prototyping) were moved to `results/paper/exp1_v2_pre_screened/` before the new runs began.

**Evidence vs README.** Cannot evaluate yet — methods are still running. Conclusion-shaped questions (token-for-time, directional-vs-random) will only be answerable after at least M0 + M2 + M1 are populated.

**Paper materials.**
- README: `experiment/exp1/README.md`
- Paper-text draft: **not yet written** — pending M0/M1/M2 data.
- Tables: `experiment/exp1/tables/` (currently has stale headers from prior run; will be overwritten by `compile_results.py` once data is in).
- Figures: `experiment/exp1/figures/` (currently empty except a stale `figS1_token_breakdown.png`).
- Raw records: `results/paper/exp1_v2/<method>/trials.jsonl`.

---

## Experiment 2 — Where should the LLM enter calibration? (`experiment/exp2/`)

**Question.** For unfamiliar basins, does HydroAgent work because the LLM can directly guess hydrological parameters, or because it can guide the calibration workflow around a numerical optimizer?

**Tasks.** 3 basins × 2 models × 4 methods (A standard SCE-UA / B Zhu direct evaluation / C LLM proposal + local search / D HydroAgent feedback). Basins: 12025000, 11532500, 03439000. MAX_ITERS = 15 (raised from the original 5 on 2026-05-24 — see paper-text "Methodology note").

**Current data status.**

| Method | Records | Status |
|---|---:|---|
| A standard_sceua          | (running, ETA ~6 min) | started 2026-05-24 09:34, `results/paper/logs/exp2_A.log` |
| B zhu_direct_eval         | 90/90 ✓ | full 15-iter rerun complete |
| C llm_local_search        | 90/90 ✓ | full 15-iter rerun complete |
| D hydroagent_feedback     |  6/6  ✓ | full 15-iter rerun complete |

**Evidence vs README.** README hypothesizes "B fast but weaker, C improves B, D most stable but expensive". Evidence:
- **D is best-on-task on 6/6 tasks**, mean best NSE +0.460 vs B +0.243 and C +0.249. ✓ supports "D is the main HydroAgent contribution".
- **B ≈ C** (mean +0.243 vs +0.249). ✗ contradicts "C improves B" — C's local-search refinement adds 3.5× wall time but no NSE on the full panel.
- **D is *not* more expensive in tokens** (mean tokens-at-best 15 k vs B's 29 k). ✗ contradicts "D ... costs more tokens". D *is* more expensive in wall time (1 609 s vs B's 198 s at best).
- **D's early-stop is wasted on 5/6 tasks**: NSE plateaus below the fixed `NSE_TARGET = 0.80`, so `stop_reason = max_rounds` fires anyway. Honest dark-side finding; preserved in the draft.

**Paper materials.**
- README: `experiment/exp2/README.md` (note: original hypothesis sentences are partially contradicted by the data; paper-text is the canonical source).
- **Paper-text draft: `experiment/exp2/paper_text_exp2.md`** (final for B/C/D; will be re-aggregated when A finishes).
- Tables:
  - `experiment/exp2/tables/table_exp2_fair_compare.csv` — fair-budget per-task best NSE / iter@best / cap-binding / cum wall@best / cum tokens@best (key table for the paper).
  - `experiment/exp2/tables/table43_methods.csv`, `table44_core_results.csv`, `table45_hydroagent_process_evidence.csv`, `tableS_exp2_method_summary.csv` — auto-generated by `compile_results.py`.
- Figures: `experiment/exp2/figures/fig43_method_comparison.png`, `fig44_search_trajectories.png`.
- Raw records: `results/paper/exp2_v2/<method>/trials.jsonl`.
- Backup of pre-fair-budget (5-iter cap) data: `results/paper/exp2_v2_5iter_capped/`.

---

## Experiment 3 — Knowledge input ablation (`experiment/exp3/`)

**Question.** Is HydroAgent's execution performance mainly determined by tool availability or by extra knowledge input?

**Tasks.** 3 conditions (K0 plain LLM no tools / K1 tools only / K2 full knowledge) × 4 tasks (T1 standard calibration / T2 model comparison / T3 code analysis / T4 failure diagnosis) × 3 repeats = 36 records.

**Current data status.** 36/36 records ✓ at `results/paper/exp3_v2/trial_records.jsonl`. Tables and figures re-compiled 2026-05-24 09:14 after two judge bugs were patched (`detect_hallucination` now skips diagnosis-type tasks; `_detect_fabricated_tool` blacklists `*_code` tokens).

**Headline numbers** (`experiment/exp3/tables/table_exp3_core_results.csv`):

| Condition | Success | Tool route | Hallucination | Mean total tokens |
|---|---:|---:|---:|---:|
| K0 plain LLM        | 25.0% | 25.0% | 16.7% |  1 827 |
| K1 tools only       | **83.3%** | 91.7% | 0.0% |  56 420 |
| K2 full knowledge   | 75.0% | 75.0% | 0.0% | 134 524 |

**Evidence vs README.** README predicts "K1 approaches K2 on standard workflows with fewer tokens". Evidence is stronger and goes one step further:
- **K1 ≥ K2 overall** (83.3% vs 75.0%). Tool access closes the entire deficit on T1–T3 (all 3/3 for both K1 and K2); knowledge text adds no further help on these tasks.
- **T4 reversal — paper-grade finding**: on the diagnosis task where the prompt itself supplies the calibration result and `calibrate_model/evaluate_model/generate_code/run_code` are listed in `forbidden_tools`, the ordering inverts to K0 (3/3) > K1 (1/3) > **K2 (0/3)**, with all 3 K2 runs invoking the forbidden `generate_code`/`run_code` tools. K2's `forbidden_tool_rate` is 25.0% versus K1's 8.3% even though the two share the same tool set. The extra 78 k tokens of injected hydrological knowledge bias the agent toward execution when the requested behavior is purely interpretive.
- Risk: n = 3 repeats per cell. The T4 signal is consistent (0/3 vs 1/3 vs 3/3 spans the full range) but reviewers may ask for n ≥ 5.

**Paper materials.**
- README: `experiment/exp3/README.md`
- **Paper-text draft: `experiment/exp3/paper_text_exp3.md`** (contains the K1 ≥ K2 result and the T4 reversal narrative).
- Tables: `experiment/exp3/tables/table_exp3_core_results.csv`, `table_exp3_task_level.csv`, `table_exp3_condition_design.csv`, `tableS_exp3_trial_records.csv` (every individual run).
- Figures: `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`, `fig_exp3_task_heatmap.png`.
- Raw records: `results/paper/exp3_v2/trial_records.jsonl`, per-run dirs under `results/paper/exp3_v2/runs/`.

---

## Experiment 4 — Capability boundary and controlled failure (`experiment/exp4/`)

**Question.** When a task crosses the current tool boundary, does the agent fail in a predictable way, or does it invent tools, misuse available tools, or fabricate results?

**Tasks.** 3 tool conditions (B0 basic tools / B1 full toolchain / B2 basic + create_skill + run_code) × 4 boundary scenarios (S1 missing basin id / S2 missing calibration tools / S3 wrong-route risk / S4 out-of-scope MCMC) × 3 repeats = 36 records.

**Current data status.** 36/36 records ✓. The compile pipeline reads `results/paper/exp4_v2/trial_records.jsonl`; the canonical 36-record dataset (after judge fixes) was repointed here on 2026-05-24 from `results/paper/exp4_v2_baseline/`. Tables and figures re-compiled 2026-05-24 09:14.

**Headline numbers** (`experiment/exp4/tables/table_exp4_failure_modes.csv`, n = 12 per condition):

| Condition | Success | Controlled failure | Hallucination | Fabricated tool | create_skill called | wrong_tool_route |
|---|---:|---:|---:|---:|---:|---:|
| B0 basic tools           | 0.0%  | 25.0% | **75.0%** | 8.3% | 0.0% | 0.0%  |
| B1 full toolchain        | **58.3%** | 8.3%  | 8.3%  | 0.0% | 8.3% | 33.3% |
| B2 basic + create_skill  | 0.0%  | 33.3% | 41.7% | 0.0% | **0.0%** | 0.0% |

**Evidence vs README.** README predicts "B0 fails safely (controlled)" and "B2 tests dynamic recovery". Evidence inverts both — these are stronger paper findings, captured in the draft:
- **B0 hallucinates 75% of the time, not "fails safely".** Without execution tools, the agent narrates plausible NSE/KGE values 9× more often than B1 does. The dominant cause of hydrological hallucination in this setting is *the absence of an executable grounding step*, not the LLM's confidence.
- **B2 `create_skill_rate = 0/12` and `success_rate = 0%`.** Even with the meta-tool explicitly enabled (and the scenarios designed to need it), the agent never invokes it and never recovers. Giving an agent a meta-tool is not the same as giving it the policy to use that meta-tool — this is the next behavioural gap.
- **B1 `wrong_tool_route = 33.3%`** versus B0's 0%. Tool richness introduces a new failure mode (routing errors that did not exist under B0). B1's improvement is real but partial.

**Paper materials.**
- README: `experiment/exp4/README.md` (note: the "fails safely" framing should be revised; the draft already inverts to the evidence-based framing).
- **Paper-text draft: `experiment/exp4/paper_text_exp4.md`** (three-pattern narrative: hallucination collapse, dead meta-tool, routing-error trade).
- Tables: `experiment/exp4/tables/table_exp4_failure_modes.csv`, `table_exp4_recovery_cost.csv`, `table_exp4_tool_conditions.csv`, `tableS_exp4_trial_records.csv`.
- Figures: `experiment/exp4/figures/fig_exp4_failure_mode_stack.png`, `fig_exp4_recovery_cost.png`.
- Raw records: `results/paper/exp4_v2/trial_records.jsonl`, per-run dirs under `results/paper/exp4_v2/runs/`. Also backed up: `results/paper/exp4_v2_baseline/` (untouched original copy).

---

## Cross-experiment notes for the paper-writing agent

- **The system prompt is split into layered fragments.** `hydroagent/skills/system_core.md` (bare K0), `system_procedural.md` (procedural/K1), and `system_domain.md` (hydrological identity, parameter meanings, model list, algorithm defaults — K2). The original monolithic `hydroagent/skills/system.md` is preserved for interactive use. Exp3 K0/K1/K2 are built by selectively injecting these fragments. Three gating flags in `hydroagent/agent.py:_build_system_prompt` (`_system_prompt_override`, `_inject_policies`, `_inject_adapter_docs`) all default to current behaviour for normal runs.
- **Adapter / package boundary.** Hydromodel commands flow through `hydroagent/adapters/HydromodelAdapter` (priority 10, default). A patched `songliao/hydromodel` (commit 721dcb7) ships the param_range/sort_keys fix needed for XAJ ranges. The adapter writes parameter range YAML with `sort_keys=False` so hydromodel's internal denormalization reads the right parameters.
- **What is *not* in this run.** No XAJ in exp1 (single screen survivor — too narrow a panel). No A baseline in exp2 yet (in progress). No M1 human runs in exp1 (operator-driven, user will fill in). DiagScore rater (Qwen) was discussed but not invoked in the current exp3 numbers; it can be added as a secondary column without re-running anything.
- **Honest limitations to surface in discussion.** exp3/exp4 n = 3 per cell. exp2 has no A baseline yet. exp1 has 5 basins, all GR4J; the panel is geographically diverse (HUC 01/03/05/06/07) but model-monoculture. The DeepSeek model is held fixed across all experiments — there is no LLM-family ablation.

When a follow-up Agent picks this up, the **per-experiment `paper_text_*.md` drafts are the canonical narrative**, the **`tables/*.csv` and `figures/*.png` are the canonical artifacts**, and the **`results/paper/exp*_v2/trial_records.jsonl` (or `trials.jsonl`) are the canonical raw data** that every number traces back to.
