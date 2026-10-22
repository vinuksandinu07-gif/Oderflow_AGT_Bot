"""Synthetic data builders for the test-suite (no real market data involved)."""
from __future__ import annotations

import numpy as np
import pandas as pd

TICK = 0.1
BASE = pd.Timestamp("2026-01-05 08:00", tz="UTC")
PERIOD = pd.Timedelta("15min")


def ts(i: int) -> pd.Timestamp:
    return BASE + i * PERIOD


def bar(i, o, h, l, c, v=1000.0) -> dict:
    return dict(timestamp=ts(i), open=o, high=h, low=l, close=c, volume=v)


def fp(p0: float, bid, ask) -> pd.DataFrame:
    """Footprint rows starting at price p0 going up one tick per row."""
    prices = [round(p0 + k * TICK, 10) for k in range(len(bid))]
    return pd.DataFrame({"price": prices, "bid_vol": bid, "ask_vol": ask})


def bullish_fp(p0: float) -> pd.DataFrame:
    """5 levels; buying imbalances on levels 1..3 (ask 40 vs bid 5 below) -> 3-level BUY stack."""
    return fp(p0, bid=[5] * 5, ask=[5, 40, 40, 40, 5])


def bearish_fp(p0: float) -> pd.DataFrame:
    """5 levels; selling imbalances on levels 1..3 (bid 40 vs ask 5 above) -> 3-level SELL stack."""
    return fp(p0, bid=[5, 40, 40, 40, 5], ask=[5] * 5)


# --- canonical scenarios -------------------------------------------------------
# Bullish stack zone = [2000.1, 2000.3]
def bull_bar0():
    return bar(0, 2000.0, 2003.0, 2000.0, 2002.8), bullish_fp(2000.0)

def bull_departure(i=1):
    return bar(i, 2002.8, 2003.5, 2002.5, 2002.6), None

def bull_retest_confirmed(i=2):
    # dips into the zone (low 2000.2), closes back above it with a bullish candle
    return bar(i, 2002.4, 2002.9, 2000.2, 2002.8), None

# Bearish stack zone = [2000.1, 2000.3]
def bear_bar0():
    return bar(0, 2000.4, 2000.4, 1997.2, 1997.4), bearish_fp(2000.0)

def bear_departure(i=1):
    return bar(i, 1997.4, 1997.9, 1996.8, 1997.6), None

def bear_retest_confirmed(i=2):
    return bar(i, 1997.8, 2000.2, 1997.1, 1997.2), None


def feed(engine, items):
    """items: list of (bar_dict, footprint_or_None). Returns all signals emitted, in order."""
    out = []
    for b, f in items:
        out.extend(engine.on_bar(b, f))
    return out


def random_market(n=300, seed=7, start=2000.0):
    """Random walk bars on the tick grid with random footprints (some stacked)."""
    rng = np.random.default_rng(seed)
    price = start
    bars, fps = [], []
    for i in range(n):
        o = price
        move = rng.normal(0, 0.8)
        c = round(max(o + move, 10.0), 1)
        h = round(max(o, c) + abs(rng.normal(0, 0.3)), 1)
        l = round(min(o, c) - abs(rng.normal(0, 0.3)), 1)
        bars.append(dict(timestamp=ts(i), open=round(o, 1), high=h, low=l, close=c,
                         volume=float(rng.integers(500, 3000))))
        prices = np.round(np.arange(l, h + 1e-9, TICK), 1)
        bid = rng.integers(0, 40, len(prices)).astype(float)
        ask = rng.integers(0, 40, len(prices)).astype(float)
        direction = 1 if c >= o else -1                     # push flow in the bar's direction
        if direction > 0:
            ask = ask * 2.0; bid = np.minimum(bid, 12.0)
        else:
            bid = bid * 2.0; ask = np.minimum(ask, 12.0)
        fps.append(pd.DataFrame({"timestamp": ts(i), "price": prices, "bid_vol": bid, "ask_vol": ask}))
        price = c
    return pd.DataFrame(bars), pd.concat(fps, ignore_index=True)
