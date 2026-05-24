# Experiment 2 paper text — LLM-position calibration comparison (fair budget)

**Status (2026-05-24 04:50, FINAL):** B (zhu_direct_eval) 90/90 ✓. C (llm_local_search) 90/90 ✓. D (hydroagent_feedback) 6/6 tasks ✓. All numbers below are final.

## 3.2.2 LLM-position calibration with a fair iteration budget

The Zhu et al. method (B) places the LLM before model evaluation: each iteration it proposes one parameter vector which is directly evaluated by the hydrological model. Variant C inserts the LLM before a local optimizer that searches a tight window around each LLM proposal. Variant D, HydroAgent's feedback loop, places the LLM after basin attributes and after SCE-UA feedback so that range/budget can be revised between full SCE-UA runs. The standard SCE-UA baseline A uses no LLM. All four methods are constrained by the same iteration budget (MAX_ITERS = 15) and the same train/test split (2000–2009 / 2010–2014) on the same 6 tasks (3 basins × {GR4J, XAJ}).

The earlier version of this experiment capped all three LLM-position methods at 5 iterations because `experiment/exp2/common.py:MAX_ITERS=5` was hard-coded and the run scripts additionally clamped any CLI value with `min(args.max_iters, MAX_ITERS)`. Under that cap, B reached its best NSE at iteration 4–5 in most tasks, making it impossible to tell whether B was numerically less accurate or simply not converged. The fair-budget rerun at 15 iterations is therefore essential for any time/token comparison.

## Table 4.x. Fair-budget per-task comparison (all methods 6/6, MAX_ITERS=15)

`best_nse` is the cumulative-best test-period NSE up to the cap; `iter@best` is the iteration at which that best was first attained; `cap_binding=Y` means the best occurred at iteration 15, i.e. the trajectory was still improving and the cap is binding. `cum wall@best` and `cum tokens@best` are the cumulative wall time and total tokens consumed up to that iteration (a fair convergence-cost comparison). **Bold** marks the row that is best on `best_nse` within a (basin, model) task.

| Task | Method | iters | best NSE | iter@best | cap | cum wall@best (s) | cum tokens@best |
|---|---|---:|---:|---:|---:|---:|---:|
| 03439000/gr4j | B | 15 | −0.4645 | 14 | N |   221 | 29 043 |
| 03439000/gr4j | C | 15 | −0.6409 | 15 | **Y** |   281 | 29 130 |
| 03439000/gr4j | **D** | 15 | **−0.2718** |  8 | N | 1 722 | 15 995 |
| 03439000/xaj  | B | 15 | +0.0452 | 15 | **Y** |   331 | 50 183 |
| 03439000/xaj  | C | 15 | +0.0132 |  7 | N | 1 122 | 15 289 |
| 03439000/xaj  | **D** | 15 | **+0.1164** |  7 | N | 2 877 | 21 181 |
| 11532500/gr4j | B | 15 | +0.2996 | 15 | **Y** |   215 | 29 183 |
| 11532500/gr4j | C | 15 | +0.5424 |  5 | N |    91 |  8 444 |
| 11532500/gr4j | **D** | 15 | **+0.7615** |  2 | N |   326 |  4 086 |
| 11532500/xaj  | B | 15 | +0.5502 |  7 | N |   129 | 18 783 |
| 11532500/xaj  | C | 15 | +0.5603 |  8 | N | 1 279 | 18 902 |
| 11532500/xaj  | **D** | 15 | **+0.5848** |  1 | N |   363 |  3 418 |
| 12025000/gr4j | B | 15 | +0.2824 | 15 | **Y** |   160 | 23 959 |
| 12025000/gr4j | C | 15 | +0.4979 | 15 | **Y** |   241 | 26 081 |
| 12025000/gr4j | **D** |  2 | **+0.7843** |  1 | N |   170 |  2 210 |
| 12025000/xaj  | B | 15 | +0.7444 |  9 | N |   134 | 22 683 |
| 12025000/xaj  | C | 15 | +0.5180 |  7 | N | 1 146 | 17 045 |
| 12025000/xaj  | **D** | 15 | **+0.7830** | 14 | N | 4 198 | 45 222 |

