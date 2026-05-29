"""HydroAgent end-to-end demo: natural-language calibration on CAMELS-US.

This is the canonical entry-point experiment script for the HydroAgent handover.
It shows how a single natural-language query drives the HydroAgent agentic loop
through ``validate_basin -> calibrate_model -> evaluate_model`` end-to-end,
using GR4J + SCE-UA on a handful of representative CAMELS-US basins.

Other scripts under ``experiment/`` either bypass the agentic loop (using the
LLM client directly) or are pure-numerical experiments. This file is the only
one that exercises ``HydroAgent.run(query)`` end-to-end and is the recommended
starting point for anyone new to the project.

Run:
    PYTHONUTF8=1 python experiment/exp1/exp1_hydroagent.py

Prerequisites:
    - ``configs/private.py`` filled in with OPENAI_API_KEY / OPENAI_BASE_URL /
      DATASET_DIR (pointing at a parent dir that contains ``CAMELS_US/``).
    - CAMELS-US dataset available on disk under ``DATASET_DIR/CAMELS_US/``.

Output:
    Per-basin agent workspaces under ``experiment/exp1/results/<basin_id>/``
    plus a single summary ``experiment/exp1/results/exp1_hydroagent_results.json``
    listing tool_sequence / calibration_dir / wall_time / token cost per run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydroagent.agent import HydroAgent
from hydroagent.interface.ui import ConsoleUI

# Three CAMELS-US basins spanning easy / medium / hard for GR4J:
#   12025000  Pacific NW humid          (baseline NSE ~ 0.75)
#   07197000  Ark-White-Red subhumid    (baseline NSE ~ 0.50)
#   08101000  Texas semiarid flashy     (baseline NSE ~ -0.83, GR4J structurally weak)
BASINS = [
    ("12025000", "easy"),
    ("07197000", "medium"),
    ("08101000", "hard"),
]
OUT = Path(__file__).parent / "results"


def build_query(basin_id: str) -> str:
    """Single natural-language calibration query handed to the agent."""
    return (
        f"请率定 GR4J 模型,流域 {basin_id},使用 SCE-UA 算法。"
        f"请先验证流域数据,然后进行率定,最后分别评估训练期和测试期的 NSE 与 KGE。"
    )


def run_one(basin_id: str, difficulty: str) -> dict:
    """Run one basin through the full HydroAgent agentic loop."""
    workspace = OUT / basin_id
    workspace.mkdir(parents=True, exist_ok=True)
    agent = HydroAgent(workspace=workspace, ui=ConsoleUI(mode="dev"))

    t0 = time.time()
    error: str | None = None
    try:
        agent.run(build_query(basin_id))
    except Exception as exc:  # noqa: BLE001  -- record any failure verbatim
        error = str(exc)
    elapsed = round(time.time() - t0, 1)

    log = list(agent.memory._log)
    tools = [e.get("tool", "") for e in log if e.get("tool")]
    cal_dir = ""
    for entry in log:
        if entry.get("tool") == "calibrate_model":
            summary = entry.get("result_summary")
            if isinstance(summary, dict) and summary.get("calibration_dir"):
                cal_dir = str(summary["calibration_dir"])
                break

    try:
        token_summary = agent.llm.tokens.summary()
    except Exception:
        token_summary = {}

    return {
        "basin_id": basin_id,
        "difficulty": difficulty,
        "tool_sequence": tools,
        "calibration_dir": cal_dir,
        "agent_turns": len(log),
        "wall_time_s": elapsed,
        "error": error,
        "total_tokens": token_summary.get("total_tokens", 0),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    records = [run_one(bid, diff) for bid, diff in BASINS]

    summary_path = OUT / "exp1_hydroagent_results.json"
    summary_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nDone. Wrote {len(records)} records to {summary_path}.")
    for r in records:
        if r["error"]:
            status = f"FAILED: {r['error'][:60]}"
        else:
            status = "OK"
        print(
            f"  {r['basin_id']} [{r['difficulty']:6}]  {status}  "
            f"turns={r['agent_turns']}  tokens={r['total_tokens']}  "
            f"time={r['wall_time_s']}s"
        )


if __name__ == "__main__":
    main()
