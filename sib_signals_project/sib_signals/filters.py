"""Independent, switchable confirmation filters.

Each filter is enabled/disabled through ``SignalConfig.filters``; the core
detection logic never changes. A filter returns one of: passed, failed, skipped
(only when ``on_missing_data='skip'`` and the data needed is genuinely absent).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import SignalConfig
from .models import Bar, History, TradeLevels, Zone, ZoneDirection

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class FilterResult:
    passed: bool
    satisfied: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


# ----------------------------- helpers ---------------------------------------
def confirmed_swings(arr: np.ndarray, n: int, kind: str, lookback: int) -> List[float]:
    """Swing highs/lows, most recent first. A swing at position j is only
    'confirmed' once n later bars exist, so this can never repaint."""
    arr = np.asarray(arr, dtype=float)[-lookback:]
    L = len(arr)
    out: List[float] = []
    for j in range(L - 1 - n, n - 1, -1):
        left, right = arr[j - n:j], arr[j + 1:j + n + 1]
        if kind == "high":
            if arr[j] > left.max() and arr[j] >= right.max():
                out.append(float(arr[j]))
        else:
            if arr[j] < left.min() and arr[j] <= right.min():
                out.append(float(arr[j]))
    return out


def htf_bias(history: History, close_time: pd.Timestamp, bar_period: pd.Timedelta,
             rule: str, ema_period: int) -> Optional[int]:
    """+1 / -1 from the last COMPLETED higher-timeframe close vs its EMA; None if not enough data.

    A higher-timeframe bucket counts only if its end <= the current bar's close
    time, so the still-forming HTF candle is never used.
    """
    frame = history.frame()
    if frame.empty:
        return None
    htf_td = pd.Timedelta(rule)
    closes = frame["close"].resample(rule).last().dropna()
    complete = closes[closes.index + htf_td <= close_time]
    if len(complete) < ema_period:
        return None
    ema = complete.ewm(span=ema_period, adjust=False).mean()
    diff = complete.iloc[-1] - ema.iloc[-1]
    return 1 if diff > 0 else (-1 if diff < 0 else 0)


def _in_session(close_time: pd.Timestamp, windows: Tuple[Tuple[int, int], ...]) -> bool:
    t = close_time.tz_convert("UTC") if close_time.tzinfo is not None else close_time
    h = t.hour + t.minute / 60.0
    for start, end in windows:
        if start <= end:
            if start <= h < end:
                return True
        elif h >= start or h < end:      # wraps midnight
            return True
    return False


# ----------------------------- main entry ------------------------------------
def confirm_entry(zone: Zone, bar: Bar, history: History, close_time: pd.Timestamp,
                  levels: TradeLevels, cfg: SignalConfig) -> FilterResult:
    """Evaluate every ENABLED filter. All enabled filters must pass."""
    f = cfg.filters
    long = zone.direction == ZoneDirection.BULLISH
    res = FilterResult(passed=True)
    missing_ok = f.on_missing_data == "skip"

    def record(name: str, outcome: str) -> None:
        if outcome == PASS:
            res.satisfied.append(name)
        elif outcome == SKIP:
            res.skipped.append(name)
        else:
            res.failed.append(name)

    def no_data(name: str) -> None:
        record(name, SKIP if missing_ok else FAIL)

    # 1. candle-close confirmation
    if f.candle.enabled:
        directional = bar.close > bar.open if long else bar.close < bar.open
        loc = f.candle.close_location
        if loc == "outside":
            located = bar.close > zone.upper if long else bar.close < zone.lower
        elif loc == "mid":
            located = bar.close >= zone.mid if long else bar.close <= zone.mid
        else:
            located = True
        record(f"candle_close({loc})", PASS if directional and located else FAIL)

    # 2. volume-delta confirmation (genuine footprint data only)
    if f.delta.enabled:
        if bar.bar_delta is None:
            no_data("volume_delta[no_footprint]")
        else:
            ok = bar.bar_delta > f.delta.min_abs_delta if long else bar.bar_delta < -f.delta.min_abs_delta
            record("volume_delta", PASS if ok else FAIL)

    # 3. market structure: break of the last confirmed swing
    if f.structure.enabled:
        a = history.arrays(f.structure.lookback_bars)
        swings = confirmed_swings(a["h" if long else "l"], f.structure.swing_n,
                                  "high" if long else "low", f.structure.lookback_bars)
        if not swings:
            no_data("structure_bos[no_confirmed_swing]")
        else:
            ok = bar.close > swings[0] if long else bar.close < swings[0]
            record("structure_bos", PASS if ok else FAIL)

    # 4. higher-timeframe bias
    if f.htf.enabled:
        bias = htf_bias(history, close_time, pd.Timedelta(cfg.bar_period), f.htf.rule, f.htf.ema_period)
        if bias is None:
            no_data(f"htf_bias({f.htf.rule})[insufficient_history]")
        else:
            record(f"htf_bias({f.htf.rule})", PASS if (bias > 0 if long else bias < 0) else FAIL)

    # 5. minimum risk-to-reward
    if f.rr.enabled:
        if levels.risk_reward is None:
            no_data("min_rr[no_target]")
        else:
            record(f"min_rr>={f.rr.min_rr}", PASS if levels.risk_reward >= f.rr.min_rr else FAIL)

    # 6. session / trading hours (judged at the confirmation bar's close time)
    if f.session.enabled:
        record("session", PASS if _in_session(close_time, f.session.windows_utc) else FAIL)

    res.passed = not res.failed
    return res
