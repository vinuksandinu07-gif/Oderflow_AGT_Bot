from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import Bar, Fill, Order, Position, Side, Signal


class BaseStrategy:
    """Base strategy interface used for research and paper execution."""
    strategy_id: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        raise NotImplementedError


@dataclass
class DirectionalDriftStrategy(BaseStrategy):
    strategy_id: str = "directional_drift"
    config: Dict[str, Any] = field(default_factory=dict)

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar: Optional[Bar] = context.get("bar")
        profile = context.get("profile")
        value_context = context.get("value_context")
        delta = context.get("delta")
        cfg = context.get("config", {})
        strategy_cfg = cfg.get("directional_drift", {})

        if bar is None or profile is None:
            return []
        if value_context in (None, "balanced_auction"):
            return []
        if strategy_cfg.get("require_delta_confirmation", True):
            if delta is None:
                return []
            threshold = float(strategy_cfg.get("delta_threshold", 0.0))
            if value_context == "bullish_drift" and delta < threshold:
                return []
            if value_context == "bearish_drift" and delta > -threshold:
                return []

        if value_context == "bullish_drift":
            side = Side.LONG
            stop = float(profile["val"])
            risk = abs(float(bar.close) - stop)
            target = float(bar.close) + risk * max(float(strategy_cfg.get("target_rr", 1.0)), 1.0)
        elif value_context == "bearish_drift":
            side = Side.SHORT
            stop = float(profile["vah"])
            risk = abs(float(bar.close) - stop)
            target = float(bar.close) - risk * max(float(strategy_cfg.get("target_rr", 1.0)), 1.0)
        else:
            return []

        if risk <= 0:
            return []

        signal = Signal(
            strategy_id=self.strategy_id,
            side=side,
            timestamp=bar.timestamp,
            entry_price=float(bar.close),
            stop_price=stop,
            target_price=target,
            invalidation_level=stop,
            source_refs=["value_profile", "delta"],
            evidence=[value_context, f"delta={delta if delta is not None else 0.0}"],
            entry_rationale="Directional drift supported by value migration and confirmed directional delta.",
            stop_rationale="Structural stop anchored at relevant value-area boundary with configured buffer.",
            exit_policy="trail_stop",
            audit_trail=["no partial exits by default", "stop trails after confirmation"],
            confidence=0.67,
            data_quality="real" if delta is not None else "proxy",
        )
        return [signal]


@dataclass
class MachineGunScalpStrategy(BaseStrategy):
    strategy_id: str = "machine_gun_scalp"
    config: Dict[str, Any] = field(default_factory=dict)

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar: Optional[Bar] = context.get("bar")
        delta = context.get("delta")
        value_context = context.get("value_context")
        cfg = context.get("config", {})
        strategy_cfg = cfg.get("machine_gun_scalp", {})

        if bar is None or delta is None or value_context in (None, "balanced_auction"):
            return []
        if not strategy_cfg.get("enabled", True):
            return []
        threshold = float(strategy_cfg.get("delta_threshold", 0.0))
        if value_context == "bullish_drift" and delta <= threshold:
            return []
        if value_context == "bearish_drift" and delta >= -threshold:
            return []

        side = Side.LONG if value_context == "bullish_drift" else Side.SHORT
        entry = float(bar.close)
        if side == Side.LONG:
            stop = float(bar.low)
            risk = abs(entry - stop)
            target = entry + risk
        else:
            stop = float(bar.high)
            risk = abs(stop - entry)
            target = entry - risk
        if risk <= 0:
            return []

        signal = Signal(
            strategy_id=self.strategy_id,
            side=side,
            timestamp=bar.timestamp,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            invalidation_level=stop,
            source_refs=["delta", "value_context"],
            evidence=[value_context, f"delta={delta}"],
            entry_rationale="Confirmed switch in control with directional delta and migration evidence.",
            stop_rationale="Protected-value stop placed beyond the local structural support/resistance area.",
            exit_policy="fixed_1r_target",
            audit_trail=["scalp target set at 1R"],
            confidence=0.58,
            data_quality="real",
        )
        return [signal]


@dataclass
class MeanReversionStrategy(BaseStrategy):
    strategy_id: str = "mean_reversion"
    config: Dict[str, Any] = field(default_factory=dict)

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        strategy_cfg = cfg.get("mean_reversion", {})
        if not strategy_cfg.get("enabled", False):
            return []
        exit_policy = strategy_cfg.get("exit_policy")
        if not exit_policy or exit_policy == "config_required":
            return []
        return []


@dataclass
class MomentumStrategy(BaseStrategy):
    strategy_id: str = "momentum"
    config: Dict[str, Any] = field(default_factory=dict)

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        strategy_cfg = cfg.get("momentum", {})
        if not strategy_cfg.get("enabled", False):
            return []
        exit_policy = strategy_cfg.get("exit_policy")
        if not exit_policy or exit_policy == "config_required":
            return []
        return []


__all__ = [
    "BaseStrategy",
    "DirectionalDriftStrategy",
    "MachineGunScalpStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
]
