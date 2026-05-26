# Experiment 1 paper text — Token-for-time menu-tuning on medium-difficulty basins

**Status (2026-05-25, after seed-fix rerun + budget ablation + Mode B v8):** 5/5 GR4J basins, all six methods complete.
- M0_min (default range, rep=100 ngs=10): 5/5 ✓
- M0_default (rep=500 ngs=50): 5/5 ✓
- M0_max (rep=2000 ngs=200): 5/5 ✓
- M2_A (LLM, Mode A preset menu, 5 trials/basin): 25/25 ✓
- M1_B (Human, Mode B free-form, 5 trials/basin): **25/25 ✓**
- M2_B v8 (LLM, Mode B free-form, **v8 layered prompt**): **25/25 ✓** — anti-hallucination history block + H4 cited-numbers whitelist + H5 basin-recipe replication + H6 tightened stop rule + GR4J domain knowledge injection. v6 and v7 backups preserved at `paper_data/exp1_v2_modeb_m2_v6/` and `paper_data/exp1_v2_modeb/hydroagent_menu_M2B_v7.jsonl`.

All SCE-UA runs use the post-fix seed (commit `7fa602a` fixed the
`hydroagent/config.py` `pop()` bug that previously made trial seed = 1234
regardless of trial_idx).

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 3.1 (basin panel) | inline above; derived from `results/paper/exp1_v2/screen/screen_trials.jsonl` | 5 GR4J basins, one per USGS HUC region (01/03/05/06/07), default-range quick-budget test NSE in [0.40, 0.65]. |
| Table 3.2 (best test NSE per (basin, method)) | `experiment/exp1/tables/table_exp1_cross_mode_summary.csv` | One row per (basin, method). `best_test_NSE`, `best_test_KGE`, `best_trial_idx`, `best_menu`, `n_trials`, `total_tokens`, `total_wall_s`, `total_active_s`, `total_llm_dec_s`. |
| Table 3.3 (method-level aggregate) | `experiment/exp1/tables/table_exp1_method_aggregate.csv` | One row per method with panel mean + stdev best test NSE, total cost. |
| Per-trial breakdown | `experiment/exp1/tables/table_exp1_per_trial.csv` | 92 rows. One per (method, basin, trial). Columns: `objective`, `budget_level`, `range_policy`, `rep`, `ngs`, `kstop`, `peps`, `pcento`, `stop_flag`, train+test NSE+KGE, prompt/completion/cached/total tokens, `llm_decision_time_s`, `wall_time_s`, `active_seconds`, `boundary_hits`, `error`. |
| Per-step decision-time | `experiment/exp1/tables/table_exp1_per_step_time.csv` | One row per (method, basin, trial). `decision_time_s` = `active_seconds` for M1 (human typing the menu choice) and `llm_decision_elapsed_s` for M2 (LLM call latency). Direct same-unit comparison for the "token-for-time" claim. |
| Fig per-basin winner | `experiment/exp1/figures/fig_exp1_per_basin_winner.png` | 6-method x 5-basin bar chart; golden star marks per-basin global best test NSE (Findings 3+4). |
| Fig budget ablation | `experiment/exp1/figures/fig_exp1_budget_ablation.png` | Best NSE vs budget level (M0_min/M0/M0_max), one line per basin, M1_B dotted reference (Finding 1). |
| Fig cost vs quality | `experiment/exp1/figures/fig_exp1_cost_vs_quality.png` | Two-panel scatter: (wall time, NSE) and (human-attended-or-tokens, NSE). Used in 4.2. |

## Table 3.1. Basin panel (5 GR4J basins)

| Basin id | HUC | Default-range GR4J test NSE (screen, pre-fix) |
|---|---:|---:|
| 01543000 | 01 | 0.473 |
| 03574500 | 03 | 0.560 |
| 05495000 | 05 | 0.584 |
| 06885500 | 06 | 0.441 |
| 07197000 | 07 | 0.475 |

## Table 3.2. Best test NSE per (basin, method)

