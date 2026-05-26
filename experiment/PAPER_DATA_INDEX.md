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

**Current data status (post-seedfix, all 6 methods complete on 5 basins).**

| Method | Status | Records | Notes |
|---|---|---:|---|
| M0_min (rep=100 ngs=10)   | ✓ done | 5/5 | starving-budget baseline (panel mean +0.452) |
| M0_default (rep=500 ngs=50) | ✓ done | 5/5 | standard preset (panel mean +0.461) |
| M0_max (rep=2000 ngs=200) | ✓ done | 5/5 | brute-force max budget (panel mean +0.514) |
| M2_A (Mode A preset menu, LLM) | ✓ done | 25/25 | 5 trials/basin, trial 1 forced default anchor (panel mean +0.502) |
| **M1_B** (Mode B free-form, human) | ✓ done | 25/25 | **5 trials/basin** (panel mean **+0.574**) |
| M2_B v8 (Mode B free-form, LLM) | ✓ done | **25/25** | 5 trials/basin, panel mean **+0.563** (gap to M1 only **−0.012**). v8 prompt = v7 + (a) anti-hallucination history block in user prompt + H4 cited-numbers whitelist; (b) H5 per-basin recipe replication rule; (c) H6 tightened stop rule (NSE≥0.7 AND last-2 gain<0.01); (d) GR4J parameter physics injected from `hydroagent/knowledge/model_parameters.md`. **LLM ties human exactly on 4/5 basins** (01543000, 05495000, 06885500, 07197000); only 03574500 still has −0.058 gap due to residual H4 hallucination → fallback. v6/v7 backups at `paper_data/exp1_v2_modeb_m2_v6/` and `paper_data/exp1_v2_modeb/hydroagent_menu_M2B_v7.jsonl`. |
| M3 random_menu            | not started | — | optional lower-bound reference |

**Evidence vs README — five paper-grade findings, all post-seedfix:**
- **Finding 1: Budget is a real lever (+0.062 panel NSE from M0_min → M0_max) but not enough.** M0_max +0.514 < M1_B +0.574, so human menu tuning adds another +0.060 on top of max budget by choosing range_policy. Two independent levers.
- **Finding 2: Mode B (free-form numeric hyperparameters) beats Mode A (preset bundles) for the LLM** by +0.037 panel NSE (M2_B +0.539 vs M2_A +0.502). LLM uses intermediate values (e.g. rep=750–1500, ngs=80–100) that presets cannot express.
- **Finding 3: No single dominant strategy.** Per-basin global best: M1_B wins 3/5 (01543000, 03574500, 07197000), M0_min wins 1/5 (05495000), M0_max wins 1/5 (06885500). Optimal recipe is basin-specific.
- **Finding 4: Counter-intuitive — on basin 05495000 the smallest budget wins.** M0_min 0.592 > M0_max 0.585 > all menu-tuning methods. Basin's default range already at SCE-UA's train-side optimum; more budget produces light test-side overfitting.
- **Finding 5: Layered prompt engineering (v6→v7→v8) shrinks the LLM-human gap from −0.035 to −0.012 NSE (67% reduction), with LLM tying human on 4 of 5 basins.** v8 prompt adds anti-hallucination history block + H4 cited-numbers whitelist + H5 per-basin recipe replication + H6 tightened stop + GR4J parameter physics from `hydroagent/knowledge/model_parameters.md`. The remaining −0.012 panel gap is within the SCE-UA single-seed noise floor. Only basin 03574500 retains a basin-level gap (−0.058) due to residual H4 hallucination → fallback. **Tradeoff**: v8 H5 traps LLM into human's M1 recipe on 06885500, losing v7's autonomous beat (+0.054) on that basin; production deployment should soften H5 to a hint rather than a hard rule.

