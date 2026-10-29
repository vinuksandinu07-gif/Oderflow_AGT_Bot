# Orderflow AGT project

This repository contains a research-first, source-aware order-flow trading framework inspired by the NASDAQ order-flow concepts discussed in the supplied transcript.

Important constraints from the source brief are reflected in the design:
- The project does not claim to reproduce the proprietary NASDAQ Effort formula exactly.
- Real footprint / MBO inputs are treated as the only trusted source of order-flow edge.
- OHLCV-only mode is deliberately named `ohlcv_proxy` and disabled by default.
- The system fails closed when operator-required configuration is missing.

## Project layout

```text
orderflow_agt_project/
├── README.md
├── requirements.txt
├── config/
│   ├── default.yaml
│   └── research_example.yaml
├── orderflow_agt/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── features.py
│   ├── strategies.py
│   ├── risk.py
│   ├── backtest.py
│   ├── reporting.py
│   └── data_import.py
├── tests/
│   ├── fixtures/
│   │   └── synthetic_bars.csv
│   └── test_orderflow_agt.py
└── examples/
    └── demo_backtest.py
```

## Quick start

PowerShell:

```powershell
cd orderflow_agt_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pytest -q
python examples/demo_backtest.py
```

Bash:

```bash
cd orderflow_agt_project
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -q
python examples/demo_backtest.py
```

## What is implemented

- typed data contracts for bars, quotes, footprint snapshots, value profiles, effort signals and orders
- deterministic feature modules for delta, VWAP, value profile, migration, absorption and OHLCV proxy classification
- separate strategy engines for directional drift, machine-gun scalp, mean reversion and momentum
- central risk manager with fail-closed validation
- event-driven backtest with paper execution and deterministic replay
- metrics/report export with synthetic-data labels
- configuration files with provenance labels and explicit operator-required settings

## Important caveats

- This is a research framework, not a live trading system.
- Live execution is disabled by default and does not send orders without explicit safety flags.
- Data provenance matters: no fake footprint or proprietary Effort signal is fabricated.
- The source transcript does not disclose the proprietary NASDAQ Effort formula or thresholds; those remain configurable placeholders rather than source facts.

## Demo / sample run

The demo script runs a synthetic historical backtest using a research configuration and writes a JSON report to the local output folder.
