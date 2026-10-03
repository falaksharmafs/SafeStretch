"""Road-risk API.  uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers"""
import hashlib
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from src.config import ROOT, TIMEZONE
from src.db import get_engine

from .auth import KEYS, require_admin, require_key
from .cache import cache
from .schemas import ReportIn, ReviewIn

log = logging.getLogger("api")
DISCLAIMER = ("Decision-support only. Scores are statistical estimates from reported accidents (which are "
              "under-reported) and are not a guarantee of safety or danger.")
HASH_SALT = os.getenv("HASH_SALT", "change-me")
limiter = Limiter(key_func=get_remote_address, default_limits=[os.getenv("RATE_LIMIT", "60/minute")])

app = FastAPI(title="Road Risk API", version="1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
if not KEYS:
    log.warning("API_KEYS not set - API is OPEN (development mode)")


def q(sql, **params):
    with get_engine().begin() as con:      # begin() so INSERT ... RETURNING is committed
        res = con.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()] if res.returns_rows else []


def multipliers():
    m = cache.get("mult")
    if m is None:
        m = {f"{r['kind']}:{r['key']}": float(r["value"]) for r in q("SELECT kind, key, value FROM risk_multipliers")}
        cache.set("mult", m, 300)
    return m


def rain_now():
    rows = q("SELECT rain_mm, ts FROM live_conditions ORDER BY ts DESC LIMIT 1")
    if not rows or (datetime.now(rows[0]["ts"].tzinfo) - rows[0]["ts"]).total_seconds() > 3 * 3600:
        return "dry", None
    mm = rows[0]["rain_mm"] or 0
    return ("heavy" if mm >= 2.5 else "light" if mm >= 0.1 else "dry"), rows[0]["ts"]


def level(pct):
    return "high" if pct >= 0.95 else "elevated" if pct >= 0.80 else "normal"


@app.get("/health")
def health():
    try:
        r = q("SELECT (SELECT MAX(as_of_period) FROM segment_risk) AS model_as_of, "
              "(SELECT MAX(ts) FROM live_conditions) AS weather_ts")[0]
        return {"status": "ok", **r}
    except Exception as e:
        raise HTTPException(503, f"database unavailable: {e.__class__.__name__}")


@app.get("/risk", dependencies=[Depends(require_key)])
def risk(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), at: datetime | None = None):
    """Risk for the road nearest to a point, optionally at a given time (ISO 8601)."""
    rows = q("""
        WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g),
        n AS (SELECT s.segment_id, s.name, s.road_type, ST_Distance(s.geom::geography, p.g::geography) AS dist_m
              FROM road_segments s, p ORDER BY s.geom <-> p.g LIMIT 1)
        SELECT n.*, r.risk_prob, r.risk_rank, r.risk_pct, r.reason_1, r.reason_2, r.reason_3, r.as_of_period,
               e.eb_rank,
               (SELECT congestion_ratio FROM live_traffic t WHERE t.segment_id = n.segment_id
                  AND t.ts > now() - interval '1 hour' ORDER BY ts DESC LIMIT 1) AS congestion_ratio
        FROM n JOIN segment_risk r USING (segment_id) LEFT JOIN segment_eb e USING (segment_id)""", lat=lat, lon=lon)
    if not rows or rows[0]["dist_m"] > 100:
        raise HTTPException(404, "No scored road within 100 m of that point")
    r = rows[0]
    tz = ZoneInfo(TIMEZONE)
    when = (at.astimezone(tz) if at and at.tzinfo else (at.replace(tzinfo=tz) if at else datetime.now(tz)))
    m = multipliers()
    rain_key, rain_ts = rain_now()
    tm, rm = m.get(f"hour:{when.hour}", 1.0), m.get(f"rain:{rain_key}", 1.0)
    return {
        "segment": {"segment_id": r["segment_id"], "name": r["name"], "road_type": r["road_type"],
                    "distance_m": round(r["dist_m"], 1)},
        "base": {"risk_prob_next_quarter": r["risk_prob"], "risk_rank": r["risk_rank"], "risk_pct": r["risk_pct"],
                 "eb_rank": r["eb_rank"], "level": level(r["risk_pct"]), "model_as_of": r["as_of_period"]},
        "live": {"hour": when.hour, "time_multiplier": tm, "rain": rain_key, "rain_multiplier": rm,
                 "live_index": r["risk_prob"] * tm * rm, "note": "relative index, not a probability"},
        "congestion_ratio": r["congestion_ratio"],
        "reasons": [x for x in (r["reason_1"], r["reason_2"], r["reason_3"]) if x],
        "disclaimer": DISCLAIMER,
    }


def route_for(s, d, lam):
    rows = q("SELECT seq, segment_id, length_m, risk_pct, geom_json FROM route_between(:s, :d, :lam)", s=s, d=d, lam=lam)
    if not rows:
        return None
    total = sum(r["length_m"] for r in rows)
    coords = [json.loads(r["geom_json"])["coordinates"] for r in rows]
    return {
        "type": "Feature",
        "geometry": {"type": "MultiLineString", "coordinates": coords},
        "properties": {"length_m": round(total), "mean_risk_pct": round(sum(r["length_m"] * r["risk_pct"] for r in rows) / total, 4),
                       "high_risk_segments": sum(1 for r in rows if r["risk_pct"] >= 0.95),
                       "segment_ids": [r["segment_id"] for r in rows]},
    }


