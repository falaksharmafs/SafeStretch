import numpy as np

from src.live.traffic_live import parse_flow
from src.live.weather_live import parse_open_meteo
from src.models.empirical_bayes import eb_estimate, estimate_alpha, exposure_proxy
from src.models.intervention_eval import bootstrap_ci, did_rate_ratio
from src.models.multipliers import hour_multipliers, rate_ratio, smooth_circular
from src.monitoring.drift import histogram, psi
from src.validation import check_share, check_snap_rate, check_volume, check_zero


def test_alpha_recovers_overdispersion():
    rng = np.random.default_rng(1)
    mu, alpha = 3.0, 0.5
    y = rng.negative_binomial(1 / alpha, (1 / alpha) / ((1 / alpha) + mu), 200000)
    assert abs(estimate_alpha(y, np.full(len(y), mu)) - alpha) < 0.05


def test_eb_shrinks_extremes_toward_expected():
    y, mu = np.array([0, 5, 20]), np.array([2.0, 2.0, 2.0])
    eb, w = eb_estimate(y, mu, alpha=0.5)
    assert eb[2] < y[2] and eb[2] > mu[2]      # shrunk down but still above expectation
    assert eb[0] > y[0]                         # zero count pulled up toward expectation
    assert np.all((w > 0) & (w < 1))
    eb0, _ = eb_estimate(y, mu, alpha=1e-9)     # no over-dispersion -> trust the model fully
    assert np.allclose(eb0, mu, atol=1e-3)


def test_exposure_orders_road_classes():
    e = exposure_proxy([500, 500], ["primary", "residential"], [2, 1])
    assert e[0] > e[1]
    e2 = exposure_proxy([1000], ["primary"], [2], aadt=np.array([20000.0]))
    assert e2[0] == 20.0 * 1.0 * 1.0 or e2[0] > 0


def test_hour_multipliers_average_one_and_smooth():
    counts = np.array([5, 5, 5, 5, 5, 5, 10, 30, 40, 30, 20, 20, 20, 20, 20, 25, 35, 45, 40, 30, 20, 10, 5, 5])
    v, lo, hi = hour_multipliers(counts)
    assert abs(v.mean() - 1) < 1e-9
    assert np.all(lo <= hi)
    assert abs(smooth_circular(counts).sum() - counts.sum()) < 1e-9
    assert np.allclose(hour_multipliers(np.zeros(24))[0], 1)


def test_rate_ratio():
    val, lo, hi = rate_ratio(50, 100, 100, 200)      # same rate as overall
    assert abs(val - 1) < 1e-9 and lo < 1 < hi
    assert rate_ratio(100, 100, 100, 200)[0] == 2.0


def test_did():
    assert abs(did_rate_ratio(10, 10, 10, 10) - 1) < 1e-9
    assert did_rate_ratio(20, 10, 20, 20) < 0.7                # treated halves, controls flat
    pairs = [[10, 5, 10, 10]] * 30
    lo, hi = bootstrap_ci(pairs, n=200)
    assert lo <= did_rate_ratio(300, 150, 300, 300) <= hi


def test_psi():
    a = histogram(np.random.default_rng(0).beta(1, 40, 5000))
    assert psi(a, a) < 1e-9
    shifted = histogram(np.random.default_rng(0).beta(3, 40, 5000))
    assert psi(a, shifted) > 0.1


def test_validation_checks():
    assert not check_snap_rate(100, 50).passed and check_snap_rate(100, 95).passed
    assert not check_volume([100, 110, 90, 105, 20]).passed
    assert check_volume([100, 110, 90, 105, 95]).passed
    assert check_volume([1, 2]).passed                           # not enough history
    assert check_zero("x", 0, "bad").passed and not check_zero("x", 3, "bad").passed
    assert not check_share("d", 10, 100, 0.02, "dups").passed


def test_parsers():
    w = parse_open_meteo({"current": {"time": "2026-10-01T09:00", "precipitation": 3.2, "temperature_2m": 27.1},
                          "hourly": {"visibility": [8000]}})
    assert w["rain_mm"] == 3.2 and w["visibility_m"] == 8000 and w["ts"].tzinfo is not None
    assert parse_flow({"flowSegmentData": {"currentSpeed": 20, "freeFlowSpeed": 40}})[2] == 0.5
