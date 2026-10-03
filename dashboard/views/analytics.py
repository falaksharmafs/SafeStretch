import numpy as np
import pandas as pd
import streamlit as st

from .. import nav
from ..config import BAND_NOTE, GRID_DEG, MIN_EVENTS
from ..core import queries as Q
from ..core.stats import hour_profile, ramp, rate_ratio
from ..ui import charts, maps, theme as th
from ..ui.compat import stretch

CFG = {"displayModeBar": False}


def _grid(seg):
    g = seg.dropna(subset=["lat", "lon"]).copy()
    g["gx"], g["gy"] = np.floor(g.lon / GRID_DEG).astype(int), np.floor(g.lat / GRID_DEG).astype(int)
    a = g.groupby(["gx", "gy"]).agg(n=("segment_id", "size"), pct=("risk_pct", "mean"),
                                    high=("band", lambda b: int(b.isin(["High", "Critical"]).sum())), acc=("n_acc", "sum")).reset_index()
    a = a[a.n >= 5]
    if a.empty:
        return a
    lo, hi = a.pct.min(), a.pct.max()
    a["polygon"] = [[[x * GRID_DEG, y * GRID_DEG], [(x + 1) * GRID_DEG, y * GRID_DEG], [(x + 1) * GRID_DEG, (y + 1) * GRID_DEG],
                     [x * GRID_DEG, (y + 1) * GRID_DEG], [x * GRID_DEG, y * GRID_DEG]] for x, y in zip(a.gx, a.gy)]
    a["color"] = [ramp((p - lo) / (hi - lo) if hi > lo else 0.5) for p in a.pct]
    a["tip"] = [f"<b>Grid cell</b> (~{GRID_DEG * 111:.0f} km)<br/>{r.n} segments · mean risk percentile {r.pct * 100:.0f}"
                f"<br/>{r.high} high/critical · {int(r.acc) if pd.notna(r.acc) else 'N/A'} accidents" for r in a.itertuples()]
    return a


