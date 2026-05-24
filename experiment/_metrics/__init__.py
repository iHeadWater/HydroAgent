"""Shared metric computation modules for paper experiments.

Used by both exp3_knowledge_ablation.py and exp4_capability_boundaries.py
so that workflow/efficiency/diagnostic metrics are defined ONCE and applied
consistently.

Module map:
  - workflow.py     workflow route metrics (core_tool_coverage, detours, etc.)
  - efficiency.py   token / call / time metrics
  - diag_score.py   DiagScore rubric loader + scoring aggregator (Exp 3)
  - exp_iv.py       capability-boundary metrics (semantic_consistency,
                    planning_scale_ratio, completion_ratio, failure_class)
"""

from . import workflow, efficiency  # noqa: F401

__all__ = ["workflow", "efficiency"]
