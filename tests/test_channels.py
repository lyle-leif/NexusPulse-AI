import pytest

from nexuspulse_analytics import daily_kpis
from nexuspulse_analytics.kpis import channel_sales
from nexuspulse_generator import MAIN_FASHION, generate_store


@pytest.fixture(scope="module")
def store():
    return generate_store(MAIN_FASHION, seed=7, days=120)


def test_channel_sales_add_up_to_the_bridge(store):
    tables, tz = store.tables(), store.profile.timezone
    daily = daily_kpis(tables, tz)
    start, end = daily.index[-28], daily.index[-1]
    ch = channel_sales(tables, tz, start, end)
    period = daily.loc[start:end]
    assert int(ch["attributed_gross"].sum()) == int(period["attributed_gross_session_date"].sum())
    assert int(ch["sessions"].sum()) == int(period["sessions"].sum())
    assert set(ch.index) == {"organic", "paid_social", "paid_search", "email", "direct"}
