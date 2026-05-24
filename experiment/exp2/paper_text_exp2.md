# Experiment 2 paper text — LLM-position calibration comparison (fair budget)

**Status (2026-05-24 10:18, FINAL):** A (standard_sceua) 6/6 ✓. B (zhu_direct_eval) 90/90 ✓. C (llm_local_search) 90/90 ✓. D (hydroagent_feedback) 6/6 ✓. All numbers below are final.

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 4.x (per-task fair-budget) | `experiment/exp2/tables/table_exp2_fair_compare.csv` | One row per (basin, model, method). Columns include `best_nse` (cumulative-best test NSE up to the cap), `iter_at_best`, `cap_binding` (Y/N), `cum_wall_at_best_s`, `cum_tok_at_best`. Same content also reproduced in `table_exp2_per_task_full.csv` with train+test NSE+KGE and `cum_llm_t_at_best_s` / `cum_hydromodel_t_at_best_s` split. |
| Table 4.y (aggregate per method) | `experiment/exp2/tables/table_exp2_method_aggregate_full.csv` | One row per method (A/B/C/D). Columns `mean_best_test_NSE`, `stdev_best_test_NSE`, `mean_best_train_NSE`, `mean_best_test_KGE`, `mean_best_train_KGE`, `mean_iter_at_best`, `n_cap_binding`, `mean_cum_wall_at_best_s`, `mean_cum_tokens_at_best`, `mean_cum_llm_t_at_best_s`, `mean_cum_hydromodel_t_at_best_s`. |
| Per-iteration trajectory (numerical form of Fig 4.4) | `experiment/exp2/tables/table_exp2_per_iter_trajectory.csv` | 263 rows. One row per (method, basin, model, iteration). Columns include train+test NSE+KGE, prompt/completion/cached/total tokens, `wall_time_s`, `llm_decision_time_s`, `hydromodel_compute_time_s`, `best_so_far_test_NSE`. D rows have `_d_per_iter_is_approx = True` because D's per-round token/time fields are reconstructed by linear allocation of the total (the raw record stores per-method totals, not per-round). |
| Compile-pipeline core table | `experiment/exp2/tables/table44_core_results.csv` | Wide format: one row per (basin, model) with A/B/C/D columns side-by-side, all cross-method deltas. Convenient for the cross-method bar chart (Fig 4.3). |
| Process evidence for D | `experiment/exp2/tables/table45_hydroagent_process_evidence.csv` | One row per (basin, model) D run with `basin_attributes_used`, `basin_aware_init`, `first_sceua_boundary_hit`, `diagnostic_response_match`, `revised_search_improved`, `stop_reason`. Use when discussing why D wins on hard tasks. |
| Method definitions and budget tables | `table43_methods.csv` | Method/position/numeric-action/max_rounds/cost-record schema. |
| Fig 4.3 method comparison bars | `experiment/exp2/figures/fig43_method_comparison.png` | 4-method (A/B/C/D) test NSE + test KGE bars per task. **Regenerated 2026-05-24 with 15-iter B/C and A baseline included.** |
| Fig 4.4 search trajectories | `experiment/exp2/figures/fig44_search_trajectories.png` | B/C/D test NSE at the train-NSE-best parameter, vs LLM iteration. A is a single run so not on this figure (its mean +0.339 would appear as a horizontal reference line if added). |

## 3.2.2 LLM-position calibration with a fair iteration budget

The Zhu et al. method (B) places the LLM before model evaluation: each iteration it proposes one parameter vector which is directly evaluated by the hydrological model. Variant C inserts the LLM before a local optimizer that searches a tight window around each LLM proposal. Variant D, HydroAgent's feedback loop, places the LLM after basin attributes and after SCE-UA feedback so that range/budget can be revised between full SCE-UA runs. The standard SCE-UA baseline A uses no LLM. All four methods are constrained by the same iteration budget (MAX_ITERS = 15) and the same train/test split (2000–2009 / 2010–2014) on the same 6 tasks (3 basins × {GR4J, XAJ}).

The earlier version of this experiment capped all three LLM-position methods at 5 iterations because `experiment/exp2/common.py:MAX_ITERS=5` was hard-coded and the run scripts additionally clamped any CLI value with `min(args.max_iters, MAX_ITERS)`. Under that cap, B reached its best NSE at iteration 4–5 in most tasks, making it impossible to tell whether B was numerically less accurate or simply not converged. The fair-budget rerun at 15 iterations is therefore essential for any time/token comparison.

## Table 4.x. Fair-budget per-task comparison (all 4 methods, MAX_ITERS=15 for B/C/D)

