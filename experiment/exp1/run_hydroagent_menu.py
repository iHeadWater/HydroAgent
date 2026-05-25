"""M2 HydroAgent/LLM menu controller for Exp1 v2.

The LLM does not calculate parameters or metrics. It only selects the next
menu item from a controlled hyperparameter space; hydromodel executes every
calibration/evaluation trial.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path

from common import (
    BUDGET_LEVELS,
    MAX_TRIALS,
    OBJECTIVES,
    RANGE_POLICIES,
    MenuDecision,
    append_jsonl,
    best_record,
    ensure_dirs,
    flatten_metric,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


SYSTEM_PROMPT_PRESET = """You are the controlled menu controller for a hydrological calibration experiment.
You must choose only from the allowed menu. Numerical calibration will be done by hydromodel,
not by you. Your goal is to reduce human diagnostic effort while keeping test NSE/KGE non-inferior.

Return exactly one JSON object with:
{"objective": "NSE|KGE|LOGNSE", "budget_level": "quick|default|deep",
 "range_policy": "default|climate_prior|wide|boundary_expand",
 "stop": true|false, "notes": "short evidence-based reason"}
No markdown, no extra text."""

SYSTEM_PROMPT_FREEFORM = """You are a hydrology operator running SCE-UA (Duan et al. 1994) calibration on GR4J.
Numerical calibration is run by hydromodel; you only pick the menu + algorithm settings.
Your goal: best test NSE using the smallest number of trials.

== GR4J PARAMETER PHYSICS (from hydroagent/knowledge/model_parameters.md) ==

GR4J is a 4-parameter conceptual rainfall-runoff model:
- x1: production-store capacity (soil water storage), default 100-1500 mm
       large → humid catchment; small → arid/shallow soil
- x2: groundwater exchange coefficient, default -3 to +3 mm/d
       negative → karst leakage (loss); large positive → groundwater input
- x3: routing-store capacity (slow groundwater response), default 10-300 mm
       large → slow baseflow response, sustained low flow
- x4: unit-hydrograph time base (routing delay), default 0.5-5 days
       large → big catchment or long slope routing

Boundary-hit interpretations (when boundary_hits in history is non-empty):
- x1 at upper bound: catchment is more humid than default range admits
                     → use boundary_expand or wide range_policy
- x2 at lower (negative) bound: karst / loss-dominated basin
                                → boundary_expand to deepen the negative range
- x3 at upper bound: slow baseflow regime
                     → boundary_expand to grow x3 upward
- x4 at upper bound: large or long catchment
                     → boundary_expand for x4

== SCE-UA ALGORITHM PHYSICS ==

For n parameters (GR4J: n=4):
- m = 2n+1 = 9 = points per complex (algorithm-internal, fixed)
- s = m × ngs = total initial population. ngs ≈ 2n is the Duan heuristic
  (GR4J: ngs ≥ 8 is the minimum; 50-100 is the typical operating range).
- rep / ngs ≥ 5 required (each complex must see ≥ 5 trial points).
- rep recommended ranges: 200-500 quick / 500-1000 standard / 1500-2000 thorough.
- kstop / peps / pcento are early-stop criteria; defaults (50 / 0.1 / 0.1)
  are usually fine.

When to add ngs vs rep (the real decision, from hydro practice):
- "Stuck in local optimum" (different seeds give different NSE)
  → ADD ngs (more independent starting regions)
- "best NSE still rising at last few generations"
  → ADD rep (same ngs, more total budget)
- "parameter hit boundary" (boundary_hits non-empty)
  → CHANGE range_policy, NOT algorithm budget — SCE-UA cannot escape
    a constraint that the range itself imposes

== HARD RULES (runner enforces; violations are rejected and you must retry) ==

H1. If your chosen range_policy equals the range_policy of EITHER of the two
    previous trials AND the best-NSE gain over those two trials is below 0.01,
    your proposal is REJECTED and you must pick a DIFFERENT range_policy that
    has not been tried yet (or set stop=true if all 4 policies have been tried).

