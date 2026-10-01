"""Generate SYNTHETIC accident data so the whole pipeline can be tested end to end.

The risk is deliberately tied to road features (junctions, alcohol outlets, curves, school zones,
speed, night hours). Because the data is generated from those rules, any model will 'discover'
them - use this ONLY to test the pipeline and never quote its results as real findings.
The dashboard shows a warning whenever source = 'synthetic' is present.
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from ..config import DATA_DIR
from ..db import get_engine

BASE = {"motorway": 3.0, "trunk": 3.0, "primary": 2.5, "secondary": 2.0, "tertiary": 1.5}
HOUR_W = np.array([3, 3, 3, 2, 2, 2, 3, 5, 7, 6, 5, 5, 5, 5, 5, 6, 7, 8, 8, 7, 6, 5, 4, 3], float)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30000)
    p.add_argument("--start", default="2019-01-01")
    p.add_argument("--end", default="2023-12-31")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    rng = np.random.default_rng(a.seed)

    q = """SELECT s.segment_id, s.road_type, s.speed_limit, s.length_m, s.geom,
                  f.curvature, f.alcohol_nearby, f.junctions_nearby, f.schools_nearby
           FROM road_segments s JOIN segment_static_features f ON f.segment_id = s.segment_id"""
    g = gpd.read_postgis(q, get_engine(), geom_col="geom").reset_index(drop=True)

    risk = (0.5 + 0.4 * g.junctions_nearby.fillna(0) + 0.8 * g.alcohol_nearby.fillna(0)
            + 0.3 * g.schools_nearby.fillna(0) + 1.5 * (g.curvature.fillna(1) > 1.15))
    w = g.road_type.map(BASE).fillna(1.0) * risk * np.clip(g.length_m, 20, 500)
    idx = rng.choice(len(g), size=a.n, p=(w / w.sum()).values)
    frac = rng.random(a.n)
    pts = [g.geometry.iloc[i].interpolate(f, normalized=True) for i, f in zip(idx, frac)]

    days = pd.to_datetime(a.start) + pd.to_timedelta(
        rng.integers(0, (pd.to_datetime(a.end) - pd.to_datetime(a.start)).days + 1, a.n), unit="D")
    hours = rng.choice(24, size=a.n, p=HOUR_W / HOUR_W.sum())
    ts = days + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(rng.integers(0, 60, a.n), unit="m")

    fast = (g.speed_limit.fillna(40).iloc[idx].values >= 60)
    u = rng.random(a.n)
    sev = np.where(u < np.where(fast, 0.12, 0.05), 1, np.where(u < np.where(fast, 0.42, 0.25), 2, 3))

    out = pd.DataFrame({
        "lat": [p.y for p in pts], "lon": [p.x for p in pts], "timestamp": ts,
        "severity": sev, "vehicles": rng.integers(1, 4, a.n), "casualties": rng.integers(1, 4, a.n),
    })
    path = DATA_DIR / "raw" / "synthetic_accidents.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {len(out):,} synthetic accidents -> {path}")


if __name__ == "__main__":
    main()
