import pandas as pd

from nexuspulse_eval.runner import score_store, summarize

DAYS = pd.date_range("2025-01-01", periods=120, freq="D")
FLAT = pd.Series(100.0, index=DAYS)
DAILY = pd.DataFrame({"net_sales": FLAT})


def _lab(kind, start, end, business=True, dq=False, direction="down"):
    return {"kind": kind, "start": start, "end": end,
            "expected": {"business_anomaly": business, "data_quality_incident": dq, "direction": direction}}


def _inc(start, end, direction="down", status="resolved"):
    return {"incident_id": f"inc_{start}", "start": start, "end": end, "direction": direction,
            "status": status, "anchor_metric": "net_sales", "strength": "Moderate"}


def test_scoring_rules():
    labels = [
        _lab("conversion_drop", "2025-02-10", "2025-02-20"),
        _lab("stockout", "2025-03-10", "2025-03-15"),
        _lab("tracking_breakage", "2025-04-01", "2025-04-08", business=False, dq=True, direction=None),
        _lab("red_herring", "2025-04-20", "2025-04-25", business=False, direction=None),
    ]
    incidents = [
        _inc("2025-02-12", "2025-02-19"),                       # detects the drop, delay 2
        _inc("2025-03-11", "2025-03-14", direction="up"),       # wrong direction -> drop missed, false alert
        _inc("2025-04-02", "2025-04-09", status="suppressed_data_quality"),
        _inc("2025-01-20", "2025-01-21"),                       # unrelated false alert
    ]
    s = score_store(labels, incidents, DAILY, FLAT, 90)
    out = {r["kind"]: r for r in s["scenarios"]}
    assert out["conversion_drop"]["outcome"] == "detected" and out["conversion_drop"]["delay_days"] == 2
    assert out["stockout"]["outcome"] == "missed"
    assert out["tracking_breakage"]["outcome"] == "suppressed"
    assert out["red_herring"]["outcome"] == "passed"
    assert s["false_alerts"] == 2

    summ = summarize([s | {"suite": "dev", "profile": "main", "seed": 1, "coverage": 0.95, "mape": 0.1}])
    assert summ["recall"] == 0.5
    assert summ["precision"] == round(1 / 3, 3)
    assert summ["non_business_handled"] == "2/2"
