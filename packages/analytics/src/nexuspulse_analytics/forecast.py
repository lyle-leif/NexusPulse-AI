"""Forecasting: seasonal naive (baseline) and robust ETS.

Models work in a transformed space (log for counts and money, logit for rates) so
intervals stay positive and noise is roughly additive. A forecast is always fitted
on data up to and including `as_of`; it never sees the days it predicts.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

Z95 = 1.959964
MODEL_VERSION = "0.1.0"

# metric id -> transform
TRANSFORMS = {"net_sales": "log", "sessions": "log", "orders": "log", "session_conversion_rate": "logit"}


def metric_frame(daily: pd.DataFrame) -> pd.DataFrame:
    """Monitored daily metrics from the KPI table.

    net_sales = gross sales minus discounts by order date, before refunds. Refunds
    arrive days later and restate history, so detection uses the unrestated figure.
    """
    full = pd.date_range(daily.index.min(), daily.index.max(), freq="D", name="date")
    daily = daily.reindex(full, fill_value=0)  # days with no activity (store closed) are zeros
    out = pd.DataFrame(index=daily.index)
    out["net_sales"] = (
        daily["attributed_gross_session_date"] + daily["timing_difference"] + daily["unattributed_gross"] - daily["discounts"]
    ) / 100.0
    out["sessions"] = daily["sessions"].astype(float)
    out["orders"] = daily["orders"].astype(float)
    out["session_conversion_rate"] = daily["converting_sessions"] / daily["sessions"].where(daily["sessions"] > 0)
    if not (daily["sessions"] > 0).any():
        # Order-only dataset: session metrics are unavailable, never approximated.
        out["sessions"] = np.nan
        out["session_conversion_rate"] = np.nan
    return out


def _fwd(y: pd.Series, kind: str) -> pd.Series:
    if kind == "logit":
        p = y.clip(1e-4, 1 - 1e-4)
        return np.log(p / (1 - p))
    return np.log1p(y.clip(lower=0))


def _inv(x, kind: str):
    if kind == "logit":
        return 1 / (1 + np.exp(-x))
    return np.expm1(x)


def _robust_sd(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 8:
        return float(np.std(r)) if len(r) else 1.0
    return float(1.4826 * np.median(np.abs(r - np.median(r)))) or float(np.std(r)) or 1e-6


def _fill_weekly(x: pd.Series, drop: pd.Index) -> pd.Series:
    """Replace dropped days with the value from 7 days earlier (already filled)."""
    x = x.copy()
    for d in sorted(drop):
        if d not in x.index:
            continue
        prev = d - pd.Timedelta(days=7)
        x.loc[d] = x.loc[prev] if prev in x.index else np.nan
    return x.interpolate(limit_direction="both")


@dataclass
class Forecast:
    metric: str
    model: str
    as_of: pd.Timestamp
    frame: pd.DataFrame  # index: target dates; columns mean, lo, hi, sigma (transformed sd), mean_t
    params: dict


_SMOOTHING_KEYS = ("smoothing_level", "smoothing_trend", "smoothing_seasonal", "damping_trend")


def _ets_fit(x: pd.Series, fixed: dict | None = None):
    """Fit ETS. With `fixed` smoothing parameters only the initial states are estimated.

    Initial states are always estimated, never taken from the heuristic: with little or
    no seasonal smoothing the heuristic start (from the first weeks of the window) would
    persist, and those weeks can be unrepresentative (e.g. a holiday shutdown).
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            x.to_numpy(), trend="add", damped_trend=True, seasonal="add", seasonal_periods=7, initialization_method="estimated"
        )
        if fixed:
            with model.fix_params({k: fixed[k] for k in _SMOOTHING_KEYS}):
                return model.fit(optimized=True)
        return model.fit(optimized=True)


def fit_forecast(
    history: pd.Series,
    metric: str,
    horizon: int,
    model: str = "ets",
    robust: bool = True,
    exclude_days: pd.Index | None = None,
    train_days: int = 365,
    fixed_params: dict | None = None,
) -> Forecast:
    """Forecast `horizon` days after the last date of `history`.

    exclude_days: days replaced before fitting (known calendar events, masked incidents).
    Raw data is never modified; replacement happens on a copy in transformed space.
    """
    kind = TRANSFORMS[metric]
    hist = history.dropna().iloc[-train_days:]
    as_of = hist.index[-1]
    x = _fwd(hist, kind)
    if exclude_days is not None and len(exclude_days):
        x = _fill_weekly(x, exclude_days.intersection(x.index))
    targets = pd.date_range(as_of + pd.Timedelta(days=1), periods=horizon, freq="D")
    h = np.arange(1, horizon + 1)
    params: dict = {"model": model, "robust": robust, "train_start": str(x.index[0].date()), "n_train": len(x)}

    if model == "seasonal_naive":
        resid = (x - x.shift(7)).iloc[-56:].to_numpy()
        sigma = _robust_sd(resid)
        last_week = x.iloc[-7:].to_numpy()
        mean_t = np.array([last_week[(i - 1) % 7] for i in h])
        sig_h = sigma * np.sqrt(np.ceil(h / 7))
    elif model == "ets":
        fit = _ets_fit(x, fixed_params)
        resid = x.to_numpy() - fit.fittedvalues
        sigma = _robust_sd(resid[-120:])
        if robust:
            # Two-pass robust fit: clip extreme residuals, refit. Limits the pull of
            # outliers without depending on the detector's decisions.
            bound = 3.5 * sigma
            clipped = fit.fittedvalues + np.clip(resid, -bound, bound)
            params["clipped_days"] = int((np.abs(resid) > bound).sum())
            fit = _ets_fit(pd.Series(clipped, index=x.index), fixed_params)
            resid = clipped - fit.fittedvalues
            sigma = _robust_sd(resid[-120:])
        mean_t = np.asarray(fit.forecast(horizon))
        sig_h = sigma * np.sqrt(1 + 0.05 * (h - 1))
        params["ets"] = {k: float(fit.params[k]) for k in _SMOOTHING_KEYS}
        params["params_reused"] = fixed_params is not None
    else:
        raise ValueError(f"unknown model {model}")

    params["sigma"] = float(sigma)
    frame = pd.DataFrame(
        {
            "mean_t": mean_t,
            "sigma": sig_h,
            "mean": _inv(mean_t, kind),
            "lo": _inv(mean_t - Z95 * sig_h, kind),
            "hi": _inv(mean_t + Z95 * sig_h, kind),
        },
        index=targets,
    )
    return Forecast(metric, model, as_of, frame, params)


def z_score(actual: float, fc_row: pd.Series, metric: str) -> float:
    """Deviation of an actual value from the forecast, in transformed-sd units."""
    a = float(_fwd(pd.Series([actual]), TRANSFORMS[metric]).iloc[0])
    return (a - fc_row["mean_t"]) / fc_row["sigma"]
