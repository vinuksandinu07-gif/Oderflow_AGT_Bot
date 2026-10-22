"""Unit tests. Run:  python -m unittest discover -s tests -v   (pytest also works)

Each test documents the scenario and the EXPECTED output.
"""
import copy
import os
import sys
import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from sib_signals import (DataMode, DataValidationError, Direction, FilterConfig, ImbalanceConfig,
                         InvalidationMode, RetestConfig, RetestMode, SignalConfig, SignalEngine,
                         ZoneStatus, DataSource, clean_footprint, detect_stacked_imbalances,
                         CandleFilter, DeltaFilter, SessionFilter, StructureFilter, RiskConfig,
                         ProxyConfig)
from sib_signals.filters import confirmed_swings, htf_bias
from sib_signals.models import History, Bar
import synthetic as S


def cfg(**kw) -> SignalConfig:
    return SignalConfig(tick_size=S.TICK, **kw)


def one_zone(engine):
    assert len(engine.zones) == 1, engine.zones
    return next(iter(engine.zones.values()))


# ======================================================================================
class TestStackDetection(unittest.TestCase):
    def grid(self, bid, ask, p0=2000.0):
        g, _ = clean_footprint(S.fp(p0, bid, ask), S.TICK)
        return g

    def test_bullish_stack_boundaries(self):
        """3 buy imbalances on levels 1..3 -> ONE bullish stack [2000.1, 2000.3], 3 levels."""
        st = detect_stacked_imbalances(self.grid([5] * 5, [5, 40, 40, 40, 5]), ImbalanceConfig(), S.TICK)
        self.assertEqual(len(st), 1)
        s = st[0]
        self.assertEqual((s.lower, s.upper, s.n_levels), (2000.1, 2000.3, 3))
        self.assertEqual(s.direction.value, "bullish")
        self.assertEqual(s.source, DataSource.FOOTPRINT)

    def test_bearish_stack(self):
        st = detect_stacked_imbalances(self.grid([5, 40, 40, 40, 5], [5] * 5), ImbalanceConfig(), S.TICK)
        self.assertEqual([(x.direction.value, x.lower, x.upper) for x in st], [("bearish", 2000.1, 2000.3)])

    def test_ratio_is_configurable(self):
        # ask 40 vs bid 15 below = 2.67:1 -> fails at 3:1, passes at 2:1
        g = self.grid([15] * 5, [5, 40, 40, 40, 5])
        self.assertEqual(detect_stacked_imbalances(g, ImbalanceConfig(ratio=3.0), S.TICK), [])
        self.assertEqual(len(detect_stacked_imbalances(g, ImbalanceConfig(ratio=2.0), S.TICK)), 1)

    def test_min_stack_length_and_min_volume(self):
        g = self.grid([5] * 5, [5, 40, 40, 5, 5])             # only 2 consecutive levels
        self.assertEqual(detect_stacked_imbalances(g, ImbalanceConfig(min_stack_levels=3), S.TICK), [])
        self.assertEqual(len(detect_stacked_imbalances(g, ImbalanceConfig(min_stack_levels=2), S.TICK)), 1)
        g2 = self.grid([1] * 5, [1, 8, 8, 8, 1])              # ratio ok, but volume below min_level_volume=10
        self.assertEqual(detect_stacked_imbalances(g2, ImbalanceConfig(min_level_volume=10), S.TICK), [])

    def test_edges_and_zero_bid(self):
        # Bottom level has no lower neighbour inside the bar -> cannot be a buying imbalance.
        g = self.grid([0] * 4, [50, 50, 50, 50])
        st = detect_stacked_imbalances(g, ImbalanceConfig(min_stack_levels=3), S.TICK)
        self.assertEqual((st[0].lower, st[0].upper), (2000.1, 2000.3))
        # zero bid below counts by default, but not when zero_denominator_counts=False
        self.assertEqual(detect_stacked_imbalances(g, ImbalanceConfig(zero_denominator_counts=False), S.TICK), [])


