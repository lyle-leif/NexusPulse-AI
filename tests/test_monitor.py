import numpy as np
import pandas as pd
import pytest

from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.monitor import Anomaly, MonitorConfig, _group, run_monitor
from nexuspulse_analytics.pipeline import analyze
from nexuspulse_analytics import daily_kpis
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store

EMPTY = pd.DatetimeIndex([])


@pytest.fixture(scope="module")
def clean_metrics():
    store = generate_store(MAIN_FASHION, seed=41, days=300)
    return metric_frame(daily_kpis(store.tables(), store.profile.timezone))


@pytest.fixture(scope="module")
def planted():
    scenarios = (
        Scenario("traffic_spike", "2025-07-15", 3, {"multiplier": 2.2, "event_offset_hours": -5.0}),
        Scenario("tracking_breakage", "2025-09-10", 8, {"lost_share": 0.7, "event_offset_hours": 0.5}),
    )
    store = generate_store(MAIN_FASHION, seed=43, days=320, scenarios=scenarios)
    _, result = analyze(store.tables(), store.profile.timezone)
    return result


def _overlaps(inc, start, days):
    s, e = pd.Timestamp(inc["start"]), pd.Timestamp(inc["end"] or "2100-01-01")
    return s <= pd.Timestamp(start) + pd.Timedelta(days=days) and e >= pd.Timestamp(start)


def test_planted_spike_is_detected(planted):
    hits = [i for i in planted.incidents if _overlaps(i, "2025-07-15", 3) and i["direction"] == "up"]
    assert hits and hits[0]["status"] != "suppressed_data_quality"


def test_tracking_breakage_is_suppressed_not_alerted(planted):
    near = [i for i in planted.incidents if _overlaps(i, "2025-09-10", 8)]
    assert near and all(i["status"] == "suppressed_data_quality" for i in near)


def test_few_false_alarms_on_clean_store(clean_metrics):
    r = run_monitor(clean_metrics, EMPTY, EMPTY)
    monitored_days = len(clean_metrics) - MonitorConfig().warmup_days
    # Regression guard for one clean seed. The eval over 20 stores measures 0.23-0.53 per
    # 30 days; this single seed sits at 1.0 (6 alerts in 180 days), so the guard is set
    # just above it rather than at the eval mean.
    assert len(r.incidents) * 30 / monitored_days <= 1.0


def test_no_lookahead(clean_metrics):
    cut = 230
    a = run_monitor(clean_metrics.iloc[:cut], EMPTY, EMPTY)
    tampered = clean_metrics.copy()
    tampered.iloc[cut:] *= 3
    b = run_monitor(tampered, EMPTY, EMPTY)
    da = a.daily.reset_index()
    db = b.daily.reset_index()
    db = db[db["date"] < clean_metrics.index[cut]]
    pd.testing.assert_frame_equal(da[["date", "metric", "z", "state"]], db[["date", "metric", "z", "state"]].reset_index(drop=True))


def test_level_shift_after_max_open_days(clean_metrics):
    m = clean_metrics.copy()
    m.iloc[200:, m.columns.get_loc("sessions")] *= 0.5  # permanent drop
    r = run_monitor(m, EMPTY, EMPTY)
    shifts = [a for a in r.anomalies if a.metric == "sessions" and a.direction == "down"]
    assert shifts and shifts[0].status == "level_shift"


def test_grouping_keeps_opposite_directions_apart():
    d = pd.Timestamp("2025-06-01")
    up = Anomaly("orders", "up", d, d + pd.Timedelta(days=3), "resolved", [d])
    down = Anomaly("orders", "down", d + pd.Timedelta(days=4), d + pd.Timedelta(days=6), "resolved", [d])
    same = Anomaly("sessions", "down", d + pd.Timedelta(days=5), d + pd.Timedelta(days=6), "resolved", [d])
    incs = _group([up, down, same], EMPTY, d + pd.Timedelta(days=30), MonitorConfig())
    assert len(incs) == 2 and incs[1]["anchor_metric"] == "orders" and len(incs[1]["members"]) == 2
