"""Bar-by-bar signal engine (usable unchanged for backtests and live paper trading).

Per closed bar, in this fixed order (this is what prevents look-ahead/repainting):
  1. validate + append the bar to history
  2. advance every EXISTING zone with this bar (zones detected on this bar are not yet in play)
  3. run confirmation filters for zones inside their retest window
  4. resolve duplicates / overlaps / long-vs-short conflicts -> at most ONE signal per bar
  5. detect NEW zones from this bar's footprint (or proxy) -> they can only be retested from the next bar
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Mapping, Optional, Union

import numpy as np
import pandas as pd

from .config import DataMode, SignalConfig
from .filters import confirm_entry
from .imbalance import clean_footprint, detect_proxy_stack, detect_stacked_imbalances
from .models import (Bar, DataSource, DataValidationError, History, Signal, TERMINAL, Zone,
                     ZoneDirection, ZoneStatus)
from .signals import compute_levels, generate_signal
from .zones import build_imbalance_zones, update_zone_status, zones_overlap

REQUIRED_BAR_KEYS = ("timestamp", "open", "high", "low", "close")


class SignalEngine:
    def __init__(self, config: Optional[SignalConfig] = None):
        self.cfg = config or SignalConfig()
        self.history = History(self.cfg.history_limit)
        self.zones: Dict[str, Zone] = {}          # every zone ever created (for analysis)
        self._active: List[Zone] = []
        self.signals: List[Signal] = []
        self.diagnostics: Counter = Counter()
        self._idx = -1
        self._last_ts: Optional[pd.Timestamp] = None
        self._emitted: set = set()
        self._bar_period = pd.Timedelta(self.cfg.bar_period)
        self._atr: Optional[float] = None
        self._tr_seed: List[float] = []
        self._prev_close: Optional[float] = None

    # ------------------------------------------------------------------ input
    def _parse_bar(self, raw: Union[Mapping, pd.Series]) -> Optional[Bar]:
        missing = [k for k in REQUIRED_BAR_KEYS if k not in raw]
        if missing:
            raise DataValidationError(f"bar missing keys: {missing}")
        try:
            ts = pd.Timestamp(raw["timestamp"])
        except Exception as e:                       # noqa: BLE001
            raise DataValidationError(f"bad timestamp {raw['timestamp']!r}") from e
        if pd.isna(ts):
            raise DataValidationError("timestamp is NaT")
        if self._last_ts is not None:
            try:
                out_of_order = ts <= self._last_ts
            except TypeError as e:
                raise DataValidationError("mixed tz-aware and tz-naive timestamps") from e
            if out_of_order:
                raise DataValidationError(f"timestamps must be strictly increasing ({ts} <= {self._last_ts})")
        try:
            o, h, l, c = (float(raw[k]) for k in ("open", "high", "low", "close"))
            v = float(raw["volume"]) if "volume" in raw and raw["volume"] is not None else float("nan")
        except (TypeError, ValueError):
            self.diagnostics["skipped_bad_bar"] += 1
            return None
        eps = 1e-9
        if (not np.isfinite([o, h, l, c]).all() or l <= 0 or h < l
                or not (l - eps <= o <= h + eps) or not (l - eps <= c <= h + eps)
                or (np.isfinite(v) and v < 0)):
            self.diagnostics["skipped_bad_bar"] += 1
            return None
        return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, idx=self._idx + 1)

    def _update_atr(self, b: Bar) -> None:
        p = self.cfg.proxy.atr_period
        pc = self._prev_close
        tr = b.high - b.low if pc is None else max(b.high - b.low, abs(b.high - pc), abs(b.low - pc))
        self._prev_close = b.close
        if self._atr is None:
            self._tr_seed.append(tr)
            if len(self._tr_seed) >= p:
                self._atr = float(np.mean(self._tr_seed[-p:]))
        else:
            self._atr = (self._atr * (p - 1) + tr) / p

    # ---------------------------------------------------------------- main API
    def on_bar(self, raw_bar: Union[Mapping, pd.Series],
               footprint: Optional[pd.DataFrame] = None) -> List[Signal]:
        """Process ONE closed bar. ``footprint`` = long-form DataFrame
        (price, bid_vol, ask_vol) for that same bar, or None."""
        b = self._parse_bar(raw_bar)
        if b is None:
            return []
        self._idx, self._last_ts = b.idx, b.timestamp

        grid = None
        if footprint is not None:
            grid, issues = clean_footprint(footprint, self.cfg.tick_size, (b.low, b.high))
            for i in issues:
                self.diagnostics[i.split(":")[0]] += 1
            if grid is not None:
                b.has_footprint = True
                b.bar_delta = float(grid["ask_vol"].sum() - grid["bid_vol"].sum())

        self.history.append(b)
        self._update_atr(b)
        close_time = b.timestamp + self._bar_period

        emitted = self._process_zones(b, close_time)
        self._detect_new_zones(b, grid)
        self._active = [z for z in self._active if z.status not in TERMINAL]
        self.signals.extend(emitted)
        return emitted

    def run(self, bars: pd.DataFrame,
            footprints: Optional[Union[pd.DataFrame, Mapping[pd.Timestamp, pd.DataFrame]]] = None
            ) -> List[Signal]:
        """Convenience wrapper: feed a DataFrame candle by candle.
        ``footprints``: long DataFrame with a 'timestamp' column (matching bar open times)
        plus price/bid_vol/ask_vol, or a {timestamp: DataFrame} mapping."""
        fp_map: Mapping = {}
        if isinstance(footprints, pd.DataFrame):
            if "timestamp" not in footprints.columns:
                raise DataValidationError("footprints DataFrame needs a 'timestamp' column")
            fp_map = {pd.Timestamp(k): g for k, g in footprints.groupby("timestamp")}
        elif footprints:
            fp_map = {pd.Timestamp(k): v for k, v in footprints.items()}
        frame = bars.reset_index() if "timestamp" not in bars.columns else bars
        out: List[Signal] = []
        for row in frame.to_dict("records"):
            out.extend(self.on_bar(row, fp_map.get(pd.Timestamp(row["timestamp"]))))
        return out

    # --------------------------------------------------------------- internals
    def _process_zones(self, b: Bar, close_time: pd.Timestamp) -> List[Signal]:
        candidates = []
        for z in list(self._active):
            if z.detected_idx >= b.idx:
                continue
            update_zone_status(z, b, self.cfg)
            if z.status != ZoneStatus.RETESTED:
                continue
            levels = compute_levels(z, b, self.history, self.cfg)
            if levels is None:
                self.diagnostics["degenerate_risk"] += 1
                continue
            res = confirm_entry(z, b, self.history, close_time, levels, self.cfg)
            if res.passed:
                candidates.append((z, levels, res))
            else:
                self.diagnostics["confirmation_failed"] += 1
        if not candidates:
            return []
        return self._resolve(candidates, b, close_time)

    def _resolve(self, candidates, b: Bar, close_time: pd.Timestamp) -> List[Signal]:
        chosen = {}
        for d in (ZoneDirection.BULLISH, ZoneDirection.BEARISH):
            group = [c for c in candidates if c[0].direction == d]
            if not group:
                continue
            group.sort(key=lambda c: (-c[0].n_levels, -c[0].detected_idx, c[0].zone_id))
            best = group[0]
            for other in group[1:]:
                if zones_overlap(best[0], other[0]):
                    other[0].set_status(ZoneStatus.SUPERSEDED, b.timestamp,
                                        f"overlaps stronger zone {best[0].zone_id}")
            chosen[d] = best

        if len(chosen) == 2:
            pol = self.cfg.conflict_policy
            self.diagnostics["long_short_conflict"] += 1
            if pol == "skip_both":
                return []
            bu, be = chosen[ZoneDirection.BULLISH], chosen[ZoneDirection.BEARISH]
            if pol == "prefer_newest":
                key = lambda c: (-c[0].detected_idx, -c[0].n_levels, c[0].zone_id)    # noqa: E731
            else:
                key = lambda c: (-c[0].n_levels, -c[0].detected_idx, c[0].zone_id)    # noqa: E731
            winner = sorted([bu, be], key=key)[0]
            chosen = {winner[0].direction: winner}

        out: List[Signal] = []
        for z, levels, res in chosen.values():
            sig = generate_signal(z, b, close_time, levels, res, self.cfg)
            if sig.signal_id in self._emitted:               # belt and braces
                self.diagnostics["duplicate_signal_blocked"] += 1
                continue
            self._emitted.add(sig.signal_id)
            z.signals_emitted += 1
            if z.signals_emitted >= self.cfg.max_signals_per_zone:
                z.set_status(ZoneStatus.TRIGGERED, b.timestamp, f"signal {sig.signal_id}")
            else:    # allow another signal, but only after a fresh departure + retest
                z.set_status(ZoneStatus.VALID, b.timestamp, f"signal {sig.signal_id}; re-arming")
                z.departed, z.retest_idx, z.retest_at, z.extreme_since_retest = False, None, None, None
                z.retest_count = 0
            out.append(sig)
        return out

    def _detect_new_zones(self, b: Bar, grid: Optional[pd.DataFrame]) -> None:
        tick, cfg = self.cfg.tick_size, self.cfg
        if cfg.data_mode == DataMode.FOOTPRINT:
            if grid is None:
                self.diagnostics["missing_footprint"] += 1
                return
            if len(grid) < cfg.imbalance.min_stack_levels + 1:
                self.diagnostics["insufficient_footprint_levels"] += 1
                return
            stacks = detect_stacked_imbalances(grid, cfg.imbalance, tick)
        else:
            a = self.history.arrays()
            pv = cfg.proxy.volume_period
            prior = a["v"][:-1][-pv:]
            avg_v = float(prior.mean()) if len(prior) >= pv and np.isfinite(prior).all() else None
            s = detect_proxy_stack(b.open, b.high, b.low, b.close, b.volume, self._atr, avg_v, cfg.proxy, tick)
            stacks = [s] if s else []
        for z in build_imbalance_zones(stacks, b.timestamp, b.idx, b.bar_delta, tick):
            if z.zone_id in self.zones:
                continue
            self.zones[z.zone_id] = z
            self._active.append(z)

    # ----------------------------------------------------------------- reports
    def signals_frame(self) -> pd.DataFrame:
        return pd.DataFrame([s.to_dict() for s in self.signals])

    def zones_frame(self) -> pd.DataFrame:
        rows = [{"zone_id": z.zone_id, "direction": z.direction.value, "lower": z.lower, "upper": z.upper,
                 "n_levels": z.n_levels, "detected_at": z.detected_at, "status": z.status.value,
                 "source": z.source.value, "retests": z.retest_count, "signals": z.signals_emitted,
                 "stack_delta": z.stack_delta, "bar_delta": z.bar_delta} for z in self.zones.values()]
        return pd.DataFrame(rows)
