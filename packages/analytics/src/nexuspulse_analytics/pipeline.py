"""End-to-end analysis of one store's tables (inference only; never sees labels)."""
from __future__ import annotations

import pandas as pd

from .forecast import metric_frame
from .kpis import daily_kpis
from .monitor import MonitorConfig, MonitorResult, known_event_days, run_monitor
from .reconcile import unattributed_share_flags


def analyze(tables: dict[str, pd.DataFrame], tz: str, config: MonitorConfig = MonitorConfig()) -> tuple[pd.DataFrame, MonitorResult]:
    daily = daily_kpis(tables, tz)
    metrics = metric_frame(daily)
    known = known_event_days(tables["change_events"], tz)
    flags = unattributed_share_flags(tables, tz)
    dq_days = flags.index[flags["flag"]]
    return daily, run_monitor(metrics, known, dq_days, config)
