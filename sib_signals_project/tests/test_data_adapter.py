import unittest
import pandas as pd

from sib_signals.data_adapter import load_trade_csv, trades_to_bars_and_footprints


class DataAdapterTests(unittest.TestCase):
    def setUp(self):
        self.trades = pd.DataFrame([
            {"timestamp": "2026-01-02T10:00:01Z", "price": 2000.0, "volume": 2.0, "side": "buy"},
            {"timestamp": "2026-01-02T10:00:05Z", "price": 2000.1, "volume": 3.0, "side": "sell"},
            {"timestamp": "2026-01-02T10:01:00Z", "price": 2000.1, "volume": 4.0, "side": "buyer"},
            {"timestamp": "2026-01-02T10:16:00Z", "price": 2000.2, "volume": 5.0, "side": "seller"},
        ])

    def test_aggregation_matches_engine_schema(self):
        bars, fps = trades_to_bars_and_footprints(self.trades, bar_period="15min", tick_size=0.1)
        self.assertEqual(list(bars.columns), ["timestamp", "open", "high", "low", "close", "volume"])
        self.assertEqual(list(fps.columns), ["timestamp", "price", "bid_vol", "ask_vol"])
        self.assertEqual(len(bars), 2)
        first = bars.iloc[0]
        self.assertAlmostEqual(first.open, 2000.0)
        self.assertAlmostEqual(first.close, 2000.1)
        self.assertAlmostEqual(first.volume, 9.0)
        first_fp = fps[fps.timestamp == first.timestamp]
        level_2000 = first_fp[first_fp.price == 2000.0].iloc[0]
        self.assertAlmostEqual(level_2000.ask_vol, 2.0)
        level_20001 = first_fp[first_fp.price == 2000.1].iloc[0]
        self.assertAlmostEqual(level_20001.bid_vol, 3.0)
        self.assertAlmostEqual(level_20001.ask_vol, 4.0)

    def test_rejects_bad_tick_size(self):
        with self.assertRaises(ValueError):
            trades_to_bars_and_footprints(self.trades, tick_size=0)

    def test_rejects_missing_columns(self):
        with self.assertRaises(ValueError):
            trades_to_bars_and_footprints(self.trades.drop(columns=["side"]))


if __name__ == "__main__":
    unittest.main()