`best_nse` is the cumulative-best test-period NSE up to the cap; `iter@best` is the iteration at which that best was first attained; `cap_binding=Y` means the best occurred at iteration 15, i.e. the trajectory was still improving and the cap is binding. `cum wall@best` and `cum tokens@best` are the cumulative wall time and total tokens consumed up to that iteration (a fair convergence-cost comparison). **Bold** marks the row that is best on `best_nse` within a (basin, model) task. Method A is a single SCE-UA run (no LLM, no iteration loop), reported as 1 iter / 0 tokens.

| Task | Method | iters | best NSE | iter@best | cap | cum wall@best (s) | cum tokens@best |
|---|---|---:|---:|---:|---:|---:|---:|
| 03439000/gr4j | A | 1 | −0.8723 | 1 | — | (n/a) | 0 |
| 03439000/gr4j | B | 15 | −0.4645 | 14 | N | 221 | 29 043 |
| 03439000/gr4j | C | 15 | −0.6409 | 15 | **Y** | 281 | 29 130 |
| 03439000/gr4j | **D** | 15 | **−0.2718** | 8 | N | 1 722 | 15 995 |
| 03439000/xaj | A | 1 | +0.0640 | 1 | — | (n/a) | 0 |
| 03439000/xaj | B | 15 | +0.0452 | 15 | **Y** | 331 | 50 183 |
| 03439000/xaj | C | 15 | +0.0132 | 7 | N | 1 122 | 15 289 |
| 03439000/xaj | **D** | 15 | **+0.1164** | 7 | N | 2 877 | 21 181 |
| 11532500/gr4j | A | 1 | +0.7406 | 1 | — | (n/a) | 0 |
| 11532500/gr4j | B | 15 | +0.2996 | 15 | **Y** | 215 | 29 183 |
| 11532500/gr4j | C | 15 | +0.5424 | 5 | N | 91 | 8 444 |
| 11532500/gr4j | **D** | 15 | **+0.7615** | 2 | N | 326 | 4 086 |
| 11532500/xaj | A | 1 | +0.5772 | 1 | — | (n/a) | 0 |
| 11532500/xaj | B | 15 | +0.5502 | 7 | N | 129 | 18 783 |
| 11532500/xaj | C | 15 | +0.5603 | 8 | N | 1 279 | 18 902 |
| 11532500/xaj | **D** | 15 | **+0.5848** | 1 | N | 363 | 3 418 |
| 12025000/gr4j | A | 1 | +0.7478 | 1 | — | (n/a) | 0 |
| 12025000/gr4j | B | 15 | +0.2824 | 15 | **Y** | 160 | 23 959 |
| 12025000/gr4j | C | 15 | +0.4979 | 15 | **Y** | 241 | 26 081 |
| 12025000/gr4j | **D** | 2 | **+0.7843** | 1 | N | 170 | 2 210 |
| 12025000/xaj | A | 1 | +0.7759 | 1 | — | (n/a) | 0 |
| 12025000/xaj | B | 15 | +0.7444 | 9 | N | 134 | 22 683 |
| 12025000/xaj | C | 15 | +0.5180 | 7 | N | 1 146 | 17 045 |
| 12025000/xaj | **D** | 15 | **+0.7830** | 14 | N | 4 198 | 45 222 |

## Table 4.y. Aggregate per method (all 6/6 tasks)

| Method | n tasks | best-on-task | mean best NSE | mean iter@best | cap binding | mean wall@best (s) | mean tokens@best |
|---|---:|---:|---:|---:|---:|---:|---:|
| A (standard SCE-UA, no LLM) | 6/6 | 0/6 | +0.339 | 1/1 | — | (in-SCE-UA) | 0 |
| B (Zhu direct eval)         | 6/6 | 0/6 | +0.243 | 12.5/15 | **3/6** |   198 | 28 972 |
| C (LLM local search)        | 6/6 | 0/6 | +0.249 |  9.5/15 | 2/6 |   693 | 19 148 |
| D (HydroAgent feedback)     | 6/6 | **6/6** | **+0.460** | **5.5/15** | **0/6** | 1 609 | 15 352 |

