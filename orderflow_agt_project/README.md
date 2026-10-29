# Orderflow AGT project

This repository contains a research-first, source-aware order-flow trading framework inspired by Nasdaq order-flow concepts discussed in the supplied transcript. The implementation is intentionally conservative and avoids claiming to reproduce the proprietary NASDAQ Effort formula exactly.

Key design constraints
- No proprietary formula is assumed or claimed to exist.
- Real footprint / executed trade / vendor MBO inputs are treated as the trusted data source.
- OHLCV-only behavior is labeled `ohlcv_proxy` and is disabled by default.
- Missing operator-required settings fail closed instead of being silently guessed.
- Session clocks are not inferred from the transcript; the operator must provide them if live or session-restricted behavior is needed.

Project layout

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

Quick start

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

What is included
- typed contracts for bars, quotes, footprint snapshots, value profiles, effort boxes, orders, fills, positions, and signals
- deterministic feature modules for delta, VWAP, value migration, absorption, and proxy labeling
- separate strategy engines for directional drift and machine-gun scalp, plus placeholder mean-reversion / momentum stubs gated behind explicit configuration
- centralized risk sizing and validation logic with fail-closed behavior
- event-driven deterministic replay and paper execution scaffolding
- summary reporting and export utilities for JSON/CSV
- explicit configuration provenance labels for source-derived, engineering-assumption, experimental proxy, and operator-required values

Important caveats
- This is a research framework, not a live-trading system.
- The project intentionally does not claim profitability or source-faithful replication of Fabio’s proprietary model.
- Real order-flow data remains the only trusted path for exact-data strategies.
- Any live or session-restricted setup must provide explicit operator inputs for session windows, account sizing, and risk limits.

Replay and reporting notes
- The backtest engine is deterministic and uses the same strategy interface expected by paper/live execution.
- Summary metrics are exportable in JSON/CSV and are intended for research transparency, not for claiming strategy success.
- The framework explicitly surfaces uncertainty, sample-size limits, and the fact that synthetic fixtures are not a substitute for real historical data.

Example research output
The project emits JSON/CSV summary data in the output folder when the report routine is used. This is meant to support auditability and reproducibility for synthetic research runs.