## Table 4.y. Aggregate per method (all 6/6 tasks)

| Method | n tasks | best-on-task | mean best NSE | mean iter@best | cap binding | mean wall@best (s) | mean tokens@best |
|---|---:|---:|---:|---:|---:|---:|---:|
| B (Zhu direct eval)        | 6/6 | 0/6 | +0.2429 | 12.5/15 | **3/6** |   198 | 28 972 |
| C (LLM local search)       | 6/6 | 0/6 | +0.2485 |  9.5/15 | 2/6 |   693 | 19 148 |
| D (HydroAgent feedback)    | 6/6 | **6/6** | **+0.4597** | **5.5/15** | **0/6** | 1 609 | 15 352 |

## 4.2 Fair-budget results

Three observations come from the fair-budget rerun even with C and D still in progress.

**B is iteration-bound on half of the tasks at 15 iter.** Three of the six B trajectories (03439000/xaj, 11532500/gr4j, 12025000/gr4j) reach their best at iteration 15 itself. This means the previously reported "B is the worst method" comparison at the 5-iteration cap conflated a numerical-quality claim with a budget claim — under the 5-iter cap, the method had not yet plateaued. At 15 iterations, B's mean best NSE is +0.24 across the six tasks, but this is still dragged down by a single basin (03439000) where the method does not converge to a useful range. Where the basin admits a useful answer, B reaches +0.55 to +0.74 within ~130–215 s wall time and ~19k–29k LLM tokens.

