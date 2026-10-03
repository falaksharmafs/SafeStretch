"""Data-quality gate. Run before every retrain:  python -m src.validation   (exit code 1 on any error)."""
import sys
from collections import namedtuple

import numpy as np

Check = namedtuple("Check", "name passed level detail")


def check_snap_rate(total, snapped, minimum=0.9):
    rate = snapped / total if total else 0.0
    return Check("snap_rate", rate >= minimum, "error", f"{rate:.1%} of accidents matched a road (min {minimum:.0%})")


def check_volume(quarter_counts, min_ratio=0.5):
    """Latest quarter's record count vs the median of up to 4 earlier quarters (catches silent feed drops)."""
    if len(quarter_counts) < 3:
        return Check("volume_drop", True, "warn", "not enough history to compare")
    last, prev = quarter_counts[-1], float(np.median(quarter_counts[-5:-1]))
    ratio = last / prev if prev else 1.0
    return Check("volume_drop", ratio >= min_ratio, "warn", f"latest quarter = {ratio:.0%} of recent median")


def check_zero(name, n_bad, what, level="error"):
    return Check(name, n_bad == 0, level, f"{n_bad} {what}")


def check_share(name, n, total, max_share, what, level="warn"):
    share = n / total if total else 0.0
    return Check(name, share <= max_share, level, f"{share:.1%} {what} (max {max_share:.0%})")


def run_checks(eng):
    import pandas as pd
    q = lambda s: pd.read_sql(s, eng)
    total = int(q("SELECT COUNT(*) n FROM accidents").n[0])
    if total == 0:
        return [Check("has_data", False, "error", "accidents table is empty")]
    snapped = int(q("SELECT COUNT(*) n FROM accidents WHERE segment_id IS NOT NULL").n[0])
    dups = int(q("SELECT COUNT(*) - COUNT(DISTINCT (occurred_at, geom::text)) n FROM accidents").n[0])
    quarters = q("SELECT date_trunc('quarter', occurred_at) q, COUNT(*) n FROM accidents "
                 "WHERE occurred_at < date_trunc('quarter', now()) GROUP BY 1 ORDER BY 1").n.tolist()
    return [
        check_snap_rate(total, snapped),
        check_zero("future_dates", int(q("SELECT COUNT(*) n FROM accidents WHERE occurred_at > now()").n[0]),
                   "accidents dated in the future"),
        check_zero("ancient_dates", int(q("SELECT COUNT(*) n FROM accidents WHERE occurred_at < '2000-01-01'").n[0]),
                   "accidents before year 2000"),
        check_zero("severity_range", int(q("SELECT COUNT(*) n FROM accidents WHERE severity NOT IN (1,2,3)").n[0]),
                   "rows with severity outside 1-3"),
        check_share("duplicates", dups, total, 0.02, "duplicate (time, location) records"),
        check_volume(quarters),
        check_share("speed_limit_missing",
                    int(q("SELECT COUNT(*) n FROM road_segments WHERE speed_limit IS NULL").n[0]),
                    int(q("SELECT COUNT(*) n FROM road_segments").n[0]), 0.9, "segments missing speed limit (OSM gap)"),
    ]


def main():
    from sqlalchemy import text

    from .db import get_engine
    eng = get_engine()
    checks = run_checks(eng)
    failed = False
    with eng.begin() as con:
        for c in checks:
            con.execute(text("INSERT INTO data_quality_log (check_name, passed, level, detail) "
                             "VALUES (:n, :p, :l, :d)"), {"n": c.name, "p": c.passed, "l": c.level, "d": c.detail})
            print(f"[{'PASS' if c.passed else c.level.upper()}] {c.name}: {c.detail}")
            failed |= (not c.passed and c.level == "error")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
