"""SafeStretch dashboard entry point.   streamlit run dashboard/app.py   (from the project root)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="SafeStretch · Road Safety Intelligence", page_icon="🛣️", layout="wide",
                   initial_sidebar_state="collapsed")

from dashboard import nav  # noqa: E402
from dashboard.core.db import scalar  # noqa: E402
from dashboard.ui import header, theme  # noqa: E402
from dashboard.views import analytics, data_health, hotspots, model, overview, risk_map  # noqa: E402

theme.inject()

try:
    scalar("SELECT 1")
except Exception as e:
    st.error("Cannot reach the database.")
    st.markdown(f"`{e.__class__.__name__}` - check that the `roadrisk-db` container is running and that `DATABASE_URL` in "
                "`.env` uses the right port (your setup: **5433**).")
    st.stop()

nav.PAGES.update({
    "overview": st.Page(overview.render, title="Overview", icon=":material/space_dashboard:", url_path="overview", default=True),
    "map": st.Page(risk_map.render, title="Risk Map", icon=":material/map:", url_path="risk-map"),
    "hotspots": st.Page(hotspots.render, title="Hotspots", icon=":material/local_fire_department:", url_path="hotspots"),
    "analytics": st.Page(analytics.render, title="Analytics", icon=":material/insights:", url_path="analytics"),
    "model": st.Page(model.render, title="Model", icon=":material/psychology:", url_path="model"),
    "health": st.Page(data_health.render, title="Data Health", icon=":material/health_and_safety:", url_path="data-health"),
})
try:
    page = st.navigation(list(nav.PAGES.values()), position="top")
except TypeError:                      # older Streamlit without top navigation
    page = st.navigation(list(nav.PAGES.values()))

header.render()
page.run()
