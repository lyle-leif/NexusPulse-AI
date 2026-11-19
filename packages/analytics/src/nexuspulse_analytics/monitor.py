"""Anomaly detection and incident management.

The monitor walks forward in time. Every `refit_every` days it fits a forecast on data
up to that day (as-of) and judges the following days against it, so actuals are always
compared with a forecast issued before them.

Rules (published; see ARCHITECTURE.md section 7):
- z = deviation of the actual from the forecast, in transformed-sd units.
- Three tests: single day |z| >= z_flag; 3-day window |sum z|/sqrt(3) >= z_window3;
  7-day window |sum z|/sqrt(7) >= z_window7. Windows catch sustained moderate changes
  that no single noisy day reveals.
- A single-day signal opens an anomaly after `persist` consecutive days, or at once when
  |z| >= z_extreme. A window signal opens at once (the window is the persistence).
- Resolved: |z| < z_in with no test firing for `resolve_days` consecutive days.
- New normal: not resolved within `max_open_days` -> reclassified as a level shift; any
  training mask for it is removed so the model learns the new level.
- Known calendar events (holidays) are never flagged and are excluded from training.
- Business incidents overlapping a data-quality incident are suppressed, not alerted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .forecast import MODEL_VERSION, Forecast, fit_forecast, z_score

HIERARCHY = ["net_sales", "orders", "sessions", "session_conversion_rate"]
MIN_VOLUME = {"session_conversion_rate": ("sessions", 200), "orders": ("orders", 20)}


@dataclass(frozen=True)
class MonitorConfig:
    model: str = "ets"
    robust: bool = True
    masking: bool = False
    warmup_days: int = 120
    calibration_days: int = 42
    refit_every: int = 7
    reoptimize_every: int = 28
    z_flag: float = 3.5
    z_extreme: float = 5.0
    z_window3: float = 3.0
    z_window7: float = 3.0
    z_in: float = 2.0
    persist: int = 2
    resolve_days: int = 3
    max_open_days: int = 14
    group_gap_days: int = 2

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__} | {"model_version": MODEL_VERSION}


@dataclass
class Anomaly:
    metric: str
    direction: str
    start: pd.Timestamp
    end: pd.Timestamp | None = None
    status: str = "open"  # open | resolved | level_shift
    days: list = field(default_factory=list)
    max_abs_z: float = 0.0
    max_window_z: float = 0.0
    impact: float = 0.0  # net sales impact in currency units (signed)
    trigger: str = ""
    forecast_as_of: str | None = None

    @property
    def strength(self) -> str:
        z = max(self.max_abs_z, self.max_window_z)
        n = len(self.days)
        if n >= 3 and z >= 5:
            return "Strong"
        if n >= 2 or z >= 5:
            return "Moderate"
        return "Weak"


@dataclass
class MonitorResult:
    config: MonitorConfig
    daily: pd.DataFrame  # (date, metric) -> actual, mean, lo, hi, z, z3, z7, state, as_of
    forecasts: list[Forecast]
    anomalies: list[Anomaly]
    incidents: list[dict]


@dataclass
class _Track:
    open: Anomaly | None = None
    pending: list = field(default_factory=list)
    in_streak: int = 0
    recent: list = field(default_factory=list)  # (day, z, impact), newest last, max 7
    mask: pd.DatetimeIndex = field(default_factory=lambda: pd.DatetimeIndex([]))
    ets_params: dict | None = None
    zhist: list = field(default_factory=list)  # raw z of days with no open anomaly
    chist: list = field(default_factory=list)  # calibrated z of those days


def known_event_days(change_events: pd.DataFrame, tz: str) -> pd.DatetimeIndex:
    days = pd.DatetimeIndex([])
    for _, r in change_events[change_events["event_type"] == "holiday"].iterrows():
        start = r["occurred_at"].tz_convert(tz).tz_localize(None).normalize()
        days = days.union(pd.date_range(start, periods=int(r["scope"].get("window_days", 1)), freq="D"))
    return days


def run_monitor(
    metrics: pd.DataFrame,
    known_days: pd.DatetimeIndex,
    dq_days: pd.DatetimeIndex,
    config: MonitorConfig = MonitorConfig(),
) -> MonitorResult:
    dates = metrics.index
    forecasts: list[Forecast] = []
    rows: list[dict] = []
    anomalies: list[Anomaly] = []
    tracks = {m: _Track() for m in HIERARCHY}

    # Forecasting starts `calibration_days` before the warm-up ends so the empirical
    # z calibration is ready when detection begins at `warmup_days`.
    first = max(56, config.warmup_days - config.calibration_days)
    for n_refit, k in enumerate(range(first, len(dates), config.refit_every)):
        as_of = dates[k - 1]
        horizon = min(config.refit_every, len(dates) - k)
        reopt = (n_refit * config.refit_every) % config.reoptimize_every == 0
        fcs = {}
        for m in HIERARCHY:
            t = tracks[m]
            exclude = known_days.union(t.mask) if config.masking else known_days
            fixed = None if (reopt or config.model != "ets") else t.ets_params
            fc = fit_forecast(metrics[m].iloc[:k], m, horizon, model=config.model, robust=config.robust,
                              exclude_days=exclude, fixed_params=fixed)
            if config.model == "ets" and fixed is None:
                t.ets_params = fc.params["ets"]
            forecasts.append(fc)
            fcs[m] = fc

        for day in dates[k : k + horizon]:
            exp_sales = fcs["net_sales"].frame.at[day, "mean"]
            for m in HIERARCHY:
                row = fcs[m].frame.loc[day]
                rows.append(_evaluate(m, day, metrics.at[day, m], row, exp_sales, as_of, tracks[m], metrics, known_days, anomalies, config))

    daily = pd.DataFrame(rows).set_index(["date", "metric"]) if rows else pd.DataFrame()
    incidents = _group(anomalies, dq_days, metrics.index[-1], config)
    return MonitorResult(config, daily, forecasts, anomalies, incidents)


def _impact(m: str, actual: float, row: pd.Series, exp_sales: float) -> float:
    if m == "net_sales":
        return float(actual - row["mean"])
    return float(exp_sales * (actual / row["mean"] - 1)) if row["mean"] else 0.0


def _window_scale(hist: np.ndarray, n: int) -> float:
    base = np.sqrt(n)
    if len(hist) < 42:
        return base
    sums = np.convolve(hist, np.ones(n), mode="valid")
    mad = 1.4826 * np.median(np.abs(sums - np.median(sums)))
    return float(max(base, mad))


def _evaluate(m, day, actual, row, exp_sales, as_of, t: _Track, metrics, known_days, anomalies, cfg) -> dict:
    out = {"date": day, "metric": m, "actual": actual, "mean": row["mean"], "lo": row["lo"], "hi": row["hi"],
           "z": np.nan, "z3": np.nan, "z7": np.nan, "state": "in_range", "as_of": as_of}
    vol = MIN_VOLUME.get(m)
    if day in known_days:
        out["state"] = "known_event"
        return out
    if vol and metrics.at[day, vol[0]] < vol[1]:
        out["state"] = "low_volume"
        return out
    if not np.isfinite(actual):
        out["state"] = "missing"
        return out

    raw = z_score(actual, row, m)
    # Empirical calibration: centre and scale by the monitor's own past out-of-sample
    # errors on calm days (strictly earlier days only). Corrects forecast bias the
    # model cannot see (e.g. yearly seasonality) and intervals that are too narrow.
    calm = np.array(t.zhist[-120:])
    if len(calm) >= cfg.calibration_days:
        med = float(np.median(calm))
        mad = float(1.4826 * np.median(np.abs(calm - med))) or 1.0
        z = (raw - med) / max(mad, 1.0)
    else:
        z = raw
    t.recent = (t.recent + [(day, z, _impact(m, actual, row, exp_sales))])[-7:]
    zs = np.array([r[1] for r in t.recent])
    # Forecast errors within one horizon are correlated, so sum/sqrt(n) overstates
    # window evidence. Scale window sums by their empirical spread over recent
    # calm history instead (fallback sqrt(n) until enough history exists).
    hist = np.array(t.chist[-120:])
    z3 = zs[-3:].sum() / _window_scale(hist, 3) if len(zs) >= 3 else np.nan
    z7 = zs.sum() / _window_scale(hist, 7) if len(zs) >= 7 else np.nan
    calibrated = len(calm) >= cfg.calibration_days
    t.zhist.append(raw)  # median/MAD are robust to the few anomalous days included
    t.chist.append(z)
    if not calibrated:
        out["state"] = "calibrating"
        return out
    out.update(z=z, z3=z3, z7=z7)

    tests = [("day", z, cfg.z_flag), ("window3", z3, cfg.z_window3), ("window7", z7, cfg.z_window7)]
    fired = [(name, v, thr) for name, v, thr in tests if np.isfinite(v) and abs(v) >= thr]
    if fired:
        out["state"] = "out_of_range"
    name, stat, _ = max(fired, key=lambda f: abs(f[1]) / f[2]) if fired else ("", z, 1.0)
    direction = "up" if stat > 0 else "down"
    wz = max(abs(np.nan_to_num(z3)), abs(np.nan_to_num(z7)))

    a = t.open
    if a is not None:
        if fired and direction == a.direction:
            a.days.append(day)
            a.max_abs_z = max(a.max_abs_z, abs(z))
            a.max_window_z = max(a.max_window_z, wz)
            t.in_streak = 0
        elif abs(z) < cfg.z_in and not fired:
            t.in_streak += 1
        else:
            t.in_streak = 0
        if np.sign(z) == (1 if a.direction == "up" else -1):
            a.impact += t.recent[-1][2]
        if cfg.masking and (day - a.start).days < cfg.max_open_days:
            t.mask = t.mask.union(pd.DatetimeIndex([day]))
        if t.in_streak >= cfg.resolve_days:
            a.status, a.end = "resolved", a.days[-1]
            t.open, t.in_streak = None, 0
        elif (day - a.start).days + 1 >= cfg.max_open_days:
            a.status, a.end = "level_shift", day
            t.mask = t.mask.difference(pd.date_range(a.start, day))  # let the model learn the new level
            t.open, t.in_streak = None, 0
        return out

    if not fired:
        t.pending = []
        return out
    opens = name != "day" or abs(z) >= cfg.z_extreme
    if name == "day":
        if t.pending and t.pending[-1][1] != direction:
            t.pending = []
        t.pending.append((day, direction))
        opens = opens or len(t.pending) >= cfg.persist
    if not opens:
        return out

    # Start = beginning of the contiguous run of same-sign deviations within the window.
    sign = 1 if direction == "up" else -1
    run = []
    for d, zz, imp in reversed(t.recent):
        if np.sign(zz) != sign:
            break
        run.append((d, zz, imp))
    run.reverse()
    if not run:  # a window fired but today's deviation has the other sign: wait
        return out
    a = Anomaly(metric=m, direction=direction, start=run[0][0], trigger=name, forecast_as_of=str(as_of.date()))
    a.days = [d for d, zz, _ in run if abs(zz) >= cfg.z_in] or [day]
    a.max_abs_z = max(abs(zz) for _, zz, _ in run)
    a.max_window_z = wz
    a.impact = sum(imp for _, _, imp in run)
    if cfg.masking:
        t.mask = t.mask.union(pd.DatetimeIndex([d for d, _, _ in run]))
    anomalies.append(a)
    t.open, t.pending, t.in_streak = a, [], 0
    return out


def _group(anomalies: list[Anomaly], dq_days: pd.DatetimeIndex, last_day: pd.Timestamp, cfg: MonitorConfig) -> list[dict]:
    gap = pd.Timedelta(days=cfg.group_gap_days)
    groups: list[list[Anomaly]] = []
    for a in sorted(anomalies, key=lambda a: a.start):
        if groups:
            g_end = max((x.end or last_day) for x in groups[-1])
            if a.start <= g_end + gap and a.direction == groups[-1][0].direction:
                groups[-1].append(a)
                continue
        groups.append([a])

    incidents = []
    for g in groups:
        anchor = min(g, key=lambda a: (HIERARCHY.index(a.metric), a.start))
        start = min(a.start for a in g)
        end = max((a.end or last_day) for a in g)
        suppressed = bool(len(pd.date_range(start, end).intersection(dq_days)))
        sales = [a for a in g if a.metric == "net_sales"]
        incidents.append(
            {
                "incident_id": f"inc_{start.date().isoformat()}_{anchor.metric}",
                "start": start.date().isoformat(),
                "end": None if anchor.status == "open" else end.date().isoformat(),
                "status": "suppressed_data_quality" if suppressed else anchor.status,
                "anchor_metric": anchor.metric,
                "direction": anchor.direction,
                "strength": anchor.strength,
                "impact": round(sum(a.impact for a in sales), 2) if sales else None,  # only when net sales itself moved
                "members": [
                    {
                        "metric": a.metric, "direction": a.direction, "start": a.start.date().isoformat(),
                        "end": a.end.date().isoformat() if a.end is not None else None, "status": a.status,
                        "strength": a.strength, "max_abs_z": round(a.max_abs_z, 2),
                        "max_window_z": round(a.max_window_z, 2), "trigger": a.trigger,
                        "forecast_as_of": a.forecast_as_of,
                    }
                    for a in g
                ],
            }
        )
    return incidents
