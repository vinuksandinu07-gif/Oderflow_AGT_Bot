"""Core data models: bars, zones, signals, history buffer."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class DataValidationError(ValueError):
    """Structural input problem (missing columns, out-of-order timestamps...)."""


class ZoneDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ZoneStatus(str, Enum):
    VALID = "valid"              # untested (or waiting for a fresh retest)
    RETESTED = "retested"        # price interacted with it; inside the confirmation window
    TRIGGERED = "triggered"      # produced its allowed number of signals
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"      # retested but never confirmed; no retests left
    SUPERSEDED = "superseded"    # overlapped a stronger same-direction zone that signalled


TERMINAL = frozenset({ZoneStatus.TRIGGERED, ZoneStatus.INVALIDATED, ZoneStatus.EXPIRED,
                      ZoneStatus.EXHAUSTED, ZoneStatus.SUPERSEDED})


class DataSource(str, Enum):
    FOOTPRINT = "footprint"
    PRICE_ACTION_PROXY = "price_action_proxy"


@dataclass(frozen=True)
class StackedImbalance:
    direction: ZoneDirection
    lower: float
    upper: float
    n_levels: int
    ask_volume: Optional[float]      # summed over the stacked levels (None for proxy zones)
    bid_volume: Optional[float]
    source: DataSource


@dataclass
class Bar:
    timestamp: pd.Timestamp          # bar OPEN time
    open: float
    high: float
    low: float
    close: float
    volume: float
    idx: int
    bar_delta: Optional[float] = None   # sum(ask) - sum(bid) over the bar, if footprint supplied
    has_footprint: bool = False


@dataclass
class Zone:
    zone_id: str
    direction: ZoneDirection
    lower: float
    upper: float
    detected_at: pd.Timestamp        # OPEN time of the bar whose close revealed the stack
    detected_idx: int
    n_levels: int
    source: DataSource
    ask_volume: Optional[float] = None
    bid_volume: Optional[float] = None
    stack_delta: Optional[float] = None
    bar_delta: Optional[float] = None
    status: ZoneStatus = ZoneStatus.VALID
    departed: bool = False
    retest_count: int = 0
    retest_idx: Optional[int] = None
    retest_at: Optional[pd.Timestamp] = None
    extreme_since_retest: Optional[float] = None
    signals_emitted: int = 0
    events: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def height(self) -> float:
        return self.upper - self.lower

    @property
    def mid(self) -> float:
        return (self.upper + self.lower) / 2.0

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    def set_status(self, status: ZoneStatus, ts: pd.Timestamp, note: str = "") -> None:
        self.status = status
        self.events.append((str(ts), f"{status.value}{': ' + note if note else ''}"))


@dataclass(frozen=True)
class TradeLevels:
    entry: float
    invalidation: float
    stop_loss: float
    take_profit: Optional[float]
    risk_reward: Optional[float]


@dataclass(frozen=True)
class Signal:
    """A *signal*, not an order. Nothing here implies a fill."""
    signal_id: str
    timestamp: pd.Timestamp            # time the signal became known (confirmation bar CLOSE)
    bar_timestamp: pd.Timestamp        # OPEN time of the confirmation bar
    instrument: str
    direction: Direction
    zone_id: str
    zone_lower: float
    zone_upper: float
    entry_price: float                 # reference only: close of the confirmation bar
    invalidation_level: float
    stop_loss: float
    take_profit: Optional[float]
    risk_reward: Optional[float]
    data_source: DataSource
    conditions_satisfied: Tuple[str, ...]
    conditions_skipped: Tuple[str, ...]
    explanation: str

    @property
    def is_proxy(self) -> bool:
        return self.data_source == DataSource.PRICE_ACTION_PROXY

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        d["data_source"] = self.data_source.value
        d["timestamp"] = str(self.timestamp)
        d["bar_timestamp"] = str(self.bar_timestamp)
        d["conditions_satisfied"] = list(self.conditions_satisfied)
        d["conditions_skipped"] = list(self.conditions_skipped)
        return d


class History:
    """Rolling buffer of PAST and CURRENT bars only (no future data can enter)."""

    def __init__(self, limit: int = 5000):
        self.limit = max(int(limit), 10)
        self.ts: List[pd.Timestamp] = []
        self.o: List[float] = []
        self.h: List[float] = []
        self.l: List[float] = []
        self.c: List[float] = []
        self.v: List[float] = []

    def append(self, b: Bar) -> None:
        self.ts.append(b.timestamp); self.o.append(b.open); self.h.append(b.high)
        self.l.append(b.low); self.c.append(b.close); self.v.append(b.volume)
        if len(self.c) > self.limit * 2:          # amortised trimming
            cut = len(self.c) - self.limit
            for name in ("ts", "o", "h", "l", "c", "v"):
                setattr(self, name, getattr(self, name)[cut:])

    def __len__(self) -> int:
        return len(self.c)

    def arrays(self, n: Optional[int] = None) -> Dict[str, np.ndarray]:
        sl = slice(-n, None) if n else slice(None)
        return {k: np.asarray(getattr(self, k)[sl], dtype=float) for k in ("o", "h", "l", "c", "v")}

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame({"open": self.o, "high": self.h, "low": self.l, "close": self.c,
                             "volume": self.v}, index=pd.DatetimeIndex(self.ts))
