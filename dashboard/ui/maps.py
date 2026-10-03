"""PyDeck layer builders for SafeStretch dashboard maps."""

import math

import numpy as np
import pandas as pd
import pydeck as pdk

from ..config import (
    ACCENT,
    BAND_COLORS,
    BAND_WIDTH,
    HOTSPOT_COLOR,
    POI,
    SEVERITY,
)
from .theme import esc


# ============================================================
# COLOR HELPERS
# ============================================================

def rgba(hexc, a=255):
    """Convert #RRGGBB into [R, G, B, A]."""
    return [
        int(hexc[i:i + 2], 16)
        for i in (1, 3, 5)
    ] + [a]


# ============================================================
# MAP VIEW
# ============================================================

def view_for_bounds(b, w_px=950, h_px=640):
    """Calculate a suitable map center and zoom from bounds."""

    w, s, e, n = b

    dlon = max(e - w, 1e-4)
    dlat = max(n - s, 1e-4)

    zoom = min(
        math.log2(w_px * 360 / (512 * dlon)),
        math.log2(h_px * 360 / (512 * dlat)),
    ) - 0.15

    return {
        "lat": (s + n) / 2,
        "lon": (w + e) / 2,
        "zoom": round(zoom, 2),
    }


# ============================================================
# MAIN DECK
# ============================================================

def make_deck(layers, view, tooltip=True):
    """Create the main PyDeck map."""

    vs = pdk.ViewState(
        latitude=view["lat"],
        longitude=view["lon"],
        zoom=view["zoom"],
        pitch=0,
        bearing=0,
    )

    try:
        vs.transition_duration = 900
    except Exception:
        pass

    # Tooltip values from the dataframe are intentionally
    # plain text. HTML inside dataframe values is rendered as
    # literal text by PyDeck.
    #
    # white-space: pre-line allows \n in tip_detail to appear
    # as separate lines.

    tip = {
        "html": """
        <div style="
            font-family: Inter, Arial, sans-serif;
            min-width: 210px;
            max-width: 300px;
            line-height: 1.5;
        ">
            <div style="
                font-size: 13px;
                font-weight: 700;
                color: #F8FAFC;
                margin-bottom: 7px;
            ">
                {tip_title}
            </div>

            <div style="
                font-size: 12px;
                color: #CBD5E1;
                white-space: pre-line;
            ">
                {tip_detail}
            </div>
        </div>
        """,
        "style": {
            "backgroundColor": "rgba(15,23,42,0.97)",
            "color": "#E6EAF0",
            "borderRadius": "10px",
            "border": "1px solid rgba(148,163,184,0.30)",
            "padding": "10px 12px",
        },
    } if tooltip else None

    # OpenStreetMap basemap.
    #
    # This is explicitly added instead of relying on PyDeck's
    # default map provider so that the map remains visible in
    # the Streamlit dashboard.

    basemap = pdk.Layer(
        "TileLayer",
        data="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        min_zoom=0,
        max_zoom=19,
        tile_size=256,
        opacity=1,
    )

    return pdk.Deck(
        layers=[
            basemap,
            *layers,
        ],
        initial_view_state=vs,
        map_provider=None,
        map_style=None,
        tooltip=tip,
    )


# ============================================================
# ROAD RISK LAYER
# ============================================================

def road_layer(df, layer_id="roads"):
    """Create the road-risk PathLayer."""

    d = df.copy()

    d["color"] = d.band.map(
        lambda b: rgba(
            BAND_COLORS[b],
            225,
        )
    )

    d["w"] = d.band.map(BAND_WIDTH)

    d["tip_title"] = [
        esc(r.label)
        for r in d.itertuples()
    ]

    # Plain text only.
    # Newlines are rendered by white-space: pre-line
    # in the main tooltip template.

    d["tip_detail"] = [
        f"Type: {esc(r.road_type)}\n"
        f"Risk rank: #{int(r.risk_rank):,}\n"
        f"Risk band: {esc(r.band)}"
        for r in d.itertuples()
    ]

    return pdk.Layer(
        "PathLayer",
        data=d[
            [
                "segment_id",
                "path",
                "color",
                "w",
                "tip_title",
                "tip_detail",
            ]
        ],
        id=layer_id,
        get_path="path",
        get_color="color",
        get_width="w",
        width_units="pixels",
        width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 255, 110],
        cap_rounded=True,
        joint_rounded=True,
    )


# ============================================================
# SELECTED ROAD
# ============================================================

def selected_layer(path):
    """Highlight a selected road segment."""

    return pdk.Layer(
        "PathLayer",
        data=[
            {
                "path": path,
                "tip_title": "Selected segment",
                "tip_detail": "",
            }
        ],
        id="selected",
        get_path="path",
        get_color=[255, 255, 255, 255],
        get_width=11,
        width_units="pixels",
        width_min_pixels=6,
        cap_rounded=True,
        joint_rounded=True,
    )


# ============================================================
# HOTSPOTS
# ============================================================

