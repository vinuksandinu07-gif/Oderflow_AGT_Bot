from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .backtest import EventBacktester


def export_json(data: Dict[str, Any], path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def export_csv(rows: Sequence[Dict[str, Any]], path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path_obj, "w", encoding="utf-8", newline="") as fh:
            fh.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path_obj, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_summary_report(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {
            "signals": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "trades": 0,
            "max_drawdown": 0.0,
        }

    pnl_values = [float(row.get("pnl", 0.0)) for row in rows]
    wins = [x for x in pnl_values if x > 0]
    losses = [x for x in pnl_values if x < 0]
    gross_pnl = float(sum(pnl_values))
    win_rate = float(len(wins) / max(len(pnl_values), 1))
    avg_pnl = float(sum(pnl_values) / len(pnl_values))
    profit_factor = float(sum(wins) / abs(sum(losses)) if sum(losses) != 0 else (float("inf") if sum(wins) > 0 else 0.0))
    max_drawdown = float(max(0.0, -min(0.0, min(pnl_values)))) if pnl_values else 0.0
    return {
        "signals": len(rows),
        "trades": len(rows),
        "gross_pnl": gross_pnl,
        "net_pnl": gross_pnl,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
    }


def generate_report(bars: Sequence[Any], strategies: Sequence[Any], config: Optional[Dict[str, Any]] = None, output_dir: str = "output") -> Dict[str, Any]:
    config = config or {"risk": {"min_order_qty": 1.0}}
    backtest = EventBacktester(config=config, bars=list(bars))
    result = backtest.run(strategies)
    summary = build_summary_report([
        {"pnl": float(entry.get("entry", 0.0) - entry.get("stop", 0.0)) if isinstance(entry, dict) else 0.0}
        for entry in result.get("signals", [])
    ])
    summary["result"] = result
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    export_json(summary, str(outdir / "report.json"))
    export_csv([{"label": "signals", "value": summary["signals"]}], str(outdir / "report.csv"))
    return summary


def replay_session(bars: Sequence[Any], strategies: Sequence[Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministic replay pass intended for research and auditability.

    This is not a live execution path and is intentionally conservative.
    """
    config = config or {"risk": {"min_order_qty": 1.0}}
    backtest = EventBacktester(config=config, bars=list(bars))
    result = backtest.run(strategies)
    return {"result": result, "summary": build_summary_report([])}


__all__ = [
    "export_json",
    "export_csv",
    "build_summary_report",
    "generate_report",
    "replay_session",
]
