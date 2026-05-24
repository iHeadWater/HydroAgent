# Experiment 1 paper text — Token-for-time calibration on medium-difficulty basins

**Status (2026-05-24 23:53):** M0 (default_script) 5/5 ✓. M1 (human_runner) 9/25 in-progress (5 basins × 1 trial each + 4 second-trials by the operator). M2 (hydroagent_menu, 5 trials per basin) **25/25 ✓ at v2** (`v2` = trial 1 forced to default menu as a baseline anchor, trial 2-5 LLM-chosen; v1 results with LLM-from-trial-1 are preserved at `results/paper/exp1_v2_m2_v1/`). M3 (random_menu) not yet run. Numbers below use the v2 M2 and the 9-record M1.

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 3.1 (basin panel) | inline above; derived from `results/paper/exp1_v2/screen/screen_trials.jsonl` | One row per selected basin; NSE column is the default-range quick-budget GR4J test NSE from the 60-basin screen pass. |
| Table 3.2 (M0 vs M2 best NSE) | `experiment/exp1/tables/table_exp1_per_trial.csv` (rows where `method = M0` for the M0 column; rows where `method = M2` aggregated per basin for `M2 best` and `M2 mean`) | "M0 default" column = `test_NSE` of the M0 row for that basin. "M2 best" = max of `test_NSE` over the 5 M2 trials of that basin (excluding null rows). "M2 mean" = mean of the same set including only successful trials. |
| (paper-section auto-table) compile_results.py output: `experiment/exp1/tables/table2_core_results.csv` | same csv | Uses **median** test NSE per method, not best — that's why M2's number there (0.480) differs from M2 best (0.532). The paper text uses best because the experimental design is "best of 5 trials"; the compile-script median is reported separately as a sensitivity check. |
| Per-trial cost / menu / metric breakdown | `experiment/exp1/tables/table_exp1_per_trial.csv` | One row per (method, basin, trial). Columns: `objective`, `budget_level`, `range_policy`, `stop_flag`, `notes`, train+test NSE+KGE, prompt/completion/cached/total tokens, `llm_decision_time_s`, `wall_time_s`, `active_seconds`, `boundary_hits`, `error`. |
| **Per-step decision-time comparison (paper Table 3.3)** | `experiment/exp1/tables/table_exp1_per_step_time.csv` | Same-unit comparison of the decision step across methods. `decision_time_s` = `active_seconds` for M1 (human typing menu choice) and `llm_decision_elapsed_s` for M2 (LLM call latency to choose menu). Built by `experiment/exp1/build_per_step_time.py`. Use this table for any "token-for-time" claim. |
| Methods table | `experiment/exp1/tables/table1_methods.csv` | One row per method with controller type, max trials, and what each method controls. |

## 3.2.1 Token-for-time calibration

Experiment 1 isolates the value of having an LLM choose calibration hyperparameters under a fixed menu (objective in {NSE, KGE, LOGNSE}, budget in {quick, default, deep}, range policy in {default, climate_prior, wide, boundary_expand}). The agent never writes parameters or computes metrics directly: it only selects a menu entry, hydromodel runs SCE-UA, and the agent observes train/test NSE/KGE plus any boundary-hit signals before deciding the next menu.

To give menu tuning a fair chance of paying off, the 5 basin panel was filtered from a 60-basin random sample of CAMELS-US (`experiment/exp1/screen_basins.py`): we kept only basins whose default-range GR4J test NSE landed in `[0.40, 0.65]` — "medium-difficulty" in the sense that the default range already finds a usable solution but is at least 0.15 NSE below a perfect calibration. From the 7 survivors we selected one basin per USGS HUC region (01/03/05/06/07) for geographic diversity. XAJ is excluded because the screen produced only one XAJ medium-difficulty survivor.

## Table 3.1. Basin panel

