"""Fetch current conditions from Open-Meteo (free, no key) for the study-area centroid."""
from datetime import datetime, timezone

import requests

URL = "https://api.open-meteo.com/v1/forecast"


def parse_open_meteo(j):
    cur = j["current"]
    vis = (j.get("hourly", {}).get("visibility") or [None])[0]
    return {
        "ts": datetime.fromisoformat(cur["time"]).replace(tzinfo=timezone.utc),
        "rain_mm": float(cur.get("precipitation") or 0.0),
        "temp_c": cur.get("temperature_2m"),
        "visibility_m": vis,
    }


def fetch(lat, lon):
    r = requests.get(URL, timeout=30, params={
        "latitude": lat, "longitude": lon, "current": "precipitation,temperature_2m",
        "hourly": "visibility", "forecast_hours": 1, "timezone": "UTC"})
    r.raise_for_status()
    return parse_open_meteo(r.json())


def main():
    from sqlalchemy import text

    from ..db import get_engine
    eng = get_engine()
    with eng.connect() as con:
        lat, lon = con.execute(text("SELECT ST_Y(ST_Centroid(geom)), ST_X(ST_Centroid(geom)) "
                                    "FROM study_area LIMIT 1")).one()
    c = fetch(lat, lon)
    with eng.begin() as con:
        con.execute(text("""INSERT INTO live_conditions (ts, rain_mm, visibility_m, temp_c, source)
                            VALUES (:ts, :rain_mm, :visibility_m, :temp_c, 'open-meteo')
                            ON CONFLICT (ts) DO UPDATE SET rain_mm = EXCLUDED.rain_mm,
                              visibility_m = EXCLUDED.visibility_m, temp_c = EXCLUDED.temp_c"""), c)
        con.execute(text("DELETE FROM live_conditions WHERE ts < now() - interval '7 days'"))
    print(f"live conditions {c['ts']:%Y-%m-%d %H:%M}Z rain={c['rain_mm']} mm")


if __name__ == "__main__":
    main()
