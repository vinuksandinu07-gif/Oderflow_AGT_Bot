"""Demo on SYNTHETIC data only. Run from the project root:  python examples/demo.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

import synthetic as S
from sib_signals import SignalConfig, SignalEngine

cfg = SignalConfig(instrument="XAUUSD", tick_size=0.1)

for name, items in (("LONG", [S.bull_bar0(), S.bull_departure(), S.bull_retest_confirmed()]),
                    ("SHORT", [S.bear_bar0(), S.bear_departure(), S.bear_retest_confirmed()])):
    engine = SignalEngine(cfg)
    signals = S.feed(engine, items)
    print(f"=== example {name} ===")
    for s in signals:
        print(json.dumps(s.to_dict(), indent=2))
    print("zones:\n", engine.zones_frame().to_string(), "\n")
