from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .models import Bar


def load_csv_bars(path: str) -> List[Bar]:
    """Load synthetic bar data from a CSV file.

    The schema is simple and clearly marked as synthetic rather than real market data.
    """
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df = df.sort_values("timestamp").reset_index(drop=True)
    bars: List[Bar] = []
    for row in df.to_dict("records"):
        ts = pd.Timestamp(row["timestamp"]).tz_localize("UTC") if pd.Timestamp(row["timestamp"]).tzinfo is None else pd.Timestamp(row["timestamp"]).tz_convert("UTC")
        bars.append(Bar(timestamp=ts, open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"])))
    return bars


def load_yaml_config(path: str) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
