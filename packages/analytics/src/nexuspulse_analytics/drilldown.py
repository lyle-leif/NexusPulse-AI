"""Segment drill-down: where is the change concentrated?

For a session dimension (channel, device, region) each segment's change in attributed
gross per day is split exactly (2-factor Shapley) into a traffic part (sessions) and a
rate part (attributed gross per session). Segment contributions sum to the total change.

For product category (an order-line dimension) the change in line value per day is
reported per category, with the same exact-sum property.

Guards: segments with fewer than MIN_BASE_SESSIONS sessions per baseline day are
reported but never selected as the concentration. A noise score compares each
segment's change with its own day-to-day variation in the baseline.

Segments the monitor flagged (their own series left the forecast range) are checked first:
one is selected when it is the largest mover of its dimension in the issue's direction.
The monitor flag stands in for the share and noise tests, which a real segment change can
fail when the other segments of its dimension swing the opposite way by chance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .decompose import baseline_days, core_factors, funnel_daily, shapley
from .kpis import local_date, valid_orders

SESSION_DIMS = ["device", "channel", "region"]
MIN_BASE_SESSIONS = 30
MIN_NOISE_SCORE = 2.0
MIN_SHARE, MAX_SHARE = 0.5, 1.5


def _noise_score(base: pd.Series, cur: pd.Series) -> float:
    if len(base) < 3 or len(cur) == 0:
        return 0.0
    sd = float(base.std(ddof=1)) or 1e-9
    return float((cur.mean() - base.mean()) / (sd / np.sqrt(len(cur))))


def segment_table(funnel_by: pd.DataFrame, dim: str, base: pd.DatetimeIndex, cur: pd.DatetimeIndex) -> list[dict]:
    rows = []
    for seg, g in funnel_by.groupby(level=dim):
        g = g.droplevel(dim)
        gb, gc = g.reindex(base, fill_value=0), g.reindex(cur, fill_value=0)
        sb, sc = gb["sessions"].mean(), gc["sessions"].mean()
        rb = gb["attributed_gross"].sum() / gb["sessions"].sum() if gb["sessions"].sum() else 0.0
        rc = gc["attributed_gross"].sum() / gc["sessions"].sum() if gc["sessions"].sum() else 0.0
        parts = shapley({"traffic": sb, "rate": rb}, {"traffic": sc, "rate": rc}, lambda s: s["traffic"] * s["rate"] / 100)
        fb, fc = core_factors(gb.sum()), core_factors(gc.sum())
        rows.append(
            {
                "dimension": dim,
                "segment": str(seg),
                "baseline_per_day": sb * rb / 100,
                "current_per_day": sc * rc / 100,
                "change": parts["traffic"] + parts["rate"],
                "traffic_part": parts["traffic"],
                "rate_part": parts["rate"],
                "baseline_sessions_per_day": float(sb),
                "factor_change": {k: (fc[k] / fb[k] - 1) if fb[k] else None for k in fb if k != "sessions"},
                "noise_score": _noise_score(gb["attributed_gross"] / 100, gc["attributed_gross"] / 100),
                "volume_ok": bool(sb >= MIN_BASE_SESSIONS),
            }
        )
    return rows


def category_table(tables: dict[str, pd.DataFrame], tz: str, base: pd.DatetimeIndex, cur: pd.DatetimeIndex) -> list[dict]:
    o = valid_orders(tables["orders"])[["order_id", "placed_at"]].copy()
    o["date"] = local_date(o["placed_at"], tz)
    it = tables["order_items"].merge(o[["order_id", "date"]], on="order_id").merge(tables["products"][["product_id", "category"]], on="product_id")
    it["value"] = it["quantity"] * it["unit_price"].astype(float)
    daily = it.groupby(["date", "category"])["value"].sum().unstack(fill_value=0.0)
    unit = 100.0 if pd.api.types.is_integer_dtype(tables["order_items"]["unit_price"]) else 1.0  # cents -> dollars
    rows = []
    for cat in daily.columns:
        b = daily[cat].reindex(base, fill_value=0) / unit
        c = daily[cat].reindex(cur, fill_value=0) / unit
        rows.append({"dimension": "category", "segment": str(cat), "baseline_per_day": float(b.mean()), "current_per_day": float(c.mean()),
                     "change": float(c.mean() - b.mean()), "noise_score": _noise_score(b, c), "volume_ok": bool(b.mean() > 0)})
    return rows


def concentration(rows: list[dict], total: float) -> dict | None:
    """Largest same-direction segment, its share of the dimension's total change."""
    if not rows or total == 0:
        return None
    eligible = [r for r in rows if r["volume_ok"] and np.sign(r["change"]) == np.sign(total)]
    if not eligible:
        return None
    top = max(eligible, key=lambda r: abs(r["change"]))
    return {"segment": top["segment"], "share": float(top["change"] / total), "noise_score": top["noise_score"]}


