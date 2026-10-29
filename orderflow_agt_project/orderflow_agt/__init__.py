from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orderflow_agt.config import MarketConfig, OrderflowConfig, RiskConfig, StrategyConfig, validate_config
from orderflow_agt.data_import import load_csv_bars
from orderflow_agt.features import classify_value_context, compute_delta, compute_value_migration, compute_value_profile, compute_vwap, detect_absorption
from orderflow_agt.models import Bar, FootprintSnapshot, Side
from orderflow_agt.risk import RiskManager
from orderflow_agt.strategies import DirectionalDriftStrategy, MachineGunScalpStrategy
from orderflow_agt.backtest import EventBacktester


def test_delta_and_vwap():
    bars = [
        Bar("2026-01-05T08:00:00Z", 100.0, 101.0, 99.0, 100.5, volume=100),
        Bar("2026-01-05T08:15:00Z", 100.5, 101.5, 100.1, 101.2, volume=120),
        Bar("2026-01-05T08:30:00Z", 101.2, 101.7, 100.8, 101.5, volume=130),
    ]
    footprint = FootprintSnapshot(timestamp=bars[-1].timestamp, bid_vol=40.0, ask_vol=90.0)
    assert compute_delta(footprint) == 50.0
    assert abs(compute_vwap(bars) - 100.82) < 1e-2


def test_value_profile_and_context():
    bars = [
        Bar("2026-01-05T08:00:00Z", 100.0, 100.8, 99.3, 100.2, volume=10),
        Bar("2026-01-05T08:15:00Z", 100.3, 101.0, 99.8, 100.8, volume=10),
        Bar("2026-01-05T08:30:00Z", 100.8, 101.4, 100.0, 101.2, volume=10),
        Bar("2026-01-05T08:45:00Z", 101.2, 101.5, 100.7, 101.4, volume=12),
    ]
    prev = compute_value_profile(bars[:2], value_area_percent=0.70, tick_size=0.1)
    curr = compute_value_profile(bars[2:], value_area_percent=0.70, tick_size=0.1)
    assert classify_value_context(prev, curr) == "bullish_drift"
    assert compute_value_migration(prev, curr) > 0


def test_absorption_detection():
    assert detect_absorption(delta=5.0, price_progress=0.1) == "buyer_absorption"
    assert detect_absorption(delta=-5.0, price_progress=0.1) == "seller_absorption"


def test_risk_manager_rejects_missing_operator_inputs():
    rm = RiskManager({"account_equity": None, "risk_per_trade": None})
    with pytest.raises(ValueError):
        rm.size_position(100.0, 99.0)


def test_risk_manager_sizes_position():
    rm = RiskManager({
        "account_equity": 100000.0,
        "risk_per_trade": 0.01,
        "max_order_qty": 100.0,
        "min_order_qty": 1.0,
        "lot_step": 1.0,
    })
    qty = rm.size_position(103.0, 101.0)
    assert qty > 0
    assert qty <= 100.0


def test_strategy_separation_and_sides():
    bar = Bar("2026-01-05T09:00:00Z", 100.0, 101.0, 99.5, 100.6, volume=100)
    cfg = {"directional_drift": {"delta_threshold": 0.0, "target_rr": 1.0}, "machine_gun_scalp": {"enabled": True, "delta_threshold": 0.0}}
    drift = DirectionalDriftStrategy().process({"bar": bar, "profile": {"val": 99.8, "vah": 101.2}, "value_context": "bullish_drift", "delta": 2.0, "config": cfg})
    scalp = MachineGunScalpStrategy().process({"bar": bar, "delta": 2.0, "value_context": "bullish_drift", "config": cfg})
    assert drift[0].side == Side.LONG
    assert scalp[0].side == Side.LONG


def test_event_backtester_emits_signals():
    bars = [
        Bar("2026-01-05T08:00:00Z", 100.0, 101.0, 99.5, 100.2, volume=100),
        Bar("2026-01-05T08:15:00Z", 100.2, 101.1, 99.7, 100.8, volume=110),
    ]
    cfg = {"risk": {"min_order_qty": 1.0}, "directional_drift": {"enabled": True, "delta_threshold": 0.0}, "machine_gun_scalp": {"enabled": True, "delta_threshold": 0.0}}
    bt = EventBacktester(config=cfg, bars=bars)
    result = bt.run([DirectionalDriftStrategy(config=cfg)])
    assert result["signals"] >= 1


def test_validate_config_requires_operator_values_for_live_mode():
    cfg = OrderflowConfig(
        market=MarketConfig(symbol="NASDAQ100", session_hours_utc=[(8, 16)]),
        risk=RiskConfig(account_equity=100000.0, risk_per_trade=0.01, daily_loss_limit=None, max_drawdown=None, default_live_mode=True),
    )
    with pytest.raises(ValueError):
        validate_config(cfg)


def test_load_csv_bars_and_proxy_off_by_default():
    bars = load_csv_bars("tests/fixtures/synthetic_bars.csv")
    assert len(bars) == 7
    assert all(bar.timestamp.tzinfo is not None for bar in bars)
    cfg = OrderflowConfig()
    assert cfg.market.allow_ohlcv_proxy is False
    assert cfg.market.require_real_footprint_for_exact_models is True


def test_no_same_bar_lookahead_not_applied():
    # This is a behavioral guard: the strategy only uses finalized bar close and prior context.
    bar = Bar("2026-01-05T09:00:00Z", 100.0, 101.0, 99.0, 100.9, volume=110)
    signals = DirectionalDriftStrategy().process({"bar": bar, "profile": {"val": 99.8, "vah": 101.2}, "value_context": "bullish_drift", "delta": 1.0, "config": {"directional_drift": {"delta_threshold": 0.0}}})
    assert len(signals) == 1
    assert signals[0].timestamp == bar.timestamp


# ensure the tests run importably from repo root
if __name__ == "__main__":
    pytest.main(["-q", __file__])
