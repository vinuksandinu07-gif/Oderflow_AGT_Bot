from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orderflow_agt.config import OrderflowConfig, MarketConfig, RiskConfig, StrategyConfig
from orderflow_agt.data_import import load_yaml_config
from orderflow_agt.features import compute_delta, compute_vwap, compute_value_profile, classify_value_context
from orderflow_agt.models import Bar, FootprintSnapshot
from orderflow_agt.risk import RiskManager


def build_demo_bars():
    base = [
        Bar("2026-01-05T08:00:00Z", 100.0, 101.0, 99.0, 100.5, volume=100),
        Bar("2026-01-05T08:15:00Z", 100.5, 101.5, 100.1, 101.2, volume=120),
        Bar("2026-01-05T08:30:00Z", 101.2, 101.7, 100.8, 101.5, volume=130),
        Bar("2026-01-05T08:45:00Z", 101.5, 102.0, 101.2, 101.8, volume=150),
        Bar("2026-01-05T09:00:00Z", 101.8, 102.2, 101.4, 102.1, volume=160),
    ]
    return base


def main():
    bars = build_demo_bars()
    profile = compute_value_profile(bars, value_area_percent=0.70)
    fp = FootprintSnapshot(timestamp=bars[-1].timestamp, bid_vol=40.0, ask_vol=90.0)
    delta = compute_delta(fp)
    vwap = compute_vwap(bars)
    value_context = classify_value_context(None, profile)
    cfg = OrderflowConfig(
        market=MarketConfig(symbol="NASDAQ100", tick_size=0.01, point_value=1.0, multiplier=1.0, timezone="UTC", exchange_timezone="America/New_York", session_hours_utc=None, value_area_percent=0.70),
        risk=RiskConfig(account_equity=100000.0, risk_per_trade=0.01, daily_loss_limit=2000.0, max_drawdown=0.2, max_concurrent_positions=1, aggregate_risk_limit=0.05, max_adds=0, max_order_qty=100.0, min_order_qty=1.0, lot_step=1.0, stop_buffer_ticks=1.0, stop_rounding="tick", allow_pyramiding=False, allow_averaging_down=False),
        directional_drift=StrategyConfig(enabled=True, require_value_context=True, require_delta_confirmation=True),
    )
    rm = RiskManager(cfg.risk.__dict__)
    size = rm.size_position(entry=103.0, stop=101.0, point_value=1.0, multiplier=1.0)
    print({
        "profile_poc": profile.poc,
        "value_context": value_context,
        "delta": delta,
        "vwap": vwap,
        "suggested_quantity": size,
    })


if __name__ == "__main__":
    main()
