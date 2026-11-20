"""UCI Online Retail II loader (real data, CC BY 4.0).

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii - a UK online gift
retailer, Dec 2009 to Dec 2011, invoice lines only.

Capability (see PRD section 5): orders, revenue, products and countries exist. There are
no sessions, funnel, channels, devices, marketing spend or change log, so session-based
metrics are unavailable and are never approximated. No sessions are fabricated.

Mapping:
- Each invoice is an order placed at InvoiceDate (Europe/London local time).
- Lines with a non-product StockCode (postage, fees, adjustments, manual), zero or
  negative price or quantity are excluded.
- Cancellation invoices ('C' prefix) do not reference the invoice they cancel, so they
  cannot be matched to an order; they are excluded and counted in `notes`. Detection uses
  net sales before refunds, so this does not affect the monitored series.
- Exact duplicate lines (the two yearly sheets overlap in December 2010) are removed.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

TIMEZONE = "Europe/London"
CURRENCY = "GBP"
RAW_ZIP = Path("data/external/online_retail_ii.zip")
CACHE = Path("data/external/online_retail_ii.csv.gz")


def read_raw(zip_path: Path = RAW_ZIP, cache: Path = CACHE) -> pd.DataFrame:
    if cache.exists():
        df = pd.read_csv(cache, dtype={"Invoice": str, "StockCode": str}, parse_dates=["InvoiceDate"])
    else:
        with zipfile.ZipFile(zip_path) as z, z.open("online_retail_II.xlsx") as f:
            df = pd.concat(pd.read_excel(f, sheet_name=None, dtype={"Invoice": str, "StockCode": str}).values())
        df.to_csv(cache, index=False)
    return df


def file_sha256(path: Path = RAW_ZIP) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_tables(raw: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict]:
    n_raw = len(raw)
    d = raw.drop_duplicates()
    n_dupes = n_raw - len(d)
    inv = d["Invoice"].astype(str)
    cancelled = inv.str.startswith("C")
    other_non_sale = ~inv.str.match(r"^\d")
    product = d["StockCode"].astype(str).str.match(r"^\d")
    ok = ~cancelled & ~other_non_sale & product & (d["Price"] > 0) & (d["Quantity"] > 0)
    lines = d[ok].copy()

    lines["unit_price"] = np.rint(lines["Price"] * 100).astype("int64")
    lines["line_value"] = lines["unit_price"] * lines["Quantity"].astype("int64")
    placed = pd.to_datetime(lines["InvoiceDate"]).dt.tz_localize(TIMEZONE, ambiguous=True, nonexistent="shift_forward").dt.tz_convert("UTC")
    lines["placed_at"] = placed.astype("datetime64[ns, UTC]")

    orders = lines.groupby("Invoice").agg(placed_at=("placed_at", "min"), gross_sales=("line_value", "sum")).reset_index()
    orders = orders.rename(columns={"Invoice": "order_id"})
    orders["session_id"] = pd.Series([None] * len(orders), dtype=object)
    orders["currency"] = CURRENCY
    orders["discount"] = np.int64(0)
    orders["status"] = "paid"
    orders["is_test"] = False
    orders = orders[["order_id", "placed_at", "session_id", "currency", "gross_sales", "discount", "status", "is_test"]]

    products = (
        lines.groupby("StockCode").agg(name=("Description", "first"), price=("unit_price", "median")).reset_index()
        .rename(columns={"StockCode": "product_id"})
    )
    products["name"] = products["name"].fillna("").astype(str)
    products["category"] = "unknown"  # the dataset has no product categories
    products["price"] = products["price"].astype("int64")
    products["cost"] = np.int64(0)
    order_items = lines.rename(columns={"Invoice": "order_id", "StockCode": "product_id", "Quantity": "quantity"})[
        ["order_id", "product_id", "quantity", "unit_price"]
    ].astype({"quantity": "int64"})

    empty_ts = pd.Series([], dtype="datetime64[ns, UTC]")
    tables = {
        "products": products[["product_id", "name", "category", "price", "cost"]],
        "sessions": pd.DataFrame({"session_id": pd.Series([], dtype=str), "started_at": empty_ts, "channel": pd.Series([], dtype=str),
                                  "device": pd.Series([], dtype=str), "region": pd.Series([], dtype=str),
                                  "reached_cart": pd.Series([], dtype=bool), "reached_checkout": pd.Series([], dtype=bool)}),
        "orders": orders.reset_index(drop=True),
        "order_items": order_items.reset_index(drop=True),
        "refunds": pd.DataFrame({"order_id": pd.Series([], dtype=str), "refunded_at": empty_ts, "amount": pd.Series([], dtype="int64")}),
        "marketing_spend": pd.DataFrame({"spend_date": pd.Series([], dtype="datetime64[us]"), "channel": pd.Series([], dtype=str),
                                         "campaign": pd.Series([], dtype=str), "spend": pd.Series([], dtype="int64"),
                                         "impressions": pd.Series([], dtype="int64"), "clicks": pd.Series([], dtype="int64")}),
        "change_events": pd.DataFrame({"event_id": pd.Series([], dtype=str), "occurred_at": pd.Series([], dtype="datetime64[us, UTC]"),
                                       "event_type": pd.Series([], dtype=str), "description": pd.Series([], dtype=str),
                                       "scope": pd.Series([], dtype=object), "source": pd.Series([], dtype=str)}),
    }
    notes = {
        "raw_lines": n_raw, "duplicate_lines_removed": n_dupes, "kept_lines": int(ok.sum()),
        "cancellation_lines_excluded": int(cancelled.sum()), "non_product_or_invalid_lines_excluded": int((~ok & ~cancelled).sum()),
        "orders": len(orders), "first_order": str(orders["placed_at"].min()), "last_order": str(orders["placed_at"].max()),
        "capabilities": {"orders": True, "revenue": True, "products": True, "categories": False, "sessions": False,
                         "funnel": False, "channel": False, "device": False, "marketing_spend": False, "change_log": False},
    }
    return tables, notes


def load_uci() -> tuple[dict[str, pd.DataFrame], dict]:
    tables, notes = to_tables(read_raw())
    notes["source"] = "UCI Online Retail II (CC BY 4.0), https://archive.ics.uci.edu/dataset/502/online+retail+ii"
    notes["sha256"] = file_sha256() if RAW_ZIP.exists() else None
    return tables, notes
