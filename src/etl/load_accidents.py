"""Load accident records from CSV into PostGIS.

Examples
  python -m src.etl.load_accidents --file data/raw/synthetic_accidents.csv --preset synthetic
  python -m src.etl.load_accidents --file data/raw/stats19.csv --preset stats19
  python -m src.etl.load_accidents --file my.csv --lat-col Lat --lon-col Lon --date-col "Date Time" \
        --severity-col Severity --dayfirst

Severity must be 1 = fatal, 2 = serious, 3 = minor. Recode before loading if your data differs.
"""
import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import text

from ..config import TIMEZONE
from ..db import get_engine

PRESETS = {
    "stats19": dict(lat_col="latitude", lon_col="longitude", date_col="date", time_col="time",
                    severity_col="accident_severity", vehicles_col="number_of_vehicles",
                    casualties_col="number_of_casualties", dayfirst=True),
    "synthetic": dict(lat_col="lat", lon_col="lon", date_col="timestamp", time_col=None,
                      severity_col="severity", vehicles_col="vehicles", casualties_col="casualties",
                      dayfirst=False),
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--preset", choices=list(PRESETS))
    p.add_argument("--lat-col"); p.add_argument("--lon-col")
    p.add_argument("--date-col"); p.add_argument("--time-col")
    p.add_argument("--severity-col"); p.add_argument("--vehicles-col"); p.add_argument("--casualties-col")
    p.add_argument("--dayfirst", action="store_true", default=None)
    p.add_argument("--tz", default=TIMEZONE)
    a = p.parse_args()
    cfg = dict(PRESETS.get(a.preset, {}))
    cfg.update({k: v for k, v in vars(a).items() if v is not None and k not in ("preset", "file", "tz")})
    for req in ("lat_col", "lon_col", "date_col"):
        if not cfg.get(req):
            p.error(f"--{req.replace('_', '-')} is required (or use --preset)")
    return a, cfg


def main():
    args, cfg = parse_args()
    eng = get_engine()
    df = pd.read_csv(args.file, low_memory=False)
    df.columns = [c.strip() for c in df.columns] if not args.preset else [c.strip().lower() for c in df.columns]

    ts = df[cfg["date_col"]].astype(str)
    if cfg.get("time_col"):
        ts = ts + " " + df[cfg["time_col"]].astype(str)
    occurred = pd.to_datetime(ts, dayfirst=bool(cfg.get("dayfirst")), errors="coerce")
    if occurred.dt.tz is None:
        occurred = occurred.dt.tz_localize(args.tz, ambiguous="NaT", nonexistent="NaT")

    out = pd.DataFrame({
        "occurred_at": occurred,
        "severity": pd.to_numeric(df[cfg["severity_col"]], errors="coerce").fillna(3).clip(1, 3).astype(int)
        if cfg.get("severity_col") else 3,
        "vehicles": pd.to_numeric(df[cfg["vehicles_col"]], errors="coerce").fillna(1).astype(int)
        if cfg.get("vehicles_col") else 1,
        "casualties": pd.to_numeric(df[cfg["casualties_col"]], errors="coerce").fillna(0).astype(int)
        if cfg.get("casualties_col") else 0,
        "source": args.preset or Path(args.file).stem,
    })
    lat = pd.to_numeric(df[cfg["lat_col"]], errors="coerce")
    lon = pd.to_numeric(df[cfg["lon_col"]], errors="coerce")
    ok = occurred.notna() & lat.notna() & lon.notna()
    print(f"{len(df):,} rows read, {int((~ok).sum()):,} dropped (bad time/coordinates)")

    gdf = gpd.GeoDataFrame(out[ok], geometry=gpd.points_from_xy(lon[ok], lat[ok]), crs="EPSG:4326")
    gdf = gdf.rename_geometry("geom")

    # keep only accidents inside the study area
    area = gpd.read_postgis("SELECT geom FROM study_area", eng, geom_col="geom")
    if len(area) == 0:
        raise SystemExit("study_area is empty - run src.etl.load_roads first")
    boundary = area.geometry.union_all() if hasattr(area.geometry, "union_all") else area.geometry.unary_union
    inside = gdf.within(boundary)
    print(f"{int((~inside).sum()):,} outside study area, dropped")
    gdf = gdf[inside]

    with eng.begin() as con:
        con.execute(text("DELETE FROM accidents WHERE source = :s"), {"s": gdf["source"].iloc[0] if len(gdf) else ""})
    gdf.to_postgis("accidents", eng, if_exists="append", index=False)
    print(f"Loaded {len(gdf):,} accidents.")


if __name__ == "__main__":
    main()
