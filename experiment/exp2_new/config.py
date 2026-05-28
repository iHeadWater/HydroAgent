"""Configuration for new Exp2: LLM-position calibration on good/medium basins.

Differences from old exp2:
- GR4J only (no XAJ)
- 5-10 good/medium basins picked from exp1_new pool (skip the hard ones)
- Parallel at task level (Pool of N basins)
- D method reused from exp1_new M2 via adapter (no rerun)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXP_DIR / "results"
TABLES_DIR = EXP_DIR / "tables"
FIGURES_DIR = EXP_DIR / "figures"

# Reuse the train/test period and OBJECTIVE from old exp2
TRAIN_PERIOD = ["2000-01-01", "2009-12-31"]
TEST_PERIOD = ["2010-01-01", "2014-12-31"]
OBJECTIVE = "NSE"

# Method assignment:
#   A (standard SCE-UA, no LLM)        -> REUSE exp1_new M0 via adapter
#   B (Zhu direct param proposal)      -> RUN (B_MAX_ITERS iterations)
#   C (LLM + scipy local search)        -> RUN (C_MAX_ITERS iterations)
#   D (HydroAgent feedback loop)       -> REUSE exp1_new M2 via adapter
# B/C run at least MIN_ITERS, then stop once best train NSE has not improved
# (> EARLY_STOP_EPS) for EARLY_STOP_PATIENCE consecutive iterations, capped at
# MAX_ITERS. This lets basins that are still improving at 50 keep going.
MIN_ITERS = 50
MAX_ITERS = 200
EARLY_STOP_PATIENCE = 10
EARLY_STOP_EPS = 0.005
# (legacy aliases kept so old call sites still import cleanly)
B_MAX_ITERS = MAX_ITERS
C_MAX_ITERS = MAX_ITERS

# Reused sources
EXP1_NEW_M0_LOG = ROOT / "experiment" / "exp1_new" / "results" / "m0_baseline" / "trials.jsonl"
EXP1_NEW_M2_LOG = ROOT / "experiment" / "exp1_new" / "results" / "m2_adaptive" / "trials.jsonl"

# C local search budget (scipy SLSQP for gr4j is fast)
LOCAL_SEARCH_BUDGET = {
    "gr4j": {"method": "SLSQP", "max_iterations": 30},
}
LOCAL_SEARCH_WINDOW = 0.03          # +/-3% normalized window around LLM proposal

# Full 20-basin pool (same as exp1_new) for complete A/B/C/D coverage.
# Analysis focuses on the good/medium 12 basins (where GR4J is adequate);
# hard 8 are reported as the model-boundary group (showing B/C/D also can't
# rescue an unsuitable model).
BASINS = [
    {"basin_id": "12025000", "name": "Newaukum River, WA",      "climate_zone": "mediterranean", "difficulty": "easy"},
    {"basin_id": "11532500", "name": "Smith River, CA",         "climate_zone": "mediterranean", "difficulty": "easy"},
    {"basin_id": "02246000", "name": "N Fork Black Creek, FL",  "climate_zone": "humid_warm",    "difficulty": "easy"},
    {"basin_id": "11482500", "name": "Redwood Creek, CA",       "climate_zone": "humid_warm",    "difficulty": "easy"},
    {"basin_id": "05495000", "name": "Fox River, MO",           "climate_zone": "humid_warm",    "difficulty": "easy"},
    {"basin_id": "03574500", "name": "Paint Rock River, AL",    "climate_zone": "humid_warm",    "difficulty": "easy"},
    {"basin_id": "05595730", "name": "Rayse Creek, IL",         "climate_zone": "humid_warm",    "difficulty": "easy"},
    {"basin_id": "01543000", "name": "Driftwood Branch, PA",    "climate_zone": "humid_cold",    "difficulty": "medium"},
    {"basin_id": "07197000", "name": "Baron Fork, OK",          "climate_zone": "humid_warm",    "difficulty": "medium"},
    {"basin_id": "06885500", "name": "Black Vermillion, KS",    "climate_zone": "semiarid",      "difficulty": "medium"},
    {"basin_id": "03049000", "name": "Buffalo Creek, PA",       "climate_zone": "humid_warm",    "difficulty": "medium"},
    {"basin_id": "02472500", "name": "Bouie Creek, MS",         "climate_zone": "humid_warm",    "difficulty": "medium"},
    {"basin_id": "01169000", "name": "North River, MA",         "climate_zone": "humid_cold",    "difficulty": "hard"},
    {"basin_id": "05057200", "name": "Baldhill Creek, ND",      "climate_zone": "semiarid",      "difficulty": "hard"},
    {"basin_id": "09508300", "name": "Wet Bottom Creek, AZ",    "climate_zone": "arid",          "difficulty": "hard"},
    {"basin_id": "09378630", "name": "Recapture Creek, UT",     "climate_zone": "arid",          "difficulty": "hard"},
    {"basin_id": "10336660", "name": "Blackwood Creek, CA",     "climate_zone": "mountain",      "difficulty": "hard"},
    {"basin_id": "04197170", "name": "Rock Creek, OH",          "climate_zone": "humid_cold",    "difficulty": "hard"},
    {"basin_id": "08101000", "name": "Cowhouse Creek, TX",      "climate_zone": "semiarid",      "difficulty": "hard"},
    {"basin_id": "03439000", "name": "French Broad River, NC",  "climate_zone": "humid_warm",    "difficulty": "hard"},
]
MODEL = "gr4j"


def ensure_dirs() -> None:
    for d in (RESULTS_DIR / "method_a", RESULTS_DIR / "method_b",
              RESULTS_DIR / "method_c", RESULTS_DIR / "method_d",
              TABLES_DIR, FIGURES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_tasks():
    """Build the exp2_new Task list reusing the old exp2/common.py Task dataclass."""
    sys.path.insert(0, str(ROOT / "experiment" / "exp2"))
    from common import Task
    return [
        Task(basin_id=b["basin_id"], basin_name=b["name"],
             climate_zone=b["climate_zone"], model=MODEL)
        for b in BASINS
    ]