# ======================================================================================
class TestLifecycle(unittest.TestCase):
    def test_valid_bullish_stack_then_successful_retest_gives_LONG(self):
        """Expected: exactly one LONG at bar 2. entry=2002.8 (bar close), stop=1999.9
        (zone low 2000.1 - 2 ticks), target=2002.8+2*2.9=2008.6, zone TRIGGERED."""
        e = SignalEngine(cfg())
        sigs = S.feed(e, [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()])
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertEqual(s.direction, Direction.LONG)
        self.assertEqual((s.zone_lower, s.zone_upper), (2000.1, 2000.3))
        self.assertAlmostEqual(s.entry_price, 2002.8)
        self.assertAlmostEqual(s.stop_loss, 1999.9)
        self.assertAlmostEqual(s.invalidation_level, 2000.1)
        self.assertAlmostEqual(s.take_profit, 2008.6)
        self.assertAlmostEqual(s.risk_reward, 2.0)
        self.assertEqual(s.timestamp, S.ts(2) + S.PERIOD)            # known at the bar CLOSE
        self.assertEqual(s.data_source, DataSource.FOOTPRINT)
        self.assertFalse(s.is_proxy)
        self.assertIn("candle_close(outside)", s.conditions_satisfied)
        self.assertTrue(s.signal_id.startswith("SIB-"))
        self.assertEqual(one_zone(e).status, ZoneStatus.TRIGGERED)

    def test_valid_bearish_stack_then_successful_retest_gives_SHORT(self):
        """Expected: one SHORT at bar 2. stop=2000.5 (zone high 2000.3 + 2 ticks), entry 1997.2,
        target=1997.2-2*3.3=1990.6."""
        e = SignalEngine(cfg())
        sigs = S.feed(e, [S.bear_bar0(), S.bear_departure(), S.bear_retest_confirmed()])
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertEqual(s.direction, Direction.SHORT)
        self.assertAlmostEqual(s.entry_price, 1997.2)
        self.assertAlmostEqual(s.stop_loss, 2000.5)
        self.assertAlmostEqual(s.take_profit, 1990.6)
        self.assertAlmostEqual(s.invalidation_level, 2000.3)

    def test_price_never_returns_zone_expires_no_signal(self):
        """Expected: no signal; zone EXPIRED once older than max_zone_age_bars (=4)."""
        e = SignalEngine(cfg(retest=RetestConfig(max_zone_age_bars=4)))
        items = [S.bull_bar0()] + [(S.bar(i, 2003 + i, 2004 + i, 2002.5 + i, 2003.5 + i), None) for i in range(1, 9)]
        self.assertEqual(S.feed(e, items), [])
        self.assertEqual(one_zone(e).status, ZoneStatus.EXPIRED)

    def test_zone_invalidated_before_retest_no_signal(self):
        """A bar that closes BELOW the zone (1999.8 < 2000.1) invalidates it. Even though that bar
        also trades through the zone it is NOT a retest. Expected: INVALIDATED, no signal, and later
        retest-looking bars cannot revive it."""
        e = SignalEngine(cfg())
        items = [S.bull_bar0(), S.bull_departure(),
                 (S.bar(2, 2002.4, 2002.5, 1999.5, 1999.8), None),
                 (S.bar(3, 1999.8, 2003.0, 1999.7, 2002.9), None)]
        self.assertEqual(S.feed(e, items), [])
        self.assertEqual(one_zone(e).status, ZoneStatus.INVALIDATED)

    def test_wick_invalidation_mode_is_stricter_than_close_mode(self):
        """Bar wicks to 2000.0 (below zone low 2000.1) but closes back up bullish.
        CLOSE mode: valid retest -> LONG.   WICK mode: zone invalidated -> no signal."""
        items = [S.bull_bar0(), S.bull_departure(), (S.bar(2, 2002.4, 2002.9, 2000.0, 2002.8), None)]
        close_sigs = S.feed(SignalEngine(cfg()), items)
        self.assertEqual(len(close_sigs), 1)
        self.assertAlmostEqual(close_sigs[0].stop_loss, 1999.8)          # stop sits beyond the wick (2000.0 - 0.2)
        e = SignalEngine(cfg(retest=RetestConfig(invalidation_mode=InvalidationMode.WICK)))
        self.assertEqual(S.feed(e, items), [])
        self.assertEqual(one_zone(e).status, ZoneStatus.INVALIDATED)

    def test_retest_without_confirmation_gives_no_signal(self):
        """Retest bar is a BEARISH candle -> candle filter fails; the window (1 bar) lapses and with
        max_retests=1 the zone is EXHAUSTED. Expected: no signal."""
        e = SignalEngine(cfg(retest=RetestConfig(confirm_window_bars=1)))
        items = [S.bull_bar0(), S.bull_departure(),
                 (S.bar(2, 2002.4, 2002.5, 2000.2, 2000.5), None),        # touches zone, bearish candle
                 (S.bar(3, 2002.0, 2002.2, 2001.0, 2001.5), None),        # bearish, no confirmation
                 (S.bar(4, 2002.0, 2002.2, 2001.0, 2001.5), None)]
        self.assertEqual(S.feed(e, items), [])
        self.assertEqual(one_zone(e).status, ZoneStatus.EXHAUSTED)

    def test_confirmation_arriving_after_retest_inside_window(self):
        """Retest bar unconfirmed, next bar is a bullish close above the zone (window=2).
        Expected: LONG on bar 3, not bar 2."""
        e = SignalEngine(cfg())
        items = [S.bull_bar0(), S.bull_departure(),
                 (S.bar(2, 2002.4, 2002.5, 2000.2, 2000.5), None),
                 (S.bar(3, 2000.6, 2003.0, 2000.5, 2002.9), None)]
        sigs = S.feed(e, items)
        self.assertEqual([s.bar_timestamp for s in sigs], [S.ts(3)])

    def test_duplicate_signals_prevented(self):
        """After the first LONG, further retests of the same zone must not signal again
        (max_signals_per_zone=1). Expected: still exactly 1 signal, unique IDs."""
        e = SignalEngine(cfg())
        items = [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed(),
                 (S.bar(3, 2002.8, 2003.5, 2002.5, 2003.0), None),
                 (S.bar(4, 2002.4, 2002.9, 2000.2, 2002.8), None),
                 (S.bar(5, 2002.4, 2002.9, 2000.2, 2002.8), None)]
        sigs = S.feed(e, items)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(len({s.signal_id for s in e.signals}), len(e.signals))

    def test_multiple_signals_per_zone_need_fresh_departure_and_retest(self):
        """max_signals_per_zone=2: second signal only after price leaves and comes back."""
        e = SignalEngine(cfg(max_signals_per_zone=2))
        items = [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed(),
                 (S.bar(3, 2002.4, 2002.9, 2000.2, 2002.8), None),         # immediate re-touch: no new departure
                 (S.bar(4, 2002.8, 2003.5, 2002.5, 2002.6), None),         # departs again
                 (S.bar(5, 2002.4, 2002.9, 2000.2, 2002.8), None)]         # fresh retest -> 2nd signal
        sigs = S.feed(e, items)
        self.assertEqual([s.bar_timestamp for s in sigs], [S.ts(2), S.ts(5)])
        self.assertEqual(one_zone(e).status, ZoneStatus.TRIGGERED)

    def test_zone_cannot_be_retested_on_its_own_detection_bar(self):
        """The bar that reveals the stack never also triggers on it."""
        e = SignalEngine(cfg(retest=RetestConfig(require_departure=False)))
        b, f = S.bull_bar0()
        self.assertEqual(e.on_bar(b, f), [])
        self.assertEqual(one_zone(e).retest_count, 0)

    def test_overlapping_same_direction_zones_yield_one_signal(self):
        """Two overlapping bullish zones both confirm on bar 3. Expected: ONE signal (for the
        newer zone, tie on size) and the older zone SUPERSEDED."""
        e = SignalEngine(cfg())
        items = [S.bull_bar0(),
                 (S.bar(1, 2000.3, 2003.0, 2000.2, 2002.8), S.bullish_fp(2000.2)),     # zone B = [2000.3, 2000.5]
                 (S.bar(2, 2002.8, 2003.5, 2002.5, 2002.6), None),
                 (S.bar(3, 2002.4, 2002.9, 2000.2, 2002.8), None)]
        sigs = S.feed(e, items)
        self.assertEqual(len(sigs), 1)
        zs = sorted(e.zones.values(), key=lambda z: z.detected_idx)
        self.assertEqual((zs[0].status, zs[1].status), (ZoneStatus.SUPERSEDED, ZoneStatus.TRIGGERED))
        self.assertEqual(sigs[0].zone_id, zs[1].zone_id)

    def _conflict_items(self):
        return [S.bull_bar0(),
                (S.bar(1, 2004.0, 2010.4, 2004.0, 2009.0), S.bearish_fp(2010.0)),      # bearish zone [2010.1, 2010.3]
                (S.bar(2, 2005.0, 2006.0, 2004.5, 2005.5), None),                       # departs both zones
                (S.bar(3, 2005.0, 2010.2, 2000.2, 2005.0), None)]                       # touches BOTH zones

    def test_long_short_conflict_is_deterministic(self):
        """Candle filter off so both zones confirm on the same bar.
        skip_both -> no signal; prefer_newest -> SHORT (newer zone); prefer_larger_stack ties -> newest."""
        base = dict(filters=FilterConfig(candle=CandleFilter(enabled=False)))
        e = SignalEngine(cfg(**base))
        self.assertEqual(S.feed(e, self._conflict_items()), [])
        self.assertEqual(e.diagnostics["long_short_conflict"], 1)
        for pol in ("prefer_newest", "prefer_larger_stack"):
            sigs = S.feed(SignalEngine(cfg(conflict_policy=pol, **base)), self._conflict_items())
            self.assertEqual([s.direction for s in sigs], [Direction.SHORT], pol)


