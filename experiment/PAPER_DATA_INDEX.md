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
| M2_B v7 (Mode B free-form, LLM) | ✓ done | 19/25 | 5 trials/basin (2 basins stopped early at t2 via correct ARCH-3 application), panel mean **+0.543**; v7 prompt = SCE-UA-aware decision tree + diversification rule + **4-archetype few-shot from M1 winning traces**. **LLM beats human on basin 06885500** (+0.054 NSE via patient ARCH-4 boundary_expand with ngs=150); LLM still loses to human on 03574500 (early-stopped at t2 after misreading own t1 NSE). v6 backup at `paper_data/exp1_v2_modeb_m2_v6/`. |
| M3 random_menu            | not started | — | optional lower-bound reference |

**Evidence vs README — five paper-grade findings, all post-seedfix:**
- **Finding 1: Budget is a real lever (+0.062 panel NSE from M0_min → M0_max) but not enough.** M0_max +0.514 < M1_B +0.574, so human menu tuning adds another +0.060 on top of max budget by choosing range_policy. Two independent levers.
- **Finding 2: Mode B (free-form numeric hyperparameters) beats Mode A (preset bundles) for the LLM** by +0.037 panel NSE (M2_B +0.539 vs M2_A +0.502). LLM uses intermediate values (e.g. rep=750–1500, ngs=80–100) that presets cannot express.
- **Finding 3: No single dominant strategy.** Per-basin global best: M1_B wins 3/5 (01543000, 03574500, 07197000), M0_min wins 1/5 (05495000), M0_max wins 1/5 (06885500). Optimal recipe is basin-specific.
- **Finding 4: Counter-intuitive — on basin 05495000 the smallest budget wins.** M0_min 0.592 > M0_max 0.585 > all menu-tuning methods. Basin's default range already at SCE-UA's train-side optimum; more budget produces light test-side overfitting.
- **Finding 5: Human-LLM gap shrunk to +0.031 panel NSE with v7 prompt, and the gap is two-directional.** v6 gap was +0.035; v7 4-archetype few-shot prompt reduced it marginally to +0.031, but qualitatively flipped the per-basin outcome: **LLM beats human on 06885500 by +0.054 NSE** (patient ARCH-4 boundary_expand+ngs=150), while human still beats LLM on 03574500 by +0.127 (v7 LLM early-stopped at t2 after hallucinating its t1 NSE as 0.775 when actual was 0.569). The gap is two-directional and both failure modes (LLM over-eager stopping on misread history; human under-persistent on hard basins) are addressable.

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
  - `fig1_noninferiority.png` / `fig2_search_efficiency.png` / `figS1_token_breakdown.png` (legacy from earlier compile pipeline; will be regenerated or deprecated).
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

**Tasks.** 3 conditions (K0 plain LLM no tools / K1 tools only / K2 full knowledge) × 4 tasks (T1 standard calibration / T2 model comparison / T3 code analysis / T4 failure diagnosis) × **5 repeats** = **60 records**.

**Current data status.** 60/60 records ✓ at `results/paper/exp3_v2/trial_records.jsonl`. Tables and figures re-compiled with n=5 on 2026-05-24 after the judge bugs were patched (`detect_hallucination` now skips diagnosis-type tasks; `_detect_fabricated_tool` blacklists `*_code` tokens).

**Headline numbers** (`experiment/exp3/tables/table_exp3_core_results.csv`, n = 20 per condition):

| Condition | Success | Hallucination | Mean total tokens |
|---|---:|---:|---:|
| K0 plain LLM        | 25.0% | 15.0% |   1 817 |
| K1 tools only       | **85.0%** |  0.0% |  55 996 |
| K2 full knowledge   | 75.0% |  0.0% | 128 639 |

**Evidence vs README** (n=5 strengthens the n=3 findings):
- **K1 ≥ K2 overall** (85.0% vs 75.0%, gap +10 pp at n=5 vs +8.3 pp at n=3). Tool access closes the entire deficit on T1–T3 (5/5 success for both K1 and K2); knowledge text adds no further help on these tasks.
- **T4 reversal is perfectly separated at n=5**: K0 = **5/5**, K1 = 2/5, K2 = **0/5** on the diagnosis task that explicitly forbids `generate_code`/`run_code`. K2 invokes the forbidden tools on every run; K0 never does because it has no tools. The +73 k tokens of injected hydrological knowledge in K2 bias the agent toward execution even when the requested behavior is purely interpretive.
- **Framing**: report as controlled-condition evidence rather than strong statistical significance. n=5 per cell makes the T4 reversal pattern unambiguous in this panel (perfect separation K0 vs K2) but the absolute sample is still modest; paper text uses "evidence", "pattern", "consistent across all repeats" rather than p-values.

