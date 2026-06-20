from __future__ import annotations

import argparse
import json
from datetime import datetime
from enum import Enum
from typing import Any

from market_agent.agent import MarketAnalysisAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Indian gold and stock market analysis agent")
    parser.add_argument("--stock", default="RELIANCE", help="Indian stock symbol to analyze")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    agent = MarketAnalysisAgent()
    result = agent.analyze(args.stock)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=_json_default))
    else:
        print(_format_text(result))


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _format_text(result: dict[str, Any]) -> str:
    gold = result["gold_prediction"]
    stock = result["stock_prediction"]
    lines = [
        "Gold Prediction:",
        f"Predicted Direction: {gold['direction']}",
        f"Signal: {gold['signal']}",
        f"Confidence Score: {gold['confidence_score']}%",
        f"Predicted Range: {gold['predicted_low']} - {gold['predicted_high']} {gold['metadata']['unit']}",
        f"Risk Score: {gold['risk_score']}%",
        "Reason:",
        *[f"- {reason}" for reason in gold["reasons"]],
        "",
        "Stock Prediction:",
        f"Stock: {stock['instrument']}",
        f"Predicted Direction: {stock['direction']}",
        f"Signal: {stock['signal']}",
        f"Confidence Score: {stock['confidence_score']}%",
        f"Predicted Range: {stock['predicted_low']} - {stock['predicted_high']} {stock['metadata']['unit']}",
        f"Risk Score: {stock['risk_score']}%",
        "Reason:",
        *[f"- {reason}" for reason in stock["reasons"]],
    ]
    if result["alerts"]:
        lines.extend(["", "Alerts:", *[f"- {alert}" for alert in result["alerts"]]])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
