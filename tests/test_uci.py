import pandas as pd

from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.kpis import daily_kpis
from nexuspulse_analytics.reconcile import unattributed_share_flags
from nexuspulse_ingest.uci import TIMEZONE, to_tables


def _raw():
    rows = [
        ("489434", "85048", "LIGHT", 2, "2010-03-01 10:00", 6.95),
        ("489434", "85048", "LIGHT", 2, "2010-03-01 10:00", 6.95),   # exact duplicate (sheet overlap)
        ("489434", "POST", "POSTAGE", 1, "2010-03-01 10:00", 18.0),  # non-product
        ("489435", "22041", "CARD", 3, "2010-03-03 11:00", 0.0),     # zero price
        ("489436", "22041", "CARD", 4, "2010-03-03 12:00", 1.25),
        ("C489437", "22041", "CARD", -1, "2010-03-04 12:00", 1.25),  # cancellation
    ]
    return pd.DataFrame(rows, columns=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price"]).assign(
        **{"Customer ID": 1.0, "Country": "United Kingdom"}, InvoiceDate=lambda d: pd.to_datetime(d["InvoiceDate"]))


def test_mapping_and_exclusions():
    tables, notes = to_tables(_raw())
    o = tables["orders"].set_index("order_id")
    assert list(o.index) == ["489434", "489436"]
    assert o.at["489434", "gross_sales"] == 1390 and o.at["489436", "gross_sales"] == 500
    assert notes["duplicate_lines_removed"] == 1 and notes["cancellation_lines_excluded"] == 1
    assert tables["sessions"].empty and o["session_id"].isna().all()


def test_session_metrics_are_unavailable_not_zero():
    tables, _ = to_tables(_raw())
    m = metric_frame(daily_kpis(tables, TIMEZONE))
    assert m["sessions"].isna().all() and m["session_conversion_rate"].isna().all()
    assert len(m) == 3 and m.loc["2010-03-02", "net_sales"] == 0  # closed day is a zero, not a gap
    assert not unattributed_share_flags(tables, TIMEZONE)["flag"].any()
