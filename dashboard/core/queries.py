"""All SQL lives here. Each function degrades gracefully (empty frame / None) when a table or column is missing."""
import json

import numpy as np
import pandas as pd
import streamlit as st

from ..config import GRID_DEG, HOTSPOT_EPS_M, POI_RADIUS_M, TIMEZONE
from . import schema as S
from .db import read, scalar
from .risk import band_for, pct_from_rank

TTL = 120
NUM_STATIC = ["speed_limit", "lanes", "length_m", "curvature", "lat", "lon", "alcohol_nearby", "junctions_nearby",
              "schools_nearby", "hospitals_nearby", "bus_stops_nearby", "crossings_nearby"]


def _col(alias, cols, name, cast="double precision", as_=None):
    return f"{alias}.{name} AS {as_ or name}" if name in cols else f"NULL::{cast} AS {as_ or name}"


# ------------------------------------------------------------------ master segment frame
@st.cache_data(ttl=TTL, show_spinner="Loading segments…")
def segments() -> pd.DataFrame:
    """One row per scored road segment: attributes + risk + history + (optional) EB / calibrated probability."""
    r, f, s = S.columns("segment_risk"), S.columns("segment_static_features"), S.columns("road_segments")
    if not r or not s:
        return pd.DataFrame()
    c_ok, e_ok = S.has_table("segment_period_counts"), S.has_table("segment_eb")
    fields = [
        "s.segment_id", _col("s", s, "name", "text"), _col("s", s, "road_type", "text"),
        _col("s", s, "length_m") if "length_m" in s else _col("f", f, "length_m"),
        _col("f", f, "speed_limit"), _col("f", f, "lanes"), _col("f", f, "oneway", "boolean"),
        _col("f", f, "curvature"), _col("f", f, "lat"), _col("f", f, "lon"),
        *[_col("f", f, c) for c in NUM_STATIC[6:]],
        "r.risk_score", "r.risk_rank", _col("r", r, "risk_prob"), _col("r", r, "risk_pct"),
        _col("r", r, "reason_1", "text"), _col("r", r, "reason_2", "text"), _col("r", r, "reason_3", "text"),
        _col("r", r, "as_of_period", "date"),
        *(["COALESCE(c.n_acc,0) AS n_acc", "COALESCE(c.n_serious,0) AS n_serious", "COALESCE(c.n_night,0) AS n_night",
           "COALESCE(c.n_rain,0) AS n_rain"] if c_ok else
          ["NULL::int AS n_acc", "NULL::int AS n_serious", "NULL::int AS n_night", "NULL::int AS n_rain"]),
        *(["e.eb_estimate", "e.eb_rank", "e.observed AS eb_observed", "e.exposure AS eb_exposure",
           "e.expected_rate AS eb_expected"] if e_ok else
          ["NULL::float AS eb_estimate", "NULL::int AS eb_rank", "NULL::int AS eb_observed",
           "NULL::float AS eb_exposure", "NULL::float AS eb_expected"]),
    ]
    sql = f"""SELECT {', '.join(fields)}
              FROM road_segments s
              JOIN segment_risk r ON r.segment_id = s.segment_id
              {'LEFT JOIN segment_static_features f ON f.segment_id = s.segment_id' if f else ''}
              {'''LEFT JOIN (SELECT segment_id, SUM(n_acc)::int n_acc, SUM(n_serious)::int n_serious,
                       SUM(n_night)::int n_night, SUM(n_rain)::int n_rain
                       FROM segment_period_counts GROUP BY 1) c ON c.segment_id = s.segment_id''' if c_ok else ''}
              {'LEFT JOIN segment_eb e ON e.segment_id = s.segment_id' if e_ok else ''}
              ORDER BY r.risk_rank"""
    df = read(sql)
    if df.empty:
        return df
    for c in NUM_STATIC + ["risk_score", "risk_rank", "risk_prob", "risk_pct", "n_acc", "n_serious", "n_night",
                           "n_rain", "eb_estimate", "eb_rank", "eb_observed", "eb_exposure", "eb_expected"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")        # speed_limit / lanes can arrive as text
    n = len(df)
    if df.risk_pct.isna().all():
        df["risk_pct"] = [pct_from_rank(x, n) for x in df.risk_rank]
    df["band"] = df.risk_pct.map(band_for)
    df["road_type"] = df.road_type.fillna("unknown")
    df["name"] = df.name.fillna("")
    df["oneway"] = df.oneway.fillna(False).astype(bool)
    df["label"] = np.where(df.name != "", df.name, "Segment #" + df.segment_id.astype(str))
    return df


@st.cache_data(ttl=300, show_spinner=False)
def road_paths(max_rank: int) -> pd.DataFrame:
    """Simplified polylines for the top-`max_rank` segments (compact payload for the browser)."""
    df = read("""SELECT s.segment_id, ST_AsGeoJSON(ST_SimplifyPreserveTopology(s.geom, 0.00001), 6) AS gj
                 FROM road_segments s JOIN segment_risk r ON r.segment_id = s.segment_id
                 WHERE r.risk_rank <= :k""", k=int(max_rank))
    paths = []
    for gj in df.gj:
        g = json.loads(gj)
        coords = g["coordinates"] if g["type"] == "LineString" else (g["coordinates"][0] if g["coordinates"] else [])
        paths.append(coords)
    df["path"] = paths
    return df[["segment_id", "path"]]


# ------------------------------------------------------------------ study area, accidents, POIs
@st.cache_data(ttl=600, show_spinner=False)
def study_area():
    if not S.has_table("study_area"):
        return None
    df = read("""SELECT name, ST_AsGeoJSON(ST_Simplify(geom, 0.0005)) AS gj, ST_XMin(geom) w, ST_YMin(geom) s,
                        ST_XMax(geom) e, ST_YMax(geom) n, ST_Area(geom::geography) / 1e6 AS km2
                 FROM study_area LIMIT 1""")
    if df.empty:
        return None
    r = df.iloc[0]
    return {"name": r["name"], "geojson": json.loads(r.gj), "bounds": (r.w, r.s, r.e, r.n), "km2": float(r.km2)}


@st.cache_data(ttl=TTL, show_spinner=False)
def accident_facts() -> dict:
    if not S.has_table("accidents"):
        return {"n": 0}
    r = read("""SELECT COUNT(*) n, MIN(occurred_at) t0, MAX(occurred_at) t1,
                       COUNT(*) FILTER (WHERE severity = 1) fatal, COUNT(*) FILTER (WHERE severity = 2) serious
                FROM accidents""").iloc[0]
    sources = read("SELECT DISTINCT source FROM accidents").source.dropna().tolist()
    return {"n": int(r.n), "t0": r.t0, "t1": r.t1, "fatal": int(r.fatal), "serious": int(r.serious),
            "sources": sources, "synthetic": any("synth" in str(x).lower() for x in sources)}


@st.cache_data(ttl=TTL, show_spinner=False)
def accidents_points(d0, d1, severities: tuple, h0: int, h1: int, limit: int = 25000) -> pd.DataFrame:
    hour = "EXTRACT(hour FROM occurred_at AT TIME ZONE :tz)"
    hour_sql = f"{hour} BETWEEN :h0 AND :h1" if h0 <= h1 else f"({hour} >= :h0 OR {hour} <= :h1)"
    return read(f"""SELECT accident_id, occurred_at, severity, segment_id, ST_X(geom) AS lon, ST_Y(geom) AS lat
                    FROM accidents
                    WHERE occurred_at >= :d0 AND occurred_at < (CAST(:d1 AS date) + 1)
                      AND severity = ANY(:sev) AND {hour_sql}
                    ORDER BY occurred_at DESC LIMIT :lim""",
                d0=d0, d1=d1, sev=list(severities), h0=h0, h1=h1, tz=TIMEZONE, lim=limit)


@st.cache_data(ttl=600, show_spinner=False)
def poi_points() -> pd.DataFrame:
    if not S.has_table("poi"):
        return pd.DataFrame(columns=["category", "lon", "lat"])
    return read("SELECT category, ST_X(geom) lon, ST_Y(geom) lat FROM poi")


# ------------------------------------------------------------------ hotspots
@st.cache_data(ttl=TTL, show_spinner="Analysing hotspots…")
def hotspots() -> pd.DataFrame:
    """Hotspot clusters (as stored by src.models.hotspots) + derived context. Derived columns are labelled as such
    in the UI: they describe what lies within the DBSCAN radius of the cluster centre, not exact cluster membership."""
    cols, gc = S.columns("hotspot_clusters"), S.geom_col("hotspot_clusters")
    if not cols or not gc:
        return pd.DataFrame()
    idc = next((c for c in ("cluster", "cluster_id") if c in cols), None)
    idx = f"h.{idc}" if idc else "row_number() OVER ()"
    poi_join = f"""LEFT JOIN LATERAL (SELECT COUNT(*) FILTER (WHERE category = 'school') AS schools,
                           COUNT(*) FILTER (WHERE category = 'hospital') AS hospitals,
                           COUNT(*) FILTER (WHERE category = 'bus_stop') AS bus_stops,
                           COUNT(*) FILTER (WHERE category = 'crossing') AS crossings,
                           COUNT(*) FILTER (WHERE category = 'alcohol_outlet') AS alcohol
                    FROM poi p WHERE ST_DWithin(p.geom::geography, h.{gc}::geography, {POI_RADIUS_M})) np ON TRUE"""
    poi_cols = "np.schools, np.hospitals, np.bus_stops, np.crossings, np.alcohol"
    if not S.has_table("poi"):
        poi_join, poi_cols = "", ("NULL::int AS schools, NULL::int AS hospitals, NULL::int AS bus_stops, "
                                  "NULL::int AS crossings, NULL::int AS alcohol")
    df = read(f"""
        SELECT {idx}::int AS cluster_id, h.n_accidents, h.n_serious, ST_X(h.{gc}) AS lon, ST_Y(h.{gc}) AS lat,
               nr.segment_id AS nearest_segment, nr.name AS nearest_name, nr.road_type AS nearest_type,
               ar.n_roads, ar.best_rank, {poi_cols}
        FROM hotspot_clusters h
        LEFT JOIN LATERAL (SELECT s.segment_id, {'s.name' if 'name' in S.columns('road_segments') else 'NULL::text AS name'},
                                  s.road_type
                           FROM road_segments s ORDER BY s.geom <-> h.{gc} LIMIT 1) nr ON TRUE
        LEFT JOIN LATERAL (SELECT COUNT(*) AS n_roads, MIN(r.risk_rank) AS best_rank
                           FROM road_segments s LEFT JOIN segment_risk r ON r.segment_id = s.segment_id
                           WHERE ST_DWithin(s.geom::geography, h.{gc}::geography, {HOTSPOT_EPS_M})) ar ON TRUE
        {poi_join}
        ORDER BY h.n_serious DESC, h.n_accidents DESC""")
    if df.empty:
        return df
    n = max(S.row_count("segment_risk"), 1)
    # best (highest) model-risk percentile among roads within the cluster radius; N/A if none scored
    df["max_pct"] = df.best_rank.map(lambda r: None if pd.isna(r) else pct_from_rank(r, n))
    df["max_pct"] = pd.to_numeric(df.max_pct, errors="coerce")
    df["serious_share"] = np.where(df.n_accidents > 0, df.n_serious / df.n_accidents, np.nan)
    df["nearest_label"] = np.where(df.nearest_name.fillna("") != "", df.nearest_name,
                                   df.nearest_type.fillna("road").astype(str) + " (unnamed)")
    return df


# ------------------------------------------------------------------ KPI / time / weather facts
@st.cache_data(ttl=TTL, show_spinner=False)
def quarterly_counts() -> pd.DataFrame:
    if not S.has_table("accidents"):
        return pd.DataFrame()
    return read("""SELECT date_trunc('quarter', occurred_at)::date AS quarter, COUNT(*) AS accidents,
                          COUNT(*) FILTER (WHERE severity <= 2) AS serious
                   FROM accidents GROUP BY 1 ORDER BY 1""")


@st.cache_data(ttl=TTL, show_spinner=False)
def weather_now() -> dict:
    """Live conditions if the live feed is running, else the newest archive row (clearly marked as not live)."""
    if S.has_table("live_conditions"):
        d = read("SELECT ts, rain_mm, temp_c, visibility_m FROM live_conditions ORDER BY ts DESC LIMIT 1")
        if not d.empty:
            r = d.iloc[0]
            age_h = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(r.ts)).total_seconds() / 3600
            if age_h <= 3:
                return {"live": True, "ts": r.ts, "rain_mm": r.rain_mm, "temp_c": r.temp_c, "visibility_m": r.visibility_m}
    if S.has_table("weather_hourly"):
        d = read("SELECT hour_ts AS ts, rain_mm, temp_c FROM weather_hourly ORDER BY hour_ts DESC LIMIT 1")
        if not d.empty:
            r = d.iloc[0]
            return {"live": False, "ts": r.ts, "rain_mm": r.rain_mm, "temp_c": r.temp_c, "visibility_m": None}
    return {"live": False, "ts": None, "rain_mm": None, "temp_c": None, "visibility_m": None}


