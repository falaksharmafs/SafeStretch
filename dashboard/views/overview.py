import math

import pandas as pd
import streamlit as st

from .. import nav
from ..config import BAND_COLORS, BAND_NOTE, HOTSPOT_EPS_M, HOTSPOT_MIN_SAMPLES
from ..core import model_info as M
from ..core import queries as Q
from ..core.risk import fmt_int, human_age
from ..core.stats import last_two_complete
from ..ui import charts, maps, theme as th
from ..ui.compat import stretch


def _empty():
    th.callout("No risk scores yet", "The segment_risk table is empty. Run `python -m src.models.train` first, then refresh.", "warn")


def _serious_kpi(acc, qc):
    delta, tone = None, "flat"
    pair = last_two_complete(qc, acc.get("t1"))
    if pair and pair[0].serious > 0:
        prev, last = pair
        ch = (last.serious - prev.serious) / prev.serious
        delta = f"{ch:+.1%} vs previous quarter ({pd.Timestamp(last.quarter):%b %Y})"
        tone = "good" if ch < 0 else "bad" if ch > 0 else "flat"
    return th.kpi_card("Serious / fatal accidents", fmt_int(acc["serious"] + acc["fatal"]),
                       f"{fmt_int(acc['fatal'])} fatal · {fmt_int(acc['serious'])} serious", "siren", "critical",
                       delta=delta, delta_tone=tone, tip="Accidents with severity 1 or 2 in the loaded data. "
                       "Change is shown only when two complete quarters exist.")


def _weather_kpi(w):
    if w["ts"] is None:
        return th.kpi_card("Weather", "N/A", "No weather data loaded", "cloud", "muted")
    ts = pd.Timestamp(w["ts"])
    temp = "N/A" if pd.isna(w["temp_c"]) else f"{w['temp_c']:.1f}"
    rain = "N/A" if pd.isna(w["rain_mm"]) else f"{w['rain_mm']:.1f} mm"
    if w["live"]:
        return th.kpi_card("Weather · live", temp, f"Rain {rain} · {human_age(ts.to_pydatetime())}",
                           "cloud", "ok", unit="°C", tip="Latest reading from the live weather feed.")
    return th.kpi_card("Weather · not live", temp, f"Archive reading {ts:%d %b %Y %H:%M} · rain {rain}",
                       "cloud", "warn", unit="°C", tip="No live feed is running; this is the newest archive hour, not current weather.")


def _model_kpi(m):
    try:
        t, s = m["temporal_test"], m["spatial_cv"]
        tm, tb = t["model"]["pr_auc"], t["baseline_history_only"]["pr_auc"]
        beats = tm > tb and s["model"]["pr_auc"] > s["baseline_history_only"]["pr_auc"]
        return th.kpi_card("Model health", "Beats baseline" if beats else "Check model",
                           f"Temporal PR-AUC {tm:.3f} vs history-only {tb:.3f}", "shield", "ok" if beats else "warn",
                           tip="Compares the model with a history-only ranking on spatial CV and a temporal hold-out. "
                               "No single 'accuracy' figure is used for rare-event ranking.")
    except Exception:
        return th.kpi_card("Model health", "N/A", "reports/metrics.json not found", "shield", "muted")


