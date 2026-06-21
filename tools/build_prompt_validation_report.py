from __future__ import annotations

import csv
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_agent.cli import main as cli_main
import market_agent.cli as cli_module
from market_agent.interfaces.query_parser import parse_market_query


PROMPTS_FILE = Path(r"C:\Users\giris\Downloads\AIPrompts.txt")
OUTPUT_DIR = ROOT / "outputs" / "prompt_validation"
CSV_PATH = OUTPUT_DIR / "prompt_validation_results.csv"
JSON_PATH = OUTPUT_DIR / "prompt_validation_results.json"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prompts = extract_prompts(PROMPTS_FILE.read_text(encoding="utf-8"))
    rows = []
    for index, prompt in enumerate(prompts, start=1):
        query = parse_market_query(prompt)
        status, response = run_prompt(prompt)
        validation_notes = validate_response(prompt, response)
        rows.append(
            {
                "No": index,
                "Prompt": prompt,
                "Instrument Type": query.instrument_type,
                "Perspective": query.perspective,
                "Detected Stock": query.stock_symbol or "",
                "Data Source": "Realtime default / category model",
                "Validation Status": status if not validation_notes else "Review",
                "Validation Notes": validation_notes or "Valid response generated",
                "Response Preview": preview(response),
                "Full Response": response,
            }
        )

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    JSON_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"csv": str(CSV_PATH), "json": str(JSON_PATH), "rows": len(rows)}, indent=2))


def extract_prompts(text: str) -> list[str]:
    prompts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.endswith(":") or line == "Prompt Library:":
            continue
        if ". " not in line:
            continue
        number, prompt = line.split(". ", 1)
        if number.isdigit():
            prompts.append(prompt.strip())
    return prompts


def run_prompt(prompt: str) -> tuple[str, str]:
    query = parse_market_query(prompt)
    old_argv = sys.argv[:]
    old_watchlist = cli_module.TOP_STOCK_WATCHLIST
    sys.argv = [
        "market_agent.cli",
        "--query",
        prompt,
        "--stock",
        query.stock_symbol or "RELIANCE",
        "--format",
        "text",
    ]
    if query.perspective == "top_stocks":
        cli_module.TOP_STOCK_WATCHLIST = (
            "TCS",
            "INFY",
            "HDFCBANK",
            "ICICIBANK",
            "SBIN",
            "LT",
            "ASIANPAINT",
            "RELIANCE",
        )
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            cli_main()
        response = buffer.getvalue().strip()
        return "Pass", response
    except Exception as exc:
        return "Fail", f"{type(exc).__name__}: {exc}"
    finally:
        sys.argv = old_argv
        cli_module.TOP_STOCK_WATCHLIST = old_watchlist


def validate_response(prompt: str, response: str) -> str:
    issues: list[str] = []
    lower_prompt = prompt.lower()
    query = parse_market_query(prompt)
    if not response:
        issues.append("No response")
    if "Sample Equity News" in response or "Sample Business Desk" in response:
        issues.append("Sample source appeared")
    if "Enter NSE stock symbol" in response:
        issues.append("Interactive ticker prompt appeared")
    if "Traceback" in response:
        issues.append("Runtime error")
    if query.perspective == "mutual_funds":
        if "Mutual Fund SIP Recommendation:" not in response and "Mutual Fund Recommendation:" not in response:
            issues.append("Mutual fund prompt did not use mutual fund format")
    if query.perspective == "top_stocks":
        if "Top Buy Stocks:" not in response:
            issues.append("Top-stock prompt did not use ranking format")
    if query.instrument_type == "gold" and query.perspective not in {"gold_silver_compare"}:
        if "Gold Prediction:" not in response and "Gold Market" not in response:
            issues.append("Gold prompt did not use gold output")
    if "Research Sources:" not in response:
        issues.append("Research sources missing")
    return "; ".join(issues)


def preview(response: str) -> str:
    lines = [line for line in response.splitlines() if line.strip()]
    return " | ".join(lines[:8])[:500]


if __name__ == "__main__":
    main()