def flagged_choice(dims: dict, flagged: list[dict] | None, direction: str | None = None) -> tuple[str, dict] | None:
    """Among monitor-flagged segments, those that are the largest mover of their dimension in the
    issue's direction; the one whose change stands out most from its own noise is chosen."""
    sign = -1.0 if direction == "down" else 1.0 if direction == "up" else None
    best = None
    for f in flagged or []:
        d = dims.get(f["dimension"])
        row = next((r for r in d["rows"] if r["segment"] == str(f["value"])), None) if d else None
        if not row or not row["volume_ok"] or row["change"] == 0:
            continue
        s = sign if sign is not None else float(np.sign(d["total_change"]))
        if np.sign(row["change"]) != s or max((r["change"] * s for r in d["rows"] if r["volume_ok"]), default=0) > row["change"] * s:
            continue
        share = float(row["change"] / d["total_change"]) if d["total_change"] else 1.0
        c = {"segment": row["segment"], "share": share, "change": row["change"], "noise_score": row["noise_score"], "flagged": True}
        if best is None or abs(c["noise_score"]) > abs(best[1]["noise_score"]):
            best = (f["dimension"], c)
    return best


def drill_down(tables: dict[str, pd.DataFrame], tz: str, start: str, end: str, exclude: pd.DatetimeIndex | None = None,
               depth: int = 2, flagged: list[dict] | None = None, direction: str | None = None) -> dict:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    f_all = funnel_daily(tables, tz)
    base = baseline_days(s, e, f_all.index, exclude=exclude)
    cur = f_all.index[(f_all.index >= s) & (f_all.index <= e)]

    dims = {}
    for dim in SESSION_DIMS:
        rows = segment_table(funnel_daily(tables, tz, by=dim), dim, base, cur)
        total = sum(r["change"] for r in rows)
        dims[dim] = {"rows": sorted(rows, key=lambda r: r["change"]), "total_change": total, "concentration": concentration(rows, total)}
    cats = category_table(tables, tz, base, cur)
    ctot = sum(r["change"] for r in cats)
    dims["category"] = {"rows": sorted(cats, key=lambda r: r["change"]), "total_change": ctot, "concentration": concentration(cats, ctot)}

    # Most concentrated dimension (session dims and category compete on share).
    # Among segments holding at least half of their dimension's change, pick the one whose
    # change stands out most from its own day-to-day noise. Shares far above 100% mean
    # other segments moved the opposite way (offsetting noise), so they are not eligible.
    best = flagged_choice(dims, flagged, direction)
    for dim, d in ([] if best else dims.items()):
        c = d["concentration"]
        if not c or not (MIN_SHARE <= c["share"] <= MAX_SHARE) or abs(c["noise_score"]) < MIN_NOISE_SCORE:
            continue
        if best is None or abs(c["noise_score"]) > abs(best[1]["noise_score"]):
            best = (dim, c)

    second = None
    if depth >= 2 and best and best[0] in SESSION_DIMS:
        dim, c = best
        sel = tables["sessions"][dim].astype(str) == c["segment"]
        sub = {**tables, "sessions": tables["sessions"][sel]}
        sub_f = funnel_daily(sub, tz)
        tot = None
        second = {}
        for d2 in [x for x in SESSION_DIMS if x != dim]:
            rows = segment_table(funnel_daily(sub, tz, by=d2), d2, base.intersection(sub_f.index), cur.intersection(sub_f.index))
            tot = sum(r["change"] for r in rows)
            second[d2] = {"rows": sorted(rows, key=lambda r: r["change"]), "total_change": tot, "concentration": concentration(rows, tot)}

    return {
        "dimensions": dims,
        "primary": {"dimension": best[0], **best[1]} if best else None,
        "second_level": second,
        "baseline_days": len(base),
    }
