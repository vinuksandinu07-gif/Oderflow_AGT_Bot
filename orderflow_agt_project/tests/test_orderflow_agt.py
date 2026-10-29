from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orderflow_agt.config import OrderflowConfig, MarketConfig, RiskConfig, StrategyConfig
from orderflow_agt.data_import import load_csv_bars
from orderflow_agt.features import classify_value_context, compute_delta, compute_value_migration, compute_value_profile, compute_vwap, detect_absorption
from orderflow_agt.models import Bar, FootprintSnapshot
from orderflow_agt.risk import RiskManager


def test_delta_and_vwap():
    bars = [
        Bar("2026-01-05T08:00:00Z", 100.0, 101.0, 99.0, 100.5, volume=100),
        Bar("2026-01-05T08:15:00Z", 100.5, 101.5, 100.1, 101.2, volume=120),
        Bar("2026-01-05T08:30:00Z", 101.2, 101.7, 100.8, 101.5, volume=130),
    ]
    footprint = FootprintSnapshot(timestamp=bars[-1].timestamp, bid_vol=40.0, ask_vol=90.0)
    assert compute_delta(footprint) == 50.0
    assert abs(compute_vwap(bars) - 100.82) < 1e-2


def test_value_profile_classification_and_migration():
    bars = [
        Bar("2026-01-05T08:00:00Z", 100.0, 100.8, 99.3, 100.2, volume=10),
        Bar("2026-01-05T08:15:00Z", 100.2, 101.0, 99.8, 100.8, volume=10),
        Bar("2026-01-05T08:30:00Z", 100.8, 101.4, 100.0, 101.2, volume=10),
        Bar("2026-01-05T08:45:00Z", 101.2, 101.5, 100.7, 101.4, volume=12),
    ]
    prev = compute_value_profile(bars[:2], value_area_percent=0.70, tick_size=0.1)
    curr = compute_value_profile(bars[2:], value_area_percent=0.70, tick_size=0.1)
    assert classify_value_context(prev, curr) == "bullish_drift"
    assert compute_value_migration(prev, curr) > 0


def test_absorption_detection():
    assert detect_absorption(delta=5.0, price_progress=0.1, requirement=1.5, progress_threshold=0.2) == "buyer_absorption"
    assert detect_absorption(delta=-5.0, price_progress=0.1, requirement=1.5, progress_threshold=0.2) == "seller_absorption"


def test_risk_manager_rejects_missing_operator_inputs():
    risk_cfg = RiskConfig(account_equity=None, risk_per_trade=None, dayli_loss_limit=None if False else None)
    rm = RiskManager(risk_cfg.__dict__)
    try:
        rm.size_position(100.0, 99.0)
        assert False
    except ValueError:
        pass


def test_risk_manager_computes_quantity():
    cfg = RiskConfig(account_equity=100000.0, risk_per_trade=0.01, daily_loss_limit=2000.0, max_drawdown=0.2, max_concurrent_positions=1, aggregate_risk_limit=0.05, max_adds=0, max_order_qty=100.0, min_order_qty=1.0, lot_step=1.0, stop_buffer_ticks=1.0, stop_rounding="tick", allow_pyramiding=False, allow_averaging_down=False)
    rm = RiskManager(cfg.__dict__)
    qty = rm.size_position(103.0, 101.0, point_value=1.0, multiplier=1.0)
    assert qty > 0
    assert qty <= 100.0


def test_load_csv_bars_and_default_config():
    from orderflow_agt.data_import import load_csv_bars
    bars = load_csv_bars("tests/fixtures/synthetic_bars.csv")
    assert len(bars) == 7
    assert all(bar.timestamp.tzinfo is not None for bar in bars)

    cfg = OrderflowConfig(
        market=MarketConfig(symbol="NASDAQ100", tick_size=0.01, point_value=1.0, multiplier=1.0, timezone="UTC", exchange_timezone="America/New_York", session_hours_utc=None, value_area_percent=0.70),
        risk=RiskConfig(account_equity=100000.0, risk_per_trade=0.01, daily_loss_limit=2000.0, max_drawdown=0.2, max_concurrent_positions=1, aggregate_risk_limit=0.05, max_adds=0, max_order_qty=100.0, min_order_qty=1.0, lot_step=1.0, stop_buffer_ticks=1.0, stop_rounding="tick", allow_pyramiding=False, allow_averaging_down=False),
        directional_drift=StrategyConfig(enabled=True),
    )
    assert cfg.market.symbol == "NASDAQ100"


def test_project_uses_real_data_and_ohlcv_proxy_is_off_by_default():
    cfg = OrderflowConfig()
    assert cfg.market.allow_ohlcv_proxy is False
    assert cfg.market.require_real_footprint_for_exact_models is True
