"""Reconciliation and data-quality checks.

Failures here become data-quality incidents, not business anomalies.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .kpis import daily_kpis, net_revenue_direct, segment_core, valid_orders


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


def run_reconciliation(tables: dict[str, pd.DataFrame], tz: str) -> list[Check]:
    checks: list[Check] = []
    daily = daily_kpis(tables, tz)

    # 1. Bridge balances to the cent against an independently computed net revenue.
    direct = net_revenue_direct(tables, tz).reindex(daily.index).fillna(0).astype("int64")
    diff = (daily["net_revenue_bridge"] - direct).abs()
    checks.append(Check("revenue_bridge_balances", bool((diff == 0).all()), f"max abs diff (cents): {int(diff.max())}"))

    # 2. Segment sums equal totals.
    for by in ("channel", "device", "region"):
        seg = segment_core(tables, tz, by).groupby(level=0).sum()
        total = daily.reindex(seg.index)
        ok = (
            (seg["sessions"] == total["sessions"]).all()
            and (seg["attributed_orders"] == total["attributed_orders"]).all()
            and (seg["attributed_gross"] == total["attributed_gross_session_date"]).all()
        )
        checks.append(Check(f"segment_sums_match_total_{by}", bool(ok)))

    # 3. Orders must not reference unknown sessions (orphans would hide as unattributed).
    sessions, orders = tables["sessions"], tables["orders"]
    with_sid = orders[orders["session_id"].notna()]
    orphans = int((~with_sid["session_id"].isin(set(sessions["session_id"]))).sum())
    checks.append(Check("no_orphan_session_references", orphans == 0, f"{orphans} orphan orders"))

    # 4. Funnel integrity: an attributed order's session must have reached checkout.
    attr = valid_orders(with_sid).merge(sessions[["session_id", "reached_checkout"]], on="session_id", how="inner")
    bad = int((~attr["reached_checkout"]).sum())
    checks.append(Check("attributed_orders_reached_checkout", bad == 0, f"{bad} violations"))

    # 5. Funnel monotonic: checkout implies cart.
    viol = int((sessions["reached_checkout"] & ~sessions["reached_cart"]).sum())
    checks.append(Check("funnel_monotonic", viol == 0, f"{viol} violations"))

    # 6. Duplicate ids.
    checks.append(Check("unique_session_ids", bool(sessions["session_id"].is_unique)))
    checks.append(Check("unique_order_ids", bool(orders["order_id"].is_unique)))
    return checks


def unattributed_share_flags(
    tables: dict[str, pd.DataFrame],
    tz: str,
    window_days: int = 14,
    threshold: float = 0.10,
    min_orders: int = 40,
) -> pd.DataFrame:
    """Trailing-window unattributed order share; flags days above the contract threshold.

    A trailing window with a minimum order count avoids alerting on noise at low volume.
    """
    d = daily_kpis(tables, tz)
    roll_orders = d["orders"].rolling(window_days, min_periods=1).sum()
    roll_unattr = d["unattributed_orders"].rolling(window_days, min_periods=1).sum()
    out = pd.DataFrame({"orders": roll_orders, "unattributed": roll_unattr})
    out["share"] = out["unattributed"] / out["orders"].where(out["orders"] > 0)
    out["flag"] = (out["share"] > threshold) & (out["orders"] >= min_orders)
    return out
