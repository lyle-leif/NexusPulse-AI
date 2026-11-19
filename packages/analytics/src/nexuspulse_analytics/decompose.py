"""Measured breakdown of a change between a baseline window and an incident window.

Level 1 - revenue bridge (exact, integer cents, average per day):
    net = attributed gross (session date) + timing + unattributed gross - discounts - refunds
Level 2 - Shapley over the multiplicative core of attributed gross, expanded through
    the funnel (the funnel stages telescope to session conversion because every
    converting session reached checkout and every checkout reached cart):
    attributed gross = sessions x cart rate x checkout rate x purchase rate
                       x orders per converting session x attributed AOV
Shapley contributions sum exactly to the change in attributed gross. They measure how
much each factor moved the total; they are not causes.
"""
from __future__ import annotations

from itertools import permutations
from math import factorial, prod

import pandas as pd

from .kpis import _attributed, daily_kpis, local_date, valid_orders

CORE_FACTORS = ["sessions", "cart_rate", "checkout_rate", "purchase_rate", "orders_per_converting_session", "attributed_aov"]
BRIDGE_LINES = [
    ("attributed_gross_session_date", 1, "Attributed gross sales"),
    ("timing_difference", 1, "Timing difference"),
    ("unattributed_gross", 1, "Unattributed gross sales"),
    ("discounts", -1, "Discounts"),
    ("refunds", -1, "Refunds"),
]


def shapley(base: dict[str, float], cur: dict[str, float], f) -> dict[str, float]:
    """Exact Shapley attribution of f(cur) - f(base) to the keys (all orderings)."""
    keys = list(base)
    contrib = dict.fromkeys(keys, 0.0)
    for order in permutations(keys):
        state = dict(base)
        prev = f(state)
        for k in order:
            state[k] = cur[k]
            val = f(state)
            contrib[k] += val - prev
            prev = val
    n = factorial(len(keys))
    return {k: v / n for k, v in contrib.items()}


def funnel_daily(tables: dict[str, pd.DataFrame], tz: str, by: str | None = None) -> pd.DataFrame:
    """Session-date counts: sessions, carts, checkouts, converting sessions, orders, gross.

    by: optional session dimension (channel, device, region) to split on.
    """
    s = tables["sessions"].copy()
    s["date"] = local_date(s["started_at"], tz)
    keys = ["date"] + ([by] if by else [])
    out = s.groupby(keys).agg(sessions=("session_id", "size"), carts=("reached_cart", "sum"), checkouts=("reached_checkout", "sum"))
    attr, _ = _attributed(valid_orders(tables["orders"]), tables["sessions"])
    a = attr.merge(s[["session_id"] + keys], on="session_id", how="left")
    g = a.groupby(keys)
    out["converting_sessions"] = g["session_id"].nunique()
    out["attributed_orders"] = g.size()
    out["attributed_gross"] = g["gross_sales"].sum()
    return out.fillna(0).astype("int64")


def core_factors(c: pd.Series) -> dict[str, float]:
    """Factor values from aggregated counts (per-day averages or totals)."""
    def r(a, b):
        return float(c[a]) / float(c[b]) if c[b] else 0.0

    return {
        "sessions": float(c["sessions"]),
        "cart_rate": r("carts", "sessions"),
        "checkout_rate": r("checkouts", "carts"),
        "purchase_rate": r("converting_sessions", "checkouts"),
        "orders_per_converting_session": r("attributed_orders", "converting_sessions"),
        "attributed_aov": r("attributed_gross", "attributed_orders"),
    }


def baseline_days(start: pd.Timestamp, end: pd.Timestamp, available: pd.DatetimeIndex, weeks: int = 4,
                  exclude: pd.DatetimeIndex | None = None) -> pd.DatetimeIndex:
    """Same weekdays as the incident window, in the `weeks` weeks before it."""
    window = pd.date_range(start, end)
    days = pd.DatetimeIndex(sorted({d - pd.Timedelta(weeks=w) for d in window for w in range(1, weeks + 1)}))
    days = days[days < start].intersection(available)
    if exclude is not None:
        days = days.difference(exclude)
    return days


def decompose(tables: dict[str, pd.DataFrame], tz: str, start: str, end: str,
              exclude: pd.DatetimeIndex | None = None, daily: pd.DataFrame | None = None,
              funnel: pd.DataFrame | None = None) -> dict:
    """Bridge and Shapley breakdown, incident window vs baseline, as averages per day."""
    daily = daily if daily is not None else daily_kpis(tables, tz)
    funnel = funnel if funnel is not None else funnel_daily(tables, tz)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    cur_days = daily.index[(daily.index >= s) & (daily.index <= e)]
    base = baseline_days(s, e, daily.index, exclude=exclude)

    def avg_cents(col, days):
        return daily.loc[days, col].sum() / len(days) if len(days) else 0.0

    bridge = []
    for col, sign, label in BRIDGE_LINES:
        b, c = sign * avg_cents(col, base), sign * avg_cents(col, cur_days)
        bridge.append({"line": col, "label": label, "baseline": b / 100, "current": c / 100, "change": (c - b) / 100})
    nb = sum(x["baseline"] for x in bridge)
    nc = sum(x["current"] for x in bridge)
    bridge.append({"line": "net_revenue", "label": "Net revenue", "baseline": nb, "current": nc, "change": nc - nb, "total": True})

    fb = core_factors(funnel.loc[funnel.index.intersection(base)].mean())
    fc = core_factors(funnel.loc[funnel.index.intersection(cur_days)].mean())
    f = lambda st: prod(st.values()) / 100  # noqa: E731  (dollars per day)
    contrib = shapley(fb, fc, f)
    core = [
        {"factor": k, "baseline": fb[k], "current": fc[k], "relative_change": (fc[k] / fb[k] - 1) if fb[k] else None,
         "contribution": contrib[k]}
        for k in CORE_FACTORS
    ]
    return {
        "window": {"start": s.date().isoformat(), "end": e.date().isoformat(), "days": len(cur_days)},
        "baseline": {"days": len(base), "rule": "same weekdays, 4 weeks before the window"},
        "bridge": bridge,
        "core": core,
        "core_total": {"baseline": f(fb), "current": f(fc), "change": f(fc) - f(fb)},
    }
