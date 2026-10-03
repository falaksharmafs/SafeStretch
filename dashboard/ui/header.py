import pandas as pd
import streamlit as st

from .. import nav
from ..config import APP_NAME, TAGLINE
from ..core import model_info as M
from ..core import queries as Q
from ..core.status import system_status
from . import theme as th
from .compat import is_dark

STATE_LABEL = {"ok": "ok", "warn": "warn", "error": "error", "off": "off"}


def _search(query, seg, hs):
    q = query.strip().lower()
    out = []
    if not q or seg.empty:
        return out
    if q.isdigit():
        hit = seg[seg.segment_id == int(q)]
        out += [("segment", int(r.segment_id), r.label, f"Segment #{r.segment_id} · {r.road_type}") for r in hit.itertuples()]
    if q.startswith(("hotspot", "hs")) and not hs.empty:
        num = "".join(ch for ch in q if ch.isdigit())
        hit = hs[hs.cluster_id == int(num)] if num else hs.head(5)
        out += [("hotspot", int(r.cluster_id), f"Hotspot {int(r.cluster_id)}", f"{int(r.n_accidents)} accidents · near {r.nearest_label}") for r in hit.itertuples()]
    by_name = seg[seg.label.str.lower().str.contains(q, regex=False)].head(6) if not q.isdigit() else seg.iloc[0:0]
    out += [("segment", int(r.segment_id), r.label, f"{r.road_type} · rank #{int(r.risk_rank):,} · {r.band}") for r in by_name.itertuples()]
    if q in set(seg.road_type.str.lower()):
        top = seg[seg.road_type.str.lower() == q].head(3)
        out += [("segment", int(r.segment_id), r.label, f"Top-ranked '{q}' road · rank #{int(r.risk_rank):,}") for r in top.itertuples()]
    if not hs.empty:
        near = hs[hs.nearest_label.str.lower().str.contains(q, regex=False)].head(3)
        out += [("hotspot", int(r.cluster_id), f"Hotspot {int(r.cluster_id)}", f"near {r.nearest_label} · {int(r.n_accidents)} accidents") for r in near.itertuples()]
    seen, uniq = set(), []
    for item in out:
        if item[:2] not in seen:
            seen.add(item[:2])
            uniq.append(item)
    return uniq[:8]


def _open(kind, ident, seg, hs):
    ss = st.session_state
    if kind == "segment":
        r = seg[seg.segment_id == ident].iloc[0]
        ss.sel_segment = ident
        ss.view = {"lat": float(r.lat) if pd.notna(r.lat) else None, "lon": float(r.lon) if pd.notna(r.lon) else None, "zoom": 15.2}
        if ss.view["lat"] is None:
            path = Q.segment_path(ident)
            if path:
                ss.view = {"lat": path[len(path) // 2][1], "lon": path[len(path) // 2][0], "zoom": 15.2}
        st.switch_page(nav.PAGES["map"])
    else:
        r = hs[hs.cluster_id == ident].iloc[0]
        ss.sel_hotspot = ident
        ss.hs_view = {"lat": float(r.lat), "lon": float(r.lon), "zoom": 16.2}
        st.switch_page(nav.PAGES["hotspots"])


def render():
    seg, hs, area, acc, m = Q.segments(), Q.hotspots(), Q.study_area(), Q.accident_facts(), M.metrics()
    status = system_status()
    states = {s for _, s, _ in status if s != "off"}
    overall = "error" if "error" in states else "warn" if "warn" in states else "ok"

    c1, c2, c3 = st.columns([2.3, 5.0, 2.7], vertical_alignment="center", gap="medium")
    with c1:
        th.render(f'<div class="ss-brand">{th.LOGO}<div><div class="name">{APP_NAME}</div><div class="tag">{TAGLINE}</div></div></div>')
    with c2:
        as_of = seg.as_of_period.dropna().iloc[0] if not seg.empty and seg.as_of_period.notna().any() else None
        pills = [th.pill(area["name"] if area else "Study area N/A", None, "Area"),
                 th.pill(f"{pd.Timestamp(as_of):%d %b %Y}" if as_of is not None else "N/A", None, "Scores as of"),
                 th.pill(M.version(m), None, "Model"),
                 th.pill({"ok": "All core services online", "warn": "Attention needed", "error": "Service down"}[overall], overall),
                 th.pill("Dark" if is_dark() else "Light", None, "Theme")]
        if acc.get("synthetic"):
            pills.insert(0, '<span class="ss-pill" style="border-color:#F5B83D"><span class="ss-dot warn"></span><b>SYNTHETIC DATA</b></span>')
        th.render('<div class="ss-meta">' + "".join(pills) + "</div>")
    with c3:
        a, b = st.columns([3, 1.25], vertical_alignment="center")
        query = a.text_input("Search", placeholder="Search roads, hotspots, IDs…", label_visibility="collapsed", key="global_search")
        with b.popover(":material/monitor_heart: System") if _popover_ok() else b.container():
            th.render('<div style="min-width:250px">' + th.rows([(n, f"● {d}") for n, s, d in status]) + "</div>")
            st.caption("Theme follows Streamlit's setting: ⋮ menu → Settings → Theme.")
    if query:
        results = _search(query, seg, hs)
        with st.expander(f"{len(results)} result(s)" if results else "No matches", expanded=True):
            for i, (kind, ident, title, sub) in enumerate(results):
                r1, r2 = st.columns([5, 1], vertical_alignment="center")
                r1.markdown(f"**{title}**  \n<span style='opacity:.65;font-size:.82rem'>{sub}</span>", unsafe_allow_html=True)
                if r2.button("Open", key=f"srch_{i}_{kind}_{ident}"):
                    _open(kind, ident, seg, hs)
            st.caption("Reports will be searchable once the Reports page is added.")


def _popover_ok():
    return hasattr(st, "popover")
