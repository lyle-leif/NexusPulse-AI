"""Read business data from Postgres as DataFrames shaped like the generator output
(money as integer cents, timestamps tz-aware UTC). Connect with the np_pipeline role.
"""
from __future__ import annotations

import pandas as pd
import psycopg

PIPELINE_DSN = "postgresql://np_pipeline:np_pipeline_dev@localhost:5433/nexuspulse"

_QUERIES = {
    "products": "SELECT product_id, name, category, (price*100)::bigint AS price, (cost*100)::bigint AS cost FROM np.products",
    "sessions": "SELECT session_id, started_at, channel, device, region, reached_cart, reached_checkout FROM np.sessions",
    "orders": (
        "SELECT order_id, placed_at, session_id, currency, (gross_sales*100)::bigint AS gross_sales, "
        "(discount*100)::bigint AS discount, status, is_test FROM np.orders"
    ),
    "order_items": "SELECT order_id, product_id, quantity, (unit_price*100)::bigint AS unit_price FROM np.order_items",
    "refunds": "SELECT order_id, refunded_at, (amount*100)::bigint AS amount FROM np.refunds",
    "marketing_spend": (
        "SELECT spend_date, channel, campaign, (spend*100)::bigint AS spend, impressions, clicks FROM np.marketing_spend"
    ),
    "change_events": "SELECT event_id, occurred_at, event_type, description, scope, source FROM np.change_events",
}


def read_tables(workspace_id: str, batch_id: str, dsn: str = PIPELINE_DSN) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for name, q in _QUERIES.items():
            cur.execute(q + " WHERE workspace_id = %s AND ingest_batch_id = %s", (workspace_id, batch_id))
            cols = [d.name for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=cols)
            for c in ("started_at", "placed_at", "refunded_at", "occurred_at"):
                if c in df:
                    df[c] = pd.to_datetime(df[c], utc=True)
            if "spend_date" in df:
                df["spend_date"] = pd.to_datetime(df["spend_date"])
            out[name] = df
    return out
