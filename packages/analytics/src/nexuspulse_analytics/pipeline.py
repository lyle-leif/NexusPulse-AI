"""End-to-end analysis of one store's tables (inference only; never sees labels)."""
from __future__ import annotations

import pandas as pd

from .forecast import metric_frame
from .kpis import daily_kpis
from .monitor import MonitorConfig, MonitorResult, known_event_days, run_monitor
from .reconcile import unattributed_share_flags


def regular_closed_days(orders: pd.Series, weeks: int = 8, share: float = 0.75) -> pd.DatetimeIndex:
    """Days with no orders on a weekday that is usually closed.

    A zero day is a regular closure when the same weekday had no orders in at least 75%
    of the previous 4-8 weeks. For the first 4 weeks, which have no such history, the
    following 4 weeks are used instead; that data is still earlier than the first
    forecast (day 56 at the soonest), so no forecast uses information from its future.
    Regular closures are left out of fitting and scoring like calendar holidays; a zero
    on a normally open weekday is still evaluated.
    """
    zero = (orders == 0).astype(float)
    by_wd = zero.groupby(zero.index.day_of_week)
    prior = by_wd.transform(lambda s: s.shift(1).rolling(weeks, min_periods=4).mean())
    nxt = by_wd.transform(lambda s: s[::-1].shift(1).rolling(4, min_periods=4).mean()[::-1])
    early = orders.index < orders.index[0] + pd.Timedelta(days=28)
    closed = (orders == 0) & ((prior >= share) | (early & (nxt >= share)))
    return orders.index[closed.to_numpy()]


def holiday_closures(orders: pd.Series, calendar: pd.DatetimeIndex, days: int = 7) -> pd.DatetimeIndex:
    """Days with no orders within a week of a calendar holiday (e.g. a Christmas shutdown)."""
    if not len(calendar):
        return pd.DatetimeIndex([])
    zero = orders.index[orders.to_numpy() == 0]
    near = [d for d in zero if abs((calendar - d).days).min() <= days]
    return pd.DatetimeIndex(near)


def analyze(tables: dict[str, pd.DataFrame], tz: str, config: MonitorConfig = MonitorConfig(),
            record_timeline: bool = False) -> tuple[pd.DataFrame, MonitorResult]:
    daily = daily_kpis(tables, tz)
    metrics = metric_frame(daily)
    calendar = known_event_days(tables["change_events"], tz)
    known = calendar.union(regular_closed_days(metrics["orders"])).union(holiday_closures(metrics["orders"], calendar))
    flags = unattributed_share_flags(tables, tz)
    dq_days = flags.index[flags["flag"]]
    return daily, run_monitor(metrics, known, dq_days, config, record_timeline)
