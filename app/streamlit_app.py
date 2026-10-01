import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import get_engine          # noqa: E402
from src.suggestions import suggest    # noqa: E402

st.set_page_config(page_title="Road Risk Map", layout="wide")
st.title("Road Accident Black-Spot Predictor")
st.caption("Ranks road segments by predicted risk of a serious accident next quarter. "
           "A prioritisation aid, not a certainty.")

eng = get_engine()

try:
    sources = pd.read_sql("SELECT DISTINCT source FROM accidents", eng).source.tolist()
    if "synthetic" in sources:
        st.warning("This database contains SYNTHETIC accident data. The map demonstrates the pipeline only.")
except Exception:
    st.error("Database not ready. Run the pipeline first (see README).")
    st.stop()

metrics_path = Path(__file__).resolve().parents[1] / "reports" / "metrics.json"
if metrics_path.exists():
    m = json.loads(metrics_path.read_text())
    with st.expander("Model validation"):
        c1, c2 = st.columns(2)
        for col, key, title in [(c1, "spatial_cv", "Spatial cross-validation"),
                                (c2, "temporal_test", "Temporal hold-out")]:
            col.subheader(title)
            col.dataframe(pd.DataFrame({"model": m[key]["model"],
                                        "history-only baseline": m[key]["baseline_history_only"]}))
        st.caption("recall_top5pct = share of future serious-accident segments captured in the top 5% ranked.")

top_n = st.sidebar.slider("Show top N riskiest segments", 50, 3000, 500, 50)
sql = f"""
SELECT r.segment_id, r.risk_score, r.risk_rank, r.reason_1, r.reason_2, r.reason_3,
       COALESCE(s.name, '') AS name, s.road_type, f.speed_limit, f.lanes, f.curvature,
       f.alcohol_nearby, f.junctions_nearby, f.schools_nearby, f.hospitals_nearby,
       f.bus_stops_nearby, f.crossings_nearby, s.geom
FROM segment_risk r
JOIN road_segments s ON s.segment_id = r.segment_id
JOIN segment_static_features f ON f.segment_id = r.segment_id
WHERE r.risk_rank <= {int(top_n)}
"""
gdf = gpd.read_postgis(sql, eng, geom_col="geom")
types = sorted(gdf.road_type.unique())
pick = st.sidebar.multiselect("Road types", types, default=types)
gdf = gdf[gdf.road_type.isin(pick)].copy()
if gdf.empty:
    st.info("No segments match the filters.")
    st.stop()

show_hot = st.sidebar.checkbox("Show DBSCAN hotspots", value=True)

gdf["color"] = gdf.risk_rank.apply(lambda r: [255, int(220 * r / top_n), 0, 210])
geojson = json.loads(gdf.to_json())
layers = [pdk.Layer("GeoJsonLayer", geojson, get_line_color="properties.color", get_line_width=10,
                    line_width_min_pixels=3, pickable=True)]
if show_hot:
    try:
        hot = pd.read_sql("SELECT n_accidents, n_serious, ST_X(geometry) AS lon, ST_Y(geometry) AS lat "
                          "FROM hotspot_clusters", eng)
        layers.append(pdk.Layer("ScatterplotLayer", hot, get_position="[lon, lat]", get_radius=60,
                                get_fill_color=[30, 90, 220, 120], pickable=True))
    except Exception:
        st.sidebar.caption("Run src.models.hotspots to enable the hotspot layer.")

minx, miny, maxx, maxy = gdf.total_bounds
st.pydeck_chart(pdk.Deck(
    layers=layers, map_provider="carto", map_style="light",
    initial_view_state=pdk.ViewState(latitude=(miny + maxy) / 2, longitude=(minx + maxx) / 2, zoom=11),
    tooltip={"html": "<b>{properties.name}</b> {properties.road_type}<br/>rank {properties.risk_rank}<br/>"
                     "{properties.reason_1}<br/>{properties.reason_2}<br/>{properties.reason_3}"}))

st.subheader("Top segments")
table = gdf.drop(columns=["geom", "geometry", "color"], errors="ignore").sort_values("risk_rank")
st.dataframe(table, use_container_width=True, height=300)

st.subheader("Segment detail")
sid = st.selectbox("Segment", table.segment_id.tolist())
row = table[table.segment_id == sid].iloc[0]
st.write(f"**Rank {row.risk_rank}** | score {row.risk_score:.3f} | {row['name'] or 'unnamed road'} ({row.road_type})")
st.write("**Why it is risky (model drivers):** " + "; ".join(x for x in [row.reason_1, row.reason_2, row.reason_3] if x))
st.write("**Suggested checks (rule-based):**")
for tip in suggest(row):
    st.write(f"- {tip}")
