"""Optional: hourly rain/temperature from Open-Meteo's free archive API for the study-area centroid."""
import pandas as pd
import requests
from sqlalchemy import text

from ..db import get_engine


def main():
    eng = get_engine()
    with eng.connect() as con:
        lat, lon = con.execute(text("SELECT ST_Y(ST_Centroid(geom)), ST_X(ST_Centroid(geom)) FROM study_area LIMIT 1")).one()
        d0, d1 = con.execute(text("SELECT MIN(occurred_at)::date, MAX(occurred_at)::date FROM accidents")).one()
    if d0 is None:
        raise SystemExit("Load accidents first so the date range is known")

    r = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={"latitude": lat, "longitude": lon, "start_date": str(d0), "end_date": str(d1),
                "hourly": "precipitation,temperature_2m", "timezone": "UTC"},
        timeout=120,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    df = pd.DataFrame({"hour_ts": pd.to_datetime(h["time"], utc=True),
                       "rain_mm": h["precipitation"], "temp_c": h["temperature_2m"]})
    with eng.begin() as con:
        con.execute(text("TRUNCATE weather_hourly"))
    df.to_sql("weather_hourly", eng, if_exists="append", index=False, method="multi", chunksize=5000)
    print(f"Loaded {len(df):,} weather hours ({d0} -> {d1}).")


if __name__ == "__main__":
    main()
