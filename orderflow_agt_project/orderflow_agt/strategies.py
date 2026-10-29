from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import numpy as np

from .models import Bar, FootprintSnapshot, ValueProfile


def compute_delta(footprint: Optional[FootprintSnapshot]) -> float:
    """Delta = ask volume minus bid volume when real inputs exist."""
    if footprint is None:
        raise ValueError("No footprint snapshot for delta calculation.")
    return float(footprint.ask_vol - footprint.bid_vol)


def compute_delta_ratio(footprint: Optional[FootprintSnapshot]) -> float:
    if footprint is None:
        raise ValueError("No footprint snapshot for delta ratio calculation.")
    denom = max(abs(footprint.bid_vol) + abs(footprint.ask_vol), 1e-9)
    return float((footprint.ask_vol - footprint.bid_vol) / denom)


def compute_vwap(bars: Sequence[Bar]) -> Optional[float]:
    if not bars:
        return None
    total_volume = sum(float(b.volume) for b in bars)
    if total_volume <= 0:
        return None
    weighted = sum(float(b.close) * float(b.volume) for b in bars)
    return float(weighted / total_volume)


def compute_value_profile(bars: Sequence[Bar], value_area_percent: float = 0.70, tick_size: float = 0.01) -> ValueProfile:
    """Simple volume profile approximation used as a transparent research proxy.

    This is not the source's proprietary profile implementation.
    """
    if not bars:
        raise ValueError("Need bars to compute a value profile.")
    closes = np.asarray([float(b.close) for b in bars], dtype=float)
    lo = float(closes.min())
    hi = float(closes.max())
    if hi <= lo:
        hi = lo + tick_size
    bins = np.arange(lo, hi + tick_size, tick_size)
    if len(bins) < 2:
        bins = np.array([lo, hi + tick_size])
    counts, edges = np.histogram(closes, bins=bins)
    poc = float(edges[np.argmax(counts)] + (tick_size / 2.0))
    cumulative = np.cumsum(counts)
    total_volume = float(cumulative[-1]) if len(cumulative) > 0 else 0.0
    if total_volume <= 0:
        total_volume = 1.0
    target = total_volume * value_area_percent
    idx = int(np.searchsorted(cumulative, target, side="left"))
    left = float(edges[idx] + tick_size / 2.0) if idx < len(edges) else float(edges[-1])
    right = float(edges[min(len(edges) - 1, idx + 1)] + tick_size / 2.0)
    return ValueProfile(
        timestamp=bars[-1].timestamp,
        poc=poc,
        vah=max(left, right),
        val=min(left, right),
        left=min(left, right),
        right=max(left, right),
        volume_total=total_volume,
    )


def compute_value_migration(prev: Optional[ValueProfile], curr: Optional[ValueProfile]) -> float:
    if prev is None or curr is None:
        return 0.0
    return float(curr.poc - prev.poc)


def classify_value_context(prev: Optional[ValueProfile], curr: Optional[ValueProfile]) -> str:
    migration = compute_value_migration(prev, curr)
    if migration > 0:
        return "bullish_drift"
    if migration < 0:
        return "bearish_drift"
    return "balanced_auction"


def detect_absorption(delta: float, price_progress: float, requirement: float = 1.5, progress_threshold: float = 0.2) -> Optional[str]:
    """Absorption hypothesis: large aggression without enough price movement.

    This is an engineering assumption, not a proprietary source rule.
    """
    if abs(delta) < requirement and abs(price_progress) < progress_threshold:
        return "buyer_absorption" if delta > 0 else "seller_absorption"
    return None


def ohlcv_proxy_signal(bar: Bar, prev_close: Optional[float] = None, atr: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Experimental OHLCV proxy; never presented as real order-flow data."""
    if prev_close is None:
        prev_close = bar.close
    if atr is None:
        atr = max(abs(bar.high - bar.low), 1e-9)
    if abs(bar.close - prev_close) < 1.5 * atr:
        return None
    side = "LONG" if bar.close >= prev_close else "SHORT"
    return {
        "strategy_id": "ohlcv_proxy",
        "side": side,
        "timestamp": bar.timestamp,
        "delta": None,
        "label": "EXPERIMENTAL_PROXY",
        "note": "OHLCV proxy; not equivalent to real order-flow data.",
    }


__all__ = [
    "compute_delta",
    "compute_delta_ratio",
    "compute_vwap",
    "compute_value_profile",
    "compute_value_migration",
    "classify_value_context",
    "detect_absorption",
    "ohlcv_proxy_signal",
]