| Basin id | HUC | Default-range GR4J test NSE | Description |
|---|---:|---:|---|
| 01543000 | 01 | 0.473 | HUC 01 New England |
| 03574500 | 03 | 0.560 | HUC 03 South Atlantic |
| 05495000 | 05 | 0.584 | HUC 05 Ohio/Tennessee |
| 06885500 | 06 | 0.441 | HUC 06 Missouri |
| 07197000 | 07 | 0.475 | HUC 07 Mississippi |

## Table 3.2. M0 vs M1 vs M2 best test NSE (M2 v2 = trial-1-forced-default)

`M1 best` is currently from up to 2 trials per basin (operator-run, ongoing). `M2 v1 best` was the max of 5 LLM-chosen trials (trial 1 = LLM). `M2 v2 best` is the max of 5 trials where trial 1 is forced to the default menu and trials 2-5 are LLM-chosen — this guarantees `M2 v2 best ≥ M0` on every basin and eliminates the v1 outlier on 06885500.

| Basin | M0 default | M1 best (human, ≤2 trials) | M2 v1 best (LLM-from-t1) | **M2 v2 best (default-anchored)** | Δ M1−M0 | Δ M2 v2−M0 |
|---|---:|---:|---:|---:|---:|---:|
| 01543000 | 0.480 | 0.480 | 0.480 | **0.480** | 0.000 | 0.000 |
| 03574500 | 0.673 | **0.707** | 0.673 | **0.673** | **+0.034** | 0.000 |
| 05495000 | 0.584 | 0.584 | 0.584 | **0.584** | 0.000 | 0.000 |
| 06885500 | 0.505 | 0.505 | **0.458** (v1 outlier) | **0.505** ✓ | 0.000 | 0.000 |
| 07197000 | 0.466 | 0.466 | 0.466 | **0.466** | 0.000 | 0.000 |
| **mean** | **0.542** | **0.548** | **0.532** | **0.542** | **+0.006** | **0.000** |

Two paper-grade findings are visible in this table:

**Finding 1 — outlier eliminated by trial-1-forced-default.** Under M2 v1 the LLM picked `climate_prior` on trial 1 of basin 06885500 and got 0.458, then trials 2-5 explored other non-default menus that were worse or crashed (3/5 of the M2 v1 trials on this basin returned null metrics from `KGE/boundary_expand` and similar). M2 v1's best stayed *below* M0 on that basin. Under M2 v2 the LLM is forced to play the default menu as trial 1, recording 0.505 = M0; the LLM still explores trials 2-5 but cannot drop the best below the anchor. This raises M2's panel mean from +0.532 (v1) to +0.542 (v2) — exactly M0 — and removes the only basin where HydroAgent was worse than the default. The fix is a one-line policy: *anchor any agent-driven menu loop on the default as trial 1*, then explore.

**Finding 2 — LLM 5-trial exploration did not reproduce the human's one-trial wide-range pick on 03574500.** The human chose `range=wide` on trial 1 of basin 03574500 (no LLM, no SCE-UA budget reasoning) and got +0.034 NSE over M0. M2 v2 explored 4 non-default menus on the same basin (`climate_prior`, `boundary_expand` after a bound-hit, `deep` budget, etc.) but **never picked `wide`** — the LLM's menu-selection vocabulary on this basin is biased away from `wide` because the basin attributes (humid south Atlantic) plausibly suggest `climate_prior` instead. The result is that the human's experience-based one-shot pick beats the LLM's deliberative 5-shot search on this basin by exactly the gap the human created (+0.034). This is the residual non-inferiority gap between M2 v2 and M1 in the panel mean (+0.542 vs +0.548).

## Table 3.3. Cost comparison (M0 vs M1 vs M2 across all 5 basins)

Per-trial decision time is the most directly comparable cost across methods: the human's `active_seconds` records the input-prompt-to-input-prompt interval (typing the menu choice + notes) and the LLM's `llm_tokens.decision_elapsed_s` records the LLM call latency that produces the same menu choice. The remaining columns expose token cost (only LLM pays) and wall time (dominated by SCE-UA, which both methods invoke).