# ======================================================================================
class TestRetestModes(unittest.TestCase):
    def run_with(self, retest_bar, **retest_kw):
        e = SignalEngine(cfg(retest=RetestConfig(**retest_kw),
                             filters=FilterConfig(candle=CandleFilter(enabled=False))))
        return S.feed(e, [S.bull_bar0(), S.bull_departure(), (retest_bar, None)]), e

    def test_touch_vs_depth_vs_enter_and_close_out(self):
        shallow = S.bar(2, 2002.4, 2002.9, 2000.3, 2002.8)        # only touches zone high 2000.3
        deep = S.bar(2, 2002.4, 2002.9, 2000.1, 2002.8)           # reaches the full depth
        closes_inside = S.bar(2, 2002.4, 2002.5, 2000.2, 2000.25) # enters, closes inside zone
        self.assertEqual(len(self.run_with(shallow, mode=RetestMode.TOUCH)[0]), 1)
        self.assertEqual(len(self.run_with(shallow, mode=RetestMode.DEPTH, depth_fraction=0.5)[0]), 0)
        self.assertEqual(len(self.run_with(deep, mode=RetestMode.DEPTH, depth_fraction=0.5)[0]), 1)
        self.assertEqual(len(self.run_with(closes_inside, mode=RetestMode.ENTER_AND_CLOSE_OUT)[0]), 0)
        self.assertEqual(len(self.run_with(shallow, mode=RetestMode.ENTER_AND_CLOSE_OUT)[0]), 1)

    def test_departure_requirement(self):
        """Without prior departure a touch is ignored; with require_departure=False it counts."""
        touch = (S.bar(1, 2002.8, 2003.0, 2000.2, 2002.9), None)           # touches right after detection (bullish close)
        e1 = SignalEngine(cfg())
        self.assertEqual(S.feed(e1, [S.bull_bar0(), touch]), [])
        e2 = SignalEngine(cfg(retest=RetestConfig(require_departure=False)))
        self.assertEqual(len(S.feed(e2, [S.bull_bar0(), touch])), 1)


