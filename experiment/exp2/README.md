# Exp2 v2: Where should the LLM enter calibration?

This experiment separates four calibration roles that were previously mixed together. The goal is not only to compare final NSE/KGE, but to make the process evidence clear: whether the LLM is directly guessing parameters, providing a prior for an optimizer, or behaving like a human operator that reads basin context and reacts to calibration feedback.

## Experimental Question

For unfamiliar basins, does HydroAgent work because the LLM can directly guess hydrological parameters, or because it can guide the calibration workflow around a numerical optimizer?

Exp2 v2 answers this by running the same `3 basins x 2 models` tasks under four method definitions:

| Method | Meaning | LLM position | Numeric action |
|---|---|---|---|
| A | Standard SCE-UA | No LLM | One SCE-UA run over default ranges |
| B | Zhu-style direct evaluation | Before model evaluation | LLM proposes one complete physical parameter set per round; the script directly evaluates it |
| C | LLM proposal + local search | Before optimization | LLM proposes a parameter set; hydromodel searches in a narrow range around it |
| D | HydroAgent feedback calibration | Before and after SCE-UA feedback | Agent reads basin attributes, runs SCE-UA, then adjusts ranges or budget from diagnostics |

## Tasks

Basins:

- `12025000` Fish River, ME
- `11532500` Smith River, CA
- `03439000` French Broad River, NC

Models:

- `gr4j`
- `xaj`

The default split is:

- Train: `2000-01-01` to `2009-12-31`
- Test: `2010-01-01` to `2014-12-31`

The optimization objective is fixed to `NSE` for all groups. Test NSE/KGE are only used for reporting, not for selecting the best trial.

## Key Implementation Detail

Method B uses `evaluate_parameter_set()` in `common.py`. It does not run a local optimizer. The helper validates that every parameter is present, checks physical bounds, writes a temporary calibration-like directory, stores the normalized parameter file expected by hydromodel, and then calls `evaluate_model()` for train and test periods.

Invalid LLM proposals are recorded as invalid trials. They are not silently clipped, because proposal validity is part of the evidence.

Method C intentionally keeps the older "LLM guess near which to search" idea, but it is now named differently from Method B. Its records include both the LLM proposed parameters and the optimizer's best parameters, plus their normalized distance.

Method D reuses `llm_calibrate()` and adds process evidence: whether basin attributes were read, whether basin-aware initial ranges were used, each round's SCE-UA metrics, boundary hits, LLM range or budget changes, token usage, and stop reason.

## Metrics

Hydrological performance:

- Train/test NSE
- Train/test KGE
- Delta NSE against A, B, and C where relevant

LLM and process cost:

- LLM calls
- Prompt, completion, cached, and total tokens
- LLM decision time
- Hydromodel compute time
- Total wall time
- Valid proposal rate for B and C
- Iterations or rounds to best

Human-like feedback evidence for D:

- Basin attributes used
- Initial range changed from default
- First SCE-UA boundary hit
- LLM response matched diagnostic signal
- Revised search improved result
- Stop reason

## Run Order

From the repository root:

```powershell
python experiment\exp2\run_standard_sceua.py
python experiment\exp2\run_zhu_direct_eval.py
python experiment\exp2\run_llm_local_search.py
python experiment\exp2\run_hydroagent_feedback.py
python experiment\exp2\compile_results.py
python experiment\exp2\plot_results.py
```

Use the project virtual environment when running the experiment:

```powershell
.\.venv\Scripts\python.exe experiment\exp2\run_standard_sceua.py --smoke --overwrite
```

The current smoke check found that hydromodel imports can fail if `hydroutils`' transitive dependency `pytz` is missing from `.venv`. Fix the environment before running full hydrological evaluations; otherwise Method A-D scripts will start correctly but the model evaluation step will return an import error.

For a quick engineering check:

```powershell
.\.venv\Scripts\python.exe experiment\exp2\run_standard_sceua.py --smoke --overwrite
.\.venv\Scripts\python.exe experiment\exp2\run_zhu_direct_eval.py --smoke --overwrite --max-iters 1
.\.venv\Scripts\python.exe experiment\exp2\run_llm_local_search.py --smoke --overwrite --max-iters 1
.\.venv\Scripts\python.exe experiment\exp2\run_hydroagent_feedback.py --smoke --overwrite --max-rounds 1
.\.venv\Scripts\python.exe experiment\exp2\compile_results.py
.\.venv\Scripts\python.exe experiment\exp2\plot_results.py
```

## Outputs

Raw records:

- `results/paper/exp2_v2/standard_sceua/trials.jsonl`
- `results/paper/exp2_v2/zhu_direct_eval/trials.jsonl`
- `results/paper/exp2_v2/llm_local_search/trials.jsonl`
- `results/paper/exp2_v2/hydroagent_feedback/trials.jsonl`

Tables:

- `experiment/exp2/tables/table43_methods.csv`
- `experiment/exp2/tables/table44_core_results.csv`
- `experiment/exp2/tables/table45_hydroagent_process_evidence.csv`
- `experiment/exp2/tables/tableS_exp2_method_summary.csv`

Figures:

- `experiment/exp2/figures/fig43_method_comparison.png`
- `experiment/exp2/figures/fig44_search_trajectories.png`

## Interpretation

If B is fast but slightly weaker, the result supports the view that direct LLM parameter guessing has speed value but limited stability. If C improves on B, the LLM proposal is better interpreted as a prior for local search. If D is the most stable but costs more tokens and model runs, the main HydroAgent contribution is the feedback workflow: it uses basin context and optimizer diagnostics to decide what to try next.
