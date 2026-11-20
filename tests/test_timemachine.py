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
