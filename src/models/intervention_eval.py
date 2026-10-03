"""Before/after evaluation of safety interventions with matched controls (difference-in-differences on rates).

Load interventions:  python -m src.models.intervention_eval --load data/interventions.csv
                     (columns: segment_id, kind, installed_on)
Evaluate:            python -m src.models.intervention_eval --window-months 12

For every treated segment we pick controls with the same road type and the closest pre-period count,
give them the same 'pseudo installation date', and compare change in serious accidents.
Matching on the pre-period count is what protects against regression to the mean.
Result is an association with a bootstrap interval, NOT a proven causal effect.
"""
import argparse
import json

import numpy as np


def did_rate_ratio(pre_t, post_t, pre_c, post_c):
    """(post/pre) for treated divided by (post/pre) for controls; +0.5 continuity correction. <1 = improvement."""
    return ((post_t + 0.5) / (pre_t + 0.5)) / ((post_c + 0.5) / (pre_c + 0.5))


def bootstrap_ci(pairs, n=2000, seed=0):
    """pairs: array (k,4) of per-intervention [pre_t, post_t, pre_c, post_c]; resample interventions."""
    rng = np.random.default_rng(seed)
    pairs = np.asarray(pairs, float)
    est = []
    for _ in range(n):
        s = pairs[rng.integers(0, len(pairs), len(pairs))].sum(axis=0)
        est.append(did_rate_ratio(*s))
    return float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))


def main():
    import pandas as pd

    from ..config import REPORTS_DIR
    from ..db import get_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--load")
    ap.add_argument("--window-months", type=int, default=12)
    ap.add_argument("--controls", type=int, default=5)
    a = ap.parse_args()
    eng = get_engine()

    if a.load:
        df = pd.read_csv(a.load)[["segment_id", "kind", "installed_on"]]
        df.to_sql("interventions", eng, if_exists="append", index=False)
        print(f"loaded {len(df)} interventions")
        return

    iv = pd.read_sql("SELECT segment_id, kind, installed_on FROM interventions", eng, parse_dates=["installed_on"])
    acc = pd.read_sql("SELECT segment_id, occurred_at::date AS d FROM accidents "
                      "WHERE severity <= 2 AND segment_id IS NOT NULL", eng, parse_dates=["d"])
    seg = pd.read_sql("SELECT segment_id, road_type FROM road_segments", eng).set_index("segment_id").road_type
    if iv.empty:
        raise SystemExit("No interventions loaded.")

    rng = np.random.default_rng(0)
    treated_ids = set(iv.segment_id)
    pairs, rows = [], []
    for r in iv.itertuples():
        t0 = r.installed_on
        lo, hi = t0 - pd.DateOffset(months=a.window_months), t0 + pd.DateOffset(months=a.window_months)
        if acc.d.min() > lo or acc.d.max() < hi:
            continue   # not enough data on both sides
        w = acc[(acc.d >= lo) & (acc.d < hi)]
        pre = w[w.d < t0].groupby("segment_id").size()
        post = w[w.d >= t0].groupby("segment_id").size()
        pre_t, post_t = int(pre.get(r.segment_id, 0)), int(post.get(r.segment_id, 0))
        pool = seg[(seg == seg.get(r.segment_id)) & (~seg.index.isin(treated_ids))].index.values
        if len(pool) < a.controls:
            continue
        pool_pre = pre.reindex(pool).fillna(0).values
        order = np.argsort(np.abs(pool_pre - pre_t) + rng.random(len(pool)) * 1e-3)[:a.controls]
        ctrl = pool[order]
        pre_c, post_c = int(pre.reindex(ctrl).fillna(0).sum()), int(post.reindex(ctrl).fillna(0).sum())
        pairs.append([pre_t, post_t, pre_c / a.controls, post_c / a.controls])
        rows.append({"segment_id": int(r.segment_id), "kind": r.kind, "pre": pre_t, "post": post_t,
                     "ctrl_pre_avg": pre_c / a.controls, "ctrl_post_avg": post_c / a.controls})
    if not pairs:
        raise SystemExit("No intervention had enough pre/post data and controls.")

    total = np.sum(pairs, axis=0)
    est = did_rate_ratio(*total)
    ci = bootstrap_ci(pairs)
    res = {"n_interventions": len(pairs), "window_months": a.window_months, "rate_ratio": est,
           "ci95": ci, "interpretation": "<1 means fewer serious accidents than matched controls after installation",
           "caveat": "observational; unmeasured changes (traffic, enforcement) can bias the estimate", "rows": rows}
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "intervention_effect.json").write_text(json.dumps(res, indent=2))
    print(f"rate ratio {est:.2f}  (95% CI {ci[0]:.2f} - {ci[1]:.2f}) over {len(pairs)} interventions")


if __name__ == "__main__":
    main()
