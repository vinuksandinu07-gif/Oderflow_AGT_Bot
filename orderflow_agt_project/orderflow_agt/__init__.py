from __future__ import annotations

from typing import Any, Dict, List, Optional

from .backtest import EventBacktester
from .config import MarketConfig, OrderflowConfig, RiskConfig, StrategyConfig, validate_config
from .features import (
    classify_value_context,
    compute_delta,
    compute_delta_ratio,
    compute_value_migration,
    compute_value_profile,
    compute_vwap,
    detect_absorption,
    ohlcv_proxy_signal,
)
from .models import Bar, EffortBox, Fill, FootprintSnapshot, MarketContext, Order, Position, Quote, Signal, Side, Trade, ValueProfile
from .risk import PaperBroker, RiskManager
from .strategies import BaseStrategy, DirectionalDriftStrategy, MachineGunScalpStrategy, MeanReversionStrategy, MomentumStrategy

__all__ = [
    "Bar",
    "Quote",
    "Trade",
    "FootprintSnapshot",
    "ValueProfile",
    "EffortBox",
    "Signal",
    "Order",
    "Fill",
    "Position",
    "MarketContext",
    "Side",
    "MarketConfig",
    "RiskConfig",
    "StrategyConfig",
    "OrderflowConfig",
    "validate_config",
    "RiskManager",
    "PaperBroker",
    "BaseStrategy",
    "DirectionalDriftStrategy",
    "MachineGunScalpStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "EventBacktester",
    "compute_delta",
    "compute_delta_ratio",
    "compute_vwap",
    "compute_value_profile",
    "compute_value_migration",
    "classify_value_context",
    "detect_absorption",
    "ohlcv_proxy_signal",
]
