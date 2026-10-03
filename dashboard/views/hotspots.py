import pandas as pd
import streamlit as st

from .. import nav
from ..config import HOTSPOT_EPS_M, HOTSPOT_MIN_SAMPLES, POI, SEVERITY
from ..core import queries as Q
from ..core.risk import fmt_int
from ..ui import maps, theme as th
from ..ui.compat import stretch

SORTS = {"Most severe": "n_serious", "Largest": "n_accidents", "Highest road risk": "max_pct"}


def _sel(key, field):
    try:
        return st.session_state[key]["selection"][field]
    except Exception:
        return None


def _sync(hs):
    ss = st.session_state
    objs = _sel("hsmap", "objects") or {}
    hot = (objs.get("hotspots") or [None])[0]
    sig = int(hot["cluster_id"]) if hot else None
    if sig != ss._hs_sig_map:
        ss._hs_sig_map = sig
        if sig is not None:
            ss.sel_hotspot = sig
    rows, ids = _sel("hs_table", "rows"), ss.get("_hs_tbl_ids", [])
    sel_t = ids[rows[0]] if rows and rows[0] < len(ids) else None
    if sel_t != ss._hs_sig_tbl:
        ss._hs_sig_tbl = sel_t
        if sel_t is not None:
            ss.sel_hotspot = sel_t
            r = hs[hs.cluster_id == sel_t].iloc[0]
            ss.hs_view = {"lat": float(r.lat), "lon": float(r.lon), "zoom": 16.2}


