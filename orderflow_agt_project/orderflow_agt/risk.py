from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import Fill, Order, Position, Side


class RiskManager:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def risk_per_unit(self, entry: float, stop: float, point_value: float = 1.0, multiplier: float = 1.0) -> float:
        distance = abs(entry - stop)
        if distance <= 0:
            raise ValueError("Invalid stop distance: zero or negative risk distance.")
        return float(distance * point_value * multiplier)

    def size_position(self, entry: float, stop: float, point_value: float = 1.0, multiplier: float = 1.0) -> float:
        equity = float(self.cfg.get("account_equity"))
        risk_pct = float(self.cfg.get("risk_per_trade"))
        if equity is None or risk_pct is None:
            raise ValueError("OPERATOR_REQUIRED: account_equity and risk_per_trade must be configured.")
        risk_amount = equity * risk_pct
        risk_per_unit = self.risk_per_unit(entry, stop, point_value, multiplier)
        if risk_per_unit <= 0:
            raise ValueError("Invalid risk per unit. Rejecting trade.")
        qty = risk_amount / risk_per_unit
        max_qty = self.cfg.get("max_order_qty")
        if max_qty is not None:
            qty = min(qty, max_qty)
        lot_step = self.cfg.get("lot_step", 1.0)
        if lot_step and qty is not None:
            qty = max(self.cfg.get("min_order_qty", 1.0), round(qty / lot_step) * lot_step)
        return float(qty)

    def validate_position(self, side: Side, entry: float, stop: float, target: Optional[float]) -> bool:
        if entry <= 0 or stop <= 0:
            return False
        if abs(entry - stop) <= 0:
            return False
        return True

    def check_loss_limits(self, realized_pnl: float) -> bool:
        daily_loss_limit = self.cfg.get("daily_loss_limit")
        if daily_loss_limit is not None and realized_pnl <= -daily_loss_limit:
            return False
        return True

    def can_add_to_position(self, current_pos: Position, new_risk: float) -> bool:
        cap = self.cfg.get("aggregate_risk_limit")
        if cap is not None and new_risk > cap:
            return False
        return True


@dataclass
class PaperBroker:
    cfg: Dict[str, Any]
    orders: List[Order] = None
    fills: List[Fill] = None

    def __post_init__(self):
        if self.orders is None:
            self.orders = []
        if self.fills is None:
            self.fills = []

    def submit_order(self, order: Order) -> Order:
        order.status = "accepted"
        self.orders.append(order)
        return order

    def fill_order(self, order: Order, price: float, quantity: Optional[float] = None, fees: float = 0.0, slippage: float = 0.0) -> Fill:
        fill_qty = quantity if quantity is not None else order.quantity
        fill = Fill(order_id=order.order_id, timestamp=order.timestamp, price=price, quantity=fill_qty, fees=fees, slippage=slippage)
        self.fills.append(fill)
        order.status = "filled"
        return fill
