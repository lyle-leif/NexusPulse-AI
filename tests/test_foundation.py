import pandas as pd
import pytest
import yaml

from nexuspulse_analytics import (
    daily_kpis,
    net_revenue_direct,
    run_reconciliation,
    unattributed_share_flags,
)
from nexuspulse_generator import LOW_VOLUME_FASHION, MAIN_FASHION, Scenario, generate_store

DAYS = 150


@pytest.fixture(scope="module")
def main_store():
    return generate_store(MAIN_FASHION, seed=11, days=DAYS)


@pytest.fixture(scope="module")
def low_store():
    return generate_store(LOW_VOLUME_FASHION, seed=12, days=DAYS)


@pytest.fixture(scope="module")
def breakage_store():
    sc = Scenario("tracking_breakage", start="2025-05-01", days=14, params={"lost_share": 0.6})
    return generate_store(MAIN_FASHION, seed=11, days=DAYS, scenarios=(sc,))


def test_generation_is_deterministic(main_store):
    again = generate_store(MAIN_FASHION, seed=11, days=DAYS)
    assert again.content_hash() == main_store.content_hash()
    other = generate_store(MAIN_FASHION, seed=99, days=DAYS)
    assert other.content_hash() != main_store.content_hash()


@pytest.mark.parametrize("fixture", ["main_store", "low_store"])
def test_reconciliation_passes_on_clean_data(fixture, request):
    store = request.getfixturevalue(fixture)
    failed = [c for c in run_reconciliation(store.tables(), store.profile.timezone) if not c.passed]
    assert failed == []


@pytest.mark.parametrize("fixture", ["main_store", "low_store"])
def test_bridge_equals_independent_net_revenue_to_the_cent(fixture, request):
    store = request.getfixturevalue(fixture)
    tz = store.profile.timezone
    daily = daily_kpis(store.tables(), tz)
    direct = net_revenue_direct(store.tables(), tz).reindex(daily.index).fillna(0).astype("int64")
    assert (daily["net_revenue_bridge"] == direct).all()
    if fixture == "main_store":
        # the timing line must be exercised (sessions crossing midnight), not trivially zero;
        # at low volume crossings are too rare to assert on.
        assert (daily["timing_difference"] != 0).any()


def test_realistic_shape(main_store):
    d = daily_kpis(main_store.tables(), main_store.profile.timezone)
    conv = d["converting_sessions"].sum() / d["sessions"].sum()
    unattr_share = d["unattributed_orders"].sum() / d["orders"].sum()
    assert 0.015 < conv < 0.045
    assert 0.02 < unattr_share < 0.07
    assert main_store.sessions["session_id"].is_unique


def test_tracking_breakage_raises_data_quality_flag(main_store, breakage_store):
    tz = main_store.profile.timezone
    clean = unattributed_share_flags(main_store.tables(), tz)
    broken = unattributed_share_flags(breakage_store.tables(), tz)
    assert not clean["flag"].any()
    window = broken.loc["2025-05-01":"2025-05-20"]
    assert window["flag"].any()
    # flag must not fire before the breakage begins
    assert not broken.loc[:"2025-04-30", "flag"].any()


def test_labels_are_separate_from_observable_data(breakage_store):
    assert breakage_store.labels and breakage_store.labels[0]["kind"] == "tracking_breakage"
    for df in breakage_store.tables().values():
        assert not any("scenario" in str(c).lower() or "label" in str(c).lower() for c in df.columns)
    descriptions = " ".join(breakage_store.change_events["description"])
    assert "tracking" not in descriptions.lower()


def test_metric_contracts_load_and_are_complete():
    with open("contracts/metrics.yaml", encoding="utf-8") as f:
        contracts = yaml.safe_load(f)
    ids = [m["id"] for m in contracts["metrics"]]
    assert len(ids) == len(set(ids))
    for required in ("net_revenue", "session_conversion_rate", "unattributed_order_share"):
        assert required in ids
    for m in contracts["metrics"]:
        assert m["requires_tables"], m["id"]
