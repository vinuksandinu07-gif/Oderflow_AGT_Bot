from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def ensure_utc(ts: Any) -> pd.Timestamp:
    if isinstance(ts, pd.Timestamp):
        out = ts
    else:
        out = pd.Timestamp(ts)
    if out.tz is None:
        out = out.tz_localize("UTC")
    return out.tz_convert("UTC")


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Bar:
    timestamp: Any
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Quote:
    timestamp: Any
    bid: float
    ask: float
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Trade:
    timestamp: Any
    price: float
    size: float
    side: str
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class FootprintSnapshot:
    timestamp: Any
    bid_vol: float
    ask_vol: float
    price_levels: Optional[List[float]] = None
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)

    @property
    def delta(self) -> float:
        return float(self.ask_vol - self.bid_vol)


@dataclass
class ValueProfile:
    timestamp: Any
    poc: float
    vah: float
    val: float
    left: float
    right: float
    volume_total: float = 0.0

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class EffortBox:
    timestamp: Any
    side: str
    lower: float
    upper: float
    strength: float
    source: str = "external"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Signal:
    strategy_id: str
    side: Side
    timestamp: Any
    entry_price: float
    stop_price: float
    target_price: Optional[float]
    invalidation_level: float
    source_refs: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    entry_rationale: str = ""
    stop_rationale: str = ""
    exit_policy: str = "trail_stop"
    audit_trail: List[str] = field(default_factory=list)
    confidence: float = 0.0
    data_quality: str = "real"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Order:
    order_id: str
    strategy_id: str
    side: Side
    quantity: float
    price: float
    status: str = "submitted"
    order_type: str = "market"
    timestamp: Any = field(default_factory=lambda: pd.Timestamp.utcnow().tz_localize("UTC"))

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Fill:
    order_id: str
    timestamp: Any
    price: float
    quantity: float
    fees: float = 0.0
    slippage: float = 0.0

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Position:
    position_id: str
    side: Side
    quantity: float
    entry_price: float
    stop_price: float
    target_price: Optional[float]
    timestamp: Any
    strategy_id: str = "unknown"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


__all__ = [
    "Bar",
    "Quote",
    "Trade",
    "FootprintSnapshot",
    "ValueProfile",
    "EffortBox",
    "Signal",
    "Order",
    "Fill",
    "Position",
    "Side",
    "ensure_utc",
]
