"""Single place for dashboard constants. Nothing here changes the pipeline."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_NAME = "SafeStretch"
TAGLINE = "Road Safety Intelligence"

# Rank-percentile bands (1.0 = riskiest segment). The API already uses 0.95 / 0.80 for high / elevated;
# Critical (top 1%) is added for the map. These are RELATIVE cut-offs for prioritisation, not universal safety thresholds.
BANDS = (("Critical", 0.99), ("High", 0.95), ("Moderate", 0.80), ("Low", 0.0))
BAND_COLORS = {"Critical": "#E5484D", "High": "#F76B15", "Moderate": "#F5B83D", "Low": "#30A46C"}
BAND_WIDTH = {"Critical": 7, "High": 5, "Moderate": 3, "Low": 2}
BAND_NOTE = ("Bands are rank-percentile cut-offs configured for this project (Critical = top 1%, High = top 5%, "
             "Moderate = top 20%). They rank segments against each other; they are not universal safety thresholds.")

ACCENT = "#3B9EFF"
HOTSPOT_COLOR = "#C2409F"
SEVERITY = {1: ("Fatal", "#E5484D"), 2: ("Serious", "#F76B15"), 3: ("Minor", "#8B98A9")}
POI = {
    "school": ("Schools", "#3B9EFF"), "hospital": ("Hospitals", "#2DD4BF"), "bus_stop": ("Bus stops", "#A78BFA"),
    "crossing": ("Crossings", "#94A3B8"), "alcohol_outlet": ("Alcohol outlets", "#E0A030"),
    "junction": ("Junctions", "#64748B"),
}

# Mirrors the pipeline defaults (src/models/hotspots.py) - displayed, never recomputed here.
HOTSPOT_EPS_M = 100
HOTSPOT_MIN_SAMPLES = 8
POI_RADIUS_M = 200
GRID_DEG = float(os.getenv("GRID_DEG", "0.02"))
MIN_EVENTS = 30                      # below this, intervals/ratios are shown as "insufficient data"
PSI_WARN, PSI_ALERT = 0.10, 0.25     # documented in src/monitoring/drift.py (used by the monitoring page, stage 2)

METRICS_PATH = ROOT / "reports" / "metrics.json"
MODEL_PATH = ROOT / "models" / "latest.joblib"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
API_URL = os.getenv("API_URL", "http://localhost:8000")
TILES_URL = os.getenv("TILES_URL", "http://localhost:7800")