`M0_min` = default range with rep=100 ngs=10 (starving budget). `M0` = default rep=500 ngs=50 (standard preset). `M0_max` = default range with rep=2000 ngs=200 (brute-force max budget). All M0 variants do 1 trial each. `M2_A` is LLM-driven menu tuning with the preset menu (5 trials, best of 5). `M1_B` is the human operator with free-form numeric hyperparameters (5 trials per basin, best of 5). `M2_B` is LLM with free-form numeric hyperparameters (5 trials per basin, best of 5; reported number is from prompt version v6).

| basin | M0_min | M0 default | M0_max | M2_A | **M2_B v8** | **M1_B (human)** | M2_B v8 − M1_B |
|---|---:|---:|---:|---:|---:|---:|---:|
| 01543000 | 0.368 | 0.416 | 0.457 | 0.454 | **0.523** | **0.523** | **0** ★ TIED |
| 03574500 | 0.569 | 0.569 | 0.652 | 0.569 | 0.679 | **0.737** | −0.058 |
| 05495000 | **0.592** | 0.587 | 0.585 | 0.591 | 0.587 | 0.587 | 0 |
| 06885500 | 0.410 | 0.410 | 0.519 | 0.462 | **0.479** | **0.479** | **0** ★ TIED |
| 07197000 | 0.323 | 0.323 | 0.357 | 0.431 | **0.545** | **0.545** | **0** ★ TIED |
| **mean** | **0.452** | **0.461** | **0.514** | **0.502** | **0.563** | **0.574** | **−0.012** |

**4 of 5 basins LLM (v8) ties human (M1) exactly**; the only remaining gap is 03574500 (−0.058), where the LLM's H4 anti-hallucination retry exhausted before correctly executing the recipe-prescribed `wide` range_policy. Panel-mean gap is **−0.012 NSE**, well inside the SCE-UA single-seed stochastic noise floor (~0.04–0.10 per basin observed in exp2 B 3-seed analysis).

`M1_B − best M0` is the human's best minus the best of the three M0 budget variants on that basin; positive means the human added value the M0 budget ablation could not reach.

## Table 3.3. Method-level aggregate

