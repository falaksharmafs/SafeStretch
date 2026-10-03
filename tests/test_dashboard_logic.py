"""Pure-logic tests for the dashboard (no Streamlit, no database)."""
import numpy as np
import pandas as pd

from dashboard.core.health import build_checks, overall
from dashboard.core.risk import (band_for, fmt_float, fmt_int, fmt_km, fmt_pct, human_age, parse_reason,
                                 pct_from_rank, percentile_of, top_overlap)
from dashboard.core.stats import hour_profile, last_two_complete, psi_status, rate_ratio, ramp


def test_rank_percentile_and_bands():
    assert pct_from_rank(1, 1000) == 1.0 and pct_from_rank(1000, 1000) == 0.0
    assert band_for(1.0) == "Critical" and band_for(0.96) == "High" and band_for(0.85) == "Moderate" and band_for(0.2) == "Low"
    n = 10000
    bands = pd.Series([band_for(pct_from_rank(r, n)) for r in range(1, n + 1)]).value_counts()
    assert 80 <= bands["Critical"] <= 120 and 350 <= bands["High"] <= 450     # ~1% and ~4%


def test_formatters_never_invent_values():
    assert fmt_int(None) == "N/A" and fmt_int(float("nan")) == "N/A" and fmt_int(1234.6) == "1,235"
    assert fmt_float(None) == "N/A" and fmt_pct(None) == "N/A" and fmt_km(None) == "N/A"
    assert fmt_km(850) == "850 m" and fmt_km(2500) == "2.5 km"
    assert human_age(None) == "N/A"


def test_parse_reason_and_percentile():
    assert parse_reason("junctions nearby: 3") == ("junctions nearby", "3")
    assert parse_reason("") is None and parse_reason(None) is None
    s = pd.Series([0, 0, 1, 2, 3])
    assert percentile_of(3, s) == 0.8 and percentile_of("x", s) is None


def test_top_overlap():
    o = top_overlap([1, 2, 3, 4], [3, 4, 5, 6])
    assert o["shared"] == 2 and o["only_a"] == 2 and o["only_b"] == 2 and abs(o["jaccard"] - 1 / 3) < 1e-9


def test_hour_profile_and_rate_ratio():
    v, lo, hi = hour_profile(np.arange(1, 25) * 10)
    assert abs(v.mean() - 1) < 1e-9 and np.all(lo <= hi)
    rr = rate_ratio(50, 100, 100, 200)
    assert abs(rr["value"] - 1) < 1e-9 and rr["lo"] < 1 < rr["hi"]
    assert rate_ratio(5, 0, 100, 200) is None


def test_psi_status_uses_project_thresholds():
    assert psi_status(0.05) == "healthy" and psi_status(0.15) == "monitor" and psi_status(0.4) == "investigate"
    assert psi_status(None) == "unknown"


def test_last_two_complete_ignores_partial_quarter():
    q = pd.DataFrame({"quarter": ["2023-01-01", "2023-04-01", "2023-07-01", "2023-10-01"], "accidents": [10, 12, 11, 5], "serious": [4, 5, 3, 1]})
    prev, last = last_two_complete(q, pd.Timestamp("2023-11-10"))      # Q4 only partly covered
    assert pd.Timestamp(last.quarter) == pd.Timestamp("2023-07-01") and prev.serious == 5
    prev, last = last_two_complete(q, pd.Timestamp("2023-12-31 23:00"))
    assert pd.Timestamp(last.quarter) == pd.Timestamp("2023-10-01")
    assert last_two_complete(q.head(1), pd.Timestamp("2023-12-31")) is None


def test_ramp_endpoints():
    assert ramp(0)[:3] == [48, 164, 108] and ramp(1)[:3] == [229, 72, 77] and len(ramp(0.5)) == 4


def _facts(**kw):
    f = dict(accidents=1000, roads=500, weather=100, poi=10, snapped=990, duplicates=0, out_of_area=0, invalid_geom=0, future=0,
             bad_severity=0, null_speed=100, null_lanes=100, poi_counts={c: 1 for c in ("junction", "school", "hospital", "crossing", "bus_stop", "alcohol_outlet")})
    f.update(kw)
    return f


def test_health_checks_flag_real_problems():
    assert overall(build_checks(_facts())) == "ok"
    assert overall(build_checks(_facts(snapped=500))) == "error"
    assert overall(build_checks(_facts(duplicates=100))) == "warn"
    poi = {"school": 3, "hospital": 2, "crossing": 1, "bus_stop": 1, "alcohol_outlet": 1}      # no junctions loaded
    names = [c.name for c in build_checks(_facts(poi_counts=poi)) if c.status == "warn"]
    assert "POI category 'junction'" in names
    assert build_checks(_facts(accidents=0))[0].status == "error"
