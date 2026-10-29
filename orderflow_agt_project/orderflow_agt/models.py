from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def ensure_utc(value: Any) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        ts = value
    else:
        ts = pd.Timestamp(value)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalStatus(str, Enum):
    EMITTED = "emitted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Bar:
    timestamp: pd.Timestamp
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
    timestamp: pd.Timestamp
    bid: float
    ask: float
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Trade:
    timestamp: pd.Timestamp
    price: float
    size: float
    side: str
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class FootprintSnapshot:
    timestamp: pd.Timestamp
    bid_vol: float
    ask_vol: float
    price_levels: Optional[List[float]] = None
    symbol: str = "NASDAQ100"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)

    @property
    def delta(self) -> float:
        return self.ask_vol - self.bid_vol


@dataclass
class ValueProfile:
    timestamp: pd.Timestamp
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
    timestamp: pd.Timestamp
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
    timestamp: pd.Timestamp
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
    raw: Optional[Dict[str, Any]] = None

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
    timestamp: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.utcnow().tz_localize("UTC"))

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class Fill:
    order_id: str
    timestamp: pd.Timestamp
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
    timestamp: pd.Timestamp
    strategy_id: str = "unknown"

    def __post_init__(self):
        self.timestamp = ensure_utc(self.timestamp)


@dataclass
class MarketContext:
    bar: Bar
    footprint: Optional[FootprintSnapshot] = None
    profile: Optional[ValueProfile] = None
    effort_boxes: List[EffortBox] = field(default_factory=list)
    vwap: Optional[float] = None
    delta: Optional[float] = None
    absorption: Optional[str] = None
