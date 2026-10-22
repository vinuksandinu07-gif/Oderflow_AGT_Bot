# Retest of a Stacked Imbalance: signal engine

Signal logic only. No execution, no position sizing, no broker code. Nothing here is a claim of profitability; every default is an initial test parameter that needs out-of-sample validation.

## 1. Rules implemented

1. **Stack.** On each closed bar's footprint (bid and ask volume per price level):
   - Buy imbalance at level L: `ask[L] >= ratio * bid[L-1]`
   - Sell imbalance at level L: `bid[L] >= ratio * ask[L+1]`
   - The imbalanced level also needs volume `>= min_level_volume`.
   - `min_stack_levels` consecutive imbalanced levels in the same direction form a zone.
2. **Zone.** Bullish zone = buy stack, bearish zone = sell stack. Boundaries are the lowest and highest stacked price levels. The zone stores direction, bounds, detection time, level count, stack volume and delta, and a status (VALID, RETESTED, TRIGGERED, INVALIDATED, EXPIRED, EXHAUSTED, SUPERSEDED).
3. **Retest.** Evaluated from the bar after detection. Modes: `TOUCH`, `DEPTH` (fraction of the zone), `ENTER_AND_CLOSE_OUT`. A zone expires after `max_zone_age_bars` if never retested.
4. **Invalidation.** Bullish zone: close below the lower edge (`CLOSE` mode) or any trade below it (`WICK` mode). Bearish: mirrored. Invalidation is checked before retest, so a bar that breaks the zone never counts as a retest.
5. **Confirmation.** Filters run on the retest bar or up to `confirm_window_bars` bars after it. Every enabled filter must pass.
6. **Signal.** LONG for bullish zones, SHORT for bearish zones, with reference entry, stop, invalidation level, target and explanation.

## 2. Ambiguities in the spec and the defaults I chose

| Ambiguity | Default | Config field |
|---|---|---|
| Does price have to leave the zone before a "return" counts? | Yes (a bar entirely beyond the zone) | `retest.require_departure` |
| Can the detection bar itself retest? | Never | fixed |
| Confirmation on the retest bar only, or later too? | Retest bar + 2 bars | `retest.confirm_window_bars` |
| How many failed retests are tolerated? | 1, then the zone is EXHAUSTED | `retest.max_retests` |
| Signals per zone | 1 | `max_signals_per_zone` |
| Zero opposing volume counts as an imbalance? | Yes, if the volume minimum is met | `imbalance.zero_denominator_counts` |
| Bottom/top level of a bar (no neighbour) | Cannot qualify | fixed |
| Candle confirmation | Directional candle closing outside the zone | `filters.candle` |
| Entry reference | Close of the confirmation bar (real fills will differ) | fixed |
| Stop | Beyond the zone edge or the retest-wick extreme, plus 2 ticks | `risk.stop_buffer_ticks` |
| Target | Fixed RR 2.0 (alternative: last confirmed swing) | `risk.tp_mode` |
| Long and short on the same bar | Emit neither | `conflict_policy` |
| Overlapping same-direction zones | One signal (larger stack, then newer); the other is SUPERSEDED | fixed |
| Missing data for an enabled filter | Block the signal | `filters.on_missing_data` (`fail` or `skip`) |
| Only the candle filter is on by default | All others off | `filters.*.enabled` |
| Timestamps | Bar OPEN time; the signal time is the bar CLOSE | `bar_period` |

## 3. Real data versus the proxy

- **Real:** `DataMode.FOOTPRINT` needs a per-bar footprint with `price, bid_vol, ask_vol`. Without one the engine creates no zones and counts `diagnostics["missing_footprint"]`. It never falls back silently.
- **Proxy:** `DataMode.OHLCV_PROXY` takes an impulse candle (large body vs ATR, close near the extreme, high volume) and uses the origin half of its body as the zone. This is a price-action heuristic, not order flow. Zones and signals are labelled `price_action_proxy`, delta statistics are `None`, and the signal explanation says "APPROXIMATE".

## 4. Data requirements and limitations

