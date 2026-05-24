# Paper data snapshot

This folder is the canonical raw-data subset committed to the repo for
reproducibility of every number in `paper_text_exp{2,3,4}.md`,
`tables/*.csv`, and `figures/*.png`.

Each `trial_records.jsonl` / `trials.jsonl` line is one full trial record
as written by the corresponding run script. The `compiled_results.json`
file is the output of the per-experiment `compile_results.py` and is what
the table-emission code actually reads when regenerating CSVs.

## Layout

```
paper_data/
├── exp2_v2/
│   ├── standard_sceua/trials.jsonl          # A baseline (6 records)
│   ├── zhu_direct_eval/
│   │   ├── trials.jsonl                     # canonical = seed0
│   │   ├── trials_seed0.jsonl               # B 30-iter seed 0 (180 records)
│   │   ├── trials_seed1.jsonl               # B 30-iter seed 1 (180 records)
│   │   └── trials_seed2.jsonl               # B 30-iter seed 2 (180 records)
│   ├── llm_local_search/trials.jsonl        # C 15-iter (90 records)
│   └── hydroagent_feedback/trials.jsonl     # D (6 records)
├── exp3_v2/
│   ├── trial_records.jsonl                  # 60 records (3 cond × 4 tasks × 5 repeats)
│   └── compiled_results.json
└── exp4_v2/
    ├── trial_records.jsonl                  # 80 records (4 cond × 4 scen × 5 repeats)
    └── compiled_results.json
```

## Notes

- The full results tree under `results/paper/` is gitignored (per-run
  workspaces, calibration outputs, intermediate SCE-UA logs). Only the
  trial-summary jsonl and the compiled JSON are tracked here. Anyone
  reproducing the paper numbers can regenerate tables and figures from
  these by running `experiment/exp{2,3,4}/compile_results.py` and
  `plot_results.py` against this folder (after adjusting their input
  paths if needed).
- `hydroagent/config.py:349` had a `pop()`-vs-`get()` random-seed bug
  that was fixed in commit 7fa602a. All records in this snapshot were
  produced under the pre-fix behaviour (SCE-UA inside used fallback
  seed 1234). The exp2/3/4 paper claims do not depend on per-trial seed
  variance, see PAPER_DATA_INDEX.md for the per-experiment analysis.
- exp1 raw data is NOT in this snapshot because the M0/M1/M2 re-runs
  under the post-fix code are still in progress.
