"""Pure helpers (no Streamlit, no DB) - unit-tested."""
import math
from datetime import datetime, timezone

from ..config import BANDS

# SHAP reason text uses these labels (see LABELS in src/models/train.py) -> static feature column
LABEL_TO_COL = {
    "speed limit": "speed_limit", "lanes": "lanes", "one-way": "oneway", "segment length (m)": "length_m",
    "curvature": "curvature", "alcohol outlets nearby": "alcohol_nearby", "junctions nearby": "junctions_nearby",
    "schools nearby": "schools_nearby", "hospitals nearby": "hospitals_nearby",
    "bus stops nearby": "bus_stops_nearby", "crossings nearby": "crossings_nearby",
    "past accidents": "n_acc", "past serious accidents": "n_serious", "past night accidents": "n_night",
    "past rain accidents": "n_rain",
}


def is_missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def pct_from_rank(rank, n):
    """1.0 = riskiest segment, 0.0 = safest."""
    return 1.0 - (rank - 1) / max(n - 1, 1)


def band_for(pct):
    for name, cut in BANDS:
        if pct >= cut:
            return name
    return BANDS[-1][0]


def fmt_int(x):
    return "N/A" if is_missing(x) else f"{int(round(x)):,}"


def fmt_float(x, d=2):
    return "N/A" if is_missing(x) else f"{x:,.{d}f}"


def fmt_pct(x, d=1):
    return "N/A" if is_missing(x) else f"{100 * x:.{d}f}%"


def fmt_km(m):
    return "N/A" if is_missing(m) else (f"{m / 1000:,.1f} km" if m >= 1000 else f"{m:,.0f} m")


def human_age(ts, now=None):
    if ts is None:
        return "N/A"
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    s = (now - ts).total_seconds()
    if s < 0:
        return "in the future"
    for unit, size in (("year", 365 * 86400), ("month", 30 * 86400), ("day", 86400), ("hour", 3600), ("min", 60)):
        if s >= size:
            v = int(s // size)
            return f"{v} {unit}{'s' if v > 1 and unit != 'min' else ''} ago"
    return "just now"


def parse_reason(text):
    """'junctions nearby: 3' -> ('junctions nearby', '3'); empty -> None."""
    if not text or not str(text).strip():
        return None
    label, _, value = str(text).partition(": ")
    return label.strip(), value.strip()


def percentile_of(value, series):
    """Share of the series strictly below value (0-1). None if not computable."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    s = series.dropna()
    return None if s.empty or math.isnan(v) else float((s < v).mean())


def top_overlap(a_ids, b_ids):
    a, b = set(a_ids), set(b_ids)
    union = len(a | b)
    return {"shared": len(a & b), "only_a": len(a - b), "only_b": len(b - a),
            "jaccard": (len(a & b) / union) if union else 0.0}