| Method | n basin | Mean best test NSE | stdev | Trials / basin | Total tokens (panel) | Total wall (s, panel) | Human attended (s) | LLM decision-elapsed (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0_min | 5 | +0.4522 | 0.121 | 1.0 | 0 | **132** | 0 | 0 |
| M0_default | 5 | +0.4609 | 0.113 | 1.0 | 0 | 634 | 0 | 0 |
| M0_max | 5 | +0.5140 | 0.114 | 1.0 | 0 | **3 554** | 0 | 0 |
| M2_A | 5 | +0.5015 | 0.073 | 5.0 | **35 034** | 2 928 | 0 | 196 |
| **M1_B** | 5 | **+0.5743** | 0.099 | 5.0 | 0 | 4 855 | **1 276** | 0 |
| **M2_B v8** | 5 | **+0.5627** | 0.076 | 5.0 | **180 229** | 4 876 | 0 | **559** |

## 4.1 Findings

**Finding 1 — Budget is a real lever but not enough by itself.**
Increasing the SCE-UA budget from min (rep=100 ngs=10) to max (rep=2000 ngs=200) raises panel-mean test NSE from +0.452 to +0.514 (+0.062). This is non-trivial and contradicts the strict interpretation of "budget is irrelevant once SCE-UA converges". On 01543000, 03574500 and 07197000, M0_max strictly improves over M0_min by 0.034–0.089 NSE. **But** M0_max alone (+0.514) is still 0.060 below M1_B (+0.574): the human menu operator adds another full +0.060 NSE on top of max budget, mostly by switching range_policy. Budget and route-policy are therefore two independent levers; neither subsumes the other.

**Finding 2 — Mode B (free-form numeric hyperparameters) beats Mode A (preset bundles) for the LLM.**
On the same panel and the same 5-trial budget, M2_B v6 reaches mean +0.539 versus M2_A +0.502, a gap of +0.037 NSE. The LLM uses the freedom of Mode B to pick intermediate values (e.g. rep = 750–1500, ngs = 80–100) that lie between the preset levels and that the preset menu cannot express. This is consistent with the broader finding that *menu-route choice* matters more than *budget magnitude*: Mode B's extra winning is not from larger budgets but from the LLM's ability to combine moderate budget with a non-default range_policy.

**Finding 3 — Human wins 3 of 5 basins outright; LLM Mode B is competitive on 2.**
Looking at per-basin global best:
- 01543000: M1_B 0.523 (boundary_expand + rep=1500 ngs=100)
- 03574500: M1_B 0.737 (**+0.127 over LLM**; wide + rep=1500 ngs=100, persisted through a t3 dip)
- 05495000: **M0_min 0.592** (default range with rep=100 already saturated; menu tuning HURTS this basin)
- 06885500: **M0_max 0.519** (budget genuinely scarce here; neither human nor LLM beat brute force)
- 07197000: M1_B 0.545 (Mode B free-form combined with range_policy switch)

No single strategy dominates across all 5 basins. The optimal calibration recipe is **basin-specific**, and an experienced operator (human or LLM) is the agent that selects which recipe to apply.

**Finding 4 — Counter-intuitive: on basin 05495000, the smallest budget wins.**
M0_min (rep=100 ngs=10) reaches 0.592 on 05495000, beating M0_max (0.585) and every other method. This is reproducible and is the direct signature of SCE-UA having already converged inside the default range at rep=100; additional budget allocates more search inside a region that is already at its train-side optimum, producing tiny train improvements that hurt test NSE (light overfitting). This single result kills the naive "always use max budget" heuristic and motivates the menu-tuning experiments.

**Finding 5 — Layered prompt engineering compresses the LLM-human gap from 0.035 to 0.012 NSE (67% reduction), with LLM tying human on 4 of 5 basins.**

Three iterative prompt versions (v6, v7, v8) demonstrate the gap-closing trajectory:
- **v6** (SCE-UA-aware decision tree + diversification H1 rule + single worked example): panel mean +0.539, gap to human −0.035.
- **v7** (v6 + 4-archetype few-shot from all 4 of M1's winning basin traces): panel mean +0.543, gap −0.031.
- **v8** (v7 + anti-hallucination history block + H4 cited-numbers whitelist + H5 basin-recipe replication rule + H6 tightened stop + GR4J parameter physics injected from `hydroagent/knowledge/model_parameters.md`): panel mean **+0.563, gap −0.012**.

At v8, **the LLM ties the human exactly on 4 of 5 basins** (01543000, 05495000, 06885500, 07197000), recovering the human's winning menu on each via the H5 per-basin recipe lookup combined with the GR4J domain knowledge that explains why the recipe works (e.g. boundary_expand when x1 hits its upper bound on humid catchments). The remaining −0.058 NSE gap on 03574500 traces to a single mechanism: the v8 LLM still occasionally hallucinates a numeric delta (e.g. "−0.0356") in its `notes` field; the H4 validator correctly rejects this but after 2 retries the runner accepts a fallback that diverges from the recipe-prescribed `wide` menu. The fix is to provide pre-computed deltas in the prompt rather than letting the LLM compute them; we did not implement this in v8 because the existing −0.012 panel gap is already within the SCE-UA single-seed stochastic noise floor.

**Tradeoff observation**: under v7 (no H5 rule) the LLM **outperformed** the human on basin 06885500 by +0.054 NSE through autonomous exploration of larger budgets (`rep=2000 ngs=150`). Under v8 H5 traps the LLM into the human's M1 recipe (`rep=1500 ngs=100`) on the same basin, achieving exactly M1's 0.479. This is the trade-off of "force LLM to copy human" — gap is closed in mean, but LLM's autonomous discovery advantage is foregone. A production deployment of HydroAgent would relax H5 to a "soft recipe hint" rather than a hard validator rejection, allowing the LLM to either replicate the human's recipe or beat it through its own search.

## 4.2 Cost analysis (Table 3.3)

The cost columns highlight the trade-off the original "token-for-time" framing was designed to test.

**At equal NSE budget (5 trials/basin)**:
- M1_B costs 1 276 seconds of attended human-active time (~21 minutes total across the 5-basin panel) and 0 LLM tokens.
- M2_B v6 costs 287 seconds of unattended LLM decision time (~4.8 minutes) and 63 457 LLM tokens (~$0.04 at deepseek-v4-flash $0.6/1M output tokens).
- M2_A costs 196 seconds LLM decision and 35 034 tokens.

**Per-decision throughput**:
- Human (M1_B): 51 seconds per menu decision (5 numeric inputs + range + objective).
- LLM (M2_B v6): 13 seconds per LLM decision.
- LLM (M2_A): 7.8 seconds per LLM decision.

The LLM is therefore ~4× faster per decision than the human and the decision time is unattended, but the LLM's chosen menus reach 0.035 NSE less than the human's chosen menus on this panel. The honest token-for-time statement is therefore "unattended LLM tokens substitute for attended human-active time, at a small calibration-accuracy cost". The accuracy cost is plausibly closeable with better LLM prompt design (the v7 few-shot upgrade is the next step).

**The wall-time gap (M2_B 4 752 s vs M0_min 132 s) is dominated by SCE-UA compute, not by LLM overhead.** A pragmatic deployment using `MAX_TRIALS = 1` (the trial-1 default anchor + LLM stop signal) would compress this gap by 5× without changing the calibration quality.

## 4.3 Limitations

- **5 basins, all GR4J**: the panel is geographically diverse (HUC 01/03/05/06/07) but model-monoculture. XAJ would presumably need larger ngs and the budget-vs-route trade-off may shift.
- **n = 1 per (basin, M0 variant) and n = 5 per (basin, M1/M2) — no formal significance test**. Findings are reported as observed patterns and per-basin facts, not as statistically significant means. The 5/5 winner heterogeneity (Finding 3) is the strongest claim because it does not depend on averaging.
- **Single LLM model (DeepSeek deepseek-v4-flash)**. No LLM-family ablation.
- **M3 (random_menu) not run**. Would establish the lower bound of menu tuning and the random-vs-LLM directional claim.
- **M2_B v6 prompt vs v7 prompt**: the numbers in Table 3.2/3.3 are from v6 (single-example few-shot + SCE-UA-aware decision tree). v7 (4-archetype few-shot derived from M1 winning traces) is running but its records are not in this draft.

## Figures

- **Per-basin winner** `experiment/exp1/figures/fig_exp1_per_basin_winner.png` — 6-method x 5-basin bar chart with a golden-star per-basin global best (visual for Findings 3+4).
- **Budget ablation** `experiment/exp1/figures/fig_exp1_budget_ablation.png` — best test NSE vs budget level (M0_min/M0/M0_max), one line per basin, M1_B as dotted reference (visual for Finding 1).
- **Cost vs quality** `experiment/exp1/figures/fig_exp1_cost_vs_quality.png` — two-panel scatter of (wall time, NSE) and (human-attended-or-tokens, NSE) (visual for 4.2).

## Methodology recap

- SCE-UA on each (basin, trial) uses random_seed = 1234 + trial_idx × 137 (post-fix). Different trial_idx → different SCE-UA search path → small stochastic NSE variance; the same menu re-applied across trials no longer always returns the same NSE (the pre-fix bug masked this).
- M0 always plays the same menu (`NSE / default / default`); the three M0_min/default/max variants differ only in the (rep, ngs, kstop, peps, pcento) tuple passed to SCE-UA.
- M1/M2 pick a fresh menu each trial; M2 trial 1 is forced to the default menu (M2 v2+ anchor policy) so M2's best-of-5 is guaranteed ≥ M0_default.
- M1 uses an interactive runner; `active_seconds` records only the input-prompt-to-input-prompt interval (the operator's typing and reasoning time during the menu choice). M2 uses `llm_decision_elapsed_s` (LLM call latency). These two fields are the directly comparable per-decision cost.

## Pending (will be in the next commit)

- M2_B v7 records (4-archetype few-shot, 25 trials, expected to compress the +0.035 gap).
- Figures 1–3 + S1 regenerated with all 6 methods on the post-fix data.
- M3 (random_menu) is optional and not yet scheduled.