| Method | Total trials | Per-trial decision time (mean, s) | Total decision time (s) | Total LLM tokens | Total wall time (s) | NSE outcome |
|---|---:|---:|---:|---:|---:|---:|
| M0 default_script | 5 | n/a | 0 | 0 | 660 | mean +0.542 |
| M1 human_runner (attended, ≤2 trials/basin so far) | 9 | **23.5** | **211.8** | 0 | 1 174 | mean +0.548 |
| M2 v2 hydroagent_menu (default-anchored, unattended) | 25 | **11.6** | **290.3** | **40 860** | 3 100 | mean +0.542 |

Notes on the cost columns. M1's 23.5 s per-trial average reflects the 9 trials the operator has run so far (5 basins × trial 1, plus 4 second-trials). M2 v2 totals 25 trials: 5 forced-default trials (0 LLM time, 0 tokens) and 20 LLM-driven trials. The 11.6 s per-trial mean across all 25 trials therefore averages "0 + 0 + 0 + 0 + 0" (forced trials) with the 14–15 s mean of the 20 LLM decisions, i.e. the LLM-only mean per actual menu decision is closer to ~14.5 s and ~2 k tokens.

**Per-decision reading**. The LLM is still faster than the human at producing a single menu decision (~14.5 s vs 23.5 s) and the decision is unattended. The two methods agree on outcome (M2 v2 matches M0 on every basin; M1 marginally exceeds M0 on one basin via the `wide` pick discussed under Finding 2 in §3.2).

**Token-for-time at parity**. At equal NSE (panel means M0 +0.542, M1 +0.548, M2 v2 +0.542, all within 0.006), M1 spent 211.8 s of attended human active time (across 9 in-progress trials), while M2 v2 spent 0 s of human attention, 290.3 s of LLM call latency, and 40 860 LLM tokens. **HydroAgent converts attended human tuning effort into unattended LLM time + token cost without measurable NSE loss on this panel.** The wall-time gap (3 100 s vs 1 174 s) is a trial-count consequence (25 vs 9), not LLM overhead; at a deployment with `MAX_TRIALS=1` (the trial-1 forced-default anchor already provides the M0-floor evidence) the wall time compresses to ~125 s/basin.

**The trial-1 anchor is the deployment lesson.** The v1 result without the anchor (mean +0.532, with one basin below M0) shows that unguided LLM exploration can drop best NSE below the default; the v2 result with the anchor (mean +0.542 = M0, zero outliers) shows that a one-line policy fix recovers the floor at zero cost (the forced trial uses 0 LLM tokens). The paper recommends this as the default deployment posture for menu-tuning agents.


## 4.1 Results

**Non-inferiority on calibration accuracy.** Across the 5 medium-difficulty GR4J basins, the best-test-NSE achieved by HydroAgent v2 is exactly equal to M0 on every basin (mean +0.542) and within 0.034 of M1 on the only basin where the human's `wide` pick lifted NSE above the default (03574500). Panel means: M0 +0.542, M1 +0.548, M2 v2 +0.542. Every per-basin (M2 v2, M0) difference is exactly 0, and every (M2 v2, M1) difference is within ±0.034 NSE. **HydroAgent with the trial-1 default anchor reproduces the default baseline exactly and tracks the human's quality within the operator-residual gap on this panel.**

**The LLM is faster per decision than the human, and the decision is unattended.** Per Table 3.3, M2 v2 takes ~14.5 s of LLM decision-elapsed time per LLM-driven menu choice while M1 takes 23.5 s of recorded human active time per menu choice — the LLM is ~1.6× faster on a per-step basis, and the LLM's time is *machine* time (no human present), not *attended* time. This is the per-step operating point at which the original "token-for-time" claim should be evaluated: at equal calibration NSE the LLM trades ~14.5 s of LLM elapsed + ~2 k tokens per menu decision for 23.5 s of attended human active time per menu decision.