def hotspot_layer(
    df,
    radius_m=120,
    layer_id="hotspots",
    selected=None,
):
    """Create accident hotspot circles."""

    d = df.copy()

    if d.empty:
        return pdk.Layer(
            "ScatterplotLayer",
            data=[],
            id=layer_id,
            get_position="[lon, lat]",
            pickable=True,
        )

    med = max(
        float(d.n_accidents.median()),
        1.0,
    )

    d["r"] = radius_m * np.clip(
        np.sqrt(
            d.n_accidents / med
        ),
        0.7,
        2.2,
    )

    d["tip_title"] = [
        f"Hotspot {int(r.cluster_id)}"
        for r in d.itertuples()
    ]

    # IMPORTANT:
    # Keep tooltip content as plain text.
    # Do NOT put <div> or <br> here.

    d["tip_detail"] = [
        f"Accidents: {int(r.n_accidents)}\n"
        f"Serious/fatal: {int(r.n_serious)}"
        for r in d.itertuples()
    ]

    d["fill"] = [
        rgba(
            HOTSPOT_COLOR,
            150 if c == selected else 85,
        )
        for c in d.cluster_id
    ]

    return pdk.Layer(
        "ScatterplotLayer",
        data=d[
            [
                "cluster_id",
                "lon",
                "lat",
                "r",
                "tip_title",
                "tip_detail",
                "fill",
            ]
        ],
        id=layer_id,
        get_position="[lon, lat]",
        get_radius="r",
        radius_units="meters",
        get_fill_color="fill",
        get_line_color=rgba(
            HOTSPOT_COLOR,
            235,
        ),
        stroked=True,
        line_width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    )


# ============================================================
# ACCIDENTS
# ============================================================

def accident_layer(df):
    """Create individual accident points."""

    d = df.copy()

    d["color"] = d.severity.map(
        lambda s: rgba(
            SEVERITY.get(
                int(s),
                ("", "#8B98A9"),
            )[1],
            190,
        )
    )

    d["tip_title"] = [
        esc(
            SEVERITY.get(
                int(r.severity),
                ("Unknown",),
            )[0]
        ) + " accident"
        for r in d.itertuples()
    ]

    d["tip_detail"] = [
        f"{pd.Timestamp(r.occurred_at):%d %b %Y %H:%M}"
        for r in d.itertuples()
    ]

    return pdk.Layer(
        "ScatterplotLayer",
        data=d[
            [
                "lon",
                "lat",
                "color",
                "tip_title",
                "tip_detail",
            ]
        ],
        id="accidents",
        get_position="[lon, lat]",
        get_radius=14,
        radius_units="meters",
        radius_min_pixels=2.5,
        get_fill_color="color",
        pickable=True,
    )


# ============================================================
# ACCIDENT DENSITY
# ============================================================

def accident_density(df):
    """Create an accident-density hexagon layer."""

    return pdk.Layer(
        "HexagonLayer",
        data=df[
            [
                "lon",
                "lat",
            ]
        ],
        id="accident_density",
        get_position="[lon, lat]",
        radius=140,
        coverage=0.92,
        extruded=False,
        pickable=False,
        opacity=0.65,
        color_range=[
            [255, 245, 204],
            [254, 217, 118],
            [253, 174, 97],
            [244, 109, 67],
            [215, 48, 39],
            [165, 0, 38],
        ],
    )


# ============================================================
# POIs
# ============================================================

def poi_layers(poi_df, cats):
    """Create layers for selected POI categories."""

    layers = []

    for cat in cats:

        sub = poi_df[
            poi_df.category == cat
        ]

        if sub.empty:
            continue

        label, color = POI[cat]

        d = sub.copy()

        d["tip_title"] = esc(label)

        d["tip_detail"] = [
            ""
            for _ in range(len(d))
        ]

        d["color"] = [
            rgba(color, 235)
        ] * len(d)

        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=d[
                    [
                        "lon",
                        "lat",
                        "tip_title",
                        "tip_detail",
                        "color",
                    ]
                ],
                id=f"poi_{cat}",
                get_position="[lon, lat]",
                get_radius=28,
                radius_units="meters",
                radius_min_pixels=4,
                get_fill_color="color",
                get_line_color=[
                    255,
                    255,
                    255,
                    200,
                ],
                stroked=True,
                line_width_min_pixels=1,
                pickable=True,
            )
        )

    return layers


# ============================================================
# STUDY-AREA BOUNDARY
# ============================================================

def boundary_layer(geojson):
    """Create the study-area boundary."""

    return pdk.Layer(
        "GeoJsonLayer",
        data={
            "type": "Feature",
            "geometry": geojson,
            "properties": {},
        },
        id="boundary",
        stroked=True,
        filled=False,
        get_line_color=rgba(
            ACCENT,
            200,
        ),
        line_width_min_pixels=2,
        pickable=False,
    )


# ============================================================
# ANALYTICS GRID
# ============================================================

def grid_layer(df):
    """Create the analytics grid layer."""

    return pdk.Layer(
        "PolygonLayer",
        data=df,
        id="grid",
        get_polygon="polygon",
        get_fill_color="color",
        stroked=True,
        get_line_color=[
            255,
            255,
            255,
            60,
        ],
        line_width_min_pixels=1,
        pickable=True,
        opacity=0.75,
    )


# ============================================================
# SEARCH / INSPECTION RING
# ============================================================

def ring_layer(lon, lat, radius_m):
    """Draw a non-filled radius ring."""

    return pdk.Layer(
        "ScatterplotLayer",
        data=[
            {
                "lon": lon,
                "lat": lat,
                "tip_title": (
                    f"Radius {radius_m:.0f} m"
                ),
                "tip_detail": "",
            }
        ],
        id="ring",
        get_position="[lon, lat]",
        get_radius=radius_m,
        radius_units="meters",
        filled=False,
        stroked=True,
        get_line_color=[
            255,
            255,
            255,
            230,
        ],
        line_width_min_pixels=2,
        pickable=False,
    )