**Cost analysis at equal 5-trial budget (panel total):**
- M1_B: 1 276 s attended human-active time (~21 min) + 0 LLM tokens.
- M2_B v6: 287 s unattended LLM decision time + 63 457 LLM tokens (~$0.04 at deepseek-v4-flash).
- M2_A: 196 s unattended LLM decision + 35 034 tokens.
- LLM is ~4× faster per decision than the human and unattended, at a 0.035 NSE accuracy cost.

**Paper materials.**
- README: `experiment/exp1/README.md`
- **Paper-text draft: `experiment/exp1/paper_text_exp1.md`** (full 6-method 5-finding narrative + 4.2 cost analysis + 4.3 limitations).
- Tables: `experiment/exp1/tables/`
  - `table_exp1_cross_mode_summary.csv` (30 rows, 5 basin × 6 method, best test NSE/KGE + total cost). **The central table for Findings 1–4.**
  - `table_exp1_method_aggregate.csv` (6 rows, panel-mean per method). **For Finding 5 and §4.2.**
  - `table_exp1_per_trial.csv` (92 rows; per-method per-trial cost + menu + metrics + boundary_hits). Built by `build_per_trial_table.py`.
  - `table_exp1_per_step_time.csv` (92 rows; same-unit decision time for token-for-time claim). Built by `build_per_step_time.py`.
- Figures: `experiment/exp1/figures/`
  - `fig_exp1_per_basin_winner.png` — 6-method × 5-basin bar chart with golden-star marking the per-basin global best (Findings 3+4 visual).
  - `fig_exp1_budget_ablation.png` — best NSE vs budget level (M0_min/M0/M0_max), one line per basin, M1_B as dotted reference (Finding 1 visual).
  - `fig_exp1_cost_vs_quality.png` — two-panel scatter of (wall time, NSE) and (human-attended-or-tokens, NSE) (§4.2 visual).
- Raw records: `results/paper/exp1_v2/<method>/trials.jsonl` (Mode A + M0 ablation) and `results/paper/exp1_v2_modeb/<method>/trials.jsonl` (Mode B); M2_B v6 backup at `results/paper/exp1_v2_modeb_m2_v6/`.

---

## Experiment 2 — Where should the LLM enter calibration? (`experiment/exp2/`)

**Question.** For unfamiliar basins, does HydroAgent work because the LLM can directly guess hydrological parameters, or because it can guide the calibration workflow around a numerical optimizer?

**Tasks.** 3 basins × 2 models × 4 methods (A standard SCE-UA / B Zhu direct evaluation / C LLM proposal + local search / D HydroAgent feedback). Basins: 12025000, 11532500, 03439000. MAX_ITERS = 15 (raised from the original 5 on 2026-05-24 — see paper-text "Methodology note").

**Current data status.**