# ======================================================================================
class TestFilters(unittest.TestCase):
    ITEMS = lambda self: [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()]

    def test_each_filter_is_independently_switchable(self):
        base = S.feed(SignalEngine(cfg()), self.ITEMS())
        self.assertEqual(len(base), 1)
        # candle filter off -> still LONG (and no longer listed)
        s = S.feed(SignalEngine(cfg(filters=FilterConfig(candle=CandleFilter(enabled=False)))), self.ITEMS())
        self.assertEqual(s[0].conditions_satisfied, ())
        # session filter: bar closes 08:45 UTC -> blocked by 12-20 window, allowed by 8-9
        blocked = SignalConfig(tick_size=S.TICK, filters=FilterConfig(session=SessionFilter(True, ((12, 20),))))
        allowed = SignalConfig(tick_size=S.TICK, filters=FilterConfig(session=SessionFilter(True, ((8, 9),))))
        self.assertEqual(S.feed(SignalEngine(blocked), self.ITEMS()), [])
        self.assertEqual(len(S.feed(SignalEngine(allowed), self.ITEMS())), 1)
        # min RR with swing targets and no swing available -> blocked (reported, not guessed)
        from sib_signals import RRFilter
        c = SignalConfig(tick_size=S.TICK, risk=RiskConfig(tp_mode="swing"),
                         filters=FilterConfig(rr=RRFilter(True, 1.5)))
        self.assertEqual(S.feed(SignalEngine(c), self.ITEMS()), [])

    def test_volume_delta_filter_uses_genuine_footprint_only(self):
        """Delta on the confirmation bar: positive -> LONG passes, negative -> blocked,
        missing -> blocked (on_missing_data='fail') or skipped-and-reported ('skip')."""
        fcfg = lambda **k: cfg(filters=FilterConfig(delta=DeltaFilter(True), **k))     # noqa: E731
        pos = S.fp(2000.2, [5, 5, 5], [30, 30, 30])
        neg = S.fp(2000.2, [30, 30, 30], [5, 5, 5])
        for fpx, expected in ((pos, 1), (neg, 0), (None, 0)):
            items = [S.bull_bar0(), S.bull_departure(), (S.bull_retest_confirmed()[0], fpx)]
            self.assertEqual(len(S.feed(SignalEngine(fcfg()), items)), expected)
        items = [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()]
        sk = S.feed(SignalEngine(fcfg(on_missing_data="skip")), items)
        self.assertEqual(len(sk), 1)
        self.assertEqual(sk[0].conditions_skipped, ("volume_delta[no_footprint]",))

    def test_confirmed_swings_need_n_later_bars(self):
        """A swing high is only confirmed after n later bars -> the last bar can never be one."""
        h = np.array([1, 2, 3, 2, 1, 2, 5.0])      # 5.0 is last bar: not confirmed
        self.assertEqual(confirmed_swings(h, 2, "high", 100), [3.0])
        self.assertEqual(confirmed_swings(np.array([1, 2, 3, 2, 1, 2, 5, 4, 3.0]), 2, "high", 100), [5.0, 3.0])

    def test_structure_filter(self):
        """BOS: the confirmation close must exceed the last CONFIRMED swing high (2003.5 on bar 1,
        confirmed one bar later with swing_n=1). Close 2002.8 -> blocked; close 2003.9 -> passes."""
        c = cfg(filters=FilterConfig(structure=StructureFilter(True, swing_n=1, lookback_bars=50)))
        blocked = S.feed(SignalEngine(c), [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()])
        self.assertEqual(blocked, [])
        items = [S.bull_bar0(), S.bull_departure(),
                 (S.bar(2, 2002.4, 2002.5, 2000.2, 2000.5), None),      # retest, bearish candle: unconfirmed
                 (S.bar(3, 2000.6, 2004.0, 2000.5, 2003.9), None)]      # closes above swing high 2003.5
        sigs = S.feed(SignalEngine(c), items)
        self.assertEqual([s.bar_timestamp for s in sigs], [S.ts(3)])
        self.assertIn("structure_bos", sigs[0].conditions_satisfied)

    def test_htf_bias_uses_only_completed_candles(self):
        h = History(1000)
        idx = pd.date_range(S.BASE, periods=40, freq="15min")
        for i, t in enumerate(idx):
            h.append(Bar(t, 100 + i, 101 + i, 99 + i, 100.5 + i, 1.0, i))
        # 40 bars = 10h of 15m bars. At the close of the last bar, 1h buckets complete.
        close_time = idx[-1] + pd.Timedelta("15min")
        self.assertEqual(htf_bias(h, close_time, pd.Timedelta("15min"), "1h", 3), 1)      # rising -> bullish
        # not enough completed HTF candles -> None (never guesses)
        self.assertIsNone(htf_bias(h, close_time, pd.Timedelta("15min"), "4h", 20))


