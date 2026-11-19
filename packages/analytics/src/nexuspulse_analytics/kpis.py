"""KPI engine implementing the metric contracts in contracts/metrics.yaml.

Money columns are integer cents. Days are bucketed in the workspace timezone.
Orders flagged is_test or with status 'cancelled' are excluded everywhere.
"""
from __future__ import annotations

import pandas as pd


def local_date(ts: pd.Series, tz: str) -> pd.Series:
    """UTC timestamps -> naive local midnight timestamps."""
    return ts.dt.tz_convert(tz).dt.tz_localize(None).dt.normalize()


def valid_orders(orders: pd.DataFrame) -> pd.DataFrame:
    return orders[(~orders["is_test"]) & (orders["status"] != "cancelled")]


def _attributed(orders: pd.DataFrame, sessions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split valid orders into attributed (session exists) and unattributed."""
    known = orders["session_id"].isin(set(sessions["session_id"]))
    return orders[known], orders[~known]


def daily_kpis(tables: dict[str, pd.DataFrame], tz: str) -> pd.DataFrame:
    sessions, orders, refunds = tables["sessions"], tables["orders"], tables["refunds"]
    o = valid_orders(orders).copy()
    o["order_date"] = local_date(o["placed_at"], tz)

    s = sessions[["session_id", "started_at"]].copy()
    s["session_date"] = local_date(s["started_at"], tz)
    sess_date = s.set_index("session_id")["session_date"]

    attr, unattr = _attributed(o, sessions)
    attr = attr.assign(session_date=attr["session_id"].map(sess_date))

    out = pd.DataFrame(index=pd.DatetimeIndex(sorted(set(s["session_date"]) | set(o["order_date"])), name="date"))
    out["sessions"] = s.groupby("session_date").size()
    out["converting_sessions"] = attr.groupby("session_date")["session_id"].nunique()
    out["attributed_orders"] = attr.groupby("session_date").size()
    out["attributed_gross_session_date"] = attr.groupby("session_date")["gross_sales"].sum()
    attr_by_order_date = attr.groupby("order_date")["gross_sales"].sum()
    out["unattributed_gross"] = unattr.groupby("order_date")["gross_sales"].sum()
    out["discounts"] = o.groupby("order_date")["discount"].sum()

    r = refunds.merge(o[["order_id", "order_date"]], on="order_id", how="inner")
    out["refunds"] = r.groupby("order_date")["amount"].sum()
    out["unattributed_orders"] = unattr.groupby("order_date").size()
    out["orders"] = o.groupby("order_date").size()

    out = out.fillna(0)
    out["timing_difference"] = attr_by_order_date.reindex(out.index).fillna(0) - out["attributed_gross_session_date"]
    out = out.astype("int64")

    out["net_revenue_bridge"] = (
        out["attributed_gross_session_date"]
        + out["timing_difference"]
        + out["unattributed_gross"]
        - out["discounts"]
        - out["refunds"]
    )
    return out


def net_revenue_direct(tables: dict[str, pd.DataFrame], tz: str) -> pd.Series:
    """Independent net revenue (order date): sum(gross - discount) - refunds, no bridge."""
    o = valid_orders(tables["orders"]).copy()
    o["order_date"] = local_date(o["placed_at"], tz)
    net = (o["gross_sales"] - o["discount"]).groupby(o["order_date"]).sum()
    r = tables["refunds"].merge(o[["order_id", "order_date"]], on="order_id", how="inner")
    return (net - r.groupby("order_date")["amount"].sum().reindex(net.index).fillna(0)).astype("int64")


def segment_core(tables: dict[str, pd.DataFrame], tz: str, by: str) -> pd.DataFrame:
    """Session-date core metrics per segment (channel, device or region)."""
    sessions, orders = tables["sessions"], tables["orders"]
    s = sessions.copy()
    s["session_date"] = local_date(s["started_at"], tz)
    attr, _ = _attributed(valid_orders(orders), sessions)
    attr = attr.merge(s[["session_id", "session_date", by]], on="session_id", how="left")
    out = pd.DataFrame({"sessions": s.groupby(["session_date", by]).size()})
    out["converting_sessions"] = attr.groupby(["session_date", by])["session_id"].nunique()
    out["attributed_orders"] = attr.groupby(["session_date", by]).size()
    out["attributed_gross"] = attr.groupby(["session_date", by])["gross_sales"].sum()
    return out.fillna(0).astype("int64")
