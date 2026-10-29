from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Bar, EffortBox, Signal, Side


class Strategy:
    strategy_id: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        return []


@dataclass
class DirectionalDriftStrategy(Strategy):
    strategy_id: str = "directional_drift"

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar = context.get("bar")
        profile = context.get("profile")
        delta = context.get("delta")
        value_label = context.get("value_context")
        if bar is None or profile is None:
            return []
        if value_label == "balanced_auction":
            return []
        if delta is None:
            return []
        side = Side.LONG if (value_label == "bullish_drift" and delta > 0) or (value_label == "bullish_drift" and delta >= 0) else Side.SHORT
        if value_label == "bearish_drift" and delta < 0:
            side = Side.SHORT
        else:
            side = Side.LONG if value_label == "bullish_drift" and delta >= 0 else Side.SHORT if value_label == "bearish_drift" and delta <= 0 else None
        if side is None:
            return []
        entry = float(bar.close)
        stop = float(profile.val if side == Side.LONG else profile.vah)
        target = entry + (entry - stop) * 1.5 if side == Side.LONG else entry - (stop - entry) * 1.5
        signal = Signal(
            strategy_id=self.strategy_id,
            side=side,
            timestamp=bar.timestamp,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            invalidation_level=stop,
            source_refs=["value_profile", "delta"],
            evidence=[value_label, f"delta={delta:.2f}"],
            entry_rationale="directional drift supported by value migration and delta confirmation",
            stop_rationale="structural stop under/over value area boundary with buffer",
            exit_policy="trail_stop",
            audit_trail=["directional_drift generated"],
            confidence=0.6,
            data_quality="real" if delta is not None else "proxy",
        )
        return [signal]


@dataclass
class MachineGunScalpStrategy(Strategy):
    strategy_id: str = "machine_gun_scalp"

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar = context.get("bar")
        delta = context.get("delta")
        value_label = context.get("value_context")
        if bar is None or delta is None or value_label == "balanced_auction":
            return []
        side = Side.LONG if delta > 0 and value_label == "bullish_drift" else Side.SHORT if delta < 0 and value_label == "bearish_drift" else None
        if side is None:
            return []
        entry = float(bar.close)
        stop_distance = abs(bar.close - bar.low) if side == Side.LONG else abs(bar.high - bar.close)
        if stop_distance <= 0:
            return []
        stop = bar.low if side == Side.LONG else bar.high
        target = entry + (entry - stop) if side == Side.LONG else entry - (stop - entry)
        signal = Signal(
            strategy_id=self.strategy_id,
            side=side,
            timestamp=bar.timestamp,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            invalidation_level=stop,
            source_refs=["delta", "value_profile"],
            evidence=[f"delta={delta:.2f}", value_label],
            entry_rationale="switch in control with directional delta and migration confirmation",
            stop_rationale="protected-value stop placed beyond the value area boundary",
            exit_policy="fixed_1r_target",
            audit_trail=["scalp generated"],
            confidence=0.55,
            data_quality="real",
        )
        return [signal]


@dataclass
class MeanReversionStrategy(Strategy):
    strategy_id: str = "mean_reversion"

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        if not cfg.get("enabled", False):
            return []
        if not cfg.get("exit_policy"):
            return []
        return []


@dataclass
class MomentumStrategy(Strategy):
    strategy_id: str = "momentum"

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        if not cfg.get("enabled", False):
            return []
        if not cfg.get("exit_policy"):
            return []
        return []
