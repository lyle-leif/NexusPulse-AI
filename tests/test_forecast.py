import numpy as np
import pandas as pd
import pytest

from nexuspulse_analytics import daily_kpis
from nexuspulse_analytics.forecast import TRANSFORMS, fit_forecast, metric_frame, z_score
from nexuspulse_generator import MAIN_FASHION, generate_store


@pytest.fixture(scope="module")
def metrics():
    store = generate_store(MAIN_FASHION, seed=31, days=280)
    return metric_frame(daily_kpis(store.tables(), store.profile.timezone))


def _backtest(m, metric, model):
    errs, cover = [], []
    for k in range(180, len(m) - 7, 7):
        fc = fit_forecast(m[metric].iloc[:k], metric, 7, model=model)
        for dt, row in fc.frame.iterrows():
            a = m.at[dt, metric]
            errs.append(abs(z_score(a, row, metric)) * row["sigma"])
            cover.append(row["lo"] <= a <= row["hi"])
    return np.mean(errs), np.mean(cover)


@pytest.mark.parametrize("metric", ["sessions", "net_sales"])
def test_ets_beats_seasonal_naive_and_intervals_are_reasonable(metrics, metric):
    ets_err, ets_cov = _backtest(metrics, metric, "ets")
    naive_err, _ = _backtest(metrics, metric, "seasonal_naive")
    assert ets_err < naive_err
    assert 0.85 <= ets_cov <= 1.0


def test_forecast_never_sees_future(metrics):
    hist = metrics["sessions"].iloc[:200]
    a = fit_forecast(hist, "sessions", 7)
    changed = metrics["sessions"].copy()
    changed.iloc[200:] *= 5  # tamper with the future
    b = fit_forecast(changed.iloc[:200], "sessions", 7)
    pd.testing.assert_frame_equal(a.frame, b.frame)
    assert a.frame.index[0] == hist.index[-1] + pd.Timedelta(days=1)


def test_robust_fit_resists_outliers(metrics):
    clean = metrics["sessions"].iloc[:200].copy()
    dirty = clean.copy()
    dirty.iloc[-10:-7] *= 4  # a 3-day spike a week before the forecast origin
    base = fit_forecast(clean, "sessions", 7, robust=False).frame["mean"]
    plain = fit_forecast(dirty, "sessions", 7, robust=False).frame["mean"]
    robust = fit_forecast(dirty, "sessions", 7, robust=True).frame["mean"]
    assert (robust - base).abs().mean() < (plain - base).abs().mean()


def test_excluded_days_do_not_modify_raw_series(metrics):
    hist = metrics["orders"].iloc[:200]
    before = hist.copy()
    fit_forecast(hist, "orders", 7, exclude_days=hist.index[-20:-10])
    pd.testing.assert_series_equal(hist, before)


def test_all_metrics_produce_ordered_intervals(metrics):
    for metric in TRANSFORMS:
        fr = fit_forecast(metrics[metric].iloc[:200], metric, 7).frame
        assert (fr["lo"] <= fr["mean"]).all() and (fr["mean"] <= fr["hi"]).all()
        assert fr.notna().all().all()
