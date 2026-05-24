# How to use this folder for paper writing

This folder contains everything needed to draft Section 4 of the paper.

- **Canonical narrative**: `paper_text_exp4.md`
- **Tables (cited in the narrative)**: `tables/*.csv`
- **Figures (cited in the narrative)**: `figures/*.png`
- **Raw data per record**: see `PAPER_DATA_INDEX.md` (parent folder)
- **Original methodology / fairness constraints**: `README.md`

When the paper-text narrative and the README disagree, the paper-text is the
source of truth (it was rewritten on 2026-05-24 to match the actual data;
the README still contains hypothesis-shaped sentences from before the run).

The cross-experiment index lives at `../PAPER_DATA_INDEX.md`.

## Granularity note

Each boundary scenario is **one full agent run**, not an iterated calibration loop. Therefore exp4 has no "per-iteration trajectory" table analogous to exp2's `table_exp2_per_iter_trajectory.csv` — the equivalent here is `tableS_exp4_trial_records.csv` where one row = one agent run = one (condition, scenario, repeat) tuple. If you need the inside-the-run tool sequence, read `results/paper/exp4_v2/runs/<run_id>/trial_record.json` for the full `tool_log`.