def render():
    seg = Q.segments()
    if seg.empty:
        return th.callout("No risk scores yet", "Run `python -m src.models.train`, then refresh.", "warn")
    acc = Q.accident_facts()
    if acc.get("synthetic"):
        th.callout("Synthetic accident data", "Time, weather and severity patterns below come from generated data and reflect how it was "
                   "generated, not real road behaviour.", "warn")
    th.section("Risk intelligence", "How risk is distributed, where it concentrates and when accidents happen.")
    t_dist, t_rank, t_where, t_time, t_wx, t_sev = st.tabs(["Distribution", "Ranking", "Road types & areas", "Time of day", "Weather", "Severity"])

    with t_dist:
        a, b = st.columns([2, 1], gap="medium")
        with a:
            stretch(st.plotly_chart, charts.risk_histogram(seg), config=CFG)
        with b:
            stretch(st.plotly_chart, charts.band_bars(seg), config=CFG)
        bands = seg.groupby("band").agg(Segments=("segment_id", "size"), Min=("risk_score", "min"), Max=("risk_score", "max")).reindex(
            ["Critical", "High", "Moderate", "Low"])
        stretch(st.dataframe, bands.rename(columns={"Min": "Min score", "Max": "Max score"}), column_config={
            "Min score": st.column_config.NumberColumn(format="%.4f"), "Max score": st.column_config.NumberColumn(format="%.4f")})
        st.caption(BAND_NOTE)

    with t_rank:
        n = st.segmented_control("Show", [10, 25, 50, 100], default=25, key="an_topn", label_visibility="collapsed") or 25
        t = seg.head(n)
        show = pd.DataFrame({"Rank": t.risk_rank.astype(int), "Road": t.label, "Type": t.road_type, "Band": t.band,
                             "Percentile": t.risk_pct * 100, "Model score": t.risk_score, "Length (m)": t.length_m,
                             "Accidents": t.n_acc, "Serious/fatal": t.n_serious, "EB rank": t.eb_rank})
        ev = stretch(st.dataframe, show, hide_index=True, on_select="rerun", selection_mode="single-row", key="an_table",
                     column_config={"Percentile": st.column_config.ProgressColumn("Risk percentile", min_value=0, max_value=100, format="%.1f"),
                                    "Model score": st.column_config.NumberColumn(format="%.4f"), "Length (m)": st.column_config.NumberColumn(format="%.0f")})
        rows = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
        if rows and st.button("Open selected road on the Risk Map", type="primary"):
            r = t.iloc[rows[0]]
            st.session_state.sel_segment = int(r.segment_id)
            st.session_state.view = {"lat": float(r.lat), "lon": float(r.lon), "zoom": 15.2} if pd.notna(r.lat) else None
            st.switch_page(nav.PAGES["map"])
        st.caption("Click a column header to sort. Select a row to open it on the map.")

    with t_where:
        a, b = st.columns(2, gap="medium")
        with a:
            th.section("Risk by road type", "Mean risk percentile of segments (50 = average)")
            stretch(st.plotly_chart, charts.road_type_bars(seg), config=CFG)
        with b:
            th.section("Risk by area", f"~{GRID_DEG * 111:.0f} km grid · cells with ≥ 5 segments")
            g = _grid(seg)
            if g.empty:
                st.caption("Insufficient data")
            else:
                area = Q.study_area()
                view = maps.view_for_bounds(area["bounds"], 560, 330) if area else {"lat": seg.lat.mean(), "lon": seg.lon.mean(), "zoom": 10.5}
                stretch(st.pydeck_chart, maps.make_deck([maps.grid_layer(g)], view), height=330)
                th.render(th.legend([("Lower mean risk", "rgb(48,164,108)"), ("Higher mean risk", "rgb(229,72,77)")]))
        st.caption("Colours compare areas with each other (relative scale from lowest to highest cell).")

    with t_time:
        counts = Q.hour_counts()
        if counts.sum() == 0:
            st.info("No accident records.")
        else:
            mult, lo, hi = hour_profile(counts)
            stretch(st.plotly_chart, charts.hour_profile(counts, mult, lo, hi), config=CFG)
            peak = int(np.argmax(mult))
            st.caption(f"Multiplier = smoothed accidents in that hour ÷ the average hour (peak: {peak}:00, ×{mult[peak]:.2f}). "
                       "Bands are Poisson 95% intervals. It includes traffic volume by design: it measures accident rate per hour of day, "
                       "not risk per vehicle.")
            thin = int((counts < MIN_EVENTS).sum())
            if thin:
                st.warning(f"{thin} of 24 hours have fewer than {MIN_EVENTS} accidents - read those points with caution.")

    with t_wx:
        rs = Q.rain_stats()
        if rs.empty:
            st.info("Not available - weather history or accidents are missing.")
        else:
            tot_a, tot_h = rs.accidents.sum(), rs.hours.sum()
            rows = []
            for r in rs.itertuples():
                rr = rate_ratio(r.accidents, r.hours, tot_a, tot_h)
                rows.append({"cond": r.cond, "accidents": r.accidents, "hours": r.hours, "value": rr["value"] if rr else np.nan,
                             "lo": rr["lo"] if rr else np.nan, "hi": rr["hi"] if rr else np.nan})
            d = pd.DataFrame(rows).set_index("cond").reindex(["Dry", "Light rain", "Heavy rain"]).dropna(how="all").reset_index()
            stretch(st.plotly_chart, charts.rain_compare(d), config=CFG)
            show = d.assign(rate=d.accidents / d.hours * 1000)
            stretch(st.dataframe, show.rename(columns={"cond": "Condition", "accidents": "Accidents", "hours": "Weather-hours", "rate": "Accidents / 1,000 h",
                                                       "value": "Rate ratio", "lo": "Lower 95%", "hi": "Upper 95%"}),
                    hide_index=True, column_config={"Rate ratio": st.column_config.NumberColumn(format="%.2f"),
                                                    "Lower 95%": st.column_config.NumberColumn(format="%.2f"),
                                                    "Upper 95%": st.column_config.NumberColumn(format="%.2f"),
                                                    "Accidents / 1,000 h": st.column_config.NumberColumn(format="%.2f")})
            st.caption(f"Rate ratio = accidents per weather-hour in that condition ÷ overall rate. Conditions with fewer than {MIN_EVENTS} "
                       "accidents are greyed out as insufficient data. Weather is one city-wide reading per hour; this shows association, "
                       "not that rain causes accidents (rainy hours also have different traffic).")

    with t_sev:
        a, b = st.columns(2, gap="medium")
        sc = Q.severity_counts()
        with a:
            th.section("Severity breakdown")
            if sc.empty:
                st.caption("N/A")
            else:
                stretch(st.plotly_chart, charts.severity_donut(sc), config=CFG)
        with b:
            th.section("Accidents per quarter")
            qc = Q.quarterly_counts()
            if qc.empty:
                st.caption("N/A")
            else:
                stretch(st.plotly_chart, charts.quarterly(qc), config=CFG)
