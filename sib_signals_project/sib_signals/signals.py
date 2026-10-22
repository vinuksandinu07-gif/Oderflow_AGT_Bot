"""Trade-level reference calculation and Signal construction."""
from __future__ import annotations

import hashlib
from typing import Optional

import pandas as pd

from .config import SignalConfig
from .filters import FilterResult, confirmed_swings
from .models import Bar, Direction, History, Signal, TradeLevels, Zone, ZoneDirection
from .zones import invalidation_level


def compute_levels(zone: Zone, bar: Bar, history: History, cfg: SignalConfig) -> Optional[TradeLevels]:
    """Reference entry/stop/target. Returns None if risk would be <= 0 (degenerate)."""
    tick, rk = cfg.tick_size, cfg.risk
    long = zone.direction == ZoneDirection.BULLISH
    entry = bar.close
    ext = zone.extreme_since_retest
    if long:
        edge = zone.lower if ext is None else min(zone.lower, ext)
        stop = edge - rk.stop_buffer_ticks * tick
        risk = entry - stop
    else:
        edge = zone.upper if ext is None else max(zone.upper, ext)
        stop = edge + rk.stop_buffer_ticks * tick
        risk = stop - entry
    if risk <= 0:
        return None

    tp: Optional[float] = None
    rr: Optional[float] = None
    if rk.tp_mode == "rr":
        tp = entry + rk.target_rr * risk if long else entry - rk.target_rr * risk
        rr = rk.target_rr
    elif rk.tp_mode == "swing":
        a = history.arrays(rk.swing_lookback)
        swings = confirmed_swings(a["h" if long else "l"], rk.swing_n,
                                  "high" if long else "low", rk.swing_lookback)
        beyond = [s for s in swings if (s > entry if long else s < entry)]
        if beyond:                      # most recent confirmed swing beyond entry
            tp = beyond[0]
            rr = abs(tp - entry) / risk
    return TradeLevels(entry=round(entry, 10), invalidation=round(invalidation_level(zone, cfg), 10),
                       stop_loss=round(stop, 10),
                       take_profit=None if tp is None else round(tp, 10), risk_reward=rr)


def make_signal_id(instrument: str, zone_id: str, bar_ts: pd.Timestamp, direction: Direction) -> str:
    raw = f"{instrument}|{zone_id}|{bar_ts.isoformat()}|{direction.value}"
    return "SIB-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def generate_signal(zone: Zone, bar: Bar, close_time: pd.Timestamp, levels: TradeLevels,
                    result: FilterResult, cfg: SignalConfig) -> Signal:
    direction = Direction.LONG if zone.direction == ZoneDirection.BULLISH else Direction.SHORT
    kind = "genuine footprint stacked imbalance" if zone.source.value == "footprint" \
        else "APPROXIMATE price-action proxy zone (not genuine order flow)"
    side = "buy" if direction == Direction.LONG else "sell"
    explanation = (
        f"{direction.value}: {zone.n_levels}-level {side} {kind} "
        f"[{zone.lower:.5g}-{zone.upper:.5g}] detected {zone.detected_at}; retested {zone.retest_at}; "
        f"confirmed by: {', '.join(result.satisfied) or 'no filters enabled'}"
        + (f"; skipped (no data): {', '.join(result.skipped)}" if result.skipped else "")
        + f". Entry ref {levels.entry:.5g} (confirmation-bar close), stop {levels.stop_loss:.5g}, "
        f"invalidation {levels.invalidation:.5g}"
        + (f", target {levels.take_profit:.5g} (RR {levels.risk_reward:.2f})" if levels.take_profit is not None
           else ", no target")
        + ". A signal is not an executed trade; fill at the next bar is not guaranteed."
    )
    return Signal(
        signal_id=make_signal_id(cfg.instrument, zone.zone_id, bar.timestamp, direction),
        timestamp=close_time, bar_timestamp=bar.timestamp, instrument=cfg.instrument,
        direction=direction, zone_id=zone.zone_id, zone_lower=zone.lower, zone_upper=zone.upper,
        entry_price=levels.entry, invalidation_level=levels.invalidation, stop_loss=levels.stop_loss,
        take_profit=levels.take_profit, risk_reward=levels.risk_reward, data_source=zone.source,
        conditions_satisfied=tuple(result.satisfied), conditions_skipped=tuple(result.skipped),
        explanation=explanation)
