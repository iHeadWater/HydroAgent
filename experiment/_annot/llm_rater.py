"""LLM-as-second-rater for DiagScore.

Reads final-report text files from results/paper/exp3/final_reports/<K>_<T>.txt,
calls the configured LLM with the rubric prompt + report text, parses
structured scores into CSV.

Usage:
  PYTHONUTF8=1 .venv/Scripts/python.exe experiment/_annot/llm_rater.py \\
    --reports-dir results/paper/exp3/final_reports/ \\
    --out experiment/_annot/llm_scores.csv

The LLM call uses temperature=0.0 (deterministic) and JSON-mode output where
supported. The rubric text is read from diag_rubric.md so human and LLM
raters see the identical specification.
"""

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

DIMENSIONS = ["D1", "D2", "D3", "D4", "D5"]


def build_prompt(rubric_md: str, report_text: str) -> str:
    return (
        "You are a hydrological-modeling reviewer. Score the following agent "
        "report using the DiagScore rubric below. Apply each dimension "
        "independently and provide ONLY a JSON object with integer scores "
        "0, 1, or 2 for each dimension.\n\n"
        "## Rubric\n\n"
        f"{rubric_md}\n\n"
        "## Agent report to score\n\n"
        "```\n"
        f"{report_text}\n"
        "```\n\n"
        "## Output\n\n"
        "Return ONLY a JSON object in this exact format (no other text):\n"
        '{\"D1\": 0|1|2, \"D2\": 0|1|2, \"D3\": 0|1|2, \"D4\": 0|1|2, \"D5\": 0|1|2, \"reasoning\": \"brief 1-line justification\"}\n'
    )


def parse_response(text: str) -> dict | None:
    """Extract D1-D5 scores from LLM response."""
    # Try JSON block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        # Bare JSON
        m = re.search(r"(\{[^{}]*?\"D5\"\s*:\s*[0-2][^{}]*?\})", text, re.DOTALL)
    if not m:
        logger.warning(f"No JSON found in LLM response: {text[:200]}")
        return None
    try:
        scores = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed: {e}")
        return None
    out = {}
    for d in DIMENSIONS:
        v = scores.get(d)
        if isinstance(v, (int, float)) and 0 <= v <= 2:
            out[d] = int(v)
        else:
            return None  # malformed
    out["reasoning"] = scores.get("reasoning", "")[:200]
    return out


def rate_report(llm, rubric_md: str, report_text: str) -> dict | None:
    prompt = build_prompt(rubric_md, report_text)
    try:
        # Use chat with no tools, temperature 0
        resp = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return parse_response(resp.text)
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return None


def parse_filename(name: str) -> tuple[str, str] | None:
    """Parse <K>_<T>.txt -> (condition, task)."""
    m = re.match(r"^(K\d[a-z]?)_(T\d)\.txt$", name)
    if not m:
        return None
    return m.group(1), m.group(2)


def main():
    ap = argparse.ArgumentParser(description="LLM-as-second-rater for DiagScore")
    ap.add_argument("--reports-dir", default="results/paper/exp3/final_reports/")
    ap.add_argument("--rubric", default="experiment/_annot/diag_rubric.md")
    ap.add_argument("--out", default="experiment/_annot/llm_scores.csv")
    # Rater model overrides: the rater MUST differ from the agent's model to
    # avoid self-evaluation bias. Agent runs on DeepSeek -> rate with Qwen here.
    ap.add_argument("--rater-model", default=None, help="Override LLM model for rating")
    ap.add_argument("--rater-base-url", default=None, help="Override API base_url")
    ap.add_argument("--rater-api-key", default=None, help="Override API key")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    rubric_path = Path(args.rubric)
    if not rubric_path.exists():
        logger.error(f"Rubric not found: {rubric_path}")
        sys.exit(1)
    rubric_md = rubric_path.read_text(encoding="utf-8")

    reports_dir = Path(args.reports_dir)
    if not reports_dir.exists():
        logger.error(f"Reports dir not found: {reports_dir}")
        sys.exit(1)

    # Lazy import to avoid loading LLM if not needed
    from hydroagent.config import load_config
    from hydroagent.llm import LLMClient
    cfg = load_config()
    # Resolve rater credentials: CLI flag > configs.private RATER_* > agent default.
    try:
        import configs.private as _priv
    except Exception:
        _priv = None
    model = args.rater_model or getattr(_priv, "RATER_MODEL", None)
    base_url = args.rater_base_url or getattr(_priv, "RATER_BASE_URL", None)
    api_key = args.rater_api_key or getattr(_priv, "RATER_API_KEY", None)
    if model:
        cfg["llm"]["model"] = model
    if base_url:
        cfg["llm"]["base_url"] = base_url
    if api_key:
        cfg["llm"]["api_key"] = api_key
    if cfg["llm"].get("model") == load_config()["llm"].get("model"):
        logger.warning("Rater model == agent model: self-evaluation bias risk! "
                       "Set RATER_MODEL in configs/private.py to a different provider.")
    logger.info(f"Rater model: {cfg['llm'].get('model')} @ {cfg['llm'].get('base_url')}")
    llm = LLMClient(cfg["llm"])

    out_path = Path(args.out)
    rows: list[dict] = []
    n_skipped = 0

    for report_file in sorted(reports_dir.glob("*.txt")):
        parsed = parse_filename(report_file.name)
        if not parsed:
            logger.info(f"Skipping {report_file.name} (does not match <K>_<T>.txt)")
            n_skipped += 1
            continue
        cond, task = parsed
        text = report_file.read_text(encoding="utf-8")
        logger.info(f"Rating {cond} × {task} ({len(text)} chars)...")
        scores = rate_report(llm, rubric_md, text)
        if scores is None:
            logger.warning(f"  -> rating failed for {cond} {task}")
            rows.append({
                "task_id": task, "condition": cond,
                "D1": "", "D2": "", "D3": "", "D4": "", "D5": "",
                "notes": "LLM rating failed"
            })
            continue
        rows.append({
            "task_id": task, "condition": cond,
            **{d: scores[d] for d in DIMENSIONS},
            "notes": scores.get("reasoning", ""),
        })
        logger.info(f"  -> {scores}")

    # Write CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["task_id", "condition", *DIMENSIONS, "notes"])
        w.writeheader()
        w.writerows(rows)
    logger.info(f"Wrote {len(rows)} ratings to {out_path}; skipped {n_skipped} files")


if __name__ == "__main__":
    main()