def nearest_node(lat, lon):
    rows = q("""WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
                SELECT node_id, ST_Distance(geom::geography, p.g::geography) AS d
                FROM road_nodes, p ORDER BY geom <-> p.g LIMIT 1""", lat=lat, lon=lon)
    if not rows or rows[0]["d"] > 500:
        raise HTTPException(404, "No road within 500 m of that point")
    return rows[0]["node_id"]


@app.get("/route", dependencies=[Depends(require_key)])
def route(from_lat: float, from_lon: float, to_lat: float, to_lon: float, lam: float = Query(3.0, ge=0, le=20)):
    """Fastest (shortest) vs safest route. lam = how strongly risk is penalised (0 = shortest)."""
    key = f"route:{from_lat:.4f},{from_lon:.4f},{to_lat:.4f},{to_lon:.4f},{lam}"
    hit = cache.get(key)
    if hit:
        return hit
    s, d = nearest_node(from_lat, from_lon), nearest_node(to_lat, to_lon)
    if s == d:
        raise HTTPException(422, "Start and end snap to the same intersection")
    fast, safe = route_for(s, d, 0.0), route_for(s, d, lam)
    if not fast:
        raise HTTPException(404, "No drivable path between those points")
    fp, sp = fast["properties"], safe["properties"]
    out = {"fastest": fast, "safest": safe,
           "comparison": {"extra_distance_m": sp["length_m"] - fp["length_m"],
                          "extra_distance_pct": round(100 * (sp["length_m"] / fp["length_m"] - 1), 1),
                          "risk_reduction_pct": round(100 * (1 - sp["mean_risk_pct"] / fp["mean_risk_pct"]), 1)
                          if fp["mean_risk_pct"] else 0.0,
                          "same_route": fp["segment_ids"] == sp["segment_ids"]},
           "disclaimer": DISCLAIMER}
    cache.set(key, out, 600)
    return out


@app.get("/hotspots", dependencies=[Depends(require_key)])
def hotspots(n: int = Query(100, ge=1, le=1000)):
    key = f"hot:{n}"
    hit = cache.get(key)
    if hit:
        return hit
    try:
        rows = q("SELECT n_accidents, n_serious, ST_AsGeoJSON(geometry)::json AS g FROM hotspot_clusters "
                 "ORDER BY n_serious DESC, n_accidents DESC LIMIT :n", n=n)
    except ProgrammingError:
        rows = []
    out = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": r["g"], "properties": {"n_accidents": r["n_accidents"], "n_serious": r["n_serious"]}}
        for r in rows]}
    cache.set(key, out, 600)
    return out


@app.get("/segments/top", dependencies=[Depends(require_key)])
def top_segments(n: int = Query(50, ge=1, le=500), by: str = Query("ml", pattern="^(ml|eb)$")):
    join, order = (("segment_risk r", "r.risk_rank"), ("segment_eb e", "e.eb_rank"))[by == "eb"]
    alias = join.split()[1]
    return q(f"SELECT s.segment_id, s.name, s.road_type, {order} AS rank, ST_AsGeoJSON(s.geom)::json AS geometry "
             f"FROM road_segments s JOIN {join} ON {alias}.segment_id = s.segment_id ORDER BY {order} LIMIT :n", n=n)


@app.post("/reports", status_code=201, dependencies=[Depends(require_key)])
@limiter.limit("5/minute")
def create_report(request: Request, body: ReportIn):
    ip = request.client.host if request.client else "unknown"
    h = hashlib.sha256((HASH_SALT + ip).encode()).hexdigest()[:16]
    if q("SELECT COUNT(*) AS n FROM user_reports WHERE reporter_hash = :h AND created_at > now() - interval '1 day'",
         h=h)[0]["n"] >= 20:
        raise HTTPException(429, "Daily report limit reached")
    rows = q("""WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
                INSERT INTO user_reports (kind, description, reporter_hash, geom, segment_id)
                SELECT :kind, :desc, :h, p.g, (SELECT segment_id FROM road_segments ORDER BY geom <-> p.g LIMIT 1)
                FROM p WHERE EXISTS (SELECT 1 FROM study_area WHERE ST_Intersects(geom, p.g))
                RETURNING id""", lon=body.lon, lat=body.lat, kind=body.kind, desc=body.description.strip(), h=h)
    if not rows:
        raise HTTPException(422, "Location is outside the study area")
    return {"id": rows[0]["id"], "status": "pending", "message": "Thanks - reports are reviewed before they appear."}


@app.get("/reports", dependencies=[Depends(require_key)])
def list_reports(days: int = Query(7, ge=1, le=60)):
    rows = q("SELECT id, kind, description, created_at, ST_AsGeoJSON(geom)::json AS g FROM user_reports "
             "WHERE status = 'approved' AND created_at > now() - make_interval(days => :d)", d=days)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": r["g"], "properties": {k: r[k] for k in ("id", "kind", "description", "created_at")}}
        for r in rows]}


@app.post("/admin/reports/{report_id}", dependencies=[Depends(require_admin)])
def review_report(report_id: int, body: ReviewIn):
    n = q("UPDATE user_reports SET status = :s WHERE id = :i RETURNING id", s=body.status, i=report_id)
    if not n:
        raise HTTPException(404, "No such report")
    return {"id": report_id, "status": body.status}


@app.get("/admin/reports/pending", dependencies=[Depends(require_admin)])
def pending_reports():
    return q("SELECT id, kind, description, created_at, ST_Y(geom) AS lat, ST_X(geom) AS lon "
             "FROM user_reports WHERE status = 'pending' ORDER BY created_at LIMIT 200")


if (ROOT / "web").exists():
    app.mount("/app", StaticFiles(directory=ROOT / "web", html=True), name="web")
