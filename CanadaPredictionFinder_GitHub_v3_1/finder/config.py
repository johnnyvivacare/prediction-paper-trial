from __future__ import annotations
import json
from pathlib import Path
from .core import digest

DEFAULT = {
    "scan_seconds": 60, "starting_cash_usd": 500, "port": 8765,
    "catalog_refresh_seconds": 900, "books_per_scan": 16, "max_catalog_markets": 240,
    "series": ["KXUNRATE", "KXCPI", "KXFED", "KXHIGHNY"],
    "discover_series": True, "max_series": 8,
    "categories": ["Economics", "Financials", "Climate and Weather", "Climate", "Weather"],
    "request_timeout_seconds": 8, "requests_per_second": 2,
    "fee_floor_usd_per_contract": 0.03, "slippage_usd_per_contract": 0.01,
    "max_quote_age_seconds": 90, "max_spread_usd": 0.06, "min_volume": 25,
    "depth_participation": 0.25, "min_edge_usd": 0.04,
    "max_event_risk_fraction": 0.02, "max_total_risk_fraction": 0.20,
    "max_category_risk_fraction": 0.06, "max_daily_loss_fraction": 0.03,
    "max_drawdown_fraction": 0.08, "max_entries_per_day": 6,
    "min_time_to_close_seconds": 1800, "max_holding_hours": 24,
    "enable_value_strategy": True, "enable_reversion_strategy": True,
    "reversion_window": 60, "reversion_zscore": 2.5, "reversion_haircut": 0.03,
    "min_entry_price_usd": 0.10, "max_entry_price_usd": 0.90,
    "stop_loss_fraction": 0.25, "retention_days": 30,
    "timezone": "America/Vancouver", "research_only": True,
    "execution": "paper", "require_canada_verification": False,
}


def validate(config: dict) -> dict:
    unknown = set(config) - set(DEFAULT)
    if unknown:
        raise ValueError("Unknown config settings: " + ", ".join(sorted(unknown)))
    c = {**DEFAULT, **config}
    if c["execution"] != "paper" or c["research_only"] is not True:
        raise ValueError("This release has no live trading mode")
    numeric_bounds = {
        "scan_seconds": (60, 3600), "starting_cash_usd": (50, 100000), "port": (1024,65535),
        "catalog_refresh_seconds": (300,86400), "books_per_scan": (1,40), "max_catalog_markets": (1,1000),
        "max_series": (1,20), "request_timeout_seconds": (2,30), "requests_per_second": (0.2,3),
        "fee_floor_usd_per_contract": (0.01,0.20), "slippage_usd_per_contract": (0,0.10),
        "max_quote_age_seconds": (10,180), "max_spread_usd": (0.01,0.20), "min_volume": (0,1000000),
        "depth_participation": (0.01,0.5), "min_edge_usd": (0.02,0.50),
        "max_event_risk_fraction": (0.001,0.02), "max_total_risk_fraction": (0.01,0.30),
        "max_category_risk_fraction": (0.001,0.10), "max_daily_loss_fraction": (0.005,0.05),
        "max_drawdown_fraction": (0.01,0.15), "max_entries_per_day": (1,20),
        "min_time_to_close_seconds": (300,604800), "max_holding_hours": (1,168),
        "reversion_window": (30,360), "reversion_zscore": (1.5,5), "reversion_haircut": (0.01,0.20),
        "min_entry_price_usd": (0.01,0.40), "max_entry_price_usd": (0.60,0.99),
        "stop_loss_fraction": (0.05,0.5), "retention_days": (7,365),
    }
    import math
    for k,(low,high) in numeric_bounds.items():
        v=c[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{k} must be within {low}..{high}")
        if isinstance(DEFAULT[k],int) and not isinstance(v,int):
            raise ValueError(k+" must be an integer")
    for k in ("discover_series","enable_value_strategy","enable_reversion_strategy","require_canada_verification"):
        if not isinstance(c[k],bool):
            raise ValueError(k+" must be true or false")
    for k in ("series","categories"):
        if not isinstance(c[k],list) or len(c[k])>100 or any(not isinstance(x,str) or not x or len(x)>100 for x in c[k]):
            raise ValueError("Invalid "+k)
    if c["timezone"] != "America/Vancouver":
        raise ValueError("This release uses the agreed America/Vancouver risk day")
    return c


def load(path: Path) -> dict:
    return validate(json.loads(path.read_text()) if path.exists() else {})


def fingerprint(config: dict) -> str:
    # Exclude presentation, storage retention and network settings; freeze strategy/risk settings.
    ignore={"port","retention_days","request_timeout_seconds","requests_per_second","catalog_refresh_seconds"}
    return digest({k:v for k,v in config.items() if k not in ignore})
