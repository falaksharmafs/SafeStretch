import math

import pandas as pd
import streamlit as st

from ..config import BAND_COLORS, BAND_NOTE, POI, SEVERITY
from ..core import queries as Q
from ..core.risk import LABEL_TO_COL, fmt_float, fmt_int, fmt_km, parse_reason, percentile_of
from ..ui import maps, theme as th
from ..ui.compat import stretch

COV = {"Top 1%": .01, "Top 5%": .05, "Top 10%": .10, "Top 20%": .20, "Top 50%": .50, "All roads": 1.0}
LAYERS = ["Risk roads", "Hotspots", "Accidents", "POIs", "Boundary"]
DEFAULTS = dict(f_layers=["Risk roads", "Hotspots", "Boundary"])


def _reset(d0=None, d1=None):
    """Dropping a widget's key returns it to the default declared where the widget is created."""
    for k in ("f_layers", "f_cov", "f_sev", "f_hours", "f_types", "f_hs", "f_accview", "f_poi", "f_dates", "f_find", "f_topn"):
        st.session_state.pop(k, None)
    st.session_state.sel_segment = st.session_state.sel_hotspot = st.session_state.view = None


def _read_selection(key, field):
    """Selection from the previous interaction with a pydeck chart / dataframe (None if nothing selected)."""
    try:
        sel = st.session_state[key]["selection"]
        return sel[field]
    except Exception:
        return None


def _sync_selection(seg):
    """Map click -> panel;  table row -> panel + fly-to.  Whichever changed most recently wins."""
    ss = st.session_state
    objs = _read_selection("riskmap", "objects") or {}
    road = (objs.get("roads") or [None])[0]
    hot = (objs.get("hotspots") or [None])[0]
    sig_map = (int(road["segment_id"]) if road else None, int(hot["cluster_id"]) if hot else None)
    if sig_map != ss._sig_map:
        ss._sig_map = sig_map
        if sig_map[0] is not None:
            ss.sel_segment = sig_map[0]
        if sig_map[1] is not None:
            ss.sel_hotspot = sig_map[1]
    rows, ids = _read_selection("risk_table", "rows"), ss.get("_tbl_ids", [])
    sel_t = ids[rows[0]] if rows and rows[0] < len(ids) else None
    if sel_t != ss._sig_tbl:
        ss._sig_tbl = sel_t
        if sel_t is not None:
            ss.sel_segment = sel_t
            r = seg[seg.segment_id == sel_t]
            if not r.empty and pd.notna(r.iloc[0].lat):
                ss.view = {"lat": float(r.iloc[0].lat), "lon": float(r.iloc[0].lon), "zoom": 15.2}


def _segment_panel(seg, sid):
    r = seg[seg.segment_id == sid]
    if r.empty:
        return st.info("Segment not found.")
    r, n = r.iloc[0], len(seg)
    top_pct = (1 - r.risk_pct) * 100
    th.render(f'<div class="ss-card"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
              f'<div style="font-size:1.08rem;font-weight:700">{th.esc(r.label)}</div>{th.band_badge(r.band)}</div>'
              f'<div style="font-size:.8rem;opacity:.65;margin-top:2px">Segment #{int(r.segment_id)} · {th.esc(r.road_type)}</div>'
              f'<div style="margin-top:10px;font-size:.9rem">Rank <b>#{int(r.risk_rank):,}</b> of {n:,} · top <b>{max(top_pct, 0.01):.2f}%</b></div></div>')
    th.render(th.stat_grid([("Length", fmt_km(r.length_m)), ("Speed limit", f"{int(r.speed_limit)} km/h" if pd.notna(r.speed_limit) else "N/A"),
                            ("Lanes", fmt_int(r.lanes)), ("One-way", "Yes" if r.oneway else "No"),
                            ("Model score", fmt_float(r.risk_score, 4)),
                            ("Calibrated probability", f"{r.risk_prob:.3f}" if pd.notna(r.risk_prob) else "Not available")]))
    st.caption("Model score is the raw, uncalibrated model output. A calibrated probability appears only after the upgraded trainer runs.")

    th.section("History", "Observed accidents on this segment (loaded data)")
    th.render(th.stat_grid([("Accidents", fmt_int(r.n_acc)), ("Serious / fatal", fmt_int(r.n_serious)),
                            ("At night", fmt_int(r.n_night)), ("In rain", fmt_int(r.n_rain))]))

    th.section("Nearby points of interest", "Within 200 m")
    items = [(POI[c][0], fmt_int(r[col]), POI[c][1]) for c, col in
             (("school", "schools_nearby"), ("hospital", "hospitals_nearby"), ("crossing", "crossings_nearby"),
              ("alcohol_outlet", "alcohol_nearby"), ("bus_stop", "bus_stops_nearby"), ("junction", "junctions_nearby"))
             if pd.notna(r[col])]
    th.render(th.chips(items) if items else "<span style='opacity:.6'>N/A</span>")

    th.section("Why is this segment risky?", "Top model drivers (SHAP) for this segment")
    drivers = [parse_reason(x) for x in (r.reason_1, r.reason_2, r.reason_3)]
    drivers = [d for d in drivers if d]
    if not drivers:
        st.caption("Explanations are generated only for the highest-ranked segments, so none are stored for this one.")
    for i, (label, value) in enumerate(drivers, 1):
        col = LABEL_TO_COL.get(label)
        p = percentile_of(r[col], seg[col]) if col and col in seg else None
        ctx = f"Higher than {p:.0%} of segments" if p is not None else None
        th.render(th.driver_card(i, label, value, ctx, fill=p))
    if drivers:
        st.caption("Drivers are ordered by contribution to this score. They describe associations learned from data, not proven causes.")

    if pd.notna(r.eb_rank):
        th.section("Historical black-spot view", "Empirical-Bayes, exposure-adjusted")
        th.render('<div class="ss-card">' + th.rows([("EB rank", f"#{int(r.eb_rank):,}"), ("Observed accidents", fmt_int(r.eb_observed)),
                                                     ("Expected for similar roads", fmt_float(r.eb_expected, 2)),
                                                     ("EB-smoothed estimate", fmt_float(r.eb_estimate, 2))]) + "</div>")


