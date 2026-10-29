from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .models import Bar, Signal, Side


class BaseStrategy:
    """Base strategy contract for research and paper execution.

    Each strategy keeps separate trigger logic, stop logic, target logic and audit trail.
    """
    strategy_id: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        raise NotImplementedError


@dataclass
class DirectionalDriftStrategy(BaseStrategy):
    strategy_id: str = "directional_drift"
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.config = self.config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar: Optional[Bar] = context.get("bar")
        profile = context.get("profile")
        value_context = context.get("value_context")
        delta = context.get("delta")
        cfg = context.get("config", {})
        if bar is None or profile is None or value_context in (None, "balanced_auction"):
            return []
        threshold = float(cfg.get("directional_drift", {}).get("delta_threshold", 0.0))
        if delta is None and cfg.get("directional_drift", {}).get("require_delta_confirmation", True):
            return []
        if delta is not None and cfg.get("directional_drift", {}).get("require_delta_confirmation", True):
            if value_context == "bullish_drift" and delta < threshold:
                return []
            if value_context == "bearish_drift" and delta > -threshold:
                return []

        if value_context == "bullish_drift":
            side = Side.LONG
            stop = float(profile.val)
            entry = float(bar.close)
            risk = abs(entry - stop)
            if risk <= 0:
                return []
            target = entry + risk * max(float(cfg.get("directional_drift", {}).get("target_rr", 1.0)), 1.0)
            invalidation = stop
            evidence = ["bullish value migration", f"delta={delta if delta is not None else 0.0}"]
            rationale = "Direction supported by rising value area and delta confirmation."
        elif value_context == "bearish_drift":
            side = Side.SHORT
            stop = float(profile.vah)
            entry = float(bar.close)
            risk = abs(stop - entry)
            if risk <= 0:
                return []
            target = entry - risk * max(float(cfg.get("directional_drift", {}).get("target_rr", 1.0)), 1.0)
            invalidation = stop
            evidence = ["bearish value migration", f"delta={delta if delta is not None else 0.0}"]
            rationale = "Direction supported by falling value area and delta confirmation."
        else:
            return []

        signal = Signal(
            strategy_id=self.strategy_id,
            side=side,
            timestamp=bar.timestamp,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            invalidation_level=invalidation,
            source_refs=["value_profile", "delta"],
            evidence=evidence,
            entry_rationale=rationale,
            stop_rationale="structural stop anchored to value-area boundary with configured buffer.",
            exit_policy="trail_stop",
            audit_trail=["primary drift signal", "no partial exits by default", "value context confirmed"],
            confidence=0.67,
            data_quality="real" if delta is not None else "proxy",
        )
        return [signal]


@dataclass
class MachineGunScalpStrategy(BaseStrategy):
    strategy_id: str = "machine_gun_scalp"
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.config = self.config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        bar: Optional[Bar] = context.get("bar")
        delta = context.get("delta")
        value_context = context.get("value_context")
        cfg = context.get("config", {})
        if bar is None or value_context in (None, "balanced_auction"):
            return []
        if delta is None:
            return []
        scalp_cfg = cfg.get("machine_gun_scalp", {})
        if not scalp_cfg.get("enabled", True):
            return []

        if value_context == "bullish_drift" and delta <= float(scalp_cfg.get("delta_threshold", 0.0)):
            return []
        if value_context == "bearish_drift" and delta >= -float(scalp_cfg.get("delta_threshold", 0.0)):
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
            evidence=[f"scalp value-context={value_context}", f"delta={delta}"] ,
            entry_rationale="switch in control with directional delta and value migration confirmation.",
            stop_rationale="protected-value stop beyond the relevant support/resistance area.",
            exit_policy="fixed_1r_target",
            audit_trail=["machine_gun_scalp generated"],
            confidence=0.58,
            data_quality="real",
        )
        return [signal]


@dataclass
class MeanReversionStrategy(BaseStrategy):
    strategy_id: str = "mean_reversion"
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.config = self.config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        strat_cfg = cfg.get("mean_reversion", {})
        if not strat_cfg.get("enabled", False):
            return []
        exit_policy = strat_cfg.get("exit_policy")
        if not exit_policy or exit_policy == "config_required":
            return []
        bar = context.get("bar")
        if bar is None:
            return []
        return []


@dataclass
class MomentumStrategy(BaseStrategy):
    strategy_id: str = "momentum"
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.config = self.config or {}

    def process(self, context: Dict[str, Any]) -> List[Signal]:
        cfg = context.get("config", {})
        strat_cfg = cfg.get("momentum", {})
        if not strat_cfg.get("enabled", False):
            return []
        exit_policy = strat_cfg.get("exit_policy")
        if not exit_policy or exit_policy == "config_required":
            return []
        bar = context.get("bar")
        if bar is None:
            return []
        return []


__all__ = [
    "BaseStrategy",
    "DirectionalDriftStrategy",
    "MachineGunScalpStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
]
