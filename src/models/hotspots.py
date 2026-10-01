"""Unsupervised hotspot discovery: DBSCAN on accident coordinates (haversine metric)."""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from ..db import get_engine

EARTH_R = 6371000.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--eps-m", type=float, default=100)
    p.add_argument("--min-samples", type=int, default=8)
    a = p.parse_args()

    eng = get_engine()
    df = pd.read_sql("SELECT accident_id, severity, ST_Y(geom) AS lat, ST_X(geom) AS lon FROM accidents", eng)
    labels = DBSCAN(eps=a.eps_m / EARTH_R, min_samples=a.min_samples, metric="haversine",
                    algorithm="ball_tree").fit_predict(np.radians(df[["lat", "lon"]].values))
    df["cluster"] = labels
    df = df[df.cluster >= 0]
    g = df.groupby("cluster").agg(n_accidents=("accident_id", "size"),
                                  n_serious=("severity", lambda s: int((s <= 2).sum())),
                                  lat=("lat", "mean"), lon=("lon", "mean")).reset_index()
    gdf = gpd.GeoDataFrame(g.drop(columns=["lat", "lon"]),
                           geometry=gpd.points_from_xy(g.lon, g.lat), crs="EPSG:4326")
    gdf.to_postgis("hotspot_clusters", eng, if_exists="replace", index=False)
    print(f"{len(gdf)} hotspot clusters (eps={a.eps_m} m, min_samples={a.min_samples})")


if __name__ == "__main__":
    main()
