"""Load risk-related points of interest from a local OpenStreetMap PBF."""

import geopandas as gpd
import pyogrio
from sqlalchemy import text

from ..config import PLACE_NAME, ROOT
from ..db import get_engine


PBF_PATH = ROOT / "data" / "planet_77.584,29.84_78.954,30.553.osm.pbf"

# Dehradun study area
WEST = 77.95
SOUTH = 30.25
EAST = 78.15
NORTH = 30.40


def main():
    eng = get_engine()

    print("Reading POIs from local PBF...")

    points = pyogrio.read_dataframe(
        PBF_PATH,
        layer="points",
        bbox=(WEST, SOUTH, EAST, NORTH),
    )

    print(f"Read {len(points):,} OSM points.")

    frames = []

    # -------------------------
    # Schools
    # -------------------------
    schools = points[
        points["other_tags"].fillna("").str.contains(
            '"amenity"=>"school"',
            regex=False,
        )
    ].copy()

    if len(schools):
        frames.append(
            gpd.GeoDataFrame(
                {"category": ["school"] * len(schools)},
                geometry=schools.geometry,
                crs="EPSG:4326",
            )
        )
        print(f"school: {len(schools)}")

    # -------------------------
    # Hospitals
    # -------------------------
    hospitals = points[
        points["other_tags"].fillna("").str.contains(
            '"amenity"=>"hospital"',
            regex=False,
        )
    ].copy()

    if len(hospitals):
        frames.append(
            gpd.GeoDataFrame(
                {"category": ["hospital"] * len(hospitals)},
                geometry=hospitals.geometry,
                crs="EPSG:4326",
            )
        )
        print(f"hospital: {len(hospitals)}")

    # -------------------------
    # Bus stops
    # -------------------------
    bus_stops = points[
        points["highway"].fillna("").eq("bus_stop")
    ].copy()

    if len(bus_stops):
        frames.append(
            gpd.GeoDataFrame(
                {"category": ["bus_stop"] * len(bus_stops)},
                geometry=bus_stops.geometry,
                crs="EPSG:4326",
            )
        )
        print(f"bus_stop: {len(bus_stops)}")

    # -------------------------
    # Pedestrian crossings
    # -------------------------
    crossings = points[
        points["highway"].fillna("").eq("crossing")
    ].copy()

    if len(crossings):
        frames.append(
            gpd.GeoDataFrame(
                {"category": ["crossing"] * len(crossings)},
                geometry=crossings.geometry,
                crs="EPSG:4326",
            )
        )
        print(f"crossing: {len(crossings)}")

    # -------------------------
    # Bars / pubs
    # -------------------------
    tags = points["other_tags"].fillna("")

    bars = points[
        tags.str.contains('"amenity"=>"bar"', regex=False)
        | tags.str.contains('"amenity"=>"pub"', regex=False)
    ].copy()

    if len(bars):
        frames.append(
            gpd.GeoDataFrame(
                {"category": ["alcohol_outlet"] * len(bars)},
                geometry=bars.geometry,
                crs="EPSG:4326",
            )
        )
        print(f"alcohol_outlet: {len(bars)}")

    # -------------------------
    # Make sure we found something
    # -------------------------
    if not frames:
        raise RuntimeError("No POIs found in the study area.")

    poi = gpd.pd.concat(
        frames,
        ignore_index=True,
    )

    # Remove invalid geometries
    poi = poi[poi.geometry.notna()].copy()
    poi = poi[~poi.geometry.is_empty].copy()

    poi = poi.rename_geometry("geom")

    # -------------------------
    # Load into PostGIS
    # -------------------------
    with eng.begin() as con:
        con.execute(
            text("TRUNCATE poi RESTART IDENTITY")
        )

    poi.to_postgis(
        "poi",
        eng,
        if_exists="append",
        index=False,
    )

    with eng.begin() as con:
        con.execute(
            text("ANALYZE poi")
        )

    print(f"Loaded {len(poi):,} POIs.")


if __name__ == "__main__":
    main()