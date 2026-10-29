from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

from .models import Bar, Fill, Order, Position, Side, Signal
from .risk import PaperBroker


@dataclass
class EventBacktester:
    """Deterministic historical runner using the same strategy and order interfaces as paper/live.

    This is a lightweight synthetic backtester intended for research and deterministic replay.
    """
    config: Dict[str, Any]
    bars: List[Bar]
    broker: PaperBroker = field(default_factory=PaperBroker)
    signals: List[Signal] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    positions: List[Position] = field(default_factory=list)

    def __post_init__(self):
        self.broker.cfg = self.config

    def run(self, strategies: Sequence[Any]) -> Dict[str, Any]:
        for bar in self.bars:
            context = {
                "bar": bar,
                "config": self.config,
                "profile": {"poc": bar.close, "val": min(bar.close, bar.low), "vah": max(bar.close, bar.high)},
                "delta": float(bar.close - bar.open),
                "value_context": "bullish_drift" if bar.close >= bar.open else "bearish_drift",
            }
            for strategy in strategies:
                for signal in strategy.process(context):
                    self.signals.append(signal)
                    order = Order(
                        order_id=f"ord-{len(self.orders)+1}",
                        strategy_id=signal.strategy_id,
                        side=signal.side,
                        quantity=max(1.0, self.config.get("risk", {}).get("min_order_qty", 1.0)),
                        price=float(signal.entry_price),
                        timestamp=signal.timestamp,
                    )
                    self.orders.append(self.broker.submit_order(order))
                    fill = self.broker.fill_order(order, price=float(signal.entry_price), quantity=order.quantity)
                    self.fills.append(fill)
                    self.positions.append(Position(
                        position_id=f"pos-{len(self.positions)+1}",
                        side=signal.side,
                        quantity=float(order.quantity),
                        entry_price=float(signal.entry_price),
                        stop_price=float(signal.stop_price),
                        target_price=signal.target_price,
                        timestamp=signal.timestamp,
                        strategy_id=signal.strategy_id,
                    ))
        return {"signals": len(self.signals), "orders": len(self.orders), "fills": len(self.fills), "positions": len(self.positions)}


def build_summary_report(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {"signals": 0, "win_rate": 0.0, "gross_pnl": 0.0}
    pnl_values = [float(row.get("pnl", 0.0)) for row in rows]
    wins = sum(1 for x in pnl_values if x > 0)
    return {
        "signals": len(rows),
        "gross_pnl": float(sum(pnl_values)),
        "win_rate": float(wins / len(pnl_values)),
        "avg_pnl": float(sum(pnl_values) / len(pnl_values)),
    }


__all__ = ["EventBacktester", "build_summary_report"]