@st.cache_data(ttl=TTL, show_spinner=False)
def hour_counts() -> np.ndarray:
    counts = np.zeros(24)
    if S.has_table("accidents"):
        d = read("SELECT EXTRACT(hour FROM occurred_at AT TIME ZONE :tz)::int AS h, COUNT(*) AS n "
                 "FROM accidents GROUP BY 1", tz=TIMEZONE)
        counts[d.h.values] = d.n.values
    return counts


@st.cache_data(ttl=TTL, show_spinner=False)
def rain_stats() -> pd.DataFrame:
    if not (S.has_table("weather_hourly") and S.has_table("accidents")):
        return pd.DataFrame()
    case = ("CASE WHEN COALESCE(w.rain_mm,0) >= 2.5 THEN 'Heavy rain' WHEN COALESCE(w.rain_mm,0) >= 0.1 "
            "THEN 'Light rain' ELSE 'Dry' END")
    h = read(f"SELECT {case} AS cond, COUNT(*) AS hours FROM weather_hourly w GROUP BY 1")
    a = read(f"SELECT {case} AS cond, COUNT(*) AS accidents FROM accidents x "
             "JOIN weather_hourly w ON w.hour_ts = date_trunc('hour', x.occurred_at) GROUP BY 1")
    return h.merge(a, on="cond", how="left").fillna({"accidents": 0})