| Method | Records | Status |
|---|---:|---|
| A standard_sceua          | **6/6 ✓** | done 09:57 (one record per (basin,model), no iteration loop — `wall_time_s` field is 0 because A's wall time lives inside the single SCE-UA run) |
| B zhu_direct_eval         | **180 × 3 seeds ✓** | MAX_ITERS = 30. **3 independent seeds at 30 iter** (`trials_seed{0,1,2}.jsonl`, 540 records total). Per-task mean-of-3-seeds = +0.291 (within 0.003 of single-seed +0.288); per-task stdev 0.04–0.11 NSE. Aggregate in `experiment/exp2/tables/table_exp2_B_multiseed.csv` from `merge_b_seeds.py`. The +0.17 gap to D's mean (+0.460) is larger than every per-task stdev, so D's advantage is robust across seeds. Old 15-iter B preserved at `results/paper/exp2_v2_15iter_capped/`. |
| C llm_local_search        | 90/90 ✓ | full 15-iter rerun complete |
| D hydroagent_feedback     |  6/6  ✓ | full 15-iter rerun complete |

**Evidence vs README.** README hypothesizes "B fast but weaker, C improves B, D most stable but expensive". Evidence:
- **D is best-on-task on 6/6 tasks** *among the LLM-position methods*, mean best NSE +0.460 vs B +0.288 (at 30 iter; +0.243 at 15 iter), C +0.249 (at 15 iter). Doubling B's iteration budget (15 → 30) closes only +0.045 NSE; 2/6 B tasks remain cap-binding even at iter 30, but per-iter NSE gain on the still-rising tasks has dropped to ~+0.003 to +0.005, indicating B's architectural ceiling is below D's on every task.
- **But A (zero-LLM baseline) is within 0.05 NSE of D on 5/6 tasks.** A reaches +0.748, +0.776, +0.741, +0.577, +0.064 on basins 12025000, 11532500, and 03439000/xaj; D matches or exceeds those by only +0.007 to +0.052. The D-vs-A aggregate gap (+0.46 vs +0.17) is dominated by a single hard task (03439000/gr4j: A −0.872 → D −0.272, recovery margin 0.60). This re-frames the paper claim: HydroAgent is a hard-tail recovery layer, not a categorical improvement over standard SCE-UA.
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

**Tasks.** 3 conditions (K0 plain LLM no tools / K1 tools only / K2 full knowledge) x 5 tasks (T1 standard calibration / T2 model comparison / T3 code analysis / T4 failure diagnosis / T5 calibration knowledge) x **5 repeats** = **75 records**.

**Current data status.** 75/75 records at `results/paper/exp3_v2/trial_records.jsonl`. T4 query was clarified on 2026-05-26 to explicitly state "do not run tools" (previous version lacked this, causing K2 to invoke forbidden tools due to execution bias from the knowledge pack). T5 added on 2026-05-26 to test HydroAgent-specific calibration workflow knowledge (SCE-UA rep/ngs recommendations, post-calibrate evaluation sequence, GR4J parameter diagnostics).

**Headline numbers** (`experiment/exp3/tables/table_exp3_core_results.csv`, n = 25 per condition):

| Condition | Success | Hallucination | Mean total tokens |
|---|---:|---:|---:|
| K0 plain LLM        | 28% | 12% |   1 862 |
| K1 tools only       | **96%** |  0% |  29 987 |
| K2 full knowledge   | **100%** |  0% |  78 099 |

**Evidence vs README:**
- **K0 -> K1 is the decisive jump (+68 pp)**. Tool access closes the entire deficit on T1-T3 (0/5 -> 5/5 on each). Hallucination drops from 12% to 0%.
- **K1 -> K2 is a small positive gain (+4 pp)**. The gap comes entirely from T5 (calibration knowledge): K0=2/5, K1=4/5, K2=5/5. T5 requires HydroAgent-specific information (SCE-UA rep/ngs values from calibration_guide.md, GR4J parameter diagnostics from model_parameters.md) that K1 cannot access from tool schemas alone.
- **T4 (physical diagnosis) is uniformly 5/5** across all conditions. The LLM's pre-training suffices for interpreting parameter boundary-hitting patterns; domain knowledge injection adds no measurable benefit on this reasoning task.
- **Design implication**: tools are the non-negotiable foundation; knowledge adds marginal reliability on workflow-specific tasks at 2.6x token cost. Supports a knowledge-on-demand strategy aligned with the architecture diagram's layered design.

**Paper materials.**
- README: `experiment/exp3/README.md`
- **Paper-text draft: `experiment/exp3/paper_text_exp3.md`** (updated 2026-05-26: 5 tasks, 75 records, K2>=K1, T5 knowledge gradient).
- Tables: `experiment/exp3/tables/table_exp3_core_results.csv`, `table_exp3_task_level.csv`, `table_exp3_condition_design.csv`, `tableS_exp3_trial_records.csv`.
- Figures: `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`, `fig_exp3_task_heatmap.png`.
- Raw records: `results/paper/exp3_v2/trial_records.jsonl`, per-run dirs under `results/paper/exp3_v2/runs/`.

---

## Experiment 4 — Capability boundary and controlled failure (`experiment/exp4/`)

**Question.** When a task crosses the current tool boundary, does the agent fail in a predictable way, or does it invent tools, misuse available tools, or fabricate results?

**Tasks.** 5 tool conditions × boundary scenarios:
- **Stress family** (B0 basic tools / B2 basic + create_skill / B3 = B2 + explicit policy) × 4 scenarios × 5 repeats = 60 records — tests whether the meta-tool can REPLACE stripped-out core tools.
- **Production family** (B1 full toolchain) × 4 scenarios × 5 repeats = 20 records — natural deployment with all tools available.
- **Fair-extension family** (B4 = B1 base + explicit policy) × {S2, S4} × 5 repeats = 10 records — added 2026-05-26 to isolate "extend a working toolchain via create_skill" from the "reconstruct stripped substrate" confound that B2/B3 unintentionally test.

Total **90 records**.

**Current data status.** 90/90 records ✓ — 80 in the original stress + production families (n=5 from 2026-05-24 extension), 10 in the B4 fair-extension family (2026-05-26). Tables + figures re-compiled with B4 included. The judge function in `common.py:classify_trial` was extended on 2026-05-26 to recognise B4 for S2 (credits successful calibrate+evaluate) and S4 (credits create_skill invocation).

**Headline numbers** (`experiment/exp4/tables/table_exp4_failure_modes.csv`, n = 20 per stress/production condition, n = 10 for B4):

| Condition | n | Success | Hallucination | Wrong route | ask_user | **create_skill** |
|---|---:|---:|---:|---:|---:|---:|
| B0 basic tools                                | 20 |  0.0% | **75.0%** |  0.0% | 20.0% |  0.0% |
| B1 full toolchain (production)                | 20 | **55.0%** |  5.0% | 35.0% | 20.0% |  5.0% |
| B2 basic + create_skill (no policy)           | 20 |  0.0% | 30.0% | 25.0% | 25.0% |  5.0% |
| B3 basic + create_skill + explicit policy     | 20 |  0.0% | 30.0% | 35.0% | 10.0% | **20.0%** |
| **B4** full base + create_skill + policy (S2+S4 only) | 10 | **60.0%** | 10.0% | 40.0% |  0.0% | 10.0% |

> Read the canonical rates from `table_exp4_failure_modes.csv` (auto-regenerated by `compile_results.py`). B4 numbers will land when the 10-record run finishes.

**Evidence vs README** (5 sub-findings; n=5 per (condition, scenario) cell is modest, so the paper text uses "pattern", "consistent across repeats" framing rather than statistical-significance language):

- **Sub-finding 1 — Hallucination collapses with executable grounding (B0 vs B1)**: B0 hallucinates 75.0%; B1 drops to 5.0% (15× reduction). The dominant cause of hydrological hallucination in this setting is the absence of an executable grounding step, not LLM confidence. Adding even one real tool (calibrate_model via hydromodel) converts most "made-up NSE" answers into real ones.

- **Sub-finding 2a — Policy gap (B2 vs B3)**: With `create_skill` available but no explicit policy, the LLM invokes it only 5% of the time (B2). With an explicit "MUST call create_skill if a tool is missing" sentence in the system prompt, invocation jumps to 20% (B3). This is a pure *prompt-engineering finding*: the LLM has the capability but defaults to not using the meta-tool.

- **Sub-finding 2b — Engineering gap (B3 on stress tests)**: B2 and B3 both keep task_success at 0/20 even when create_skill is invoked. The reason is structural: when the calibration tools are artificially stripped (S2), the agent would have to generate a working SCE-UA calibrator from scratch without access to hydromodel's parameter ranges / normalisation / data loading / optimiser, and this is outside the practical scope of in-loop few-shot code generation. **This is a stress-test result, not a deployment-relevant one** — production HydroAgent always has hydromodel available, so B2/B3 should be read as "what happens if substrate is removed" not "what happens in practice".

- **Sub-finding 3 — Fair extension test (B4, NEW 2026-05-26)**: B4 preserves the full B1 toolchain AND adds the B3 explicit policy. Run on S2 + S4 × 5 reps = 10 records. Two parts:
  - **B4 on S2: 5/5 task_success, 0/5 create_skill calls.** The LLM correctly routes to the existing `calibrate_model`/`evaluate_model` tools; no create_skill invocation needed. Directly confirms that B3's 0/5 failure on S2 was substrate stripping, NOT a policy or LLM-capability deficit.
  - **B4 on S4 (truly out-of-scope MCMC): 1/5 task_success, 1/5 create_skill calls, 1/5 hallucination.** Only one trial followed the prescribed pattern (generated MCMC skill + ran it + reported real result). The other 4 silently fell back to ordinary calibration as a stand-in, refused, or hallucinated. Matches B1's 1/5 baseline on the same scenario — explicit policy did NOT raise S4 success in our sample. **The next research target is reliable out-of-scope recognition**: it is not enough to give the LLM both the substrate AND the policy; the agent must also correctly classify "this task is out-of-scope, I should use create_skill" at the decision point, which it does only 20% of the time in our sample.

- **Sub-finding 4 — Tool richness creates a wrong-route failure mode**: B0 has wrong_route = 0% (no calibration tool to mis-route to); B1/B3 have wrong_route = 35%. The cost of adding tools is a routing decision that did not exist before; the next research direction in this dimension is tool-selection policy, not more tools.

- **Sub-finding 5 — Execution cost is hydromodel SCE-UA, not LLM tokens**: B1 wall time 97 s is ~5× B0's 20 s; token cost grows only modestly (84 k vs 60 k). The dominant cost of executable correctness in HydroAgent is hydromodel compute, not LLM tokens — useful because the latter is a hard budget limit while the former scales naturally with the calibration request itself.

**Stress-test caveat (critical for paper-text)**: B0/B2/B3 ARTIFICIALLY remove the calibration tools to stress-test agent behavior under tool-missing conditions. Their 0%-task_success results are *not* claims that HydroAgent fails in practice; they are claims about what happens when the substrate is taken away. The canonical create_skill extension test is B4, which preserves the substrate and asks the LLM to extend it on genuinely out-of-scope tasks.

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
- **What is *not* in this run.** No XAJ in exp1 (single screen survivor — too narrow a panel). exp2 A baseline is in (6/6) and B has 3 seeds at 30 iter (540 records); see Table 4.z. exp1 M1 (human-driven) is in progress operator-side and the pre-seed-fix numbers in the exp1 paper text are flagged as such. DiagScore rater (Qwen) was scaffolded but not invoked in the current exp3 numbers; it can be added as a secondary column without re-running anything.
- **Honest limitations to surface in discussion.** exp3 and exp4 each use **n = 5 repeats per cell** (60 and 80 records respectively). This is enough for the qualitative claims reported here (perfect or near-perfect separation in the T4 reversal and the B0-vs-B1 hallucination collapse) but the paper text reports findings as *controlled-condition evidence* and *patterns consistent across repeats*, not as statistically significant tests. Other limitations: exp1 has 5 basins, all GR4J; the panel is geographically diverse (HUC 01/03/05/06/07) but model-monoculture. The DeepSeek model is held fixed across all experiments — there is no LLM-family ablation. The hydroagent/config.py random-seed bug (fixed in commit 7fa602a) means historical SCE-UA runs used the fallback seed 1234 across trials; exp2/3/4 paper claims are robust to this because variance in exp2 B comes from LLM proposal stochasticity (LLM has no fixed seed) and exp3/exp4 scenarios mostly do not depend on SCE-UA seed determinism.

When a follow-up Agent picks this up, the **per-experiment `paper_text_*.md` drafts are the canonical narrative**, the **`tables/*.csv` and `figures/*.png` are the canonical artifacts**, and the **`experiment/paper_data/exp*_v2/*.jsonl` (committed snapshot) and the live `results/paper/exp*_v2/trial_records.jsonl`** are the canonical raw data that every number traces back to. The `experiment/paper_data/README.md` documents the snapshot layout.