- Genuine imbalances need trades with aggressor side (bid/ask), for example CME futures data, or crypto exchange trades with a buyer/seller flag. CFD or MT5 OHLCV candles cannot provide this, and CFD tick volume is not real volume.
- The tick grid (`tick_size`) must match the footprint's price increments.
- One-bar footprints are assumed. Footprints on time bars from tick data must use the same bar boundaries as your OHLCV.
- Gold CFD (OANDA) prices differ from COMEX futures, so signals found on futures data need separate validation on the CFD.
- Imbalance ratio, minimum volume, stack length, retest rules and confirmations are untested starting values. Expect overfitting risk when tuning.
- Backtests need realistic fills (a limit order is only filled if price trades through the level), spread, commission and slippage. These are not in this module.
- The HTF filter re-aggregates history each time it is evaluated, which is fine for research but slower on very long runs.

## 5. Look-ahead protection

- `on_bar()` sees only the current and earlier bars.
- Zones detected on a bar can only be retested from the next bar.
- Swings are "confirmed" only after `n` later bars exist; the HTF filter uses only completed candles.
- Signals are final: nothing is edited or removed later.
- The test `test_prefix_invariance_on_random_market` checks that running the first k bars gives exactly the signals the full run emitted by bar k.

## 6. Using it in a backtest

```python
from sib_signals import SignalConfig, SignalEngine

engine = SignalEngine(SignalConfig(instrument="XAUUSD", tick_size=0.1))
for bar, fp in zip(bars_iter, footprints_iter):      # bar: dict/Series with timestamp, open, high, low, close, volume
    for sig in engine.on_bar(bar, fp):               # fp: DataFrame[price, bid_vol, ask_vol] or None
        broker_sim.submit(sig)                       # YOUR code: fills, sizing, costs
```

- The same `on_bar()` works for live paper trading: feed each bar as it closes.
- A backtester should fill at the NEXT bar's open (or a limit-fill model), never at `entry_price`, which is only a reference.
- `engine.signals_frame()` and `engine.zones_frame()` give DataFrames for analysis; `engine.diagnostics` counts dropped or skipped data.
- Batch use: `engine.run(bars_df, footprints_long_df)`, where the footprint frame has `timestamp, price, bid_vol, ask_vol`.

## 7. Tests (`python -m unittest discover -s tests -v`)

| Scenario | Expected result |
|---|---|
| Bullish stack, departure, retest with bullish close | One LONG: entry 2002.8, stop 1999.9, target 2008.6; zone TRIGGERED |
| Bearish mirror | One SHORT: entry 1997.2, stop 2000.5, target 1990.6 |
| Price never returns | No signal; zone EXPIRED |
| Close below zone before retest | No signal; zone INVALIDATED |
| Wick below zone, closes back | CLOSE mode: LONG with stop beyond the wick; WICK mode: no signal |
| Retest with a bearish candle | No signal; zone EXHAUSTED after the window |
| Confirmation one bar after retest | Signal on the confirming bar |
| Further retests after a signal | No duplicates; unique IDs |
| Two overlapping bullish zones | One signal; older zone SUPERSEDED |
| Long and short on the same bar | `skip_both`: none; `prefer_*`: SHORT (newer zone) |
| Missing or too-short footprint | No zone; diagnostics incremented |
| Malformed rows or bars | Rows dropped or bar skipped; out-of-order timestamps raise |
| Delta filter without footprint | Blocked, or skipped and reported if `on_missing_data="skip"` |
| Garbage future bars / prefix runs | Past signals are identical |

## 8. Preparing real trade data (new CSV adapter)

`sib_signals.data_adapter` converts executed trade prints into the exact OHLCV and
long-form footprint schemas expected by `SignalEngine.run`.

Expected CSV columns (names can be mapped in the example):

```csv
timestamp,price,volume,side
2026-01-02T10:00:01Z,2000.0,2.0,buy
2026-01-02T10:00:05Z,2000.1,3.0,sell
```

- `side=buy` means a buyer-initiated trade and contributes to `ask_vol`.
- `side=sell` means a seller-initiated trade and contributes to `bid_vol`.
- Timestamps are normalized to UTC; bars are timestamped at their opening time.
- Prices are rounded to the configured tick grid.
- Example: `python examples/prepare_trade_csv.py` (edit `CSV_PATH` first).
- Install dependencies with `python -m pip install -r requirements.txt`.

**Data warning:** this adapter does not turn ordinary bid/ask quote updates into executed
volume. The input must be actual trades with a reliable aggressor-side label. A feed that
only provides timestamp, bid price and ask price is not enough to build genuine footprints.
Check the provider's volume meaning, side convention, timezone, symbol and tick size first.
The adapter is a research utility, not a broker feed or trading system.