def render():
    ss = st.session_state
    for k in ("sel_hotspot", "hs_view", "_hs_sig_map", "_hs_sig_tbl"):
        ss.setdefault(k, None)
    hs, area, seg = Q.hotspots(), Q.study_area(), Q.segments()
    if hs.empty:
        return th.callout("No hotspots yet", "Run `python -m src.models.hotspots`, then refresh.", "warn")
    _sync(hs)

    th.section("Hotspot explorer", f"Clusters of accidents found by DBSCAN (ε = {HOTSPOT_EPS_M} m, ≥ {HOTSPOT_MIN_SAMPLES} accidents).")
    top_sev, top_big = hs.sort_values("n_serious", ascending=False).iloc[0], hs.sort_values("n_accidents", ascending=False).iloc[0]
    cols = st.columns(4)
    cards = [
        th.kpi_card("Hotspots", fmt_int(len(hs)), f"{int(hs.n_accidents.sum()):,} accidents inside clusters", "flame", "critical"),
        th.kpi_card("Hotspot density", f"{len(hs) / area['km2']:.1f}" if area else "N/A", "per km² of study area", "map", "accent",
                    tip="Cluster count divided by study-area size."),
        th.kpi_card("Largest hotspot", fmt_int(top_big.n_accidents), f"Hotspot {int(top_big.cluster_id)} · {top_big.nearest_label}", "alert", "risk", unit="accidents"),
        th.kpi_card("Most severe hotspot", fmt_int(top_sev.n_serious), f"Hotspot {int(top_sev.cluster_id)} · {top_sev.nearest_label}", "siren", "critical", unit="serious/fatal"),
    ]
    for c, card in zip(cols, cards):
        c.markdown(th.h(card), unsafe_allow_html=True)

    left, right = st.columns([2.5, 1.2], gap="medium")
    sel = ss.sel_hotspot
    with left:
        base = maps.view_for_bounds(area["bounds"]) if area else {"lat": hs.lat.mean(), "lon": hs.lon.mean(), "zoom": 11}
        view = ss.hs_view or base
        layers = ([maps.boundary_layer(area["geojson"])] if area else []) + [maps.hotspot_layer(hs, 110, layer_id="hotspots", selected=sel)]
        if sel is not None:
            r = hs[hs.cluster_id == sel].iloc[0]
            near = Q.accidents_near(float(r.lon), float(r.lat), HOTSPOT_EPS_M * 1.5)
            layers += [maps.ring_layer(float(r.lon), float(r.lat), HOTSPOT_EPS_M)] + ([maps.accident_layer(near)] if not near.empty else [])
        th.render(th.legend([("Hotspot", "#C2409F"), ("Fatal", SEVERITY[1][1]), ("Serious", SEVERITY[2][1]), ("Minor", SEVERITY[3][1])]))
        stretch(st.pydeck_chart, maps.make_deck(layers, view), height=620, on_select="rerun",
                selection_mode="single-object", key="hsmap")
        if st.button(":material/zoom_out_map: Back to study area"):
            ss.hs_view, ss.sel_hotspot = None, None
            st.rerun()
    with right:
        if sel is None:
            th.render('<div class="ss-card"><b>Select a hotspot</b><div style="opacity:.7;font-size:.86rem;margin-top:4px">'
                      'Click a circle on the map or a row in the table. Individual accidents inside the cluster then appear on the map.</div></div>')
        else:
            r = hs[hs.cluster_id == sel].iloc[0]
            th.render(f'<div class="ss-card"><div style="font-size:1.08rem;font-weight:700">Hotspot {int(r.cluster_id)}</div>'
                      f'<div style="font-size:.8rem;opacity:.65">Nearest road: {th.esc(r.nearest_label)}</div>'
                      f'<div style="font-size:.8rem;opacity:.65">{r.lat:.5f}, {r.lon:.5f}</div></div>')
            th.render(th.stat_grid([("Accidents", fmt_int(r.n_accidents)), ("Serious / fatal", fmt_int(r.n_serious)),
                                    ("Serious share", f"{r.serious_share:.0%}" if pd.notna(r.serious_share) else "N/A"),
                                    ("Cluster radius ε", f"{HOTSPOT_EPS_M} m"),
                                    ("Roads within ε", fmt_int(r.n_roads)),
                                    ("Top nearby road percentile", f"{r.max_pct * 100:.1f}" if pd.notna(r.max_pct) else "N/A")]))
            st.caption("Roads within ε and the road-risk percentile describe what lies near the cluster centre; they are derived, "
                       "not stored cluster membership.")
            th.section("Nearby points of interest", "Within 200 m of the centre")
            th.render(th.chips([(POI["school"][0], fmt_int(r.schools), POI["school"][1]), (POI["hospital"][0], fmt_int(r.hospitals), POI["hospital"][1]),
                                (POI["crossing"][0], fmt_int(r.crossings), POI["crossing"][1]), (POI["bus_stop"][0], fmt_int(r.bus_stops), POI["bus_stop"][1]),
                                (POI["alcohol_outlet"][0], fmt_int(r.alcohol), POI["alcohol_outlet"][1])]))
            if pd.notna(r.nearest_segment) and not seg.empty and st.button("Inspect nearest road on Risk Map"):
                row = seg[seg.segment_id == int(r.nearest_segment)]
                ss.sel_segment = int(r.nearest_segment)
                ss.view = {"lat": float(row.iloc[0].lat), "lon": float(row.iloc[0].lon), "zoom": 15.5} if not row.empty and pd.notna(row.iloc[0].lat) else None
                st.switch_page(nav.PAGES["map"])

    th.section("Hotspot ranking", "Select a row to zoom the map")
    sort = st.segmented_control("Rank by", list(SORTS), default="Most severe", key="hs_sort") or "Most severe"
    t = hs.sort_values(SORTS[sort], ascending=False, na_position="last").head(100)
    ss._hs_tbl_ids = t.cluster_id.astype(int).tolist()
    show = pd.DataFrame({"Hotspot": t.cluster_id.astype(int), "Near": t.nearest_label, "Accidents": t.n_accidents, "Serious/fatal": t.n_serious,
                         "Serious share": t.serious_share * 100, "Roads ≤ε": t.n_roads, "Top road percentile": t.max_pct * 100,
                         "Schools": t.schools, "Hospitals": t.hospitals, "Crossings": t.crossings})
    stretch(st.dataframe, show, hide_index=True, on_select="rerun", selection_mode="single-row", key="hs_table",
            column_config={"Serious share": st.column_config.ProgressColumn("Serious share", min_value=0, max_value=100, format="%.0f%%"),
                           "Top road percentile": st.column_config.NumberColumn(format="%.1f")})
