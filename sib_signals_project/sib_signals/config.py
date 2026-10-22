"""Configuration for the Retest-of-a-Stacked-Imbalance signal engine.

Every number here is an *initial test parameter*, not a proven optimum.
All configs are frozen dataclasses; use ``dataclasses.replace`` to override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


class RetestMode(str, Enum):
    TOUCH = "touch"                          # bar range overlaps the zone
    DEPTH = "depth"                          # bar penetrates >= depth_fraction of the zone
    ENTER_AND_CLOSE_OUT = "enter_and_close_out"  # touches the zone AND closes back outside it


class InvalidationMode(str, Enum):
    CLOSE = "close"   # a bar CLOSING beyond the far edge invalidates the zone
    WICK = "wick"     # any bar trading beyond the far edge invalidates the zone


class DataMode(str, Enum):
    FOOTPRINT = "footprint"        # genuine bid/ask volume per price level (required for real imbalances)
    OHLCV_PROXY = "ohlcv_proxy"    # APPROXIMATE price-action proxy; NOT genuine order flow


@dataclass(frozen=True)
class ImbalanceConfig:
    ratio: float = 3.0                  # 3:1 diagonal ratio
    min_stack_levels: int = 3           # consecutive imbalanced levels required
    min_level_volume: float = 10.0      # in the volume units of your data; PLACEHOLDER, tune per instrument
    zero_denominator_counts: bool = True  # ask>=min_vol vs bid==0 counts as an imbalance

    def __post_init__(self):
        if self.ratio <= 1:
            raise ValueError("imbalance ratio must be > 1")
        if self.min_stack_levels < 2:
            raise ValueError("min_stack_levels must be >= 2")
        if self.min_level_volume < 0:
            raise ValueError("min_level_volume must be >= 0")


@dataclass(frozen=True)
class ProxyConfig:
    """Approximate stand-in for stacked imbalances when only OHLCV exists.

    An 'impulse candle' (large body, close near the extreme, high volume) is
    assumed to contain aggressive one-sided flow. The zone is the origin-side
    portion of its body. This is a heuristic, NOT order-flow detection.
    """
    impulse_atr_mult: float = 1.5
    min_close_location: float = 0.7     # close must sit in the top/bottom 30% of the range
    volume_mult: float = 1.5            # volume >= mult * average of prior bars; 0 disables
    zone_body_fraction: float = 0.5     # zone = first X of the body, measured from the open
    atr_period: int = 14
    volume_period: int = 20


@dataclass(frozen=True)
class RetestConfig:
    mode: RetestMode = RetestMode.TOUCH
    depth_fraction: float = 0.25        # used by RetestMode.DEPTH (0 = touch the edge, 1 = reach far edge)
    require_departure: bool = True      # price must first leave the zone before a "return" counts
    max_zone_age_bars: int = 50         # untested zones expire this many bars after detection
    confirm_window_bars: int = 2        # confirmation allowed on the retest bar + this many bars after
    max_retests: int = 1                # failed (unconfirmed) retests tolerated before the zone is exhausted
    invalidation_mode: InvalidationMode = InvalidationMode.CLOSE
    invalidation_buffer_ticks: float = 0.0

    def __post_init__(self):
        if not 0 <= self.depth_fraction <= 1:
            raise ValueError("depth_fraction must be in [0, 1]")
        if self.max_zone_age_bars < 1 or self.confirm_window_bars < 0 or self.max_retests < 1:
            raise ValueError("invalid retest window settings")


@dataclass(frozen=True)
class CandleFilter:
    enabled: bool = True
    close_location: str = "outside"     # 'outside' | 'mid' | 'any'
    def __post_init__(self):
        if self.close_location not in ("outside", "mid", "any"):
            raise ValueError("close_location must be 'outside', 'mid' or 'any'")


@dataclass(frozen=True)
class DeltaFilter:
    enabled: bool = False               # needs genuine footprint data on the confirmation bar
    min_abs_delta: float = 0.0          # LONG needs delta > this; SHORT needs delta < -this


@dataclass(frozen=True)
class StructureFilter:
    enabled: bool = False               # BOS: close beyond the last CONFIRMED swing
    swing_n: int = 2
    lookback_bars: int = 100


@dataclass(frozen=True)
class HTFFilter:
    enabled: bool = False               # close of last COMPLETED HTF candle vs its EMA
    rule: str = "4h"                    # fixed-length pandas offset, e.g. '1h', '4h'
    ema_period: int = 20


@dataclass(frozen=True)
class RRFilter:
    enabled: bool = False
    min_rr: float = 1.5


@dataclass(frozen=True)
class SessionFilter:
    enabled: bool = False
    windows_utc: Tuple[Tuple[int, int], ...] = ((7, 16),)   # [start_hour, end_hour) in UTC; may wrap midnight


@dataclass(frozen=True)
class FilterConfig:
    candle: CandleFilter = field(default_factory=CandleFilter)
    delta: DeltaFilter = field(default_factory=DeltaFilter)
    structure: StructureFilter = field(default_factory=StructureFilter)
    htf: HTFFilter = field(default_factory=HTFFilter)
    rr: RRFilter = field(default_factory=RRFilter)
    session: SessionFilter = field(default_factory=SessionFilter)
    on_missing_data: str = "fail"       # 'fail' = block the signal, 'skip' = ignore that filter (reported)
    def __post_init__(self):
        if self.on_missing_data not in ("fail", "skip"):
            raise ValueError("on_missing_data must be 'fail' or 'skip'")


@dataclass(frozen=True)
class RiskConfig:
    stop_buffer_ticks: float = 2.0      # beyond the zone edge / retest extreme
    tp_mode: str = "rr"                 # 'rr' | 'swing' | 'none'
    target_rr: float = 2.0
    swing_n: int = 2
    swing_lookback: int = 100
    def __post_init__(self):
        if self.tp_mode not in ("rr", "swing", "none"):
            raise ValueError("tp_mode must be 'rr', 'swing' or 'none'")


@dataclass(frozen=True)
class SignalConfig:
    instrument: str = "XAUUSD"
    tick_size: float = 0.1              # price increment of the footprint grid (COMEX GC = 0.1)
    data_mode: DataMode = DataMode.FOOTPRINT
    bar_period: str = "15min"           # bar timestamps are bar OPEN times
    max_signals_per_zone: int = 1
    conflict_policy: str = "skip_both"  # LONG vs SHORT on the same bar: skip_both | prefer_newest | prefer_larger_stack
    history_limit: int = 5000
    imbalance: ImbalanceConfig = field(default_factory=ImbalanceConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    retest: RetestConfig = field(default_factory=RetestConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def __post_init__(self):
        if self.tick_size <= 0:
            raise ValueError("tick_size must be > 0")
        if self.conflict_policy not in ("skip_both", "prefer_newest", "prefer_larger_stack"):
            raise ValueError("invalid conflict_policy")
        if self.max_signals_per_zone < 1:
            raise ValueError("max_signals_per_zone must be >= 1")
