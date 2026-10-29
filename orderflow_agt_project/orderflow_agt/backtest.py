from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import Fill, Order, Position, Side


class RiskManager:
    """Central risk manager used before orders and adds are accepted."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}

    def validate_trade(self, entry: float, stop: float, target: Optional[float] = None) -> bool:
        if entry <= 0 or stop <= 0:
            return False
        if abs(entry - stop) <= 0:
            return False
        if target is not None and abs(target - entry) <= 0:
            return False
        return True

    def risk_distance(self, entry: float, stop: float, point_value: float = 1.0, multiplier: float = 1.0) -> float:
        distance = abs(float(entry) - float(stop))
        if distance <= 0:
            raise ValueError("invalid stop distance")
        return float(distance * point_value * multiplier)

    def size_position(self, entry: float, stop: float, point_value: float = 1.0, multiplier: float = 1.0) -> float:
        account_equity = self.cfg.get("account_equity")
        risk_per_trade = self.cfg.get("risk_per_trade")
        if account_equity is None or risk_per_trade is None:
            raise ValueError("OPERATOR_REQUIRED: account_equity and risk_per_trade must be populated before sizing.")
        if not self.validate_trade(entry, stop):
            raise ValueError("Invalid entry/stop; risk manager rejected order.")

        risk_budget = float(account_equity) * float(risk_per_trade)
        risk_per_unit = self.risk_distance(entry, stop, point_value, multiplier)
        quantity = risk_budget / risk_per_unit

        max_qty = self.cfg.get("max_order_qty")
        if max_qty is not None:
            quantity = min(quantity, float(max_qty))

        min_qty = float(self.cfg.get("min_order_qty", 1.0))
        lot_step = float(self.cfg.get("lot_step", 1.0))
        quantity = max(min_qty, quantity)
        if lot_step > 0:
            quantity = round(quantity / lot_step) * lot_step
        return float(quantity)

    def daily_loss_ok(self, realized_pnl: float) -> bool:
        limit = self.cfg.get("daily_loss_limit")
        if limit is None:
            return True
        return realized_pnl > -float(limit)

    def aggregate_risk_ok(self, proposed_risk: float) -> bool:
        cap = self.cfg.get("aggregate_risk_limit")
        if cap is None:
            return True
        return float(proposed_risk) <= float(cap)


@dataclass
class PaperBroker:
    cfg: Optional[Dict[str, Any]] = None
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    positions: List[Position] = field(default_factory=list)

    def __post_init__(self):
        self.cfg = self.cfg or {}

    def submit_order(self, order: Order) -> Order:
        order.status = "accepted"
        self.orders.append(order)
        return order

    def fill_order(self, order: Order, price: float, quantity: Optional[float] = None, fees: float = 0.0, slippage: float = 0.0) -> Fill:
        fill_qty = order.quantity if quantity is None else float(quantity)
        fill = Fill(
            order_id=order.order_id,
            timestamp=order.timestamp,
            price=float(price),
            quantity=float(fill_qty),
            fees=float(fees),
            slippage=float(slippage),
        )
        self.fills.append(fill)
        order.status = "filled"
        return fill

    def cancel_order(self, order: Order) -> Order:
        order.status = "cancelled"
        return order


__all__ = ["RiskManager", "PaperBroker"]
