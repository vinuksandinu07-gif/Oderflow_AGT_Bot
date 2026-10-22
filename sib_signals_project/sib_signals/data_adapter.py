"""Aggregate classified executed trades into OHLCV bars and footprint levels.

Requires trade prints with aggressor-side classification. Quote ticks alone do not
provide executed bid/ask volume and must not be treated as genuine footprint data.
"""
from __future__ import annotations
from pathlib import Path
from typing import Union
import numpy as np
import pandas as pd


def load_trade_csv(path: Union[str, Path], *, timestamp_col="timestamp",
                   price_col="price", volume_col="volume", side_col="side") -> pd.DataFrame:
    """Load trades. `buy` means buyer-aggressor; `sell` means seller-aggressor.

    Accepted side aliases: buy/buyer/ask/b/1 and sell/seller/bid/s/-1.
    Timestamps are normalized to UTC. Invalid rows are dropped.
    """
    raw = pd.read_csv(path)
    cols = [timestamp_col, price_col, volume_col, side_col]
    missing = [c for c in cols if c not in raw.columns]
    if missing:
        raise ValueError(f"Trade CSV missing required columns: {missing}")
    df = raw[cols].copy()
    df.columns = ["timestamp", "price", "volume", "side"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    aliases = {"buy":"buy", "buyer":"buy", "ask":"buy", "b":"buy", "1":"buy",
               "sell":"sell", "seller":"sell", "bid":"sell", "s":"sell", "-1":"sell"}
    df["side"] = df["side"].astype(str).str.strip().str.lower().map(aliases)
    valid = (df.timestamp.notna() & np.isfinite(df.price) & np.isfinite(df.volume)
             & (df.price > 0) & (df.volume > 0) & df.side.isin(["buy", "sell"]))
    df = df.loc[valid, ["timestamp", "price", "volume", "side"]]
    if df.empty:
        raise ValueError("No valid trade rows remain after cleaning.")
    return df.sort_values("timestamp", kind="stable").reset_index(drop=True)


def trades_to_bars_and_footprints(trades: pd.DataFrame, *, bar_period="15min",
                                  tick_size=0.1) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return bars and long-form footprints compatible with `SignalEngine.run`.

    Bars have timestamp (bar OPEN, UTC), open, high, low, close, volume.
    Footprints have timestamp (matching bar OPEN), price, bid_vol, ask_vol.
    Price levels are rounded to nearest tick. Verify tick size and side semantics.
    """
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    required = {"timestamp", "price", "volume", "side"}
    if not required.issubset(trades.columns):
        raise ValueError(f"Trades DataFrame needs columns: {sorted(required)}")
    df = trades[list(required)].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    aliases = {"buyer":"buy", "ask":"buy", "b":"buy", "1":"buy",
               "seller":"sell", "bid":"sell", "s":"sell", "-1":"sell"}
    df["side"] = df["side"].astype(str).str.strip().str.lower().replace(aliases)
    valid = (df.timestamp.notna() & np.isfinite(df.price) & np.isfinite(df.volume)
             & (df.price > 0) & (df.volume > 0) & df.side.isin(["buy", "sell"]))
    df = df.loc[valid].sort_values("timestamp", kind="stable").copy()
    if df.empty:
        raise ValueError("No valid trades available to aggregate.")

    indexed = df.set_index("timestamp")
    px = indexed["price"].resample(bar_period, label="left", closed="left")
    bars = pd.DataFrame({
        "open": px.first(), "high": px.max(), "low": px.min(), "close": px.last(),
        "volume": indexed["volume"].resample(bar_period, label="left", closed="left").sum(),
    }).dropna(subset=["open", "high", "low", "close"]).reset_index()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)

    df["bar_timestamp"] = df["timestamp"].dt.floor(bar_period)
    df["price"] = (np.rint(df["price"].to_numpy(dtype=float) / tick_size) * tick_size).round(10)
    df["bid_vol"] = np.where(df["side"].eq("sell"), df["volume"], 0.0)
    df["ask_vol"] = np.where(df["side"].eq("buy"), df["volume"], 0.0)
    footprints = (df.groupby(["bar_timestamp", "price"], as_index=False)[["bid_vol", "ask_vol"]]
                  .sum().rename(columns={"bar_timestamp":"timestamp"})
                  .sort_values(["timestamp", "price"], kind="stable").reset_index(drop=True))
    return bars[["timestamp", "open", "high", "low", "close", "volume"]], footprints


def load_and_aggregate_csv(path: Union[str, Path], *, bar_period="15min", tick_size=0.1,
                           timestamp_col="timestamp", price_col="price", volume_col="volume",
                           side_col="side") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience wrapper for CSV loading and aggregation."""
    trades = load_trade_csv(path, timestamp_col=timestamp_col, price_col=price_col,
                            volume_col=volume_col, side_col=side_col)
    return trades_to_bars_and_footprints(trades, bar_period=bar_period, tick_size=tick_size)