def render():
    seg = Q.segments()
    if seg.empty:
        return _empty()
    n, acc, hs, area, m, w, qc = len(seg), Q.accident_facts(), Q.hotspots(), Q.study_area(), M.metrics(), Q.weather_now(), Q.quarterly_counts()
    if acc.get("synthetic"):
        th.callout("Synthetic accident data", "Accidents in this database are generated for pipeline testing. Everything below demonstrates the "
                   "system; none of it is a real-world finding or performance claim.", "warn")

    hi = int(seg.band.isin(["High", "Critical"]).sum())
    km = seg.length_m.sum() / 1000
    age = human_age(pd.Timestamp(acc["t1"]).to_pydatetime()) if acc.get("t1") is not None else "N/A"
    stale = acc.get("t1") is not None and (pd.Timestamp.now(tz="UTC") - pd.Timestamp(acc["t1"]).tz_convert("UTC")).days > 90

    th.section("City snapshot", "Relative risk is ranked across all scored road segments; counts come straight from the database.")
    r1 = st.columns(4)
    cards1 = [
        th.kpi_card("High & critical segments", fmt_int(hi), f"of {n:,} · top 5% by model rank", "alert", "risk",
                    tip=BAND_NOTE + " This count is relative by construction (about 5% of segments)."),
        th.kpi_card("Active hotspots", fmt_int(len(hs)) if not hs.empty else "N/A",
                    f"DBSCAN ε = {HOTSPOT_EPS_M} m · ≥ {HOTSPOT_MIN_SAMPLES} accidents", "flame", "critical",
                    tip="Spatial clusters of accidents found by DBSCAN. Settings shown are the pipeline defaults."),
        _serious_kpi(acc, qc) if acc.get("n") else th.kpi_card("Serious / fatal accidents", "N/A", "No accidents loaded", "siren", "muted"),
        th.kpi_card("Monitored road length", f"{km:,.0f}", f"{n:,} drivable segments", "route", "accent", unit="km",
                    tip="Sum of segment lengths in the study area (OpenStreetMap)."),
    ]
    r2 = st.columns(4)
    cards2 = [
        _weather_kpi(w),
        th.kpi_card("Current risk level", "N/A", "Live risk layer not enabled yet", "gauge", "muted",
                    tip="Becomes available once live weather + hour multipliers are running. It will be shown as a relative index, never a probability."),
        th.kpi_card("Data freshness", age, f"Latest accident record · {pd.Timestamp(acc['t1']):%d %b %Y}" if acc.get("t1") is not None else "",
                    "clock", "warn" if stale else "ok", tip="Age of the newest accident record. Amber when older than 90 days."),
        _model_kpi(m),
    ]
    for col, card in zip(r1, cards1):
        col.markdown(th.h(card), unsafe_allow_html=True)
    st.write("")
    for col, card in zip(r2, cards2):
        col.markdown(th.h(card), unsafe_allow_html=True)

    th.section("Where risk concentrates", "Top 5% of segments by model rank, with accident hotspots.")
    left, right = st.columns([2.4, 1], gap="medium")
    with left:
        k = math.ceil(0.05 * n)
        d = seg.merge(Q.road_paths(k), on="segment_id")
        view = maps.view_for_bounds(area["bounds"]) if area else {"lat": seg.lat.mean(), "lon": seg.lon.mean(), "zoom": 11}
        layers = ([maps.boundary_layer(area["geojson"])] if area else []) + [maps.road_layer(d)]
        if not hs.empty:
            layers.append(maps.hotspot_layer(hs.head(150), 90))
        stretch(st.pydeck_chart, maps.make_deck(layers, view), height=470)
        th.render(th.legend([(b, c) for b, c in BAND_COLORS.items() if b != "Low"] + [("Hotspot", "#C2409F")]))
    with right:
        th.render('<div class="ss-card" style="padding:12px 14px"><b>Priority segments</b>'
                  '<div style="font-size:.76rem;opacity:.65;margin-bottom:6px">Highest model-ranked roads</div></div>')
        for r in seg.head(6).itertuples():
            a, b = st.columns([4, 1.2], vertical_alignment="center")
            a.markdown(f"**#{int(r.risk_rank)} {r.label}**  \n<span style='opacity:.65;font-size:.78rem'>{r.road_type}</span>",
                       unsafe_allow_html=True)
            if b.button("Inspect", key=f"ov_{r.segment_id}"):
                st.session_state.sel_segment = int(r.segment_id)
                st.session_state.view = {"lat": float(r.lat), "lon": float(r.lon), "zoom": 15.2} if pd.notna(r.lat) else None
                st.switch_page(nav.PAGES["map"])

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        th.section("Segments by risk band", "Rank-percentile bands (relative)")
        stretch(st.plotly_chart, charts.band_bars(seg), config={"displayModeBar": False})
    with c2:
        th.section("Accidents by quarter", "Observed counts in the loaded data")
        if qc.empty:
            st.caption("N/A")
        else:
            stretch(st.plotly_chart, charts.quarterly(qc), config={"displayModeBar": False})
    with c3:
        th.section("Severity mix", "Share of recorded accidents")
        sc = Q.severity_counts()
        if sc.empty:
            st.caption("N/A")
        else:
            stretch(st.plotly_chart, charts.severity_donut(sc), config={"displayModeBar": False})
