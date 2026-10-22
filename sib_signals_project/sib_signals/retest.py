"""Retest / departure detection for a single zone and a single closed bar."""
from __future__ import annotations

from .config import RetestConfig, RetestMode
from .models import Bar, Zone, ZoneDirection


def has_departed(bar: Bar, zone: Zone) -> bool:
    """Bar lies entirely beyond the zone on the 'far from the zone' side:
    above a bullish zone / below a bearish zone."""
    if zone.direction == ZoneDirection.BULLISH:
        return bar.low > zone.upper
    return bar.high < zone.lower


def detect_retest(bar: Bar, zone: Zone, cfg: RetestConfig) -> bool:
    """Does this closed bar count as a retest under the configured definition?

    Invalidation is handled *before* this is called, so a bar that broke the
    zone never reaches here.
    """
    bullish = zone.direction == ZoneDirection.BULLISH
    overlaps = bar.low <= zone.upper and bar.high >= zone.lower
    if not overlaps:
        return False
    if cfg.mode == RetestMode.TOUCH:
        return True
    if cfg.mode == RetestMode.DEPTH:
        if bullish:
            return bar.low <= zone.upper - cfg.depth_fraction * zone.height
        return bar.high >= zone.lower + cfg.depth_fraction * zone.height
    if cfg.mode == RetestMode.ENTER_AND_CLOSE_OUT:
        return bar.close > zone.upper if bullish else bar.close < zone.lower
    raise ValueError(f"unknown retest mode {cfg.mode}")
