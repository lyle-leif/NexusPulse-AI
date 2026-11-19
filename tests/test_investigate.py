import pandas as pd
import pytest

from nexuspulse_analytics.investigate import evidence_level, investigate
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store

EMPTY = pd.DatetimeIndex([])


@pytest.fixture(scope="module")
def store():
    sc = (
        Scenario("conversion_drop", "2025-06-10", 10, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True, "event_offset_hours": -3.0}),
        Scenario("stockout", "2025-08-10", 9, {"category": "Dresses", "event": False}),
    )
    return generate_store(MAIN_FASHION, seed=51, days=260, scenarios=sc)


def _incident(start, end):
    return {"incident_id": "inc_test", "start": start, "end": end, "anchor_metric": "net_sales", "direction": "down",
            "members": [{"start": start, "end": end}]}


def test_conversion_drop_strong_with_deploy(store):
    inv = investigate(store.tables(), store.profile.timezone, _incident("2025-06-10", "2025-06-19"), EMPTY, EMPTY)
    assert inv["driver_group"] == "conversion"
    assert inv["segment"] == {"dimension": "device", "segment": "mobile"}
    assert inv["cause_event"] is not None and inv["cause_event"]["type"] == "deploy"
    assert inv["explanation_evidence"]["level"] in ("Strong", "Moderate")  # share near the 80% line
    assert all(c["passed"] for c in inv["validation"])
    statuses = {f["type"]: f["status"] for f in inv["findings"]}
    assert statuses["driver"] == "attributed" and statuses["event"] == "associated" and statuses["hypothesis"] == "hypothesis"


def test_stockout_without_event_is_not_strong(store):
    inv = investigate(store.tables(), store.profile.timezone, _incident("2025-08-10", "2025-08-18"), EMPTY, EMPTY)
    assert inv["segment"]["segment"] == "Dresses"
    assert inv["cause_event"] is None
    assert inv["explanation_evidence"]["level"] in ("Moderate", "Weak")


def test_evidence_rules():
    scoped = [{"match": "scope_match"}]
    unscoped = [{"match": "unscoped"}]
    assert evidence_level(0.9, scoped, True)[0] == "Strong"
    assert evidence_level(0.9, scoped, False)[0] == "Moderate"
    assert evidence_level(0.6, scoped, True)[0] == "Moderate"
    assert evidence_level(0.3, unscoped, True)[0] == "Weak"
    assert evidence_level(0.3, [], True)[0] == "None"
    assert evidence_level(None, [], True)[0] == "None"
