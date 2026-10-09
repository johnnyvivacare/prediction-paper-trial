"""Validated market types and exact monetary arithmetic (1 USD = 10,000 units)."""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any

USD = 10_000
CENT = 100
UTC = timezone.utc


def utcnow() -> float:
    return datetime.now(UTC).timestamp()


def iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(utcnow() if ts is None else ts, UTC).isoformat()


def timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Nonfinite timestamp")
        return float(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing timestamp")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return d.timestamp()


def decimal(value: Any) -> Decimal:
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid numeric value") from exc
    if not x.is_finite():
        raise ValueError("Nonfinite numeric value")
    return x


def money(value: Any) -> int:
    x = decimal(value) * USD
    if x != x.to_integral_value():
        raise ValueError("More than four price decimals; unsupported precision")
    return int(x)


def dollars(value: int | None) -> float | None:
    return None if value is None else round(value / USD, 4)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ceil_cent(units: int | Decimal) -> int:
    return int((decimal(units) / CENT).to_integral_value(rounding=ROUND_CEILING)) * CENT


@dataclass(frozen=True)
class Fee:
    """Paper fee estimate; rejects missing/unsupported upstream fee metadata.

    Kalshi's documented quadratic taker formula, with a configurable conservative
    per-contract minimum. This is NOT a verified Canadian broker fee schedule.
    """
    kind: str
    multiplier: str
    observed_at: float
    floor_units: int = 300

    def valid(self, now: float) -> bool:
        try:
            return (self.kind in {"quadratic", "quadratic_with_maker_fees"}
                    and Decimal("0") < decimal(self.multiplier) <= Decimal("100")
                    and 0 <= now - self.observed_at <= 3600
                    and 0 <= self.floor_units < USD)
        except ValueError:
            return False

    def charge(self, qty: int, price: int) -> int:
        if qty < 0 or not 0 <= price <= USD or self.kind not in {"quadratic", "quadratic_with_maker_fees"}:
            raise ValueError("Unsupported fee or invalid size")
        if not 0 < decimal(self.multiplier) <= 100:
            raise ValueError("Invalid fee multiplier")
        p = Decimal(price) / USD
        computed = ceil_cent(Decimal("0.07") * decimal(self.multiplier) * qty * p * (1-p) * USD)
        return max(computed, ceil_cent(qty * self.floor_units))


@dataclass(frozen=True)
class Market:
    ticker: str
    event: str
    series: str
    title: str
    category: str
    close_at: float
    status: str
    rules_hash: str
    rules: str
    volume: float
    yes_bid: int | None
    yes_ask: int | None
    result: str = ""
    source: str = "kalshi_public"
    provisional: bool = False

    @classmethod
    def parse(cls, raw: dict, category: str = "Unknown", series: str = "") -> Market:
        if raw.get("market_type") != "binary" or raw.get("mve_collection_ticker"):
            raise ValueError("Only plain binary markets are supported")
        t, e = raw.get("ticker"), raw.get("event_ticker")
        if not isinstance(t, str) or not t or not isinstance(e, str) or not e:
            raise ValueError("Missing contract identity")
        notional = raw.get("notional_value_dollars")
        if notional is not None and money(notional) != USD:
            raise ValueError("Only $1 payout contracts are supported")
        result=str(raw.get("result") or "").upper()
        payout=raw.get("settlement_value_dollars")
        if raw.get("status") in {"settled","finalized"} and payout is not None and result in {"YES","NO"}:
            if money(payout)!=(USD if result=="YES" else 0):
                raise ValueError("Non-binary or inconsistent settlement payout; requires review")
        rules = str(raw.get("rules_primary") or "") + "\n" + str(raw.get("rules_secondary") or "")
        if not rules.strip():
            raise ValueError("Missing settlement rules")
        terms = {k: raw.get(k) for k in ("ticker", "event_ticker", "rules_primary", "rules_secondary",
                    "strike_type", "floor_strike", "cap_strike", "functional_strike", "custom_strike",
                    "expiration_time", "latest_expiration_time", "notional_value_dollars")}
        def price(key: str) -> int | None:
            value = raw.get(key + "_dollars")
            if value is None:
                return None
            p = money(value)
            return p if 0 <= p <= USD else None
        return cls(t, e, series or e.split("-")[0], str(raw.get("title") or t), category,
                   timestamp(raw.get("close_time")), str(raw.get("status", "")), digest(terms), rules,
                   float(decimal(raw.get("volume_24h_fp") or raw.get("volume_fp") or "0")),
                   price("yes_bid"), price("yes_ask"), str(raw.get("result") or "").upper(),
                   "kalshi_public", bool(raw.get("is_provisional", False)))

    def active(self, now: float) -> bool:
        return self.status in {"active", "open"} and self.close_at > now and not self.provisional


@dataclass(frozen=True)
class Book:
    ticker: str
    fetched_at: float
    yes_bids: tuple[tuple[int, int], ...]
    no_bids: tuple[tuple[int, int], ...]

    @classmethod
    def parse(cls, ticker: str, raw: dict, fetched_at: float) -> Book:
        """Only the documented fixed-point response is accepted; no silent schema guessing."""
        body = raw.get("orderbook_fp")
        if not isinstance(body, dict):
            raise ValueError("Expected orderbook_fp; source schema may have changed")
        def levels(key: str) -> tuple[tuple[int, int], ...]:
            values = body.get(key)
            if values is None:
                values = []  # Documented empty side, NOT executable liquidity.
            if not isinstance(values, list):
                raise ValueError("Invalid book side")
            merged: dict[int, int] = {}
            for row in values:
                if not isinstance(row, (tuple, list)) or len(row) != 2:
                    raise ValueError("Invalid depth row")
                p, q = money(row[0]), decimal(row[1])
                if not 0 < p < USD or q < 0:
                    raise ValueError("Invalid depth price or quantity")
                # Fractional depth is floored; this simulator trades whole contracts only.
                size = int(q)
                if size:
                    merged[p] = merged.get(p, 0) + size
            return tuple(sorted(merged.items(), reverse=True))
        book = cls(ticker, fetched_at, levels("yes_dollars"), levels("no_dollars"))
        if book.yes_bids and book.no_bids and book.yes_bids[0][0] + book.no_bids[0][0] > USD:
            raise ValueError("Crossed/inconsistent book; not free-money arbitrage")
        return book

    def bids(self, side: str) -> tuple[tuple[int, int], ...]:
        if side not in {"YES", "NO"}:
            raise ValueError("Unknown side")
        return self.yes_bids if side == "YES" else self.no_bids

    def asks(self, side: str) -> tuple[tuple[int, int], ...]:
        if side not in {"YES","NO"}:raise ValueError("Unknown side")
        opposite = "NO" if side == "YES" else "YES"
        # Official Kalshi complement mapping includes BOTH price and available size.
        return tuple(sorted((USD-p, qty) for p, qty in self.bids(opposite)))

    def mid(self, side: str = "YES") -> float | None:
        b, a = self.bids(side), self.asks(side)
        return (b[0][0] + a[0][0]) / (2 * USD) if b and a else None

    def spread(self, side: str) -> int | None:
        b, a = self.bids(side), self.asks(side)
        return a[0][0] - b[0][0] if b and a else None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Fill:
    qty: int
    gross: int
    fee: int
    cash: int
    average: int


def walk(book: Book, side: str, qty: int, fee: Fee, buy: bool,
         slippage: int = 100, participation: float = 0.25) -> Fill:
    """Simulate against depth. A snapshot is not a guarantee of a real fill.

    Fee rounding is applied at each consumed level, conservatively. Entry/exit use
    the same depth participation cap, so queue availability is not assumed unlimited.
    """
    if qty < 1 or not 0 < participation <= 1 or not 0 <= slippage < USD:
        raise ValueError("Invalid execution settings")
    remaining, count, gross, fees = qty, 0, 0, 0
    levels = book.asks(side) if buy else book.bids(side)
    for price, available in levels:
        take = min(remaining, int(available * participation))
        adjusted = price + slippage if buy else price - slippage
        if not 0 < adjusted < USD or take <= 0:
            continue
        level_fee=fee.charge(take,adjusted)
        if not buy and take*adjusted<=level_fee:
            continue  # Do not invent a free exit when fees exceed sale proceeds.
        gross += take * adjusted
        fees += level_fee
        count += take
        remaining -= take
        if not remaining:
            break
    cash = gross + fees if buy else max(0, gross - fees)
    return Fill(count, gross, fees, cash, (gross // count) if count else 0)
