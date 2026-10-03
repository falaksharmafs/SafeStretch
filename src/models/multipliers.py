"""Learn live-scoring multipliers from history.

hour : expected accident rate in each hour of day relative to the average hour (smoothed).
       Includes traffic exposure by design - rush hour is risky partly because it is busy.
rain : accidents per weather-hour in dry / light / heavy rain relative to the overall accidents per hour.
Each value comes with a Poisson 95% interval. Needs weather_hourly loaded (src.etl.load_weather).
"""
import numpy as np

from ..config import TIMEZONE

RAIN_SQL = "CASE WHEN COALESCE(w.rain_mm,0) >= 2.5 THEN 'heavy' WHEN COALESCE(w.rain_mm,0) >= 0.1 THEN 'light' ELSE 'dry' END"


def smooth_circular(v, w=(0.25, 0.5, 0.25)):
    v = np.asarray(v, float)
    return w[0] * np.roll(v, 1) + w[1] * v + w[2] * np.roll(v, -1)


def hour_multipliers(counts):
    """counts: 24 accident counts by local hour. Returns (value, lo, hi) arrays; mean value = 1."""
    c = np.asarray(counts, float)
    mean = c.mean()
    if mean == 0:
        return np.ones(24), np.ones(24), np.ones(24)
    half = 1.96 * np.sqrt(np.maximum(c, 1))
    return smooth_circular(c) / mean, np.maximum(c - half, 0) / mean, (c + half) / mean


def rate_ratio(count, hours, total_count, total_hours):
    """Rate in a condition relative to the overall rate, with Poisson 95% interval."""
    base = total_count / total_hours
    if hours <= 0 or base == 0:
        return 1.0, 1.0, 1.0
    half = 1.96 * np.sqrt(max(count, 1))
    return (count / hours) / base, max(count - half, 0) / hours / base, (count + half) / hours / base


def main():
    import pandas as pd
    from sqlalchemy import text

    from ..db import get_engine

    eng = get_engine()
    rows = []
    with eng.connect() as con:
        h = pd.read_sql(text("SELECT EXTRACT(hour FROM occurred_at AT TIME ZONE :tz)::int AS h, COUNT(*) AS n "
                             "FROM accidents GROUP BY 1"), con, params={"tz": TIMEZONE})
        counts = np.zeros(24)
        counts[h.h.values] = h.n.values
        v, lo, hi = hour_multipliers(counts)
        for i in range(24):
            rows.append(("hour", str(i), v[i], lo[i], hi[i], int(counts[i])))

        hrs = pd.read_sql(text(f"SELECT {RAIN_SQL} AS k, COUNT(*) AS hours FROM weather_hourly w GROUP BY 1"), con)
        acc = pd.read_sql(text(f"SELECT {RAIN_SQL} AS k, COUNT(*) AS n FROM accidents a "
                               "JOIN weather_hourly w ON w.hour_ts = date_trunc('hour', a.occurred_at) GROUP BY 1"), con)
    if len(hrs) and acc.n.sum() > 0:
        m = hrs.merge(acc, on="k", how="left").fillna({"n": 0}).set_index("k")
        for k in ("dry", "light", "heavy"):
            if k in m.index:
                val, l, u = rate_ratio(m.loc[k, "n"], m.loc[k, "hours"], m.n.sum(), m.hours.sum())
                rows.append(("rain", k, val, l, u, int(m.loc[k, "n"])))
    else:
        print("No weather overlap found - rain multipliers skipped (they default to 1.0).")

    out = pd.DataFrame(rows, columns=["kind", "key", "value", "lo", "hi", "n_events"])
    with eng.begin() as con:
        con.exec_driver_sql("TRUNCATE risk_multipliers")
        out.to_sql("risk_multipliers", con, if_exists="append", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
