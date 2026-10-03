import json
from datetime import datetime

import streamlit as st

from ..config import METRICS_PATH, MODEL_PATH


@st.cache_data(ttl=60, show_spinner=False)
def _load(mtime: float):
    return json.loads(METRICS_PATH.read_text())


def metrics():
    """reports/metrics.json written by the trainer, or None."""
    if not METRICS_PATH.exists():
        return None
    try:
        return _load(METRICS_PATH.stat().st_mtime)
    except Exception:
        return None


def version(m):
    if m and m.get("model_version"):
        return str(m["model_version"])
    if METRICS_PATH.exists():
        return "unversioned · " + datetime.fromtimestamp(METRICS_PATH.stat().st_mtime).strftime("%d %b %Y")
    return "N/A"


def trained_at():
    return datetime.fromtimestamp(METRICS_PATH.stat().st_mtime) if METRICS_PATH.exists() else None


def has_model_artifact():
    return MODEL_PATH.exists()
