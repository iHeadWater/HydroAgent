# DiagScore Annotation Workflow (paper §4.3.2)

This directory hosts the human + LLM rating pipeline for DiagScore.

## Files

| File | Purpose |
|------|---------|
| `diag_rubric.md` | The 5-dimension × 0/1/2 rubric (source of truth for both raters) |
| `human_template.csv` | Empty template for human rater to fill in |
| `llm_rater.py` | Script: call LLM with rubric+report, output `llm_scores.csv` |
| `aggregate_diag.py` | Merge human + LLM CSVs, compute Cohen's κ, flag disagreements |

## Workflow

1. **Run Exp 3** (this generates the agent's final reports):
   ```bash
   PYTHONUTF8=1 .venv/Scripts/python.exe experiment/exp3_knowledge_ablation.py
   ```
   This writes 12 text files to `results/paper/exp3/final_reports/` named `<K>_<T>.txt`.

2. **Human rates manually** (~1 hour for 12 items × 5 dimensions):
   ```bash
   cp experiment/_annot/human_template.csv experiment/_annot/human_scores.csv
   # Open human_scores.csv in your editor, read each report, fill D1..D5
   ```
   For each report, read the agent's final answer text and assign 0/1/2 per
   `diag_rubric.md` for D1 problem identification, D2 evidence citation,
   D3 hydrological causality, D4 actionability, D5 limit acknowledgment.

3. **LLM rates the same items** (~10 minutes API time):
   ```bash
   PYTHONUTF8=1 .venv/Scripts/python.exe experiment/_annot/llm_rater.py
   ```
   This calls the configured LLM (deterministic, temperature=0) with the
   same rubric prompt and parses scores into `llm_scores.csv`.

4. **Aggregate + compute Cohen's κ**:
   ```bash
   PYTHONUTF8=1 .venv/Scripts/python.exe experiment/_annot/aggregate_diag.py
   ```
   Prints per-dimension κ and overall κ. Flags any item where human and LLM
   differ by >1 point (re-review recommended). Saves combined `combined_scores.csv`.

## Reporting in the paper

- Report **per-dimension κ** in §4.3.2 methods.
- Report **mean DiagScore per condition × task** as Table 4.III-1 column.
- Document **"LLM as second annotator"** in methods with the same rubric
  text shared via Supplementary Material, plus an honest caveat that this
  is "automated second annotation" not gold truth.
- If κ < 0.6 on any dimension, expand human rater pool OR refine rubric.

## Honest caveats

- LLM-as-rater is not gold ground truth; reported κ is "human vs LLM"
  agreement and serves to defend the rating reliability.
- The same LLM model used by the agent itself should NOT be used as the
  rater (avoid self-evaluation bias). Recommended: if agent runs use
  Qwen/DeepSeek, set the rater to a different provider (Claude/GPT-4).
- For especially controversial items (κ < 0.4 on a specific dimension),
  consider human-only scoring with notes on rubric ambiguity.
