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

## exp1 snapshot (added 2026-05-25)

```
paper_data/
├── exp1_v2/
│   ├── default_script.jsonl           # M0 default (5 records)
│   ├── default_script_min.jsonl       # M0_min rep=100 ngs=10 (5)
│   ├── default_script_max.jsonl       # M0_max rep=2000 ngs=200 (5)
│   └── hydroagent_menu_M2A.jsonl      # M2 Mode A preset menu (25)
├── exp1_v2_modeb/
│   └── human_script_M1B.jsonl         # M1 Mode B human freeform (25)
└── exp1_v2_modeb_m2_v6/
    └── hydroagent_menu_M2B_v6.jsonl   # M2 Mode B freeform LLM v6 (22)
```

Notes for exp1:
- All records use post-seedfix SCE-UA seed (`hydroagent/config.py` `pop()`→`get()`
  fix in commit 7fa602a). Each trial's `algorithm_params.random_seed` matches
  the trial_idx-derived value `1234 + trial_idx*137`.
- M2 Mode B v6 prompt = SCE-UA-aware decision tree + diversification rule +
  single 01543000 example. v7 prompt (4-archetype few-shot from M1 winning
  traces) is in-progress; when v7 produces 25 records it will replace v6 in
  the canonical M2_B location.
- M1 Mode B (human) jsonl includes the operator's `notes` field and per-trial
  decision time in `active_seconds`.
