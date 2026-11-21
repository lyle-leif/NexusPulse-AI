import pandas as pd

from nexuspulse_analytics import daily_kpis
from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.monitor import run_monitor
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store

EMPTY = pd.DatetimeIndex([])


def test_timeline_equals_runs_stopped_on_that_day():
    sc = (Scenario("conversion_drop", "2025-06-20", 10, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True, "event_offset_hours": -3.0}),)
    st = generate_store(MAIN_FASHION, seed=61, days=240, scenarios=sc)
    m = metric_frame(daily_kpis(st.tables(), st.profile.timezone))
    full = run_monitor(m, EMPTY, EMPTY, record_timeline=True)
    days = ["2025-06-18", "2025-06-22", "2025-06-26", "2025-07-08"]
    assert any(i["end"] is None for d in days for i in full.timeline[d])  # covers an incident still open on that day
    for day in days:
        cut = run_monitor(m.loc[:day], EMPTY, EMPTY)
        assert full.timeline[day] == cut.incidents, day


def _cut(tables: dict, tz: str, day: str) -> dict:
    """The tables as they stood at the end of `day` (local time): nothing that happened later."""
    from nexuspulse_analytics.kpis import local_date

    d = pd.Timestamp(day)
    t = dict(tables)
    t["sessions"] = tables["sessions"][local_date(tables["sessions"]["started_at"], tz) <= d]
    t["orders"] = tables["orders"][local_date(tables["orders"]["placed_at"], tz) <= d]
    t["order_items"] = tables["order_items"][tables["order_items"]["order_id"].isin(t["orders"]["order_id"])]
    t["refunds"] = tables["refunds"][local_date(tables["refunds"]["refunded_at"], tz) <= d]
    ce = tables["change_events"]
    t["change_events"] = ce[local_date(ce["occurred_at"], tz) <= d] if len(ce) else ce
    return t


def test_timeline_with_segments_equals_runs_stopped_on_that_day():
    """Segment monitoring keeps the Time Machine promise: each day's list is what a run on the
    data available at the end of that day reports, including segment-only issues."""
    from dataclasses import replace

    from nexuspulse_analytics.monitor import MonitorConfig
    from nexuspulse_analytics.pipeline import analyze

    sc = (Scenario("traffic_loss", "2025-06-20", 10, {"multiplier": 0.3, "segment": {"channel": "paid_social"}, "event": True}),
          Scenario("stockout", "2025-07-20", 8, {"category": "Dresses", "event": False}))
    st = generate_store(MAIN_FASHION, seed=62, days=240, scenarios=sc)
    tz = st.profile.timezone
    cfg = replace(MonitorConfig(), segments=True)
    _, full = analyze(st.tables(), tz, cfg, record_timeline=True)
    days = ["2025-06-24", "2025-07-02", "2025-07-24", "2025-08-10"]
    assert any(i.get("scope") == "segment" or i.get("segments") for d in days for i in full.timeline[d])  # segments matter here
    for day in days:
        _, cut = analyze(_cut(st.tables(), tz, day), tz, cfg)
        assert full.timeline[day] == cut.incidents, day