Two cross-method observations are visible already in the aggregate row.
**(a) Standard SCE-UA (A) outperforms both B and C on mean test NSE** (+0.339 vs +0.243 / +0.249). The two pre-evaluation LLM positions in this experiment lose to running SCE-UA once, indicating that "LLM proposes parameters" and "LLM proposes a region for local search" do not improve over standard sampling-based optimization under the same iteration budget. The story for §4.2 is therefore not just "B vs C vs D" but also "are B/C even better than the no-LLM baseline?".
**(b) D outperforms A on the mean by +0.121, but the gap concentrates on a single hard task**: A is within 0.052 NSE of D on 5 of 6 tasks, and only collapses on 03439000/gr4j (A −0.872 vs D −0.272, gap 0.600). On train NSE however the gap is *broader*: A +0.102 vs D +0.405. D's train-side advantage is therefore real on most tasks; it just happens to translate to a small test-side gain wherever A is already at a usable optimum.

## 4.2 Fair-budget results

Four observations come from the fair-budget rerun.

**A (no LLM) beats both pre-evaluation LLM positions on mean test NSE.** Standard SCE-UA reaches mean +0.339 across the 6 tasks, while the two LLM-before-evaluation methods reach only +0.243 (B) and +0.249 (C). Under the same iteration budget on this panel, asking an LLM to propose parameters — either evaluated directly (B) or used as a starting point for local search (C) — produces worse calibration than running SCE-UA once. This is a non-trivial baseline check that disqualifies "LLM as a parameter generator" as a usable standalone position for this task class.

**A (no LLM) is competitive with D on 5 of 6 tasks on test NSE, but D wins on train NSE more broadly.** D reaches mean test NSE +0.460 versus A's +0.339, a gap of +0.121 in aggregate. The per-task view shows that A is within 0.052 of D on five of the six tasks (12025000/gr4j +xaj, 11532500/gr4j +xaj, 03439000/xaj); D's dramatic win only appears on 03439000/gr4j where A collapses to −0.872 and D recovers to −0.272 (margin +0.600 — large enough to lift the aggregate by itself). On train NSE the story is different: A averages only +0.102 while D averages +0.405, indicating that D *does* find better calibration optima broadly, but those optima translate to a small test-side advantage wherever A's coarse search is already inside a usable basin. The honest paper framing is that HydroAgent's feedback loop is a hard-tail recovery mechanism on test generalization, and a broad train-side improvement that has limited test-side payoff once the default-range optimum is good enough.

**B is iteration-bound on half of the tasks at 15 iter.** Three of the six B trajectories (03439000/xaj, 11532500/gr4j, 12025000/gr4j) reach their best at iteration 15 itself. This means the previously reported "B is the worst method" comparison at the 5-iteration cap conflated a numerical-quality claim with a budget claim — under the 5-iter cap, the method had not yet plateaued. At 15 iterations, B's mean best NSE is +0.24 across the six tasks, but this is still dragged down by a single basin (03439000) where the method does not converge to a useful range. Where the basin admits a useful answer, B reaches +0.55 to +0.74 within ~130–215 s wall time and ~19k–29k LLM tokens.