def _hotspot_panel(hs, cid):
    r = hs[hs.cluster_id == cid]
    if r.empty:
        return
    r = r.iloc[0]
    th.render(f'<div class="ss-card"><div style="font-weight:700;font-size:1.05rem">Hotspot {int(r.cluster_id)}</div>'
              f'<div style="font-size:.8rem;opacity:.65">Near {th.esc(r.nearest_label)}</div></div>')
    th.render(th.stat_grid([("Accidents", fmt_int(r.n_accidents)), ("Serious / fatal", fmt_int(r.n_serious))]))
    st.caption("See the Hotspots page for the full breakdown.")


def render():
    ss = st.session_state
    for k in ("sel_segment", "sel_hotspot", "view", "_sig_map", "_sig_tbl"):
        ss.setdefault(k, None)
    seg = Q.segments()
    if seg.empty:
        return th.callout("No risk scores yet", "Run `python -m src.models.train`, then refresh.", "warn")
    acc, hs, area, poi = Q.accident_facts(), Q.hotspots(), Q.study_area(), Q.poi_points()
    d0 = pd.Timestamp(acc["t0"]).date() if acc.get("t0") is not None else None
    d1 = pd.Timestamp(acc["t1"]).date() if acc.get("t1") is not None else None
    poi_cats = sorted(poi.category.unique()) if not poi.empty else []
    _sync_selection(seg)

    # ---------------- control bar
    c1, c2, c3, c4, c5 = st.columns([5, 1.25, 1.35, 1.25, 1], vertical_alignment="center")
    c1.pills("Layers", LAYERS, selection_mode="multi", default=DEFAULTS["f_layers"], key="f_layers", label_visibility="collapsed")
    with c2.popover(":material/tune: Filters"):
        st.multiselect("Accident severity", [1, 2, 3], default=[1, 2, 3], key="f_sev", format_func=lambda s: SEVERITY[s][0])
        st.select_slider("Show roads in", list(COV), value="Top 20%", key="f_cov")
        st.multiselect("Road types", sorted(seg.road_type.unique()), key="f_types", placeholder="All road types")
        st.slider("Hour of day (accidents)", 0, 23, value=(0, 23), key="f_hours")
        if d0:
            st.date_input("Accident dates", value=(d0, d1), min_value=d0, max_value=d1, key="f_dates")
        st.slider("Hotspot marker radius (display only, m)", 50, 300, value=120, key="f_hs")
        st.segmented_control("Accident view", ["Points", "Density"], default="Points", key="f_accview")
        st.multiselect("POI categories", poi_cats, default=poi_cats, key="f_poi",
                       format_func=lambda c: POI.get(c, (c,))[0])
    with c3.popover(":material/search: Find road"):
        q = st.text_input("Name or segment ID", key="f_find", placeholder="e.g. Rajpur Road or 1234")
        if q:
            hit = seg[seg.label.str.lower().str.contains(q.lower(), regex=False) | (seg.segment_id.astype(str) == q.strip())].head(6)
            for r in hit.itertuples():
                if st.button(f"{r.label} · #{r.risk_rank:,}", key=f"find_{r.segment_id}"):
                    ss.sel_segment = int(r.segment_id)
                    ss.view = {"lat": float(r.lat), "lon": float(r.lon), "zoom": 15.2} if pd.notna(r.lat) else None
                    st.rerun()
            if hit.empty:
                st.caption("No matching road.")
    if stretch(c4.button, ":material/zoom_out_map: Study area"):
        ss.view = None
    stretch(c5.button, ":material/restart_alt:", help="Reset all filters and selection", on_click=_reset, args=(d0, d1))

    # ---------------- build layers
    layers_on = ss.get('f_layers') or []
    base_view = maps.view_for_bounds(area["bounds"]) if area else {"lat": seg.lat.mean(), "lon": seg.lon.mean(), "zoom": 11}
    view = ss.view if ss.view and ss.view.get("lat") is not None else base_view
    layers, notes = [], []
    if "Boundary" in layers_on and area:
        layers.append(maps.boundary_layer(area["geojson"]))
    if "Risk roads" in layers_on:
        k = min(len(seg), math.ceil(COV[ss.get("f_cov", "Top 20%")] * len(seg)))
        d = seg.merge(Q.road_paths(k), on="segment_id")
        if ss.get("f_types", []):
            d = d[d.road_type.isin(ss.get("f_types", []))]
        layers.append(maps.road_layer(d))
        notes.append(f"{len(d):,} road segments shown")
    if "Hotspots" in layers_on and not hs.empty:
        layers.append(maps.hotspot_layer(hs, ss.get("f_hs", 120), selected=ss.sel_hotspot))
    if "Accidents" in layers_on and d0:
        fd = ss.get("f_dates")
        dates = fd if isinstance(fd, (tuple, list)) and len(fd) == 2 else (d0, d1)
        pts = Q.accidents_points(dates[0], dates[1], tuple(ss.get("f_sev") or [1, 2, 3]), ss.get("f_hours", (0, 23))[0], ss.get("f_hours", (0, 23))[1])
        if not pts.empty:
            layers.append(maps.accident_density(pts) if ss.get("f_accview", "Points") == "Density" else maps.accident_layer(pts))
        notes.append(f"{len(pts):,} accidents" + (" (latest 25,000)" if len(pts) >= 25000 else ""))
    if "POIs" in layers_on and not poi.empty:
        layers += maps.poi_layers(poi, ss.get("f_poi") or list(POI))
    if ss.sel_segment:
        path = Q.segment_path(int(ss.sel_segment))
        if path:
            layers.append(maps.selected_layer(path))

    # ---------------- map + panel
    left, right = st.columns([2.7, 1.15], gap="medium")
    with left:
        legend = [(b, c) for b, c in BAND_COLORS.items()]
        if "Hotspots" in layers_on:
            legend.append(("Hotspot", "#C2409F"))
        th.render(th.legend(legend) + f'<div class="ss-legend" style="margin-top:-4px">{" · ".join(notes)}</div>')
        stretch(st.pydeck_chart, maps.make_deck(layers, view), height=690, on_select="rerun",
                selection_mode="single-object", key="riskmap")
        with st.expander("About the risk bands & overlays"):
            st.markdown(BAND_NOTE)
            st.caption("Weather and traffic map overlays are not shown: there is no live traffic feed, and weather is a single "
                       "city-wide reading (see the Overview and Live Risk pages).")
    with right:
        if ss.sel_segment:
            _segment_panel(seg, int(ss.sel_segment))
        elif ss.sel_hotspot is not None and not hs.empty:
            _hotspot_panel(hs, int(ss.sel_hotspot))
        else:
            th.render('<div class="ss-card"><b>Inspect a road</b><div style="opacity:.7;font-size:.86rem;margin-top:4px">'
                      'Click a road on the map, search by name, or pick a row from the ranking below. '
                      'The panel shows its attributes, history and the model\'s top drivers.</div></div>')

    # ---------------- ranking table (synced)
    th.section("Risk ranking", "Select a row to fly the map to that segment")
    topn = st.segmented_control("Show", [10, 25, 50, 100], default=25, key="f_topn", label_visibility="collapsed") or 25
    t = seg if not ss.get("f_types", []) else seg[seg.road_type.isin(ss.get("f_types", []))]
    t = t.head(topn)
    ss._tbl_ids = t.segment_id.astype(int).tolist()
    show = pd.DataFrame({"Rank": t.risk_rank.astype(int), "Road": t.label, "Type": t.road_type, "Band": t.band,
                         "Percentile": t.risk_pct * 100, "Model score": t.risk_score, "Accidents": t.n_acc,
                         "Serious/fatal": t.n_serious, "Top driver": t.reason_1})
    stretch(st.dataframe, show, hide_index=True, on_select="rerun", selection_mode="single-row", key="risk_table",
            column_config={"Percentile": st.column_config.ProgressColumn("Risk percentile", min_value=0, max_value=100, format="%.1f"),
                           "Model score": st.column_config.NumberColumn(format="%.4f", help="Uncalibrated model output"),
                           "Rank": st.column_config.NumberColumn(format="%d")})
