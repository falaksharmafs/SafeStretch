"""Exposure-adjusted Empirical-Bayes black-spot ranking (Hauer-style).

Why: a segment with 5 crashes in one period may just be unlucky (regression to the mean), and busy roads
crash more simply because more vehicles use them. We therefore
  1. fit a Poisson GLM  log(mu) = X*beta + log(exposure)  -> expected crashes for 'similar' roads,
  2. estimate NB over-dispersion alpha by method of moments,
  3. shrink each segment's observed count toward its expected count:
        w = 1 / (1 + alpha*mu),    EB = w*mu + (1-w)*observed
Segments are ranked by EB, not by raw counts.

Exposure is a PROXY (length x road-class factor x lanes) unless you pass --traffic-csv (segment_id,aadt).
"""
import argparse

import numpy as np

ROAD_FACTOR = {"motorway": 3.0, "trunk": 3.0, "primary": 2.5, "secondary": 2.0, "tertiary": 1.5,
               "unclassified": 0.8, "residential": 0.7, "living": 0.4, "service": 0.3}


def exposure_proxy(length_m, road_type, lanes, aadt=None):
    """Relative vehicle-km exposure. If AADT is supplied, use it instead of the road-class guess."""
    length_km = np.clip(np.asarray(length_m, float), 20, None) / 1000.0
    if aadt is not None and not np.all(np.isnan(aadt)):
        a = np.where(np.isnan(aadt), np.nanmedian(aadt), aadt)
        return length_km * a / 1000.0
    group = np.array([str(r).split("_")[0] for r in road_type])
    factor = np.array([ROAD_FACTOR.get(g, 1.0) for g in group])
    lanes = np.where(np.isnan(np.asarray(lanes, float)), 1.0, np.asarray(lanes, float))
    return length_km * factor * np.sqrt(np.clip(lanes, 1, None))


def estimate_alpha(y, mu):
    """Method-of-moments NB dispersion: Var = mu + alpha*mu^2."""
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    return float(max(np.sum((y - mu) ** 2 - mu) / np.sum(mu ** 2), 1e-6))


def eb_estimate(y, mu, alpha):
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    w = 1.0 / (1.0 + alpha * mu)
    return w * mu + (1.0 - w) * y, w


def main():
    import pandas as pd
    import statsmodels.api as sm

    from ..db import get_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--serious", action="store_true", help="use serious/fatal crashes only")
    ap.add_argument("--traffic-csv", help="optional CSV with columns segment_id, aadt")
    a = ap.parse_args()

    eng = get_engine()
    st = pd.read_sql("SELECT s.*, r.length_m AS _l FROM segment_static_features s "
                     "JOIN road_segments r USING (segment_id)", eng).drop(columns="_l")
    col = "n_serious" if a.serious else "n_acc"
    obs = pd.read_sql(f"SELECT segment_id, SUM({col})::int AS y, COUNT(DISTINCT period_start) AS q "
                      "FROM segment_period_counts GROUP BY 1", eng)
    span = pd.read_sql("SELECT MIN(period_start) a, MAX(period_start) b FROM segment_period_counts", eng).iloc[0]
    years = max(((pd.to_datetime(span.b) - pd.to_datetime(span.a)).days + 92) / 365.25, 0.25)

    df = st.merge(obs[["segment_id", "y"]], on="segment_id", how="left").fillna({"y": 0})
    aadt = None
    if a.traffic_csv:
        t = pd.read_csv(a.traffic_csv)[["segment_id", "aadt"]]
        aadt = df[["segment_id"]].merge(t, on="segment_id", how="left")["aadt"].values.astype(float)
    exposure = exposure_proxy(df.length_m, df.road_type.fillna("unknown"), df.lanes.astype(float), aadt) * years

    top = df.road_type.fillna("unknown").str.split("_").str[0].value_counts().index[:8]
    grp = df.road_type.fillna("unknown").str.split("_").str[0].where(lambda s: s.isin(top), "other")
    X = pd.get_dummies(grp, prefix="rt", drop_first=True, dtype=float)
    X["speed"] = df.speed_limit.astype(float).fillna(df.speed_limit.astype(float).median()).fillna(40) / 50
    X["log_curv"] = np.log(df.curvature.clip(lower=1.0).astype(float))
    for c in ["junctions_nearby", "alcohol_nearby", "schools_nearby", "hospitals_nearby",
              "bus_stops_nearby", "crossings_nearby"]:
        X[c] = np.log1p(df[c].fillna(0).astype(float))
    X = sm.add_constant(X, has_constant="add")

    y = df.y.values.astype(float)
    res = sm.GLM(y, X, family=sm.families.Poisson(), offset=np.log(exposure)).fit()
    mu = np.asarray(res.mu)
    alpha = estimate_alpha(y, mu)
    eb, w = eb_estimate(y, mu, alpha)
    print(f"NB dispersion alpha={alpha:.3f}  (0 = pure Poisson); mean shrinkage weight={w.mean():.2f}")

    out = pd.DataFrame({"segment_id": df.segment_id, "exposure": exposure, "observed": y.astype(int),
                        "expected_rate": mu, "eb_estimate": eb})
    out["eb_rank"] = out.eb_estimate.rank(ascending=False, method="first").astype(int)
    with eng.begin() as con:
        con.exec_driver_sql("TRUNCATE segment_eb")
        out.to_sql("segment_eb", con, if_exists="append", index=False, method="multi", chunksize=5000)
    print(f"wrote {len(out):,} rows to segment_eb")


if __name__ == "__main__":
    main()
