"""Score-distribution drift: Population Stability Index (PSI) between consecutive training runs.
PSI < 0.1 stable, 0.1-0.25 moderate shift, > 0.25 investigate."""
import json
import logging

import numpy as np

EDGES = np.array([0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0001])
log = logging.getLogger("drift")


def histogram(scores):
    h = np.histogram(np.clip(np.asarray(scores, float), 0, 1), EDGES)[0].astype(float)
    return h / max(h.sum(), 1.0)


def psi(expected, actual, eps=1e-4):
    e, a = np.clip(np.asarray(expected, float), eps, None), np.clip(np.asarray(actual, float), eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def record_snapshot(engine, scores, version):
    """Store this run's histogram and PSI against the previous run. Returns the PSI (or None)."""
    from sqlalchemy import text
    hist = histogram(scores)
    with engine.begin() as con:
        prev = con.execute(text("SELECT hist FROM risk_snapshots ORDER BY id DESC LIMIT 1")).first()
        value = psi(prev[0], hist) if prev else None
        con.execute(text("INSERT INTO risk_snapshots (model_version, hist, psi) VALUES (:v, CAST(:h AS jsonb), :p)"),
                    {"v": version, "h": json.dumps(hist.tolist()), "p": value})
    if value is not None and value > 0.25:
        log.warning("Score drift PSI=%.3f (>0.25) - investigate data or retrain", value)
    return value