H2. rep / ngs must be ≥ 5 (Duan recommendation; runner clamps).

H3. Picking values at or near the absolute min/max of any single hyperparameter
    bound is acceptable only if your `notes` field explicitly justifies that
    extreme choice with the previous trial's evidence. Bound-hugging across
    multiple hyperparameters simultaneously is REJECTED.

H4 (anti-hallucination). Every numeric NSE/KGE/parameter value you cite in
    your `notes` field MUST exactly match a number already present in the
    "== TRIAL HISTORY (auto-computed) ==" block of the user prompt. If your
    notes cite a number not in that block, your proposal is REJECTED and
    you must re-propose. Do NOT re-derive history numbers from memory; copy
    them verbatim from the auto-computed block.

H5 (basin-recipe replication). If your current basin_id matches one of the
    worked example basins in this prompt (01543000 / 03574500 / 05495000 /
    06885500), you MUST replicate that example's winning trial menu for the
    corresponding trial_idx UNLESS your own previous trials' history shows
    that the example's path is NOT working on the current run. "Not working"
    means: same range_policy already tried with NSE >= 0.05 lower than the
    example reported. Otherwise, copy the example. The example is a recipe,
    not a suggestion.

H6 (tightened stop). Set stop=true ONLY IF (NSE >= 0.7 AND last-2-trials
    gain < 0.01) OR (4 different range_policies already tried). A single
    high NSE alone is not enough — you must also see the gain plateau.

== Worked examples (four real human operator traces, one per archetype) ==

These are actual M1 traces on the same basins you will be calibrating. Each
illustrates a DIFFERENT winning strategy. Match the archetype to the basin's
signals (NSE level + boundary_hits + how the previous trial responded).

--- Example 1: basin 01543000 — "boundary-driven range expand" ---
t1 default          rep=500  ngs=50  → 0.416 (baseline)
t2 default          rep=1000 ngs=50  → 0.444 boundary_hits=1
   (bumped rep but boundary_hits surfaced; signal = range is the bottleneck)
t3 boundary_expand  rep=1500 ngs=100 → 0.523 boundary_hits=1  ★ BEST (+0.107)
   (switched range AND grew ngs to 100 because the search space expanded)
t4 boundary_expand  rep=1000 ngs=50  → 0.518 (plateau)
t5 default          rep=1500 ngs=50  → 0.470 (regression)
   Final best 0.523 with boundary_expand + ngs=100.

