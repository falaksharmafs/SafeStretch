import streamlit as st
import pydeck as pdk
import pandas as pd

st.set_page_config(layout="wide")

df = pd.DataFrame([
    {
        "lon": 78.032,
        "lat": 30.316,
        "tip_title": "Hotspot 1",
        "tip_detail": """
        <div>Accidents: 42</div>
        <div>Serious/fatal: 7</div>
        """,
    }
])

layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[lon, lat]",
    get_radius=500,
    radius_units="meters",
    get_fill_color=[180, 70, 220, 180],
    pickable=True,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=pdk.ViewState(
        latitude=30.316,
        longitude=78.032,
        zoom=12,
    ),
    tooltip={
        "html": """
        <div style="
            font-family: Arial;
            min-width: 220px;
            line-height: 1.5;
        ">
            <div style="font-weight:700;">
                {tip_title}
            </div>
            <div>
                {tip_detail}
            </div>
        </div>
        """,
        "style": {
            "backgroundColor": "rgba(15,23,42,0.97)",
            "color": "#E6EAF0",
            "padding": "10px",
        },
    },
)

st.pydeck_chart(deck, width="stretch")