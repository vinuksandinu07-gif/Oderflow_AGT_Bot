from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .models import Bar, EffortBox, Signal, Side


@dataclass
class EventBacktester:
    bars: List[Bar]
    config: Dict[str, Any]
    broker: Any = None
    realized: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.broker is None:
            self.broker = type("Broker", (), {"orders": [], "fills": []})()

    def run(self, strategies: Iterable[Any]) -> Dict[str, Any]:
        strategies = list(strategies)
        for idx, bar in enumerate(self.bars):
            context = {
                "bar": bar,
                "config": self.config,
                "profile": self._synthetic_profile(idx),
                "delta": float(bar.close - bar.open),
                "value_context": "bullish_drift" if bar.close >= bar.open else "bearish_drift",
            }
            for strategy in strategies:
                for signal in strategy.process(context):
                    self.realized.append({
                        "strategy_id": signal.strategy_id,
                        "side": signal.side.value,
                        "timestamp": str(signal.timestamp),
                        "entry": signal.entry_price,
                        "stop": signal.stop_price,
                        "target": signal.target_price,
                    })
        return {"signals": self.realized}

    def _synthetic_profile(self, idx: int) -> Dict[str, Any]:
        base = 100.0 + idx * 0.5
        return {
            "poc": base,
            "vah": base + 1.5,
            "val": base - 1.5,
        }


def build_summary_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"signals": 0, "avg_pnl": 0.0, "win_rate": 0.0}
    pnl = [float(r.get("pnl", 0.0)) for r in rows]
    wins = sum(1 for x in pnl if x > 0)
    return {
        "signals": len(rows),
        "avg_pnl": float(sum(pnl) / len(pnl)),
        "win_rate": float(wins / len(pnl)),
        "gross_pnl": float(sum(pnl)),
    }


def export_report(summary: Dict[str, Any], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
