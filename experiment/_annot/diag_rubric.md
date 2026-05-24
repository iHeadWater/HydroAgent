# DiagScore Rubric (paper §4.3.2)

A 5-dimension × {0, 1, 2} rubric for evaluating an agent's final-report
diagnostic reasoning quality. Both the human rater and the LLM second-rater
follow this rubric verbatim.

DiagScore = (D1 + D2 + D3 + D4 + D5) / 10  ∈ [0, 1]

---

## D1 — Problem identification

Did the agent name the actual hydrological issue (not just symptoms)?

- **0**: Misses the issue entirely or asserts there is no problem when there is.
- **1**: Identifies a surface-level symptom only ("NSE is low") but does not
  point to a root cause.
- **2**: Identifies symptom AND root cause (e.g. "NSE low + FHV strongly
  negative + B parameter at upper bound → soil moisture distribution
  exponent is constrained, model cannot generate enough peak flow").

## D2 — Evidence citation

Did the agent cite specific numerical evidence to support its claims?

- **0**: No numbers cited; pure narrative.
- **1**: Cites a single metric or parameter value (e.g. "NSE was 0.65").
- **2**: Cites at least 2 consistent pieces of evidence (e.g. metric +
  parameter value + boundary-hit status, or 2 metrics + 1 attribute).

## D3 — Hydrological causality

Is there a clear physical causal chain connecting evidence to conclusion?

- **0**: No physical reasoning; conclusion is asserted without justification.
- **1**: Invokes a hydrological concept but the causal link to the evidence
  is loose or hand-wavy.
- **2**: Explicit causal chain rooted in hydrology, e.g.
  "high baseflow_index → groundwater-dominated regime → CG should be near 1
   → current CG upper bound at 0.95 is too low".

## D4 — Actionability

Is the recommendation specific and executable?

- **0**: No recommendation, or vague "should investigate further".
- **1**: Generic recommendation without specifics (e.g. "adjust parameters",
  "try other algorithms").
- **2**: Specific, executable action with parameter / direction / rationale
  (e.g. "expand B upper bound from 0.4 to 0.6 because baseflow-dominated
  catchments need stronger soil-moisture nonlinearity").

## D5 — Limit acknowledgment

Does the agent honestly bound its claims, especially about what calibration
cannot fix?

- **0**: Pretends certainty or overclaims (e.g. promises NSE > 0.8 in any
  case, ignores structural limits).
- **1**: General hedging ("results may vary", "performance could improve")
  without identifying which limits apply.
- **2**: Explicitly distinguishes parameter-tunable issues from structural
  / data limits (e.g. "this basin's complex topography may exceed XAJ's
  lumped representational capacity; calibration cannot fix structural
  inadequacy").

---

## Scoring procedure

1. Read the agent's final report (results/paper/exp3/final_reports/<K>_<T>.txt).
2. For each dimension, assign 0, 1, or 2 per the criteria above.
3. Record into the human CSV template; note any unusual cases in `notes`.
4. The LLM rater (experiment/_annot/llm_rater.py) is given this same rubric
   verbatim and produces an independent rating per item.
5. Cohen's κ is computed per dimension and overall by aggregate_diag.py.

## Anchoring examples (cross-rater calibration)

Use these to calibrate your judgment before scoring:

**Example: D1 score = 2**
> "The calibration achieves NSE = 0.42 on test period. Examining the parameter
> set, SM hits its upper bound (100 mm) and CG hits its upper bound (0.998).
> Combined with the basin's baseflow_index = 0.65, this indicates the model
> is constrained from representing the slow groundwater recession that
> dominates this basin's hydrograph."

**Example: D2 score = 0**
> "The model performs reasonably and the parameters look sensible."
(No numbers cited.)

**Example: D5 score = 2**
> "The persistent low NSE (0.08) despite calibration suggests this is not a
> parameter-tuning problem. The XAJ lumped model may not adequately
> represent French Broad's complex Appalachian topography and multi-stream
> network. Further calibration cycles are unlikely to help; a
> distributed-model or different forcing dataset would be appropriate
> follow-up directions."