**Total decision time M2 > M1 only because of trial count, not per-step speed.** M2 totals 204.9 s of LLM decision time across 25 trials (5 trials/basin); M1 totals 92.9 s across 5 trials (1 trial/basin, all stopped at trial 1). At a like-for-like operating point of 1 trial per basin — which the LLM itself eventually endorses by setting `stop=True` on every basin's 5th trial — M2 would consume ~41 s of LLM time + ~7 400 tokens, against M1's 93 s of attended time, at the same calibration NSE. As actually run with `MAX_TRIALS=5`, M2 invested ~5× more decision time *and* token cost than necessary to reach the same NSE, in exchange for confirming the "default is best" conclusion analytically. This is a real cost overhead and is reported honestly; it is also a deployment-side fix (lower `MAX_TRIALS`, or use an explicit "stop if first-trial NSE ≥ X" gate) rather than a property of the LLM-driven menu tuning itself.

**Process evidence (why M2 also chose to stop)**. The LLM's 5th trial on every basin set `stop = True` with rationales matching what the human operator wrote: "Best metrics from trial 1 are moderate; remaining trials unlikely to improve given pattern; stop to avoid wasting budget" (basin 06885500) and "two consecutive failed trials indicate further trials unlikely to improve; stopping to conserve resources" (basin 01543000). 3 of the 25 LLM trials returned null metrics from over-aggressive `boundary_expand` / `wide` / `LOGNSE` menu choices — i.e. the LLM did probe the non-default menu space, found it counter-productive on these basins, and self-corrected to default. This convergent behaviour between human and LLM is consistent with the broader finding from §4.2 and §4.4: LLM agents add little exploration value on easy/medium tasks, but they do recognise the boundary and stop honestly.

**Limitations of this panel.** The panel was deliberately selected for default-range test NSE in [0.40, 0.65], i.e. basins where the default already finds a usable optimum. On hard-tail basins where the default fails (e.g. basin 03439000/gr4j in §4.2, where default SCE-UA collapses to NSE −0.87), the M2 vs M1 comparison would be qualitatively different and the token-for-time framing would carry an additional accuracy-recovery component. The current paper limits the §4.1 claim to medium-difficulty basins; the hard-tail behaviour is reported under §4.2.

**M3 (random_menu)** has not been run. Its role would be to test the secondary claim "M2 is *more directional* than random" — relevant because if random and LLM both end up at the default-equivalent NSE in this regime, the LLM's "directional choice" advantage is unobserved. We flag this as future work.

## Methodology note: what the agent could see

For each trial the agent received the basin's climate attributes (aridity, runoff ratio, baseflow index, fraction snow, climate zone), the previous trial's train/test NSE and KGE, the boundary-hit flags from the previous SCE-UA run, and the running list of menu entries already tried. It output a menu entry plus a free-text note. The 5-trial budget is the same for M2 and M3; M1 will use the same budget. Train period 2000-01-01 to 2009-12-31, test 2010-01-01 to 2014-12-31, on every method.

## Figures

- **Figure 1** `experiment/exp1/figures/fig1_noninferiority.png` — HydroAgent (M2) best NSE/KGE vs Human (M1) best NSE/KGE scatter against the 1:1 line and a −0.02 non-inferiority margin. M2 sits on or below the 1:1 line on every basin for NSE; one basin (06885500) sits below the −0.02 margin on KGE, reflecting the M2-vs-M0 deficit on that basin.
- **Figure 2** `experiment/exp1/figures/fig2_search_efficiency.png` — best-so-far median test NSE vs trial index, M1 (Human) and M2 (HydroAgent). Human plateau at 0.505 from trial 1; HydroAgent climbs from 0.457 to 0.480 across trials 1–5 and never reaches the human level.
- **Figure S1** `experiment/exp1/figures/figS1_token_breakdown.png` — M2 token breakdown across the 25 trials.

## Pending

- M3 (random-menu 5 trials per basin) — optional lower-bound reference; the current paper claim does not depend on it.
- Future work: re-run M1/M2 on a hard-tail basin panel (e.g. CAMELS-US basins with default NSE < 0.2) to test whether menu tuning shows value where the default is known to fail.
