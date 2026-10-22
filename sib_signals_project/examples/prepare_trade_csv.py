"""Example: convert classified trade prints to bars and footprints, then run SIB."""
from pathlib import Path

from sib_signals import SignalConfig, SignalEngine, load_and_aggregate_csv

CSV_PATH = Path("data/trades.csv")  # Change this to your own CSV path.
BAR_PERIOD = "15min"
TICK_SIZE = 0.1  # Verify against the source instrument before using.

bars, footprints = load_and_aggregate_csv(
    CSV_PATH,
    bar_period=BAR_PERIOD,
    tick_size=TICK_SIZE,
    timestamp_col="timestamp",
    price_col="price",
    volume_col="volume",
    side_col="side",
)

config = SignalConfig(instrument="XAUUSD", tick_size=TICK_SIZE, bar_period=BAR_PERIOD)
engine = SignalEngine(config)
engine.run(bars, footprints)

Path("output").mkdir(exist_ok=True)
engine.signals_frame().to_csv("output/signals.csv", index=False)
engine.zones_frame().to_csv("output/zones.csv", index=False)
print(f"Bars processed: {len(bars)}")
print(f"Footprint rows: {len(footprints)}")
print(f"Signals generated: {len(engine.signals)}")
print(f"Diagnostics: {engine.diagnostics}")
print("Saved output/signals.csv and output/zones.csv")
