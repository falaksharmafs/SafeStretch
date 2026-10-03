"""Live service checks. Each returns (name, state, detail); state in ok | warn | error | off."""
import os
import urllib.request

import pandas as pd
import streamlit as st

from ..config import API_URL, TILES_URL
from . import queries as Q
from . import schema as S
from .db import scalar


def _http(url, timeout=0.8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


@st.cache_data(ttl=20, show_spinner=False)
def system_status():
    out = []
    try:
        out.append(("PostGIS", "ok", f"Online · v{str(scalar('SELECT PostGIS_Version()', 'unknown')).split()[0]}"))
        db_ok = True
    except Exception as e:
        out.append(("PostGIS", "error", f"Offline ({e.__class__.__name__})"))
        db_ok = False
    out.append(("API", "ok" if _http(f"{API_URL}/health") else "off",
                "Online" if _http(f"{API_URL}/health") else "Not running (optional)"))
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            redis.Redis.from_url(redis_url, socket_timeout=0.8).ping()
            out.append(("Redis", "ok", "Online"))
        except Exception:
            out.append(("Redis", "off", "Offline"))
    else:
        out.append(("Redis", "off", "Not configured"))
    if db_ok:
        ver = scalar("SELECT extversion FROM pg_extension WHERE extname = 'pgrouting'")
        out.append(("pgRouting", "ok" if ver else "warn", f"Available · v{ver}" if ver else "Unavailable - safest-route disabled"))
        w = Q.weather_now()
        if w["live"]:
            out.append(("Weather", "ok", "Live"))
        elif w["ts"] is not None:
            out.append(("Weather", "warn", f"Stale · archive to {pd.Timestamp(w['ts']):%d %b %Y}"))
        else:
            out.append(("Weather", "off", "No data"))
        traffic = scalar("SELECT COUNT(*) FROM live_traffic WHERE ts > now() - interval '1 hour'", 0) if S.has_table("live_traffic") else 0
        out.append(("Traffic", "ok" if traffic else "off", "Available" if traffic else "Disabled (no TomTom feed)"))
        n = S.row_count("segment_risk")
        out.append(("ML scores", "ok" if n else "warn", f"{n:,} segments scored" if n else "No scores - run training"))
    out.append(("Tiles", "ok" if _http(f"{TILES_URL}/index.json") else "off",
                "Online" if _http(f"{TILES_URL}/index.json") else "Not running (optional)"))
    return out
