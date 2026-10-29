from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MarketConfig:
    """Instrument and market metadata.

    session_hours_utc is intentionally left blank until the operator provides it.
    This is explicit and refuses to invent a trading session from the video transcript.
    """
    symbol: str = "NASDAQ100"
    tick_size: float = 0.01
    point_value: float = 1.0
    multiplier: float = 1.0
    timezone: str = "UTC"
    exchange_timezone: str = "America/New_York"
    session_hours_utc: Optional[List[Tuple[int, int]]] = None
    value_area_percent: float = 0.70
    profile_method: str = "swing"
    allow_ohlcv_proxy: bool = False
    require_real_footprint_for_exact_models: bool = True
    effort_box_source: str = "external"
    source_provenance: str = "SOURCE_EXPLICIT"


@dataclass
class RiskConfig:
    """Fail-closed risk limits used by both paper and live paths."""
    account_equity: Optional[float] = None  # OPERATOR_REQUIRED
    risk_per_trade: Optional[float] = None  # OPERATOR_REQUIRED
    daily_loss_limit: Optional[float] = None  # OPERATOR_REQUIRED for live; optional for paper
    max_drawdown: Optional[float] = None  # OPERATOR_REQUIRED
    max_concurrent_positions: int = 1
    aggregate_risk_limit: Optional[float] = None
    max_adds: int = 0
    max_order_qty: Optional[float] = None
    min_order_qty: float = 1.0
    lot_step: float = 1.0
    max_loss_streak: Optional[int] = None
    stop_buffer_ticks: float = 1.0
    stop_rounding: str = "tick"
    allow_pyramiding: bool = False
    allow_averaging_down: bool = False
    default_live_mode: bool = False


@dataclass
class StrategyConfig:
    """Strategy parameters. Unknown source values are labeled assumptions."""
    enabled: bool = True
    min_confirmation_bars: int = 1
    use_real_effort_boxes: bool = False
    require_value_context: bool = True
    require_delta_confirmation: bool = True
    allow_1r_target: bool = True
    allow_1_2_target: bool = False
    target_rr: float = 1.0
    max_trailing_boxes: int = 5
    min_absorption_strength: float = 1.5  # ENGINEERING_ASSUMPTION
    delta_threshold: float = 0.0  # ENGINEERING_ASSUMPTION
    use_ohlcv_proxy: bool = False  # EXPERIMENTAL_PROXY
    exit_policy: str = "trail_stop"
    use_partial_exits: bool = False  # SOURCE_EXPLICIT: default no partial profits


@dataclass
class OrderflowConfig:
    market: MarketConfig = field(default_factory=MarketConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    directional_drift: StrategyConfig = field(default_factory=StrategyConfig)
    machine_gun_scalp: StrategyConfig = field(default_factory=StrategyConfig)
    mean_reversion: StrategyConfig = field(default_factory=StrategyConfig)
    momentum: StrategyConfig = field(default_factory=StrategyConfig)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "OrderflowConfig":
        return OrderflowConfig(
            market=MarketConfig(**data.get("market", {})),
            risk=RiskConfig(**data.get("risk", {})),
            directional_drift=StrategyConfig(**data.get("directional_drift", {})),
            machine_gun_scalp=StrategyConfig(**data.get("machine_gun_scalp", {})),
            mean_reversion=StrategyConfig(**data.get("mean_reversion", {})),
            momentum=StrategyConfig(**data.get("momentum", {})),
        )


def validate_config(cfg: OrderflowConfig) -> None:
    """Hard-fail on critical invalid settings."""
    if cfg.risk.account_equity is None or cfg.risk.risk_per_trade is None:
        raise ValueError("OPERATOR_REQUIRED: account_equity and risk_per_trade must be populated before sizing or live deployment.")
    if cfg.risk.stop_buffer_ticks <= 0:
        raise ValueError("stop_buffer_ticks must be positive.")
    if cfg.risk.default_live_mode:
        if cfg.market.session_hours_utc is None:
            raise ValueError("OPERATOR_REQUIRED: session_hours_utc is required before live mode can be enabled.")
        if cfg.risk.daily_loss_limit is None or cfg.risk.max_drawdown is None:
            raise ValueError("OPERATOR_REQUIRED: daily_loss_limit and max_drawdown are required for live mode.")


__all__ = [
    "MarketConfig",
    "RiskConfig",
    "StrategyConfig",
    "OrderflowConfig",
    "validate_config",
]