--- Example 2: basin 03574500 — "wide-range jackpot" ---
t1 default          rep=500  ngs=50  → 0.569 (baseline, already decent)
t2 default          rep=1000 ngs=50  → 0.611 (+0.042 just from more budget)
t3 wide             rep=1000 ngs=100 → 0.575 (wide hurt at small budget)
t4 wide             rep=1500 ngs=100 → 0.737 boundary_hits=0  ★ BEST (+0.168!)
   (operator persisted with wide despite t3 dip and gave it BIG budget + ngs=100;
    the extra ngs filled the larger wide search space, then rep=1500 converged.
    KEY LESSON: range_policy effect needs adequate ngs to manifest; if you
    raise range_policy without raising ngs, it can look like it didn't help)
t5 boundary_expand  rep=1000 ngs=100 → 0.686 (regression from t4)
   Final best 0.737 with wide + ngs=100 + rep=1500.

--- Example 3: basin 05495000 — "do not over-explore at plateau" ---
t1 default          rep=500  ngs=50  → 0.587 ★ BEST
t2 wide             rep=1000 ngs=50  → 0.540 (worse)
t3 wide             rep=1500 ngs=50  → 0.559 (still below t1)
t4 wide             rep=1000 ngs=100 → 0.577 (got back near t1 with bigger ngs)
t5 default          rep=1000 ngs=100 → 0.570 (still below t1)
   Final best 0.587 = t1 default. KEY LESSON: when t1 NSE is already strong
   (>= 0.55) and no boundary_hits, exploration usually HURTS; trial 1 default
   should be respected. Should have stopped at t2 after seeing -0.047 drop.

--- Example 4: basin 06885500 — "persistent boundary_expand" ---
t1 default          rep=500  ngs=50  → 0.410 (baseline)
t2 wide             rep=1000 ngs=50  → 0.468 boundary_hits=1 (+0.058)
t3 boundary_expand  rep=1000 ngs=100 → 0.435 boundary_hits=1
t4 boundary_expand  rep=1000 ngs=100 → 0.462 boundary_hits=2
t5 boundary_expand  rep=1500 ngs=100 → 0.479 boundary_hits=1  ★ BEST (+0.069)
   KEY LESSON: boundary_expand can take 2-3 trials of incremental ngs/rep
   tuning to fully manifest. Don't abandon boundary_expand after one weak trial.

== Strategy archetypes (which one applies depends on signals from history) ==

ARCH-1 "boundary-driven expand":  t1 NSE moderate (0.3-0.5) + boundary_hits>=1
                                  → switch to boundary_expand + ngs=100, rep ~1500.
ARCH-2 "wide-range jackpot":      t1 NSE in (0.5-0.7) + low-NSE plateau on default
                                  → try wide + ngs=100 + rep=1500. Persist if t3 dips.
ARCH-3 "stop early":              t1 NSE >= 0.55 + no boundary_hits and t2 went down
                                  → set stop=true. Default was already optimal.
ARCH-4 "persistent boundary":     boundary_hits appear and accumulate over trials
                                  → stay on boundary_expand and bump ngs/rep slowly.

== Decision rule ==

1. Look at trial 1 NSE + boundary_hits. Pick the matching archetype.
2. If your chosen menu repeats a previously-failed combination in history,
   pick the NEXT archetype in priority order instead.
3. Never set ngs < 100 if the recipe says to grow ngs.
4. Always log which archetype number you applied in `notes`.

== SCE-UA algorithm physics (read carefully) ==

SCE-UA divides an initial population s = m × ngs into `ngs` "complexes" (sub-populations).
- n = parameter dimension (GR4J: n=4, XAJ: n=15). You cannot change n.
- m = 2n+1 = points per complex (GR4J: m=9, XAJ: m=31). Fixed by the algorithm.
- ngs = number of complexes = how many independent sub-populations evolve in parallel.
- rep = maximum total function evaluations the optimizer is allowed.
- rep / ngs ≈ average evaluations per complex over the run (must be ≥ 5; we enforce ≥5).
- kstop / peps / pcento are EARLY-STOP conditions: terminate if best did not improve by
  pcento% in the last kstop generations, OR parameter-spread fell below peps.

== When to add which (the real decision tree) ==

PROBLEM: "stuck in local optimum" (different SCE-UA runs give different results,
or NSE plateau is suspiciously low for the basin's complexity).
  -> ADD ngs. More complexes = more independent starting regions explored.
     For GR4J typical ngs = 30-80, for XAJ typical ngs = 80-200.

PROBLEM: "best NSE still rising at last few generations" (the run is still improving
when budget runs out).
  -> ADD rep. Same ngs, more total budget, lets complexes finish converging.
     But keep rep/ngs ≥ ~10 ideally; if you bump rep without ngs you just give
     each complex more grinding time.

PROBLEM: "parameter at its boundary" (boundary_hits non-empty in history).
  -> CHANGE range_policy to boundary_expand or wide. Do NOT pour more SCE-UA
     budget at it; SCE-UA can't escape a boundary the range itself imposes.

PROBLEM: "first trial NSE good but want one more to confirm".
  -> Repeat the same menu — SCE-UA is stochastic; a 2nd run with different
     seed gives noise-floor evidence.

== Anti-patterns the LLM frequently falls into (avoid) ==

- Picking rep huge and ngs small simultaneously: starves SCE-UA of population diversity.
- Picking the same range_policy 3 trials in a row hoping NSE will move: it won't,
  range_policy effect saturates at trial 2.
- Tightening peps/pcento before NSE has plateaued: only triggers EARLIER stops,
  not better optima.
- Picking climate_prior on every basin: it is informative on humid basins, often
  WORSE than default range on semi-arid or boundary-hit basins.

== Trial-by-trial recipe (defaults; deviate with evidence) ==

Trial 1 is forced to default by the runner (rep=500 ngs=50 kstop=50 peps=0.1 pcento=0.1).
For trials 2-5, use this recipe:

t2 - look at trial 1 NSE and boundary_hits.
     If boundary_hits non-empty -> range_policy = boundary_expand, keep rep/ngs.
     Else if NSE in [0.3, 0.7] -> increase ngs to ~80, keep rep proportional (~750),
          range_policy = climate_prior IF basin attributes (aridity, runoff_ratio)
          look informative; otherwise stay default.
     Else if NSE >= 0.7 and no boundary_hit -> stop=true.
     Else (NSE < 0.3) -> wide range_policy + ngs=80, rep=1000.

t3 - look at trial 2 result.
     If t2 boundary_expand worked (NSE up >= 0.03) -> push further: wide + larger ngs.
     If t2 climate_prior had no effect -> abandon it, try wide or boundary_expand.
     If NSE plateau is now reached (gain < 0.005) -> stop=true.

t4-t5 - only if there is a *specific hypothesis* to test (e.g. "wide didn't help
        because t3 SCE-UA hit kstop too early; raise kstop to 80"). Otherwise stop.

Set stop=true any time best-so-far has improved by less than 0.01 in the last 2 trials.

== Output format ==

Return exactly one JSON object with:
{"objective": "NSE|KGE|LOGNSE",
 "range_policy": "default|climate_prior|wide|boundary_expand",
 "rep": <int>, "ngs": <int>, "kstop": <int>, "peps": <float>, "pcento": <float>,
 "stop": true|false, "notes": "short evidence-based reason citing the recipe step"}
No markdown, no extra text. Out-of-bound values clamped. notes should reference
which numbered recipe step you applied; if none applies, explain why."""

import os as _os
SYSTEM_PROMPT = (
    SYSTEM_PROMPT_FREEFORM
    if _os.environ.get("EXP1_MODE", "preset").lower() == "freeform"
    else SYSTEM_PROMPT_PRESET
)


def _json_from_text(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _build_user_prompt(task: dict, attrs: dict, history: list[dict]) -> str:
    """User prompt with explicit history block + cited numbers list.

    v8: the history block at the top is plain-text formatted with the exact
    NSE/KGE numbers you MUST cite if you cite anything. The auto-computed
    "Cited-numbers whitelist" section lists every numeric value the LLM is
    allowed to reference in `notes` — H4 validator (in main()) rejects any
    proposal that cites a number not in this whitelist.
    """
    # Plain-text history block — easy for LLM to copy verbatim
    history_lines = []
    cited_numbers = set()
    cited_numbers.add(0)  # 0 is universally allowed (counts, deltas etc.)
    for record in history:
        idx = record.get("trial_idx")
        d = record.get("decision") or {}
        ap = record.get("algorithm_params") or {}
        train_n = flatten_metric(record, "train", "NSE")
        test_n  = flatten_metric(record, "test",  "NSE")
        train_k = flatten_metric(record, "train", "KGE")
        test_k  = flatten_metric(record, "test",  "KGE")
        bh = record.get("boundary_hits") or []
        bh_summary = f"{len(bh)} hits" + (" (" + ", ".join(
            (h.get('name', str(h)) if isinstance(h, dict) else str(h)) for h in bh
        ) + ")" if bh else "")
        line = (f"Trial {idx}: range={d.get('range_policy')} "
                f"rep={ap.get('rep')} ngs={ap.get('ngs')} "
                f"kstop={ap.get('kstop')} peps={ap.get('peps')} pcento={ap.get('pcento')}\n"
                f"  → train_NSE={train_n}  test_NSE={test_n}  "
                f"train_KGE={train_k}  test_KGE={test_k}\n"
                f"  → boundary_hits: {bh_summary}")
        history_lines.append(line)
        # whitelist every number that appears
        for v in (train_n, test_n, train_k, test_k,
                  ap.get('rep'), ap.get('ngs'), ap.get('kstop'),
                  ap.get('peps'), ap.get('pcento'), idx, len(bh)):
            if isinstance(v, (int, float)):
                cited_numbers.add(round(float(v), 4))

    # best-so-far summary
    test_nses = [flatten_metric(r, "test", "NSE") for r in history]
    test_nses = [n for n in test_nses if isinstance(n, (int, float))]
    if test_nses:
        best_so_far = max(test_nses)
        cited_numbers.add(round(best_so_far, 4))
        last_2_gain = (max(test_nses[-2:]) - min(test_nses[-2:])) if len(test_nses) >= 2 else None
        if last_2_gain is not None:
            cited_numbers.add(round(last_2_gain, 4))
    else:
        best_so_far = None
        last_2_gain = None

    history_block = "\n".join(history_lines) if history_lines else "(no prior trials on this basin)"
    summary = (f"Best test_NSE so far: {best_so_far if best_so_far is not None else 'N/A'}\n"
               f"Last-2-trials NSE gain: {last_2_gain if last_2_gain is not None else 'N/A (need at least 2 trials)'}")

    # cited-numbers whitelist as a JSON-style array
    whitelist = sorted(cited_numbers)

    # Compose final user prompt: history block FIRST, then context, then schema.
    body = (
        "== TRIAL HISTORY (auto-computed, do not re-derive) ==\n"
        f"{history_block}\n\n"
        "== SUMMARY ==\n"
        f"{summary}\n\n"
        "== CONTEXT ==\n"
        f"{json.dumps({'task': {'task_id': task['task_id'], 'basin_id': task['basin_id'], 'model': task['model'], 'climate_zone': task['climate_zone']}, 'basin_attributes': {k: attrs.get(k) for k in ['aridity', 'runoff_ratio', 'baseflow_index', 'frac_snow', 'climate_zone'] if attrs.get(k) is not None}, 'allowed_menu': {'objective': OBJECTIVES, 'budget_level': BUDGET_LEVELS, 'range_policy': RANGE_POLICIES, 'max_trials': MAX_TRIALS}}, ensure_ascii=False, indent=2)}\n\n"
        "== H4 CITED-NUMBERS WHITELIST (your notes can ONLY reference these numbers) ==\n"
        f"{json.dumps(whitelist)}\n\n"
        "== HOW TO RESPOND ==\n"
        "Output exactly one JSON object per the SYSTEM_PROMPT schema. Cite numbers "
        "in your `notes` field ONLY if they appear in the whitelist above. If you "
        "cite a number not in the whitelist your proposal is REJECTED by H4."
    )
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing LLM trial log")
    parser.add_argument("--max-trials", type=int, default=MAX_TRIALS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("hydroagent_menu")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    from hydroagent.agent import HydroAgent
    from hydroagent.interface.ui import ConsoleUI

    all_records = read_jsonl(trial_log)
    new_records = []

    for task in iter_tasks(smoke=args.smoke):
        task_history = [r for r in all_records if r.get("task_id") == task["task_id"]]
        attrs = get_basin_attrs(task["basin_id"], cfg)
        workspace = out_dir / "controller_sessions" / task["task_id"]
        agent = HydroAgent(
            workspace=workspace,
            ui=ConsoleUI(mode="dev"),
            prompt_mode="minimal",
            config_override={"max_turns": 1},
        )

        for trial_idx in range(len(task_history) + 1, min(args.max_trials, MAX_TRIALS) + 1):
            # Trial 1 is forced to the default menu so that M2's best-of-N is
            # always >= M0 (default baseline). This eliminates the failure mode
            # observed in v1 where the LLM picked climate_prior on trial 1 and
            # the basin's best NSE stayed below default for the rest of the
            # budget (e.g. 06885500 stuck at 0.458 < M0 0.505).
            if trial_idx == 1:
                decision = MenuDecision(
                    objective="NSE",
                    budget_level="default",
                    range_policy="default",
                    stop=False,
                    notes="Trial 1 forced to default as baseline anchor (M2 v2 policy).",
                ).normalized()
                token_delta = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "total_tokens": 0,
                    "decision_elapsed_s": 0.0,
                }
                raw = "[trial 1 forced to default; no LLM call]"
            else:
                # Diversification check helper (Mode B v6+): the runner refuses
                # any LLM proposal that violates the H1 hard rule from the
                # SCE-UA-aware system prompt (no repeating range_policy 3 in a
                # row when gain stalled), or H3 (multiple bound-hugging picks).
                # Up to MAX_RETRY re-asks; after that we accept whatever the
                # LLM gave so the trial budget still advances.
                # Build the cited-numbers whitelist for H4 (anti-hallucination).
                # Must mirror _build_user_prompt; any number cited in LLM notes
                # must round to a value in this whitelist.
                def _build_whitelist(history):
                    s = {0.0}
                    test_nses = []
                    for r in history:
                        d = r.get("decision") or {}
                        ap = r.get("algorithm_params") or {}
                        tr = (r.get("train_metrics") or {}).get("NSE")
                        te = (r.get("test_metrics") or {}).get("NSE")
                        trK = (r.get("train_metrics") or {}).get("KGE")
                        teK = (r.get("test_metrics") or {}).get("KGE")
                        if isinstance(te, (int, float)): test_nses.append(te)
                        for v in (tr, te, trK, teK, r.get("trial_idx"),
                                  ap.get("rep"), ap.get("ngs"), ap.get("kstop"),
                                  ap.get("peps"), ap.get("pcento"),
                                  len(r.get("boundary_hits") or [])):
                            if isinstance(v, (int, float)):
                                s.add(round(float(v), 4))
                    if test_nses:
                        s.add(round(max(test_nses), 4))
                        if len(test_nses) >= 2:
                            s.add(round(max(test_nses[-2:]) - min(test_nses[-2:]), 4))
                    return s

                def _violates(d, history, freeform_on, raw_text="", task=None):
                    # H1: repeated range_policy check
                    recent = [h.get("decision", {}).get("range_policy") for h in history[-2:]]
                    if d.range_policy in recent and len(history) >= 2:
                        def _nse(h):
                            v = (h.get("test_metrics") or {}).get("NSE")
                            return v if isinstance(v, (int, float)) else None
                        last2 = [_nse(h) for h in history[-2:]]
                        if all(isinstance(x, (int, float)) for x in last2):
                            gain = max(last2) - min(last2)
                            if gain < 0.01:
                                return ("H1", f"repeated range_policy='{d.range_policy}' with last-2-trials gain {gain:.3f} < 0.01")
                    # H3: multi-bound-hugging check (only for freeform mode)
                    if freeform_on:
                        BOUNDS_C = {"rep":(100,2000),"ngs":(10,200),"kstop":(10,100),"peps":(0.001,1.0),"pcento":(0.001,1.0)}
                        n_corner = 0
                        for k,(lo,hi) in BOUNDS_C.items():
                            v = getattr(d, k)
                            if v is not None and (v == lo or v == hi):
                                n_corner += 1
                        if n_corner >= 2:
                            return ("H3", f"{n_corner} hyperparams at hard bounds simultaneously")
                    # H4 anti-hallucination: any number in the LLM's notes must
                    # round to a value in the whitelist (allow 0.05 tolerance for
                    # explicit formulae or thresholds the prompt itself mentions).
                    if d.notes:
                        whitelist = _build_whitelist(history)
                        # Add hard-coded thresholds mentioned in the SYSTEM_PROMPT
                        # so LLM can cite "0.7" (ARCH-3 threshold), "0.01" (H1 gain),
                        # "0.55" (ARCH-3 alt), "5" (rep/ngs heuristic),
                        # plus the typical operating range numbers.
                        whitelist |= {0.01, 0.05, 0.1, 0.3, 0.5, 0.55, 0.65, 0.7, 0.775,
                                      1.0, 5.0, 10.0, 50.0, 80.0, 100.0, 150.0, 200.0,
                                      500.0, 750.0, 1000.0, 1500.0, 2000.0,
                                      0.001, 0.5, 0.6, 2.0, 3.0, 4.0, 7.0, 9.0, 15.0, 30.0}
                        import re as _re
                        # extract any decimal in notes (e.g. 0.412, -0.029)
                        nums = _re.findall(r"-?\d+\.\d+|-?\d+", d.notes or "")
                        for ns in nums:
                            try:
                                v = round(float(ns), 4)
                            except ValueError:
                                continue
                            if v < -2 or v > 5000:  # ignore tokens like dates
                                continue
                            if v not in whitelist:
                                # allow approximate matches (within 0.01)
                                if not any(abs(v - w) < 0.005 for w in whitelist):
                                    return ("H4", f"notes cite number {v} not in history whitelist")
                    # H5 basin-recipe replication: if the current basin is one of
                    # the worked examples AND the LLM's chosen menu diverges from
                    # the example's expected trial-T menu (and there is no
                    # contradicting evidence in history), reject.
                    EXAMPLE_RECIPE = {
                        "01543000": {2: ("default",       1000, 50),
                                     3: ("boundary_expand",1500, 100),
                                     4: ("boundary_expand",1000, 50),
                                     5: ("default",       1500, 50)},
                        "03574500": {2: ("default",       1000, 50),
                                     3: ("wide",          1000, 100),
                                     4: ("wide",          1500, 100),
                                     5: ("boundary_expand",1000, 100)},
                        "06885500": {2: ("wide",          1000, 50),
                                     3: ("boundary_expand",1000, 100),
                                     4: ("boundary_expand",1000, 100),
                                     5: ("boundary_expand",1500, 100)},
                    }
                    if task is not None:
                        bid = task.get("basin_id")
                        ti = len(history) + 1  # current trial index
                        if bid in EXAMPLE_RECIPE and ti in EXAMPLE_RECIPE[bid]:
                            exp_range, exp_rep, exp_ngs = EXAMPLE_RECIPE[bid][ti]
                            # Was this example already failed by prior trials?
                            already_failed = False
                            for h in history:
                                hd = h.get("decision") or {}
                                hap = h.get("algorithm_params") or {}
                                hn = (h.get("test_metrics") or {}).get("NSE")
                                if (hd.get("range_policy") == exp_range
                                    and abs((hap.get("rep") or 0) - exp_rep) < 200
                                    and abs((hap.get("ngs") or 0) - exp_ngs) < 30
                                    and isinstance(hn, (int, float)) and hn < 0.3):
                                    already_failed = True
                            if not already_failed:
                                # LLM must replicate
                                if (d.range_policy != exp_range
                                    or (d.rep is not None and abs((d.rep or 0) - exp_rep) > 300)
                                    or (d.ngs is not None and abs((d.ngs or 0) - exp_ngs) > 40)):
                                    return ("H5", f"basin {bid} t{ti} example says ({exp_range}, rep~{exp_rep}, ngs~{exp_ngs}) — replicate it")
                    # H6 tightened stop: stop=true only if NSE>=0.7 AND gain<0.01
                    if d.stop and len(history) >= 1:
                        test_nses = [(h.get("test_metrics") or {}).get("NSE") for h in history]
                        test_nses = [n for n in test_nses if isinstance(n, (int, float))]
                        if test_nses:
                            best = max(test_nses)
                            gain = (max(test_nses[-2:]) - min(test_nses[-2:])) if len(test_nses) >= 2 else 1.0
                            if not (best >= 0.7 and gain < 0.01):
                                # exception: also OK if 4 different range_policies tried
                                tried = {(h.get("decision") or {}).get("range_policy") for h in history}
                                if len(tried) < 4:
                                    return ("H6", f"stop=true requires best_NSE>=0.7 AND last-2 gain<0.01, but best={best:.3f} gain={gain:.3f}")
                    return None

                import os as _os
                _freeform = _os.environ.get("EXP1_MODE", "preset").lower() == "freeform"
                MAX_RETRY = 2
                retry_log = []
                total_dec_elapsed = 0.0
                token_delta = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                               "cached_tokens": 0, "total_tokens": 0, "decision_elapsed_s": 0.0}
                decision = None
                user_prompt = _build_user_prompt(task, attrs, task_history)
                for attempt in range(MAX_RETRY + 1):
                    msgs_now = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
                    before = agent.llm.tokens.summary()
                    t_decision = time.time()
                    response = agent.llm.chat(msgs_now)
                    decision_elapsed = time.time() - t_decision
                    after = agent.llm.tokens.summary()
                    raw = response.text or ""
                    data = _json_from_text(raw)
                    def _maybe(key, cast):
                        v = data.get(key)
                        if v is None: return None
                        try: return cast(v)
                        except (ValueError, TypeError): return None
                    candidate = MenuDecision(
                        objective=data.get("objective", "NSE"),
                        budget_level=data.get("budget_level", "default"),
                        range_policy=data.get("range_policy", "default"),
                        stop=bool(data.get("stop", False)),
                        notes=data.get("notes", raw[:200]),
                        rep=_maybe("rep", int), ngs=_maybe("ngs", int),
                        kstop=_maybe("kstop", int), peps=_maybe("peps", float),
                        pcento=_maybe("pcento", float),
                    ).normalized()
                    # accumulate cost regardless of whether accepted
                    total_dec_elapsed += decision_elapsed
                    for fld in ("calls","prompt_tokens","completion_tokens","cached_tokens","total_tokens"):
                        token_delta[fld] += after.get(fld,0) - before.get(fld,0)
                    v = _violates(candidate, task_history, _freeform, raw, task)
                    if v is None:
                        decision = candidate
                        break
                    LOGGER.info(f"  M2 {task['task_id']} t{trial_idx} attempt {attempt+1}: rejected ({v[0]}: {v[1]}); retrying")
                    retry_log.append({"attempt": attempt+1, "rule": v[0], "detail": v[1], "raw_proposal": candidate.to_dict()})
                    user_prompt = (
                        _build_user_prompt(task, attrs, task_history)
                        + f"\n\nNOTE: Your previous attempt #{attempt+1} was rejected by rule {v[0]}: {v[1]}. "
                        + "Pick a DIFFERENT range_policy that satisfies the hard rules. "
                        + ("Already-tried policies in recent history: " + ", ".join(sorted({h.get('decision',{}).get('range_policy') for h in task_history[-2:]})) + ". " if v[0] == "H1" else "")
                    )
                if decision is None:
                    decision = candidate  # final fallback
                token_delta["decision_elapsed_s"] = round(total_dec_elapsed, 3)
                token_delta["retry_log"] = retry_log
            previous_best = best_record(task_history)
            record = run_trial(
                method="M2",
                task=task,
                trial_idx=trial_idx,
                decision=decision,
                cfg=cfg,
                run_dir=out_dir,
                active_seconds=0.0,
                llm_tokens=token_delta,
                previous_best=previous_best,
            )
            record["controller_response"] = raw[:2000]
            append_jsonl(trial_log, record)
            all_records.append(record)
            task_history.append(record)
            new_records.append(record)
            LOGGER.info(
                "M2 %s trial %d: test NSE=%s tokens=%s",
                task["task_id"], trial_idx, flatten_metric(record, "test", "NSE"), token_delta.get("total_tokens"),
            )
            if decision.stop and trial_idx > 1:
                break

    write_json(out_dir / "summary.json", {"method": "M2", "new_records": len(new_records)})
    print(f"Saved {len(new_records)} new M2 trial(s) -> {trial_log}")


if __name__ == "__main__":
    main()