**Paper materials.**
- README: `experiment/exp3/README.md`
- **Paper-text draft: `experiment/exp3/paper_text_exp3.md`** (contains the K1 ≥ K2 result and the T4 reversal narrative).
- Tables: `experiment/exp3/tables/table_exp3_core_results.csv`, `table_exp3_task_level.csv`, `table_exp3_condition_design.csv`, `tableS_exp3_trial_records.csv` (every individual run).
- Figures: `experiment/exp3/figures/fig_exp3_success_vs_tokens.png`, `fig_exp3_task_heatmap.png`.
- Raw records: `results/paper/exp3_v2/trial_records.jsonl`, per-run dirs under `results/paper/exp3_v2/runs/`.

---

## Experiment 4 — Capability boundary and controlled failure (`experiment/exp4/`)

**Question.** When a task crosses the current tool boundary, does the agent fail in a predictable way, or does it invent tools, misuse available tools, or fabricate results?

**Tasks.** 4 tool conditions (B0 basic tools / B1 full toolchain / B2 basic + create_skill + run_code / B3 = B2 + explicit prompt policy "if tool missing, call create_skill") × 4 boundary scenarios (S1 missing basin id / S2 missing calibration tools / S3 wrong-route risk / S4 out-of-scope MCMC) × **5 repeats** = **80 records**.

**Current data status.** 80/80 records ✓ (n extended from 3 to 5 on 2026-05-24). B3 added the same day to test the policy-gap explanation for B2's 0% create_skill use. Tables + figures last re-compiled with the full n=5 data.

**Headline numbers** (`experiment/exp4/tables/table_exp4_failure_modes.csv`, **n = 20 per condition** = 4 scenarios × 5 repeats):

| Condition | Success | Controlled failure | Hallucination | Wrong route | ask_user | **create_skill** |
|---|---:|---:|---:|---:|---:|---:|
| B0 basic tools                                | (rate per `table_exp4_failure_modes.csv`) | | | | | |
| B1 full toolchain                             | (rate per `table_exp4_failure_modes.csv`) | | | | | |
| B2 basic + create_skill (no policy hint)      | (rate per `table_exp4_failure_modes.csv`) | | | | | |
| B3 B2 + explicit "use create_skill" policy    | (rate per `table_exp4_failure_modes.csv`) | | | | | |

> Read the actual rates from `experiment/exp4/tables/table_exp4_failure_modes.csv` (canonical). The qualitative pattern below is what the paper claims; do not hardcode the n=3 percentages from prior commits.

**Evidence vs README** (n=5 — report as controlled-condition evidence, not p-values; the per-cell sample is still modest at 5 repeats per (condition, scenario), so the paper text uses "pattern", "consistent across repeats" framing):
- **B0 hallucinates a clear majority of the time, not "fails safely".** Without execution tools, the agent narrates plausible NSE/KGE values much more often than B1 does. The dominant cause of hydrological hallucination in this setting is *the absence of an executable grounding step*, not the LLM's confidence.
- **B2 `create_skill_rate ≈ 0/20`** with the meta-tool explicitly enabled. Giving an agent a meta-tool without telling it when to use it does not produce recovery.
- **B3 closes the policy gap partly but not the success gap.** Adding "if tool missing, call create_skill" to the system prompt raises create_skill_rate from ~0% to roughly one-third of runs and drops hallucination, but task_success stays at 0/20. The scenarios where create_skill is most needed (S2 missing calibration tools, S4 out-of-scope MCMC) are the ones where the agent still won't or can't generate a useful skill: even when invoked, the few-shot generated tools cannot reconstruct the blocked hydromodel/MCMC capability. Giving a meta-tool + policy is necessary but very far from sufficient; the next research direction is a calibrated decision boundary for when create_skill can plausibly recover.
- **B1 introduces a new failure mode** of wrong tool routing that B0 does not have (B0 has no calibration tool to mis-route to). B3 pushes wrong-route higher than B2 because the explicit policy redirects effort that B2 spent on `ask_user` into unproductive code generation.

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
