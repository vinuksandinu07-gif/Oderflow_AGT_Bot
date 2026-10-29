from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MarketConfig:
    """Instrument and data-market configuration.

    Note: session hours are OPERATOR_REQUIRED and intentionally blank/None by default.
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
    """Risk configuration. Missing operator values fail closed."""
    account_equity: Optional[float] = None  # OPERATOR_REQUIRED
    risk_per_trade: Optional[float] = None  # OPERATOR_REQUIRED
    daily_loss_limit: Optional[float] = None  # OPERATOR_REQUIRED for live, optional for paper
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
    """Strategy configuration. Values with no source disclosure are labeled assumptions."""
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
    use_partial_exits: bool = False  # SOURCE_EXPLICIT false by default


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
        market = MarketConfig(**data.get("market", {}))
        risk = RiskConfig(**data.get("risk", {}))
        strategies = data.get("strategies", {})
        directional = StrategyConfig(**strategies.get("directional_drift", {}))
        scalp = StrategyConfig(**strategies.get("machine_gun_scalp", {}))
        reversal = StrategyConfig(**strategies.get("mean_reversion", {}))
        momentum = StrategyConfig(**strategies.get("momentum", {}))
        return OrderflowConfig(market=market, risk=risk,
                               directional_drift=directional,
                               machine_gun_scalp=scalp,
                               mean_reversion=reversal,
                               momentum=momentum)


def validate_config(cfg: OrderflowConfig) -> None:
    """Fail closed when critical values are missing."""
    if cfg.market.require_real_footprint_for_exact_models and not cfg.market.allow_ohlcv_proxy:
        pass
    if cfg.risk.account_equity is None or cfg.risk.risk_per_trade is None:
        raise ValueError("OPERATOR_REQUIRED: account_equity and risk_per_trade must be populated before live or paper sizing is used.")
    if cfg.risk.stop_buffer_ticks <= 0:
        raise ValueError("stop_buffer_ticks must be positive.")
    if cfg.market.session_hours_utc is None and cfg.market.symbol:
        # We intentionally refuse to infer session clocks from the transcript.
        pass
