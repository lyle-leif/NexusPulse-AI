"""Deterministic synthetic store generator (fashion boutique).

Output is what a real store would have: sessions, orders, items, refunds,
marketing spend and change events. Money columns are integer cents.

Ground-truth labels for injected scenarios are returned separately in
`StoreData.labels` and must never be given to inference code.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .scenarios import Scenario, build_effects

GENERATOR_VERSION = "0.3.0"

CHANNELS = ["organic", "paid_social", "paid_search", "email", "direct"]
DEVICES = ["mobile", "desktop"]
REGIONS = ["north_america", "europe", "asia_pacific", "other"]

_CHANNEL_SHARE = np.array([0.30, 0.22, 0.20, 0.12, 0.16])
_MOBILE_SHARE = np.array([0.62, 0.85, 0.60, 0.70, 0.45])  # per channel
_REGION_SHARE = np.array([0.45, 0.30, 0.18, 0.07])
_P_CART = np.array([0.11, 0.08, 0.12, 0.16, 0.14])  # per channel
_DEVICE_CART_MULT = np.array([0.90, 1.20])           # mobile, desktop
_P_CHECKOUT = np.array([0.50, 0.62])                 # given cart: mobile, desktop
_P_BUY = np.array([0.42, 0.55])                      # given checkout: mobile, desktop
_CPC = {"paid_social": 0.55, "paid_search": 0.85, "email": 0.02}
_HOUR_WEIGHT = np.array(
    [1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 5, 5, 6, 6, 5, 5, 5, 6, 7, 8, 9, 8, 5, 2], dtype=float
)
_WEEKLY = np.array([0.95, 0.92, 0.95, 1.00, 1.08, 1.15, 1.05])  # Mon..Sun

_CATEGORIES = {
    "Dresses": (6000, 18000, 0.22),
    "Tops": (2500, 7000, 0.24),
    "Bottoms": (4000, 9500, 0.16),
    "Outerwear": (9000, 26000, 0.10),
    "Shoes": (6500, 17000, 0.14),
    "Accessories": (1500, 5500, 0.14),
}


@dataclass(frozen=True)
class StoreProfile:
    name: str
    base_sessions: float
    annual_growth: float = 0.25
    day_noise: float = 0.06
    start: str = "2025-01-01"
    days: int = 540
    timezone: str = "Asia/Manila"
    currency: str = "USD"
    unattributed_share: float = 0.04
    refund_rate: float = 0.08
    multi_order_rate: float = 0.06
    discount_rate: float = 0.15
    cancel_rate: float = 0.015
    test_order_rate: float = 0.003


MAIN_FASHION = StoreProfile(name="main_fashion", base_sessions=1500)
LOW_VOLUME_FASHION = StoreProfile(name="low_volume_fashion", base_sessions=150, day_noise=0.10)


@dataclass
class StoreData:
    profile: StoreProfile
    seed: int
    products: pd.DataFrame
    sessions: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    refunds: pd.DataFrame
    marketing_spend: pd.DataFrame
    change_events: pd.DataFrame
    labels: list[dict]  # ground truth; evaluation only

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "products": self.products,
            "sessions": self.sessions,
            "orders": self.orders,
            "order_items": self.order_items,
            "refunds": self.refunds,
            "marketing_spend": self.marketing_spend,
            "change_events": self.change_events,
        }

    def content_hash(self) -> str:
        h = hashlib.sha256()
        for name, df in sorted(self.tables().items()):
            h.update(name.encode())
            hashable = df.copy()
            for col in hashable.columns:
                if hashable[col].map(lambda v: isinstance(v, dict)).any():
                    hashable[col] = hashable[col].map(lambda v: repr(sorted(v.items())) if isinstance(v, dict) else v)
            h.update(pd.util.hash_pandas_object(hashable, index=False).values.tobytes())
        return h.hexdigest()


def _hex_ids(rng: np.random.Generator, n: int, prefix: str) -> np.ndarray:
    vals = rng.integers(0, 2**62, size=n).tolist()
    return np.array([f"{prefix}{v:016x}" for v in vals], dtype=object)


def _build_products() -> pd.DataFrame:
    rows = []
    for cat, (lo, hi, _) in _CATEGORIES.items():
        for i in range(8):
            price = int(round((lo + (hi - lo) * i / 7) / 100.0) * 100 - 1)  # e.g. 4999
            rows.append(
                {
                    "product_id": f"p_{cat[:3].lower()}_{i + 1}",
                    "name": f"{cat[:-1] if cat.endswith('s') else cat} {i + 1}",
                    "category": cat,
                    "price": price,
                    "cost": int(round(price * (0.40 + 0.015 * i))),
                }
            )
    return pd.DataFrame(rows)


def _product_weights(products: pd.DataFrame) -> np.ndarray:
    pop = {c: w for c, (_, _, w) in _CATEGORIES.items()}
    w = products["category"].map(pop).to_numpy(dtype=float)
    return w / w.sum()


def _nth_weekday(dates: pd.DatetimeIndex, month: int, weekday: int, nth: int) -> pd.Series:
    mask = (dates.month == month) & (dates.day_of_week == weekday)
    day_ok = (dates.day > 7 * (nth - 1)) & (dates.day <= 7 * nth)
    return pd.Series(mask & day_ok, index=dates)


def _holiday_multipliers(dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, list[tuple]]:
    traffic = np.ones(len(dates))
    conv = np.ones(len(dates))
    events: list[tuple] = []
    bf = _nth_weekday(dates, 11, 4, 4).to_numpy()  # 4th Friday of November
    cyber = np.roll(bf, 3)
    cyber[:3] = False
    traffic[bf], conv[bf] = 1.8, 1.30
    traffic[cyber], conv[cyber] = 1.5, 1.20
    xmas = (dates.month == 12) & (dates.day <= 23)
    traffic[xmas] *= 1.25
    val = (dates.month == 2) & (dates.day >= 8) & (dates.day <= 14)
    traffic[val] *= 1.20
    for i, d in enumerate(dates):
        if bf[i]:
            events.append((d, "holiday", "Black Friday"))
        if cyber[i]:
            events.append((d, "holiday", "Cyber Monday"))
        if d.month == 12 and d.day == 1:
            events.append((d, "holiday", "Holiday season begins"))
        if d.month == 2 and d.day == 8:
            events.append((d, "holiday", "Valentine's Day promotion window"))
    return traffic, conv, events


def _local_to_utc(date_values: np.ndarray, day_idx: np.ndarray, seconds: np.ndarray, tz: str) -> np.ndarray:
    local = date_values[day_idx] + (seconds * 1e9).astype("timedelta64[ns]")
    return pd.DatetimeIndex(local).tz_localize(tz).tz_convert("UTC").tz_localize(None).values


def _utc_series(values: np.ndarray) -> pd.Series:
    return pd.Series(pd.DatetimeIndex(values, tz="UTC"))


def generate_store(
    profile: StoreProfile,
    seed: int,
    days: int | None = None,
    scenarios: tuple[Scenario, ...] = (),
) -> StoreData:
    p = profile if days is None else replace(profile, days=days)
    rng = np.random.default_rng(seed)

    dates = pd.date_range(p.start, periods=p.days, freq="D")
    date_values = dates.values
    n_days = p.days
    t = np.arange(n_days)

    # ---- scenario effects (separate stream so labels never depend on data draws) --
    cat_w = {c: w for c, (_, _, w) in _CATEGORIES.items()}
    cat_share = {c: w / sum(cat_w.values()) for c, w in cat_w.items()}
    fx = build_effects(tuple(scenarios), dates, cat_share, np.random.default_rng([seed, 7]))

    # ---- daily traffic level ------------------------------------------------
    h_traffic, h_conv, holiday_events = _holiday_multipliers(dates)
    yearly = 1 + 0.12 * np.cos(2 * np.pi * (dates.day_of_year.to_numpy() - 350) / 365.25)
    level = (
        p.base_sessions
        * (1 + p.annual_growth) ** (t / 365.0)
        * _WEEKLY[dates.day_of_week.to_numpy()]
        * yearly
        * h_traffic
        * rng.lognormal(0, p.day_noise, n_days)
    )

    # ---- sessions per day x channel x device -------------------------------
    cell_share = np.zeros(10)
    for c in range(5):
        cell_share[c * 2] = _CHANNEL_SHARE[c] * _MOBILE_SHARE[c]
        cell_share[c * 2 + 1] = _CHANNEL_SHARE[c] * (1 - _MOBILE_SHARE[c])
    counts = rng.poisson(level[:, None] * cell_share[None, :] * fx.traffic)  # (days, 10)
    cell = np.repeat(np.arange(n_days * 10), counts.ravel())
    day_idx = cell // 10
    ch_idx = (cell % 10) // 2
    dev_idx = (cell % 10) % 2
    n_sessions = len(cell)

    region_idx = rng.choice(len(REGIONS), size=n_sessions, p=_REGION_SHARE)
    hour = rng.choice(24, size=n_sessions, p=_HOUR_WEIGHT / _HOUR_WEIGHT.sum())
    seconds = hour * 3600 + rng.random(n_sessions) * 3600
    started_utc = _local_to_utc(date_values, day_idx, seconds, p.timezone)

    # ---- funnel -------------------------------------------------------------
    cell_in_day = cell % 10
    p_cart = np.minimum(_P_CART[ch_idx] * _DEVICE_CART_MULT[dev_idx] * h_conv[day_idx] * fx.cart[day_idx, cell_in_day], 0.95)
    p_buy = np.minimum(_P_BUY[dev_idx] * fx.buy[day_idx, cell_in_day], 0.99)
    reached_cart = rng.random(n_sessions) < p_cart
    reached_checkout = reached_cart & (rng.random(n_sessions) < _P_CHECKOUT[dev_idx])
    buys = reached_checkout & (rng.random(n_sessions) < p_buy)

    session_ids = _hex_ids(rng, n_sessions, "s_")
    sessions = pd.DataFrame(
        {
            "session_id": session_ids,
            "started_at": _utc_series(started_utc),
            "channel": np.array(CHANNELS, dtype=object)[ch_idx],
            "device": np.array(DEVICES, dtype=object)[dev_idx],
            "region": np.array(REGIONS, dtype=object)[region_idx],
            "reached_cart": reached_cart,
            "reached_checkout": reached_checkout,
        }
    )

    # ---- attributed orders --------------------------------------------------
    conv_idx = np.flatnonzero(buys)
    per_session = 1 + (rng.random(len(conv_idx)) < p.multi_order_rate).astype(int)
    order_sess = np.repeat(conv_idx, per_session)
    n_attr = len(order_sess)
    attr_placed = started_utc[order_sess] + (rng.exponential(600.0, n_attr) * 1e9).astype("timedelta64[ns]")
    order_day = day_idx[order_sess]

    # ---- baseline unattributed orders --------------------------------------
    attr_per_day = np.bincount(order_day, minlength=n_days)
    unattr_lambda = attr_per_day * p.unattributed_share / (1 - p.unattributed_share)
    unattr_counts = rng.poisson(unattr_lambda)
    unattr_day = np.repeat(np.arange(n_days), unattr_counts)
    n_unattr = len(unattr_day)
    u_hour = rng.choice(24, size=n_unattr, p=_HOUR_WEIGHT / _HOUR_WEIGHT.sum())
    unattr_placed = _local_to_utc(date_values, unattr_day, u_hour * 3600 + rng.random(n_unattr) * 3600, p.timezone)

    n_orders = n_attr + n_unattr
    order_ids = _hex_ids(rng, n_orders, "o_")
    order_session_id = np.concatenate([session_ids[order_sess], np.full(n_unattr, None, dtype=object)])
    placed = np.concatenate([attr_placed, unattr_placed])
    order_local_day = np.concatenate([order_day, unattr_day])

    # ---- scenarios: tracking breakage --------------------------------------
    for first, last, lost_share in fx.tracking:
        in_window = (order_local_day >= first) & (order_local_day <= last)
        lost = in_window & (order_session_id != None) & (rng.random(n_orders) < lost_share)  # noqa: E711
        order_session_id = np.where(lost, None, order_session_id)
    labels = fx.labels

    # ---- order items, gross, discount --------------------------------------
    products = _build_products()
    prices = products["price"].to_numpy(dtype=np.int64)
    weights = _product_weights(products)
    n_items = rng.choice([1, 2, 3], size=n_orders, p=[0.6, 0.3, 0.1])
    item_order = np.repeat(np.arange(n_orders), n_items)
    item_prod = rng.choice(len(products), size=len(item_order), p=weights)
    item_day = order_local_day[item_order]
    prod_cat = products["category"].to_numpy()
    for first, last, cat in fx.blocked:  # stock-out: those products cannot be bought
        allowed = prod_cat != cat
        w_allowed = np.where(allowed, weights, 0.0)
        w_allowed /= w_allowed.sum()
        hit = (item_day >= first) & (item_day <= last) & (prod_cat[item_prod] == cat)
        item_prod[hit] = rng.choice(len(products), size=int(hit.sum()), p=w_allowed)
    item_qty = 1 + (rng.random(len(item_order)) < 0.10).astype(int)
    unit_price = np.rint(prices[item_prod] * fx.price[item_day]).astype(np.int64)
    gross = np.rint(np.bincount(item_order, weights=item_qty * unit_price, minlength=n_orders)).astype(np.int64)
    disc_mask = rng.random(n_orders) < p.discount_rate
    disc_pct = rng.choice([0.10, 0.15, 0.20], size=n_orders)
    discount = np.where(disc_mask, np.rint(gross * disc_pct), 0).astype(np.int64)

    status = np.where(rng.random(n_orders) < p.cancel_rate, "cancelled", "paid").astype(object)
    is_test = rng.random(n_orders) < p.test_order_rate

    orders = pd.DataFrame(
        {
            "order_id": order_ids,
            "placed_at": _utc_series(placed),
            "session_id": order_session_id,
            "currency": p.currency,
            "gross_sales": gross,
            "discount": discount,
            "status": status,
            "is_test": is_test,
        }
    ).sort_values("placed_at", kind="stable").reset_index(drop=True)

    order_items = pd.DataFrame(
        {
            "order_id": order_ids[item_order],
            "product_id": products["product_id"].to_numpy(dtype=object)[item_prod],
            "quantity": item_qty,
            "unit_price": unit_price,
        }
    )

    # ---- refunds ------------------------------------------------------------
    end_utc = pd.Timestamp(dates[-1] + pd.Timedelta(days=1)).tz_localize(p.timezone).tz_convert("UTC")
    paid_valid = (status == "paid") & (~is_test)
    refund_mask = paid_valid & (rng.random(n_orders) < p.refund_rate)
    ref_idx = np.flatnonzero(refund_mask)
    frac = np.where(rng.random(len(ref_idx)) < 0.7, 1.0, 0.5)
    ref_amount = np.rint((gross[ref_idx] - discount[ref_idx]) * frac).astype(np.int64)
    ref_time = placed[ref_idx] + (rng.uniform(3, 20, len(ref_idx)) * 86400 * 1e9).astype("timedelta64[ns]")
    refunds = pd.DataFrame(
        {"order_id": order_ids[ref_idx], "refunded_at": _utc_series(ref_time), "amount": ref_amount}
    )
    refunds = refunds[(refunds["amount"] > 0) & (refunds["refunded_at"] < end_utc)].reset_index(drop=True)

    # ---- marketing spend ----------------------------------------------------
    sess_by_ch = counts.reshape(n_days, 5, 2).sum(axis=2)
    spend_rows = []
    for ch, cpc in _CPC.items():
        c = CHANNELS.index(ch)
        spend = np.rint(sess_by_ch[:, c] * cpc * rng.lognormal(0, 0.10, n_days) * 100).astype(np.int64)
        spend_rows.append(
            pd.DataFrame(
                {
                    "spend_date": dates,
                    "channel": ch,
                    "campaign": f"{ch}_always_on",
                    "spend": spend,
                    "impressions": (sess_by_ch[:, c] / 0.02).astype(np.int64),
                    "clicks": sess_by_ch[:, c].astype(np.int64),
                }
            )
        )
    marketing_spend = pd.concat(spend_rows, ignore_index=True)

    # ---- change events (holidays + routine newsletter) ----------------------
    nine = pd.Timedelta(hours=9)
    # Holidays come from a calendar, so their window length is known in advance.
    windows = {"Black Friday": 1, "Cyber Monday": 1, "Holiday season begins": 23, "Valentine's Day promotion window": 7}
    ev = [(d + nine, typ, desc, {"window_days": windows[desc]}) for d, typ, desc in holiday_events]
    for d in dates[dates.day_of_week == 3]:
        ev.append((d + nine, "campaign", "Weekly newsletter sent", {"channel": "email"}))
    ev.extend(fx.events)  # scenario events, already in local time
    ev_ids = _hex_ids(rng, len(ev), "e_")
    local_times = pd.DatetimeIndex([e[0] for e in ev])
    change_events = pd.DataFrame(
        {
            "event_id": ev_ids,
            "occurred_at": _utc_series(local_times.tz_localize(p.timezone).tz_convert("UTC").tz_localize(None).values),
            "event_type": [e[1] for e in ev],
            "description": [e[2] for e in ev],
            "scope": [e[3] for e in ev],
            "source": "synthetic",
        }
    ).sort_values("occurred_at").reset_index(drop=True)

    sessions = sessions.sort_values("started_at", kind="stable").reset_index(drop=True)
    return StoreData(p, seed, products, sessions, orders, order_items, refunds, marketing_spend, change_events, labels)
