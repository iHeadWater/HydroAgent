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

SYSTEM_PROMPT_FREEFORM = """You are a hydrology operator running SCE-UA (Duan et al. 1994) calibration trial by trial.
Numerical calibration is run by hydromodel; you only pick the menu + algorithm settings.
Your goal: best test NSE/KGE using the smallest number of trials.

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
    compact_history = []
    for record in history:
        compact_history.append({
            "trial_idx": record.get("trial_idx"),
            "decision": record.get("decision"),
            "train_NSE": flatten_metric(record, "train", "NSE"),
            "test_NSE": flatten_metric(record, "test", "NSE"),
            "train_KGE": flatten_metric(record, "train", "KGE"),
            "test_KGE": flatten_metric(record, "test", "KGE"),
            "boundary_hits": record.get("boundary_hits", []),
        })
    return json.dumps({
        "task": {
            "task_id": task["task_id"],
            "basin_id": task["basin_id"],
            "model": task["model"],
            "climate_zone": task["climate_zone"],
        },
        "basin_attributes": {
            k: attrs.get(k)
            for k in ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
            if attrs.get(k) is not None
        },
        "allowed_menu": {
            "objective": OBJECTIVES,
            "budget_level": BUDGET_LEVELS,
            "range_policy": RANGE_POLICIES,
            "max_trials": MAX_TRIALS,
        },
        "history": compact_history,
        "decision_guidance": [
            "Use climate_prior on the first trial when basin attributes are informative.",
            "Use boundary_expand only when previous best has boundary_hits.",
            "Use deep only when metrics are poor or previous improvement is still plausible.",
            "Set stop=true when the best result is already satisfactory or additional trials are unlikely to help.",
        ],
    }, ensure_ascii=False)


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
                def _violates(d, history, freeform_on):
                    # H1: repeated range_policy check
                    recent = [h.get("decision", {}).get("range_policy") for h in history[-2:]]
                    if d.range_policy in recent and len(history) >= 2:
                        # gain over last 2 trials
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
                    v = _violates(candidate, task_history, _freeform)
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
