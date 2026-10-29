from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .models import Bar


def load_csv_bars(path: str) -> List[Bar]:
    """Read synthetic CSV bars. The schema is intentionally simple and clearly marked synthetic."""
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df = df.sort_values("timestamp").reset_index(drop=True)
    out: List[Bar] = []
    for row in df.to_dict("records"):
        ts = pd.Timestamp(row["timestamp"])
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        out.append(Bar(timestamp=ts, open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"])))
    return out


def export_json(data: Dict[str, Any], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def build_summary_report(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {"signals": 0, "win_rate": 0.0, "gross_pnl": 0.0}
    pnl_values = [float(r.get("pnl", 0.0)) for r in rows]
    win_rate = sum(1 for x in pnl_values if x > 0) / len(pnl_values)
    return {
        "signals": len(rows),
        "gross_pnl": float(sum(pnl_values)),
        "win_rate": float(win_rate),
        "avg_pnl": float(sum(pnl_values) / len(pnl_values)),
    }
