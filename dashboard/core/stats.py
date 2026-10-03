"""Self-contained copies of the small statistics used by the pipeline (so the dashboard has no hard dependency on
modules that only exist in the upgraded project)."""
import numpy as np


def smooth_circular(v, w=(0.25, 0.5, 0.25)):
    v = np.asarray(v, float)
    return w[0] * np.roll(v, 1) + w[1] * v + w[2] * np.roll(v, -1)


def hour_profile(counts):
    """24 hourly accident counts -> (multiplier, lo, hi). Multiplier averages 1; interval is Poisson 95%."""
    c = np.asarray(counts, float)
    mean = c.mean()
    if mean == 0:
        return np.ones(24), np.ones(24), np.ones(24)
    half = 1.96 * np.sqrt(np.maximum(c, 1))
    return smooth_circular(c) / mean, np.maximum(c - half, 0) / mean, (c + half) / mean


def rate_ratio(count, hours, total_count, total_hours):
    """Accident rate per weather-hour in a condition relative to the overall rate, with Poisson 95% interval."""
    if hours <= 0 or total_hours <= 0 or total_count <= 0:
        return None
    base = total_count / total_hours
    half = 1.96 * np.sqrt(max(count, 1))
    return {"value": (count / hours) / base, "lo": max(count - half, 0) / hours / base,
            "hi": (count + half) / hours / base}


def psi_status(psi, warn=0.10, alert=0.25):
    if psi is None:
        return "unknown"
    return "healthy" if psi < warn else ("monitor" if psi < alert else "investigate")


def last_two_complete(q, t_last):
    """q: DataFrame(quarter, accidents, serious). Returns (previous, latest) rows of the last two COMPLETE quarters, or None.
    A quarter is complete if the data reaches (within a day of) its end - avoids comparing a partial quarter."""
    import pandas as pd
    if q is None or len(q) < 2 or t_last is None:
        return None
    d = q.copy()
    d["quarter"] = pd.to_datetime(d["quarter"])
    end = d["quarter"] + pd.offsets.QuarterEnd(0)
    t = pd.Timestamp(t_last)
    t = t.tz_localize(None) if t.tzinfo is not None else t
    d = d[t.normalize() >= end - pd.Timedelta(days=1)]
    return None if len(d) < 2 else (d.iloc[-2], d.iloc[-1])


def ramp(t, stops=((0.0, (48, 164, 108)), (0.5, (245, 184, 61)), (1.0, (229, 72, 77)))):
    """Green -> amber -> red for t in [0,1]; returns [r, g, b, a]."""
    t = min(max(float(t), 0.0), 1.0)
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            f = (t - a) / (b - a) if b > a else 0
            return [int(ca[i] + (cb[i] - ca[i]) * f) for i in range(3)] + [200]
    return list(stops[-1][1]) + [200]
