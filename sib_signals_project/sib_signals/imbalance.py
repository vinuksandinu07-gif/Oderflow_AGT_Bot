"""Stacked-imbalance detection.

GENUINE detection requires a footprint: bid and ask volume at every price level.
`detect_proxy_stack` is an APPROXIMATION from OHLCV and is always labelled as such.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import ImbalanceConfig, ProxyConfig
from .models import (DataSource, DataValidationError, StackedImbalance, ZoneDirection)

FOOTPRINT_COLUMNS = ("price", "bid_vol", "ask_vol")
_ROUND = 10  # decimals used to kill float drift on tick-grid prices


def level_to_price(level: int, tick_size: float) -> float:
    return round(level * tick_size, _ROUND)


def clean_footprint(fp: Optional[pd.DataFrame], tick_size: float,
                    price_range: Optional[Tuple[float, float]] = None
                    ) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """Validate a one-bar footprint and return a dense integer-level grid.

    Input columns: price, bid_vol, ask_vol (long form, one row per price level;
    duplicates are summed). Returns (grid, issues). ``grid`` is indexed by integer
    tick level, contiguous from the lowest to the highest traded level (empty levels
    filled with 0). ``grid`` is None when nothing usable remains.
    Structural errors (missing columns) raise DataValidationError; bad *rows* are
    dropped and reported in ``issues``.
    """
    issues: List[str] = []
    if fp is None or len(fp) == 0:
        return None, ["footprint_empty"]
    missing = [c for c in FOOTPRINT_COLUMNS if c not in fp.columns]
    if missing:
        raise DataValidationError(f"footprint missing columns: {missing}")

    df = fp[list(FOOTPRINT_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    ok = np.isfinite(df.to_numpy(dtype=float)).all(axis=1) & (df["bid_vol"] >= 0) & (df["ask_vol"] >= 0)
    if not ok.all():
        issues.append(f"footprint_bad_rows_dropped:{int((~ok).sum())}")
        df = df[ok]
    if price_range is not None and len(df):
        lo, hi = price_range
        inside = (df["price"] >= lo - tick_size) & (df["price"] <= hi + tick_size)
        if not inside.all():
            issues.append(f"footprint_rows_outside_bar_range_dropped:{int((~inside).sum())}")
            df = df[inside]
    if df.empty:
        return None, issues + ["footprint_empty_after_cleaning"]

    levels = np.rint(df["price"].to_numpy() / tick_size).astype(np.int64)
    grid = (pd.DataFrame({"level": levels, "bid_vol": df["bid_vol"].to_numpy(),
                          "ask_vol": df["ask_vol"].to_numpy()})
            .groupby("level").sum().sort_index())
    full = np.arange(grid.index.min(), grid.index.max() + 1)
    return grid.reindex(full, fill_value=0.0), issues


def _runs(mask: np.ndarray, min_len: int) -> List[Tuple[int, int]]:
    """Inclusive (start, end) positions of True-runs of length >= min_len."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out


def detect_stacked_imbalances(grid: pd.DataFrame, cfg: ImbalanceConfig,
                              tick_size: float) -> List[StackedImbalance]:
    """Find stacked diagonal imbalances in a cleaned footprint grid.

    Buying imbalance at level L : ask[L]   >= ratio * bid[L-1]
    Selling imbalance at level L: bid[L]   >= ratio * ask[L+1]
    A level also needs the numerator >= min_level_volume (and > 0). The bottom
    level cannot be tested for buying and the top level cannot be tested for
    selling (no adjacent level inside the bar), so they never qualify.
    """
    if grid is None or len(grid) < cfg.min_stack_levels + 1:
        return []
    ask = grid["ask_vol"].to_numpy(dtype=float)
    bid = grid["bid_vol"].to_numpy(dtype=float)
    n = len(grid)
    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)

    num, den = ask[1:], bid[:-1]
    cond = (num >= cfg.ratio * den) & (num >= cfg.min_level_volume) & (num > 0)
    if not cfg.zero_denominator_counts:
        cond &= den > 0
    buy[1:] = cond

    num, den = bid[:-1], ask[1:]
    cond = (num >= cfg.ratio * den) & (num >= cfg.min_level_volume) & (num > 0)
    if not cfg.zero_denominator_counts:
        cond &= den > 0
    sell[:-1] = cond

    base = int(grid.index[0])
    stacks: List[StackedImbalance] = []
    for mask, direction in ((buy, ZoneDirection.BULLISH), (sell, ZoneDirection.BEARISH)):
        for s, e in _runs(mask, cfg.min_stack_levels):
            stacks.append(StackedImbalance(
                direction=direction,
                lower=level_to_price(base + s, tick_size),
                upper=level_to_price(base + e, tick_size),
                n_levels=e - s + 1,
                ask_volume=float(ask[s:e + 1].sum()),
                bid_volume=float(bid[s:e + 1].sum()),
                source=DataSource.FOOTPRINT))
    return stacks


def detect_proxy_stack(o: float, h: float, l: float, c: float, volume: float,
                       atr: Optional[float], avg_volume: Optional[float],
                       cfg: ProxyConfig, tick_size: float) -> Optional[StackedImbalance]:
    """APPROXIMATE zone from an impulse candle. NOT genuine order flow.

    Needs: body >= impulse_atr_mult * ATR, close near the extreme, and (if
    volume_mult > 0) volume >= volume_mult * prior average. Returns None if
    any needed input is unavailable rather than guessing.
    """
    if atr is None or not np.isfinite(atr) or atr <= 0 or h <= l:
        return None
    if cfg.volume_mult > 0:
        if avg_volume is None or not np.isfinite(avg_volume) or not np.isfinite(volume):
            return None
        if volume < cfg.volume_mult * avg_volume:
            return None
    body = abs(c - o)
    if body < cfg.impulse_atr_mult * atr:
        return None
    loc = (c - l) / (h - l)
    if c > o and loc >= cfg.min_close_location:
        lo, hi, direction = o, o + cfg.zone_body_fraction * body, ZoneDirection.BULLISH
    elif c < o and (1 - loc) >= cfg.min_close_location:
        lo, hi, direction = o - cfg.zone_body_fraction * body, o, ZoneDirection.BEARISH
    else:
        return None
    lo, hi = round(lo, _ROUND), round(hi, _ROUND)
    return StackedImbalance(direction, lo, hi, max(1, int(round((hi - lo) / tick_size))),
                            None, None, DataSource.PRICE_ACTION_PROXY)
