import pandas as pd

from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.kpis import daily_kpis, segment_core
from nexuspulse_analytics.monitor import MonitorConfig
from nexuspulse_analytics.segments import MIN_SEGMENT_SESSIONS, drop_recoveries, merge_incidents, segment_config, segment_series
from nexuspulse_generator import MAIN_FASHION, generate_store


def _inc(start, end, direction="down", scope="store", segment=None, status="resolved"):
    i = {"incident_id": f"inc_{start}", "start": start, "end": end, "direction": direction, "status": status, "anchor_metric": "net_sales"}
    if segment:
        i |= {"scope": "segment", "segment": {"dimension": segment[0], "value": segment[1]}}
    return i


def test_segment_alert_attaches_to_overlapping_store_alert():
    store = [_inc("2025-03-01", "2025-03-05")]
    seg = [_inc("2025-03-06", "2025-03-09", segment=("channel", "email"))]  # within the 2-day pad
    out = merge_incidents(store, seg, "2025-12-31")
    assert len(out) == 1 and out[0]["scope"] == "store"
    assert out[0]["segments"][0]["dimension"] == "channel" and out[0]["segments"][0]["value"] == "email"


def test_segment_alert_alone_or_opposite_direction_stays_separate():
    store = [_inc("2025-03-01", "2025-03-05")]
    seg = [_inc("2025-03-02", "2025-03-04", direction="up", segment=("device", "mobile")),
           _inc("2025-06-01", "2025-06-04", segment=("category", "Shoes"))]
    out = merge_incidents(store, seg, "2025-12-31")
    assert [i["scope"] for i in out] == ["store", "segment", "segment"]
    assert out[0]["segments"] == []


def test_overlapping_segment_alerts_become_one_incident():
    seg = [_inc("2025-06-01", "2025-06-04", segment=("channel", "paid_social")),
           _inc("2025-06-02", "2025-06-06", segment=("device", "mobile"))]
    out = merge_incidents([], seg, "2025-12-31")
    assert len(out) == 1
    assert [(s["dimension"], s["value"]) for s in out[0]["segments"]] == [("channel", "paid_social"), ("device", "mobile")]


def test_suppressed_segment_alerts_are_dropped():
    seg = [_inc("2025-06-01", "2025-06-04", segment=("channel", "email"), status="suppressed_data_quality")]
    assert merge_incidents([], seg, "2025-12-31") == []


def test_segment_series_skip_small_segments_and_match_totals():
    store = generate_store(MAIN_FASHION, seed=7, days=90)
    tables, tz = store.tables(), MAIN_FASHION.timezone
    idx = metric_frame(daily_kpis(tables, tz)).index
    series = segment_series(tables, tz, idx)
    assert all(f["sessions"].mean() >= MIN_SEGMENT_SESSIONS for (d, _), f in series.items() if d != "category")
    assert all(list(f.columns) == ["net_sales"] for (d, _), f in series.items() if d == "category")
    # every watched channel's visits are exactly that channel's visits
    seg = segment_core(tables, tz, "channel")
    for (dim, value), f in series.items():
        if dim == "channel":
            exp = seg.xs(value, level="channel")["sessions"].reindex(idx, fill_value=0)
            assert (f["sessions"].to_numpy() == exp.to_numpy()).all()


def test_segment_config_is_stricter_and_does_not_recurse():
    base = MonitorConfig(segments=True)
    cfg = segment_config(base)
    assert not cfg.segments
    assert cfg.z_flag > 50 and cfg.z_extreme > 50 and cfg.masking
    assert cfg.z_window7 == base.seg_z_window > base.z_window7


def test_recovery_after_an_alert_is_dropped():
    down = _inc("2025-09-14", "2025-09-26", direction="down")
    rebound = _inc("2025-10-06", "2025-10-16", direction="up")  # within 14 days of the end
    later = _inc("2025-12-01", "2025-12-05", direction="up")  # long after: a new change
    assert drop_recoveries([rebound, down, later]) == [down, later]
    # an open alert has no end yet, so nothing after it counts as a recovery
    still_open = _inc("2025-09-14", None, direction="down")
    assert drop_recoveries([still_open, rebound]) == [still_open, rebound]


def test_window_clip_stops_one_extreme_day_firing_a_window():
    import numpy as np

    from nexuspulse_analytics.monitor import run_monitor

    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    rng = np.random.default_rng(3)
    y = pd.Series(1000 * np.exp(rng.normal(0, 0.15, len(idx))), index=idx)
    y.iloc[230] = 0.0  # one day with no sales
    frame = pd.DataFrame({"net_sales": y})
    empty = pd.DatetimeIndex([])
    base = segment_config(MonitorConfig(segments=True))
    from dataclasses import replace

    unclipped = run_monitor(frame, empty, empty, replace(base, window_clip=0.0))
    clipped = run_monitor(frame, empty, empty, base)
    assert any(i["start"] >= "2024-08-15" for i in unclipped.incidents)  # the zero day alone fires a window
    assert not any(i["start"] >= "2024-08-15" for i in clipped.incidents)


def test_segment_issue_report_leads_with_the_flagged_segment():
    from nexuspulse_analytics.investigate import investigate
    from nexuspulse_analytics.report import template_summary
    from nexuspulse_generator import Scenario

    sc = (Scenario("stockout", "2025-07-20", 8, {"category": "Dresses", "event": False}),)
    st = generate_store(MAIN_FASHION, seed=63, days=240, scenarios=sc)
    inc = {"incident_id": "inc_seg", "start": "2025-07-20", "end": "2025-07-27", "status": "resolved", "anchor_metric": "net_sales",
           "direction": "down", "strength": "Strong", "impact": None, "scope": "segment", "segment": {"dimension": "category", "value": "Dresses"},
           "members": [{"metric": "net_sales", "start": "2025-07-20", "end": "2025-07-27"}]}
    empty = pd.DatetimeIndex([])
    inv = investigate(st.tables(), MAIN_FASHION.timezone, inc, empty, empty)
    f = [x for x in inv["findings"] if x["type"] == "flagged_segment"]
    assert len(f) == 1 and f[0]["status"] == "observed"
    assert f[0]["values"]["relative_change"] < -0.5  # a stockout removes most of the category's sales
    first = template_summary(inv)[0]
    assert first["text"].startswith("Sales from Dresses (category)") and f[0]["finding_id"] in first["finding_ids"]


def test_store_issue_report_has_no_flagged_segment():
    from nexuspulse_analytics.investigate import investigate

    st = generate_store(MAIN_FASHION, seed=64, days=150)
    inc = {"incident_id": "inc_store", "start": "2025-04-20", "end": "2025-04-24", "status": "resolved", "anchor_metric": "net_sales",
           "direction": "down", "strength": "Weak", "impact": None, "members": [{"metric": "net_sales", "start": "2025-04-20", "end": "2025-04-24"}]}
    empty = pd.DatetimeIndex([])
    inv = investigate(st.tables(), MAIN_FASHION.timezone, inc, empty, empty)
    assert not [x for x in inv["findings"] if x["type"] == "flagged_segment"]