# ======================================================================================
class TestDataHandling(unittest.TestCase):
    def test_missing_footprint_creates_no_zone_and_is_reported(self):
        e = SignalEngine(cfg())
        self.assertEqual(e.on_bar(S.bull_bar0()[0], None), [])
        self.assertEqual(len(e.zones), 0)
        self.assertEqual(e.diagnostics["missing_footprint"], 1)

    def test_insufficient_footprint_levels(self):
        e = SignalEngine(cfg())
        e.on_bar(S.bar(0, 2000.0, 2000.2, 2000.0, 2000.1), S.fp(2000.0, [5, 5, 5], [5, 40, 40]))
        self.assertEqual(len(e.zones), 0)
        self.assertEqual(e.diagnostics["insufficient_footprint_levels"], 1)

    def test_malformed_footprint_rows_are_dropped(self):
        f = S.bullish_fp(2000.0)
        f.loc[0, "bid_vol"] = np.nan
        f.loc[4, "ask_vol"] = -3
        grid, issues = clean_footprint(f, S.TICK)
        self.assertEqual(list(grid.index), [20001, 20002, 20003])
        self.assertTrue(any(i.startswith("footprint_bad_rows_dropped") for i in issues))
        with self.assertRaises(DataValidationError):
            clean_footprint(f.drop(columns=["ask_vol"]), S.TICK)

    def test_footprint_rows_outside_bar_range_dropped(self):
        f = pd.concat([S.bullish_fp(2000.0), S.fp(2050.0, [5], [5])])
        grid, issues = clean_footprint(f, S.TICK, (2000.0, 2003.0))
        self.assertEqual(int(grid.index.max()), 20004)
        self.assertTrue(any("outside_bar_range" in i for i in issues))

    def test_bad_bars_skipped_structural_problems_raise(self):
        e = SignalEngine(cfg())
        self.assertEqual(e.on_bar(S.bar(0, 2000, 1999, 2001, 2000), None), [])          # high < low
        self.assertEqual(e.on_bar(S.bar(0, 2000, 2001, 1999, float("nan")), None), [])
        self.assertEqual(e.diagnostics["skipped_bad_bar"], 2)
        e.on_bar(S.bar(5, 2000, 2001, 1999, 2000), None)
        with self.assertRaises(DataValidationError):
            e.on_bar(S.bar(5, 2000, 2001, 1999, 2000), None)                              # same timestamp
        with self.assertRaises(DataValidationError):
            e.on_bar({"timestamp": S.ts(9), "open": 1}, None)                             # missing keys

    def test_run_wrapper_with_long_footprint_frame(self):
        items = [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()]
        bars = pd.DataFrame([b for b, _ in items])
        fpf = S.bullish_fp(2000.0).assign(timestamp=S.ts(0))
        sigs = SignalEngine(cfg()).run(bars, fpf)
        self.assertEqual([s.direction for s in sigs], [Direction.LONG])


