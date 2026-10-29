from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .models import Bar, FootprintSnapshot, ValueProfile


def compute_delta(footprint: FootprintSnapshot) -> float:
    """Delta = ask volume minus bid volume when real inputs exist.

    This is intentionally strict: no fabricated delta if the underlying data are absent.
    """
    if footprint is None:
        raise ValueError("No footprint snapshot available for delta calculation.")
    return float(footprint.ask_vol - footprint.bid_vol)


def compute_delta_ratio(footprint: FootprintSnapshot) -> float:
    if footprint is None:
        raise ValueError("No footprint snapshot available for delta ratio calculation.")
    denom = max(abs(footprint.bid_vol) + abs(footprint.ask_vol), 1e-9)
    return float((footprint.ask_vol - footprint.bid_vol) / denom)


def compute_vwap(bars: Sequence[Bar]) -> Optional[float]:
    """VWAP where volume semantics support a valid computation."""
    if not bars:
        return None
    total_volume = sum(float(b.volume) for b in bars)
    if total_volume <= 0:
        return None
    weighted = sum(float(b.close) * float(b.volume) for b in bars)
    return float(weighted / total_volume)


def compute_value_profile(bars: Sequence[Bar], value_area_percent: float = 0.70, tick_size: float = 0.01) -> ValueProfile:
    """Simple deterministic volume profile approximation.

    This is not a source fact about the proprietary NASDAQ profile model; it is a transparent research proxy.
    """
    if not bars:
        raise ValueError("Need bars to compute a value profile.")
    closes = np.asarray([float(b.close) for b in bars], dtype=float)
    price_range = float(np.max(closes) - np.min(closes))
    if price_range <= 0:
        price_range = tick_size
    bins = np.arange(np.min(closes), np.max(closes) + tick_size, tick_size)
    if len(bins) < 2:
        bins = np.array([np.min(closes), np.max(closes) + tick_size])
    values, edges = np.histogram(closes, bins=bins)
    poc = float(edges[np.argmax(values)] + tick_size / 2.0)
    cum = np.cumsum(values)
    total = max(float(cum[-1]), 1.0)
    target = total * value_area_percent
    lower_idx = int(np.searchsorted(cum, target * 0.5, side="left"))
    upper_idx = int(np.searchsorted(cum, target, side="right"))
    left = float(edges[lower_idx] + tick_size / 2.0)
    right = float(edges[min(upper_idx, len(edges) - 1)] + tick_size / 2.0)
    return ValueProfile(
        timestamp=bars[-1].timestamp,
        poc=poc,
        vah=max(left, right),
        val=min(left, right),
        left=min(left, right),
        right=max(left, right),
        volume_total=float(total),
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
    """Absorption hypothesis: strong aggression without enough price progress.

    This is an engineering assumption used only as a research indicator; it is not a proprietary rule.
    """
    if abs(delta) < requirement and abs(price_progress) < progress_threshold:
        return "buyer_absorption" if delta > 0 else "seller_absorption"
    if abs(delta) < requirement:
        return None
    if abs(price_progress) < progress_threshold:
        if delta > 0:
            return "buyer_absorption"
        return "seller_absorption"
    return None


def ohlcv_proxy_signal(bar: Bar, prev_close: Optional[float] = None, atr: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Experimental OHLCV proxy. It is labeled as a proxy and never treated as real order flow."""
    if prev_close is None:
        prev_close = bar.close
    if atr is None:
        atr = max(abs(bar.high - bar.low), 1e-9)
    impulse = abs(bar.close - prev_close) >= 1.5 * atr
    if not impulse:
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
