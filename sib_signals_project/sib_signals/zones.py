"""Zone construction and lifecycle (validity, retest, invalidation, expiry)."""
from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from .config import SignalConfig, InvalidationMode
from .models import (Bar, DataSource, StackedImbalance, TERMINAL, Zone, ZoneDirection, ZoneStatus)
from .retest import detect_retest, has_departed


def build_imbalance_zones(stacks: Sequence[StackedImbalance], timestamp: pd.Timestamp, idx: int,
                          bar_delta: Optional[float], tick_size: float) -> List[Zone]:
    """Turn detected stacks into Zone records (detected at the CLOSE of bar ``idx``)."""
    zones = []
    for s in stacks:
        tag = "B" if s.direction == ZoneDirection.BULLISH else "S"
        src = "fp" if s.source == DataSource.FOOTPRINT else "px"
        zid = f"Z{idx}-{tag}-{src}-{round(s.lower / tick_size)}-{round(s.upper / tick_size)}"
        stack_delta = (s.ask_volume - s.bid_volume) if s.ask_volume is not None else None
        z = Zone(zone_id=zid, direction=s.direction, lower=s.lower, upper=s.upper,
                 detected_at=timestamp, detected_idx=idx, n_levels=s.n_levels, source=s.source,
                 ask_volume=s.ask_volume, bid_volume=s.bid_volume,
                 stack_delta=stack_delta, bar_delta=bar_delta)
        z.events.append((str(timestamp), "detected"))
        zones.append(z)
    return zones


def is_invalidated(zone: Zone, bar: Bar, cfg: SignalConfig) -> bool:
    buf = cfg.retest.invalidation_buffer_ticks * cfg.tick_size
    wick = cfg.retest.invalidation_mode == InvalidationMode.WICK
    if zone.direction == ZoneDirection.BULLISH:
        level = zone.lower - buf
        return (bar.low < level) if wick else (bar.close < level)
    level = zone.upper + buf
    return (bar.high > level) if wick else (bar.close > level)


def invalidation_level(zone: Zone, cfg: SignalConfig) -> float:
    buf = cfg.retest.invalidation_buffer_ticks * cfg.tick_size
    return zone.lower - buf if zone.direction == ZoneDirection.BULLISH else zone.upper + buf


def update_zone_status(zone: Zone, bar: Bar, cfg: SignalConfig) -> ZoneStatus:
    """Advance one zone by one CLOSED bar. Uses only this bar and zone state.

    Order of checks (fixed, so results are deterministic):
      1. confirmation-window timeout of an earlier retest
      2. invalidation (so a bar that breaks the zone can never count as a retest)
      3. expiry of untested zones
      4. departure tracking (a bar that departs cannot also be the retest)
      5. retest detection
      6. track the adverse extreme since the retest began (used for the stop)
    """
    if zone.status in TERMINAL:
        return zone.status
    rc = cfg.retest
    ts = bar.timestamp

    if zone.status == ZoneStatus.RETESTED and bar.idx - zone.retest_idx > rc.confirm_window_bars:
        if zone.retest_count >= rc.max_retests:
            zone.set_status(ZoneStatus.EXHAUSTED, ts, "retest never confirmed")
            return zone.status
        zone.set_status(ZoneStatus.VALID, ts, "confirmation window lapsed; awaiting a new retest")
        zone.departed, zone.retest_idx, zone.retest_at, zone.extreme_since_retest = False, None, None, None

    if is_invalidated(zone, bar, cfg):
        zone.set_status(ZoneStatus.INVALIDATED, ts, f"{rc.invalidation_mode.value} beyond far edge")
        return zone.status

    if zone.status == ZoneStatus.VALID and bar.idx - zone.detected_idx > rc.max_zone_age_bars:
        zone.set_status(ZoneStatus.EXPIRED, ts, f"older than {rc.max_zone_age_bars} bars")
        return zone.status

    if zone.status == ZoneStatus.VALID:
        if rc.require_departure and not zone.departed:
            if has_departed(bar, zone):
                zone.departed = True
                zone.events.append((str(ts), "price departed from zone"))
            return zone.status
        if detect_retest(bar, zone, rc):
            zone.retest_count += 1
            zone.retest_idx, zone.retest_at = bar.idx, ts
            zone.set_status(ZoneStatus.RETESTED, ts, f"retest #{zone.retest_count}")

    if zone.status == ZoneStatus.RETESTED:
        if zone.direction == ZoneDirection.BULLISH:
            zone.extreme_since_retest = bar.low if zone.extreme_since_retest is None \
                else min(zone.extreme_since_retest, bar.low)
        else:
            zone.extreme_since_retest = bar.high if zone.extreme_since_retest is None \
                else max(zone.extreme_since_retest, bar.high)
    return zone.status


def zones_overlap(a: Zone, b: Zone) -> bool:
    return a.lower <= b.upper and b.lower <= a.upper