# ======================================================================================
class TestNoLookahead(unittest.TestCase):
    def test_future_bars_cannot_change_past_signals(self):
        """Replace everything after the signal bar with garbage -> identical signals up to that bar."""
        items = [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()]
        tail_a = [(S.bar(3 + i, 2002.8, 2003.5, 2002.5, 2003.0), None) for i in range(5)]
        tail_b = [(S.bar(3 + i, 2100 + i, 2200 + i, 1900 - i, 2000 + 7 * i), None) for i in range(5)]
        a = S.feed(SignalEngine(cfg()), items + tail_a)
        b = S.feed(SignalEngine(cfg()), items + tail_b)
        self.assertEqual([s.signal_id for s in a], [s.signal_id for s in b])
        self.assertEqual(a[0].entry_price, b[0].entry_price)

    def test_prefix_invariance_on_random_market(self):
        """Processing the first k bars yields EXACTLY the signals that the full run emitted by bar k
        (same IDs, same levels). This is the practical no-repaint / no-look-ahead check."""
        bars, fps = S.random_market(n=260, seed=11)
        c = cfg(imbalance=ImbalanceConfig(ratio=2.0, min_stack_levels=2, min_level_volume=10),
                filters=FilterConfig(candle=CandleFilter(True, "any"),
                                     structure=StructureFilter(True, 2, 60)),
                retest=RetestConfig(max_zone_age_bars=30))
        full = SignalEngine(c)
        full_sigs = full.run(bars, fps)
        self.assertGreaterEqual(len(full_sigs), 3, "test would be vacuous without signals")
        fmap = {k: g for k, g in fps.groupby("timestamp")}
        for k in range(20, len(bars), 17):
            part = SignalEngine(c)
            got = []
            for row in bars.iloc[:k].to_dict("records"):
                got.extend(part.on_bar(row, fmap.get(row["timestamp"])))
            expected = [s for s in full_sigs if s.bar_timestamp <= bars.iloc[k - 1]["timestamp"]]
            self.assertEqual([(s.signal_id, s.entry_price, s.stop_loss) for s in got],
                             [(s.signal_id, s.entry_price, s.stop_loss) for s in expected], f"k={k}")


