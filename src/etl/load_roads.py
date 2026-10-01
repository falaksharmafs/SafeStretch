"""Load the drivable road network from a local OpenStreetMap PBF into PostGIS."""

import geopandas as gpd
import pyogrio
from shapely.geometry import box
from sqlalchemy import text

from ..config import PLACE_NAME, ROOT, SNAP_MAX_M
from ..db import get_engine
from .osm_utils import to_bool, to_int, to_text


PBF_PATH = ROOT / "data" / "planet_77.584,29.84_78.954,30.553.osm.pbf"

# Dehradun study area
WEST = 77.95
SOUTH = 30.25
EAST = 78.15
NORTH = 30.40

# Road types we actually want
DRIVABLE_ROADS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
}


def main():
    eng = get_engine()

    print(f"Loading roads from: {PBF_PATH}")
    print("Reading Dehradun road data from local PBF...")

    # Read only the Dehradun bounding box.
    roads = pyogrio.read_dataframe(
        PBF_PATH,
        layer="lines",
        bbox=(WEST, SOUTH, EAST, NORTH),
    )

    print(f"Read {len(roads):,} OSM line features.")

    # Keep only actual drivable roads.
    roads = roads[roads["highway"].isin(DRIVABLE_ROADS)].copy()

    print(f"Drivable roads: {len(roads):,}")

    # Remove empty geometries.
    roads = roads[roads.geometry.notna()].copy()
    roads = roads[~roads.geometry.is_empty].copy()

    # Create our database fields.
    df = gpd.GeoDataFrame(
        {
            # OSM provides osm_id rather than graph node IDs.
            # Use osm_id as a stable source identifier.
            "osm_u": roads["osm_id"].astype("int64"),
            "osm_v": roads["osm_id"].astype("int64"),

            "name": [
                to_text(v) for v in roads["name"]
            ],

            "road_type": [
                to_text(v, "unknown") for v in roads["highway"]
            ],

            "speed_limit": [
                to_int(v) for v in roads.get(
                    "maxspeed",
                    [None] * len(roads)
                )
            ],

            "lanes": [
                to_int(v) for v in roads.get(
                    "lanes",
                    [None] * len(roads)
                )
            ],

            "oneway": [
                to_bool(v) for v in roads.get(
                    "oneway",
                    [False] * len(roads)
                )
            ],

            "length_m": roads.to_crs("EPSG:32644").geometry.length.astype(float),

        },
        geometry=roads.geometry.values,
        crs="EPSG:4326",
    ).rename_geometry("geom")

    df["speed_limit"] = df["speed_limit"].astype("Int64")
    df["lanes"] = df["lanes"].astype("Int64")

    # Create the study-area polygon locally.
    # No Nominatim/Overpass request required.
    area_geom = box(WEST, SOUTH, EAST, NORTH)

    area = gpd.GeoDataFrame(
        {
            "name": [PLACE_NAME],
        },
        geometry=[area_geom],
        crs="EPSG:4326",
    ).rename_geometry("geom")

    with eng.begin() as con:
        # CASCADE clears dependent accident records as well.
        con.execute(
            text(
                "TRUNCATE study_area, road_segments "
                "RESTART IDENTITY CASCADE"
            )
        )

    area.to_postgis(
        "study_area",
        eng,
        if_exists="append",
        index=False,
    )

    df.to_postgis(
        "road_segments",
        eng,
        if_exists="append",
        index=False,
    )

    with eng.begin() as con:
        con.execute(text("ANALYZE road_segments"))

    print(f"Loaded {len(df):,} road segments into PostGIS.")


if __name__ == "__main__":
    main()