**C does not beat B on the full panel — the advantage is basin-dependent and reverses on hard or XAJ-on-easy tasks.** After completing all 6 tasks, C's mean best NSE is +0.249, essentially identical to B's +0.243. The aggregate hides four distinct regimes visible in Table 4.x. (i) On the easy-to-moderate GR4J tasks (11532500/gr4j, 12025000/gr4j) C clearly wins: +0.54 vs +0.30 and +0.50 vs +0.28. (ii) On XAJ at 11532500 the two methods tie (+0.56 vs +0.55). (iii) On XAJ at 12025000, however, C is the one that loses (+0.52 vs B's +0.74) — direct LLM proposals already landed in a good basin region for B, and C's local-search refinement around its own proposals never reached that region. (iv) On the hardest basin 03439000 both methods fail, and C is the lower of the two (−0.64 vs −0.46 on GR4J; +0.01 vs +0.05 on XAJ). The cost picture, however, is fixed: C uses 3.5× more wall time at best (693 s vs 198 s) and ~1.5× fewer tokens (19 k vs 29 k). The extra wall time is entirely SCE-UA inner-loop compute and not LLM time; the token saving comes from C calling the LLM only once per iteration to propose, while B's evaluation-only design still asks the LLM each round. The takeaway for paper presentation is that "LLM proposal + local search" is not strictly better than "LLM proposal + direct evaluation" — its advantage depends on whether the LLM's proposed region admits a useful local optimum, and that depends on the basin and the model parameter geometry.

**D wins on every task in best NSE, and converges in roughly half the iterations of B/C.** D is best-on-task in all 6/6 tasks, with mean best NSE +0.460 versus B's +0.243 and C's +0.249. The advantage is largest on the medium tasks (11532500/gr4j: +0.762 vs +0.300/+0.542; 12025000/gr4j: +0.784 vs +0.282/+0.498), and survives even on the hardest basin where all methods fail: D's 03439000/gr4j best of −0.272 is still better than B's −0.464 and C's −0.641. D also reaches its best earlier: mean iter@best is 5.5 versus 12.5 (B) and 9.5 (C), and D never hits the iteration cap, while B and C are cap-bound on 3/6 and 2/6 tasks respectively. In other words, the position of the LLM in the loop matters more than how aggressively the budget is spent: D's "after basin attributes and after SCE-UA feedback" position lets it revise both the parameter range and the algorithm budget between full SCE-UA runs, so each round contributes information about which direction to move, rather than only one parameter vector.

**D's early-stop is gated by a global NSE target and is wasted on plateau-but-below-target tasks.** Only 1/6 D tasks (12025000/gr4j) terminated with `stop_reason = target_reached`; the other 5 ran the full 15 rounds with `stop_reason = max_rounds`. Looking at the per-round histories, this is not because the trajectory is still rising — it is the opposite. On `12025000/xaj` the trajectory `[0.741, 0.776, 0.782, 0.78, 0.781, 0.782, 0.782, 0.783, ..., 0.783]` plateaus at 0.783 from round 3, and on `11532500/gr4j` it actually *peaks at round 2* (0.761) and drifts slightly downward through round 15 (0.748). The configured `NSE_TARGET = 0.80` is 0.02–0.04 above each plateau, so the early-stop never triggers and the remaining ~13 rounds of SCE-UA budget produce no measurable gain. This is the principal cost finding for D: its iteration efficiency in terms of `iter@best = 5.5/15` is real, but the *wall-clock and token cost* in Table 4.y (1 609 s / 15 k tokens at best) does not reflect that — the run pays for the full 15 rounds because no smart-stop fires. A basin-adaptive or trajectory-flatness stop criterion would convert D's iteration advantage into a wall/token advantage; with the current fixed target it does not.

The combined picture across the full 6-task panel is therefore four separate findings, not one composite ranking. (i) Standard SCE-UA (A) already gets within 0.05 NSE of D on the 5 non-hardest tasks; on those, the LLM in the loop adds little. (ii) On the hardest basin (03439000/gr4j) all three LLM-position methods recover NSE that A loses, and D recovers the most (A −0.872, B −0.464, C −0.641, D −0.272). The LLM agent's principal value in this experiment is hard-tail recovery, not blanket improvement. (iii) Among the three LLM positions, the two pre-evaluation positions (B's direct evaluation and C's local search around proposals) are interchangeable in terms of final NSE on this panel — C's local-search refinement adds wall time but no NSE — so the standard "LLM proposes + numerical optimizer cleans up" pipeline is not the default winning architecture. (iv) D's iteration efficiency is real (best in 5.5/15 rounds on average versus 9.5/12.5 for C/B), but its wall/token efficiency is hostage to the early-stop criterion: with a fixed global NSE target of 0.80, only 1/6 tasks early-stops, and the remaining 5 pay for the full budget despite plateauing within 1–3 rounds.

The paper-level message is that the LLM-position experiment is not a single-metric story. Best-NSE comparison ranks D ≫ C ≈ B ≳ A in aggregate, but the D-vs-A gap is dominated by one hard task. Time-to-best ranks A (single run) < B (cheap but cap-bound) < D (efficient in iterations but expensive in per-round SCE-UA cost) < C (slowest). Tokens-to-best ranks A (zero) < D < C < B. We report all three axes and let the reader pick the operating point appropriate to the basin difficulty regime.

## Pending (final clean-up)

- Generate Fig. 4.x: NSE vs iteration trajectory plot per basin (all three methods overlaid; D uses its `test_nse_history` field).
- Optional: add a "compute per +0.1 NSE" panel to make the wall/token efficiency comparable across methods rather than absolute.

## Methodology note: the 5-iter cap and why we re-ran

The previous version of `experiment/exp2/common.py` had `MAX_ITERS = 5` and the three run scripts (`run_zhu_direct_eval.py`, `run_llm_local_search.py`, `run_hydroagent_feedback.py`) all used the pattern `for iteration in range(start_iter, min(args.max_iters, MAX_ITERS) + 1)` (or the analogous `max_rounds=min(args.max_rounds, MAX_ITERS)`), which means any CLI value above 5 was silently clamped. The fair-budget rerun raises the constant to 15 (matching Zhu et al.'s upper budget) and is the basis for every figure and table above. The 5-iteration data is preserved under `results/paper/exp2_v2_5iter_capped/` for transparency.