@st.cache_data(ttl=TTL, show_spinner=False)
def severity_counts() -> pd.DataFrame:
    if not S.has_table("accidents"):
        return pd.DataFrame(columns=["severity", "n"])
    return read("SELECT severity, COUNT(*) AS n FROM accidents GROUP BY 1 ORDER BY 1")


# ------------------------------------------------------------------ data health
@st.cache_data(ttl=60, show_spinner=False)
def health_facts() -> dict:
    f = {"accidents": S.row_count("accidents"), "roads": S.row_count("road_segments"),
         "weather": S.row_count("weather_hourly"), "poi": S.row_count("poi"), "snapped": 0, "duplicates": 0,
         "out_of_area": 0, "invalid_geom": 0, "future": 0, "bad_severity": 0, "null_speed": 0, "null_lanes": 0,
         "poi_counts": {}, "last_accident": None, "last_weather": None, "snap_p95": None}
    if f["accidents"]:
        a = read("""SELECT COUNT(*) FILTER (WHERE segment_id IS NOT NULL) snapped,
                           COUNT(*) - COUNT(DISTINCT (occurred_at, geom::text)) dups,
                           COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) invalid,
                           COUNT(*) FILTER (WHERE occurred_at > now()) future,
                           COUNT(*) FILTER (WHERE severity NOT IN (1,2,3)) bad_sev,
                           MAX(occurred_at) last_ts,
                           percentile_cont(0.95) WITHIN GROUP (ORDER BY snap_dist_m) p95
                    FROM accidents""").iloc[0]
        f.update(snapped=int(a.snapped), duplicates=int(a.dups), invalid_geom=int(a.invalid), future=int(a.future),
                 bad_severity=int(a.bad_sev), last_accident=a.last_ts, snap_p95=a.p95)
        if S.has_table("study_area"):
            f["out_of_area"] = int(scalar("""SELECT COUNT(*) FROM accidents x WHERE NOT EXISTS
                                             (SELECT 1 FROM study_area sa WHERE ST_Intersects(sa.geom, x.geom))""", 0))
    if f["roads"]:
        s = S.columns("road_segments")
        for key, col in (("null_speed", "speed_limit"), ("null_lanes", "lanes")):
            f[key] = int(scalar(f"SELECT COUNT(*) FROM road_segments WHERE {col} IS NULL", 0)) if col in s else f["roads"]
    if f["poi"]:
        d = read("SELECT category, COUNT(*) n FROM poi GROUP BY 1")
        f["poi_counts"] = dict(zip(d.category, d.n.astype(int)))
    if f["weather"]:
        f["last_weather"] = scalar("SELECT MAX(hour_ts) FROM weather_hourly")
    return f


@st.cache_data(ttl=60, show_spinner=False)
def dq_log() -> pd.DataFrame:
    if not S.has_table("data_quality_log"):
        return pd.DataFrame()
    return read("SELECT run_at, check_name, passed, level, detail FROM data_quality_log ORDER BY id DESC LIMIT 40")


@st.cache_data(ttl=300, show_spinner=False)
def segment_path(segment_id: int):
    d = read("SELECT ST_AsGeoJSON(geom, 6) AS gj FROM road_segments WHERE segment_id = :i", i=int(segment_id))
    if d.empty:
        return []
    g = json.loads(d.gj[0])
    return g["coordinates"] if g["type"] == "LineString" else (g["coordinates"][0] if g["coordinates"] else [])


@st.cache_data(ttl=300, show_spinner=False)
def accidents_near(lon: float, lat: float, radius_m: float = 150) -> pd.DataFrame:
    return read("""SELECT accident_id, occurred_at, severity, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM accidents
                   WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)""",
                lon=lon, lat=lat, r=radius_m)