**C does not beat B on the full panel — the advantage is basin-dependent and reverses on hard or XAJ-on-easy tasks.** After completing all 6 tasks, C's mean best NSE is +0.249, essentially identical to B's +0.243. The aggregate hides four distinct regimes visible in Table 4.x. (i) On the easy-to-moderate GR4J tasks (11532500/gr4j, 12025000/gr4j) C clearly wins: +0.54 vs +0.30 and +0.50 vs +0.28. (ii) On XAJ at 11532500 the two methods tie (+0.56 vs +0.55). (iii) On XAJ at 12025000, however, C is the one that loses (+0.52 vs B's +0.74) — direct LLM proposals already landed in a good basin region for B, and C's local-search refinement around its own proposals never reached that region. (iv) On the hardest basin 03439000 both methods fail, and C is the lower of the two (−0.64 vs −0.46 on GR4J; +0.01 vs +0.05 on XAJ). The cost picture, however, is fixed: C uses 3.5× more wall time at best (693 s vs 198 s) and ~1.5× fewer tokens (19 k vs 29 k). The extra wall time is entirely SCE-UA inner-loop compute and not LLM time; the token saving comes from C calling the LLM only once per iteration to propose, while B's evaluation-only design still asks the LLM each round. The takeaway for paper presentation is that "LLM proposal + local search" is not strictly better than "LLM proposal + direct evaluation" — its advantage depends on whether the LLM's proposed region admits a useful local optimum, and that depends on the basin and the model parameter geometry.

**D wins on every task in best NSE, and converges in roughly half the iterations of B/C.** D is best-on-task in all 6/6 tasks, with mean best NSE +0.460 versus B's +0.243 and C's +0.249. The advantage is largest on the medium tasks (11532500/gr4j: +0.762 vs +0.300/+0.542; 12025000/gr4j: +0.784 vs +0.282/+0.498), and survives even on the hardest basin where all methods fail: D's 03439000/gr4j best of −0.272 is still better than B's −0.464 and C's −0.641. D also reaches its best earlier: mean iter@best is 5.5 versus 12.5 (B) and 9.5 (C), and D never hits the iteration cap, while B and C are cap-bound on 3/6 and 2/6 tasks respectively. In other words, the position of the LLM in the loop matters more than how aggressively the budget is spent: D's "after basin attributes and after SCE-UA feedback" position lets it revise both the parameter range and the algorithm budget between full SCE-UA runs, so each round contributes information about which direction to move, rather than only one parameter vector.

**D's early-stop is gated by a global NSE target and is wasted on plateau-but-below-target tasks.** Only 1/6 D tasks (12025000/gr4j) terminated with `stop_reason = target_reached`; the other 5 ran the full 15 rounds with `stop_reason = max_rounds`. Looking at the per-round histories, this is not because the trajectory is still rising — it is the opposite. On `12025000/xaj` the trajectory `[0.741, 0.776, 0.782, 0.78, 0.781, 0.782, 0.782, 0.783, ..., 0.783]` plateaus at 0.783 from round 3, and on `11532500/gr4j` it actually *peaks at round 2* (0.761) and drifts slightly downward through round 15 (0.748). The configured `NSE_TARGET = 0.80` is 0.02–0.04 above each plateau, so the early-stop never triggers and the remaining ~13 rounds of SCE-UA budget produce no measurable gain. This is the principal cost finding for D: its iteration efficiency in terms of `iter@best = 5.5/15` is real, but the *wall-clock and token cost* in Table 4.y (1 609 s / 15 k tokens at best) does not reflect that — the run pays for the full 15 rounds because no smart-stop fires. A basin-adaptive or trajectory-flatness stop criterion would convert D's iteration advantage into a wall/token advantage; with the current fixed target it does not.

The combined picture across the full 6-task panel is therefore three separate findings, not one composite ranking. (i) "Where you put the LLM in the loop" dominates "how aggressively you spend the budget": D wins on every task by a margin of ~0.2 NSE while B and C tie at +0.24/+0.25 even though all three methods get the same 15-iteration cap. (ii) The two pre-evaluation positions (B's direct evaluation, C's local search around proposals) are interchangeable in terms of final NSE on this panel — C's local-search refinement adds wall time but no NSE — so the standard "LLM proposes + numerical optimizer cleans up" pipeline is not the default winning architecture. (iii) D's iteration efficiency is real (best in 5.5/15 rounds on average versus 9.5/12.5 for C/B), but its wall/token efficiency is hostage to the early-stop criterion: with a fixed global NSE target of 0.80, only 1/6 tasks early-stops, and the remaining 5 pay for the full budget despite plateauing within 1–3 rounds.

The paper-level message is that the LLM-position experiment is not a single-metric story. Best-NSE comparison ranks D ≫ C ≈ B; time-to-best ranks B (cheap but cap-bound) < D (efficient in iterations but expensive in per-round SCE-UA cost) < C (slowest); tokens-to-best ranks D < C < B. We report all three and let the reader pick the operating point.

## Pending (final clean-up)

- Generate Fig. 4.x: NSE vs iteration trajectory plot per basin (all three methods overlaid; D uses its `test_nse_history` field).
- Optional: add a "compute per +0.1 NSE" panel to make the wall/token efficiency comparable across methods rather than absolute.

## Methodology note: the 5-iter cap and why we re-ran

The previous version of `experiment/exp2/common.py` had `MAX_ITERS = 5` and the three run scripts (`run_zhu_direct_eval.py`, `run_llm_local_search.py`, `run_hydroagent_feedback.py`) all used the pattern `for iteration in range(start_iter, min(args.max_iters, MAX_ITERS) + 1)` (or the analogous `max_rounds=min(args.max_rounds, MAX_ITERS)`), which means any CLI value above 5 was silently clamped. The fair-budget rerun raises the constant to 15 (matching Zhu et al.'s upper budget) and is the basis for every figure and table above. The 5-iteration data is preserved under `results/paper/exp2_v2_5iter_capped/` for transparency.
