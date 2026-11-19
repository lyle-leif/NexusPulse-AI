"""Append-only loader: DataFrames (money as integer cents) -> Postgres np.* tables.

Knows nothing about the generator or ground-truth labels.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import psycopg

DEFAULT_ADMIN_DSN = "postgresql://nexuspulse:nexuspulse_dev@localhost:5433/nexuspulse"

# table -> (columns in DB order excluding workspace/batch, money columns, timestamp columns)
_SPEC = {
    "products": (["product_id", "name", "category", "price", "cost"], ["price", "cost"], []),
    "sessions": (
        ["session_id", "started_at", "channel", "device", "region", "reached_cart", "reached_checkout"],
        [],
        ["started_at"],
    ),
    "orders": (
        ["order_id", "placed_at", "session_id", "currency", "gross_sales", "discount", "status", "is_test"],
        ["gross_sales", "discount"],
        ["placed_at"],
    ),
    "order_items": (["order_id", "product_id", "quantity", "unit_price"], ["unit_price"], []),
    "refunds": (["order_id", "refunded_at", "amount"], ["amount"], ["refunded_at"]),
    "marketing_spend": (
        ["spend_date", "channel", "campaign", "spend", "impressions", "clicks"],
        ["spend"],
        [],
    ),
    "change_events": (
        ["event_id", "occurred_at", "event_type", "description", "scope", "source"],
        [],
        ["occurred_at"],
    ),
}


def _cents_to_text(s: pd.Series) -> pd.Series:
    s = s.astype("int64")
    sign = s.lt(0).map({True: "-", False: ""})
    a = s.abs()
    return sign + (a // 100).astype(str) + "." + (a % 100).astype(str).str.zfill(2)


def _prepare(name: str, df: pd.DataFrame, workspace_id: str, batch_id: str) -> pd.DataFrame:
    cols, money, stamps = _SPEC[name]
    out = df[cols].copy()
    for c in money:
        out[c] = _cents_to_text(out[c])
    for c in stamps:
        out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    if name == "change_events":
        out["scope"] = out["scope"].map(json.dumps)
    if name == "marketing_spend":
        out["spend_date"] = out["spend_date"].dt.strftime("%Y-%m-%d")
    out.insert(0, "workspace_id", workspace_id)
    out["ingest_batch_id"] = batch_id
    return out


def load_tables(
    tables: dict[str, pd.DataFrame],
    workspace_id: str,
    batch_id: str,
    dsn: str = DEFAULT_ADMIN_DSN,
) -> dict[str, int]:
    """Append one batch. Refuses to reuse an existing (workspace, batch) pair."""
    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM np.sessions WHERE workspace_id = %s AND ingest_batch_id = %s",
                (workspace_id, batch_id),
            )
            if cur.fetchone()[0]:
                raise ValueError(f"batch {batch_id!r} already loaded for workspace {workspace_id!r}")
            for name in _SPEC:
                data = _prepare(name, tables[name], workspace_id, batch_id)
                buf = io.StringIO()
                data.to_csv(buf, index=False, header=False, na_rep="")
                buf.seek(0)
                cols = ", ".join(data.columns)
                with cur.copy(f"COPY np.{name} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
                    while chunk := buf.read(1 << 20):
                        cp.write(chunk)
                counts[name] = len(data)
        conn.commit()
    return counts
