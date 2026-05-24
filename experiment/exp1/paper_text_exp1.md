# Experiment 1 paper text — Token-for-time calibration on medium-difficulty basins

**Status (2026-05-24 10:30):** M0 (default_script) 5/5 ✓. M2 (hydroagent_menu, 5 trials per basin) 25/25 ✓. M1 (human_runner) reserved for the human operator; M3 (random_menu) not yet run. Numbers below are final for M0 and M2.

## Tables and files (paper-section → source)

| Reference in this text | File | Row/column meaning |
|---|---|---|
| Table 3.1 (basin panel) | inline above; derived from `results/paper/exp1_v2/screen/screen_trials.jsonl` | One row per selected basin; NSE column is the default-range quick-budget GR4J test NSE from the 60-basin screen pass. |
| Table 3.2 (M0 vs M2 best NSE) | `experiment/exp1/tables/table_exp1_per_trial.csv` (rows where `method = M0` for the M0 column; rows where `method = M2` aggregated per basin for `M2 best` and `M2 mean`) | "M0 default" column = `test_NSE` of the M0 row for that basin. "M2 best" = max of `test_NSE` over the 5 M2 trials of that basin (excluding null rows). "M2 mean" = mean of the same set including only successful trials. |
| (paper-section auto-table) compile_results.py output: `experiment/exp1/tables/table2_core_results.csv` | same csv | Uses **median** test NSE per method, not best — that's why M2's number there (0.480) differs from M2 best (0.532). The paper text uses best because the experimental design is "best of 5 trials"; the compile-script median is reported separately as a sensitivity check. |
| Per-trial cost / menu / metric breakdown | `experiment/exp1/tables/table_exp1_per_trial.csv` | One row per (method, basin, trial). Columns: `objective`, `budget_level`, `range_policy`, `stop_flag`, `notes`, train+test NSE+KGE, prompt/completion/cached/total tokens, `llm_decision_time_s`, `wall_time_s`, `active_seconds`, `boundary_hits`, `error`. |
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

## Table 3.2. M0 vs M2 best test NSE (n_trials_M2 = 5 per basin)

| Basin | M0 default | M2 best | M2 mean (5 trials) | Δ (best − M0) |
|---|---:|---:|---:|---:|
| 01543000 | 0.480 | 0.480 | 0.462 | 0.000 |
| 03574500 | 0.673 | 0.673 | 0.594 | 0.000 |
| 05495000 | 0.584 | 0.584 | 0.554 | 0.000 |
| 06885500 | 0.505 | 0.458 | 0.397 | **−0.047** |
| 07197000 | 0.466 | 0.466 | 0.385 | 0.000 |
| **mean** | **0.541** | **0.532** | **0.478** | **−0.009** |

## 4.1 Results

On this panel of 5 medium-difficulty GR4J basins, **M2 does not improve over M0** — the LLM-driven menu tuning matches M0 on 4 of 5 basins (the best of 5 trials equals the M0 default outcome) and is 0.047 NSE *worse* on 1 basin (06885500). The mean across the 5 basins is M0 +0.541 versus M2-best +0.532 (M2 deficit −0.009) and M2-mean +0.478 (−0.063). No basin shows M2 beating M0 in the 5-trial budget. This is a negative result on the original "HydroAgent improves calibration accuracy" framing, but it is informative about *what HydroAgent actually does* under this experimental design.

**The agent learns to give up.** On every one of the 5 basins, the 5th trial chose `stop = True` with explanatory notes such as "Best metrics from trial 1 are moderate; remaining trials unlikely to improve given pattern; stop to avoid wasting budget" (basin 06885500) and "two consecutive failed trials indicate further trials unlikely to improve; stopping to conserve resources" (basin 01543000). The non-default menus the agent does try — `climate_prior` range, `boundary_expand` after a bound-hit, `wide` range, `LOGNSE` and `KGE` objectives, `deep` budget — generally produce worse test NSE or fail outright with null metrics (3 of the 25 trials returned no valid evaluation). The LLM's exploration of the non-default menu space therefore costs LLM tokens and SCE-UA budget without producing better calibration, and the agent correctly identifies this within 5 trials and stops.

**This re-positions the contribution.** The original framing was that the LLM trades token cost for human active tuning time, with the implicit assumption that the LLM's tuning is at least as good as a careful human's. On this medium-difficulty panel, the LLM's tuning is not better than the fixed default, but the LLM does provide one machine-checkable benefit: it explicitly recognises and reports "the default is the best you will get from this menu within the trial budget". A human operator would also reach this conclusion eventually, but only after running the trials themselves. The LLM does the same work in LLM-token cost rather than human-active time, and produces a stop signal that is visible in the trial log. The negative-result framing therefore aligns with the broader finding from Experiments 2 and 4 that LLM-driven hydrological agents add little to easy or medium tasks, and that their value lives on the hard tail (Section 4.2, basin 03439000/gr4j).

**M1 (human-driven) is reserved for the operator** and will be filled in as a separate row in Table 3.2 once available. Its expected role is to provide the upper bound of what menu tuning can achieve on this panel; if M1 also fails to beat M0 by more than ε, the conclusion sharpens to "menu tuning is not the right lever for medium-difficulty basins, regardless of who pulls it". If M1 beats M0 noticeably, the gap between M1 and M2 quantifies the LLM's tuning-quality deficit. M3 (random menu) is the lower bound; running M3 last is sufficient because M2's behaviour is already mostly bounded by M0 from above.

## Methodology note: what the agent could see

For each trial the agent received the basin's climate attributes (aridity, runoff ratio, baseflow index, fraction snow, climate zone), the previous trial's train/test NSE and KGE, the boundary-hit flags from the previous SCE-UA run, and the running list of menu entries already tried. It output a menu entry plus a free-text note. The 5-trial budget is the same for M2 and M3; M1 will use the same budget. Train period 2000-01-01 to 2009-12-31, test 2010-01-01 to 2014-12-31, on every method.

## Pending

- M1 (human-driven 5 trials per basin) — operator will fill in.
- M3 (random-menu 5 trials per basin) — schedule after M1.
- Per-basin trial trajectory figure (NSE vs trial index, M0/M1/M2/M3 overlaid).
- Cost-vs-performance scatter once M1/M3 are populated.
