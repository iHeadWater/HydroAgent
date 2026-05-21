# Exp1 v2: Token-for-time calibration experiment

This folder contains the paper-facing replacement for the original Exp1 scripts.
The old top-level `experiment/exp1_standard_calibration.py` files are retained
as historical baselines; this folder is the authoritative Exp1 v2 workflow.

## Research Question

In unfamiliar basin calibration tasks, can HydroAgent preserve hydrological
performance while replacing human active tuning time with LLM token cost, and
does it choose hyperparameters more directionally than random search under the
same menu?

## Tasks

- Basins: `12025000`, `03439000`, `06043500`, `08101000`, `11532500`
- Models: `xaj`, `gr4j`
- Tasks: `5 basins x 2 models = 10`
- Train period: `2000-01-01` to `2009-12-31`
- Test period: `2010-01-01` to `2014-12-31`

## Methods

| Method | Script | Controller | Max trials |
| --- | --- | --- | --- |
| M0 | `run_default_script.py` | fixed default SCE-UA | 1 |
| M1 | `run_human_runner.py` | human menu tuning | 5 |
| M2 | `run_hydroagent_menu.py` | HydroAgent/LLM menu tuning | 5 |
| M3 | `run_random_menu.py` | random menu tuning | 5 x repeats |

All methods use the same controlled menu:

- objective: `NSE`, `KGE`, `LOGNSE`
- budget: `quick`, `default`, `deep`
- range policy: `default`, `climate_prior`, `wide`, `boundary_expand`

HydroAgent and human operators do not directly create final parameters or
metrics. They only select menu options. Hydromodel performs every numerical
calibration and evaluation.

## Human Active Time

Human active time is measured by `run_human_runner.py`.

Included:

- reading basin attributes;
- reading previous NSE/KGE and boundary-hit diagnostics;
- selecting the next menu configuration;
- writing short diagnostic notes.

Excluded:

- SCE-UA calibration waiting time;
- model evaluation waiting time;
- file I/O and script overhead.

This makes the human-time metric correspond to diagnostic and tuning effort,
which is the part HydroAgent is intended to replace with token cost.

## Outputs

Data:

- `results/paper/exp1_v2/<method>/trials.jsonl`
- `results/paper/exp1_v2/compiled_results.json`

Tables:

- `experiment/exp1/tables/table1_methods.csv`
- `experiment/exp1/tables/table2_core_results.csv`
- `experiment/exp1/tables/tableS1_task_level_results.csv`

Figures:

- `experiment/exp1/figures/fig1_noninferiority.png`
- `experiment/exp1/figures/fig2_search_efficiency.png`
- `experiment/exp1/figures/figS1_token_breakdown.png`

## Run Order

Smoke test:

```bash
python experiment/exp1/run_default_script.py --smoke --overwrite
python experiment/exp1/run_hydroagent_menu.py --smoke --overwrite --max-trials 1
python experiment/exp1/run_random_menu.py --smoke --overwrite --repeats 1
python experiment/exp1/compile_results.py
python experiment/exp1/plot_results.py
```

Full run:

```bash
python experiment/exp1/run_default_script.py --overwrite
python experiment/exp1/run_hydroagent_menu.py --overwrite
python experiment/exp1/run_random_menu.py --overwrite
python experiment/exp1/run_human_runner.py
python experiment/exp1/compile_results.py
python experiment/exp1/plot_results.py
```

Use `--overwrite` only when intentionally replacing a method's previous trial
log. The human runner appends by default so interrupted manual sessions can be
continued.

## Paper Tables and Figures

Main text should use only:

- Table 1: methods and fairness constraints;
- Table 2: core performance, time, token, and random-percentile results;
- Figure 1: HydroAgent vs human non-inferiority scatter;
- Figure 2: best-so-far search trajectories.

Supplement:

- Table S1: task-level results;
- Figure S1: token breakdown.