# ======================================================================================
class TestProxyMode(unittest.TestCase):
    def test_proxy_zones_are_labelled_and_never_use_fake_delta(self):
        """OHLCV-only mode: impulse candle -> PRICE_ACTION_PROXY zone; the signal says so explicitly."""
        c = cfg(data_mode=DataMode.OHLCV_PROXY,
                proxy=ProxyConfig(impulse_atr_mult=1.5, volume_mult=1.5, atr_period=5, volume_period=5))
        e = SignalEngine(c)
        bars = [S.bar(i, 2000 + 0.1 * (i % 2), 2000.6, 1999.6, 2000.1, 1000) for i in range(8)]       # quiet
        bars.append(S.bar(8, 2000.0, 2004.1, 1999.9, 2004.0, 3000))                                    # impulse up
        bars.append(S.bar(9, 2004.0, 2005.0, 2003.2, 2004.6, 1000))                                    # departs zone
        bars.append(S.bar(10, 2003.0, 2004.8, 2001.0, 2004.5, 1000))                                   # retest + bullish close
        sigs = S.feed(e, [(b, None) for b in bars])
        z = one_zone(e)
        self.assertEqual(z.source, DataSource.PRICE_ACTION_PROXY)
        self.assertIsNone(z.ask_volume)
        self.assertEqual(len(sigs), 1)
        self.assertTrue(sigs[0].is_proxy)
        self.assertIn("APPROXIMATE", sigs[0].explanation)

    def test_footprint_mode_never_falls_back_to_proxy(self):
        e = SignalEngine(cfg())              # default FOOTPRINT mode, OHLCV only
        for i in range(30):
            e.on_bar(S.bar(i, 2000, 2001 + i, 1999, 2000 + i, 1000 * (1 + (i == 20))), None)
        self.assertEqual(len(e.zones), 0)
        self.assertEqual(e.diagnostics["missing_footprint"], 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
