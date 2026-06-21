from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from market_agent.cli import (
    CATEGORY_PERSPECTIVES,
    SUPPORTED_SINGLE_ASSETS,
    _analyze_top_stocks,
    _attach_prompt_training,
    _category_prompt_response,
    _format_category_prompt_text,
    _format_data_source_error,
    _format_missing_symbol_error,
    _format_text,
    _format_top_stocks_text,
    _prompt_training_context,
)
from market_agent.data.realtime_sources import DataSourceError, RealtimeIndiaMarketDataSource
from market_agent.interfaces.query_parser import MarketQuery, parse_market_query
from market_agent.services.agent import MarketAnalysisAgent


STATIC_DIR = Path(__file__).resolve().parent / "web_static"
APP_VERSION = "20260621_1915"


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), InvestmentWebHandler)
    print(f"AI Investment Intelligence Platform web app {APP_VERSION}: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb app stopped.")
    finally:
        server.server_close()


def analyze_prompt(
    prompt: str,
    *,
    no_prompt_training: bool = False,
    prompt_dataset: str | None = None,
    prompt_limit: int = 5,
) -> dict[str, Any]:
    query = parse_market_query(prompt)
    args = argparse.Namespace(
        no_prompt_training=no_prompt_training,
        use_prompt_training=False,
        prompt_dataset=prompt_dataset,
        prompt_limit=prompt_limit,
        scan_limit=None,
    )
    prompt_training = _prompt_training_context(query, args)
    if _needs_stock_symbol(query):
        result = _missing_symbol_result(query)
        text = _format_category_prompt_text(result)
        return {
            "ok": True,
            "query": _query_payload(query),
            "text": text,
            "error": "",
            "analysis": result,
            "summary": _summary_from_text(text),
        }

    data_source = RealtimeIndiaMarketDataSource()
    if _is_actual_value_query(query):
        try:
            result = _actual_value_result(query, data_source)
            text = _format_category_prompt_text(result)
            return {
                "ok": True,
                "query": _query_payload(query),
                "text": text,
                "error": "",
                "analysis": result,
                "summary": _summary_from_text(text),
            }
        except DataSourceError as exc:
            result = _realtime_unavailable_result(query, exc)
            text = _format_category_prompt_text(result)
            return {
                "ok": True,
                "query": _query_payload(query),
                "text": text,
                "error": "",
                "analysis": result,
                "summary": _summary_from_text(text),
            }

    agent = MarketAnalysisAgent(data_source=data_source)
    try:
        if query.perspective == "top_stocks":
            result = _analyze_top_stocks(agent, query, "realtime")
            _attach_prompt_training(result, prompt_training)
            text = _format_top_stocks_text(result)
        elif query.instrument_type not in SUPPORTED_SINGLE_ASSETS or query.perspective in CATEGORY_PERSPECTIVES:
            result = _category_prompt_response(query)
            _attach_prompt_training(result, prompt_training)
            text = _format_category_prompt_text(result)
        else:
            result = agent.analyze_gold() if query.instrument_type == "gold" else agent.analyze(query.stock_symbol or "RELIANCE")
            result["user_query"] = {
                "text": query.raw_text,
                "instrument_type": query.instrument_type,
                "stock_symbol": query.stock_symbol,
                "requested_datetime": query.requested_datetime_text,
                "certainty_label": query.certainty_label,
                "perspective": query.perspective,
                "horizons": query.horizons,
                "investment_amount": query.investment_amount,
                "risk_profile": query.risk_profile,
                "top_n": query.top_n,
                "data_source": "realtime",
            }
            if prompt_training:
                result["user_query"]["prompt_training"] = prompt_training
            text = _format_text(result, query)
    except DataSourceError as exc:
        result = _realtime_unavailable_result(query, exc)
        text = _format_category_prompt_text(result)
        return {
            "ok": True,
            "query": _query_payload(query),
            "text": text,
            "error": "",
            "analysis": result,
            "summary": _summary_from_text(text),
        }

    return {
        "ok": True,
        "query": _query_payload(query),
        "text": text,
        "error": "",
        "analysis": result,
        "summary": _summary_from_text(text),
    }


def _needs_stock_symbol(query: MarketQuery) -> bool:
    return (
        query.instrument_type == "stock"
        and query.perspective not in CATEGORY_PERSPECTIVES
        and query.perspective != "top_stocks"
        and not query.stock_symbol
    )


def _is_actual_value_query(query: MarketQuery) -> bool:
    lower = query.raw_text.lower()
    if query.instrument_type not in {"gold", "silver", "stock"}:
        return False
    if query.perspective in CATEGORY_PERSPECTIVES and query.instrument_type != "silver":
        return False
    if query.perspective == "top_stocks":
        return False
    value_terms = (
        "price",
        "value",
        "rate",
        "quote",
        "close",
        "closing",
        "actual",
        "current",
        "today",
        "today's",
        "todays",
        "last traded",
    )
    if not any(term in lower for term in value_terms):
        return False
    requested_date = _requested_date(query)
    if requested_date is not None:
        return requested_date <= date.today()
    if _has_future_language(lower) and not any(term in lower for term in ("actual", "current", "today", "today's", "todays", "past", "historical")):
        return False
    return True


def _has_future_language(lower: str) -> bool:
    return any(
        phrase in lower
        for phrase in (
            "will be",
            "what will",
            "future",
            "predict",
            "prediction",
            "forecast",
            "expected",
            "estimate",
            "target",
            "outlook",
        )
    )


def _requested_date(query: MarketQuery) -> date | None:
    if not query.requested_datetime_text:
        return None
    date_text = re.sub(r"\s+at\s+.*$", "", query.requested_datetime_text.strip(), flags=re.I)
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, fmt).date()
        except ValueError:
            continue
    return None


def _actual_value_result(query: MarketQuery, data_source: RealtimeIndiaMarketDataSource) -> dict[str, Any]:
    requested_date = _requested_date(query)
    if query.instrument_type == "gold":
        value = data_source.get_gold_price_on(requested_date)
        actual_value = f"{value['domestic_price']} {value['domestic_unit']}"
        title = "Actual Gold Market Value"
        instrument = value["instrument"]
        rate_rows = tuple(
            {
                "metric": f"{label} Rate",
                "value": f"{rate['price']} {rate['unit']}",
                "interpretation": "Groww published rate for this purity and quantity.",
            }
            for label, rate in (value.get("rates") or {}).items()
        )
        rows = (
            {"metric": "Observed Value", "value": actual_value, "interpretation": "Actual/current market value from the realtime provider; no forecast range used."},
            {"metric": "Observation Date", "value": value["date"], "interpretation": _date_interpretation(value)},
            *rate_rows,
        )
        if value.get("international_price") is not None:
            rows = (
                *rows,
                {"metric": "International Gold", "value": f"{value['international_price']} {value['international_unit']}", "interpretation": "Underlying global gold future/spot proxy used for conversion."},
                {"metric": "USD/INR", "value": value["usd_inr"], "interpretation": "Currency conversion input used for INR domestic value."},
            )
    elif query.instrument_type == "silver":
        value = data_source.get_silver_price_on(requested_date)
        actual_value = f"{value['domestic_price']} {value['domestic_unit']}"
        title = "Actual Silver Market Value"
        instrument = value["instrument"]
        rate_rows = tuple(
            {
                "metric": f"{label} Rate",
                "value": f"{rate['price']} {rate['unit']}",
                "interpretation": "Groww published or historical converted rate for this quantity.",
            }
            for label, rate in (value.get("rates") or {}).items()
        )
        rows = (
            {"metric": "Observed Value", "value": actual_value, "interpretation": "Actual/current or historical market value; no forecast range used."},
            {"metric": "Observation Date", "value": value["date"], "interpretation": _date_interpretation(value)},
            *rate_rows,
        )
        if value.get("international_price") is not None:
            rows = (
                *rows,
                {"metric": "International Silver", "value": f"{value['international_price']} {value['international_unit']}", "interpretation": "Underlying global silver future/spot proxy used for conversion."},
                {"metric": "USD/INR", "value": value["usd_inr"], "interpretation": "Currency conversion input used for INR domestic value."},
            )
    else:
        value = data_source.get_stock_price_on(query.stock_symbol or "RELIANCE", requested_date)
        actual_value = f"{value['last_price']} {value['unit']}"
        title = "Actual Stock Market Value"
        instrument = value["instrument"]
        rows = (
            {"metric": "Observed Value", "value": actual_value, "interpretation": "Actual/current market value from the realtime provider; no forecast range used."},
            {"metric": "Observation Date", "value": value["date"], "interpretation": _date_interpretation(value)},
            {"metric": "Ticker", "value": instrument, "interpretation": "Resolved equity ticker used for the market quote."},
        )
    profile = {
        "type": "actual_market_value",
        "title": title,
        "summary": f"{instrument} observed value is {actual_value} for {value['date']}.",
        "direction": "Observed Actual",
        "signal": "Hold",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 95,
        "predicted_range": actual_value,
        "actual_value": actual_value,
        "risk_score": 0,
        "reasons": (
            "This is a direct actual/current or historical value lookup, not a buy/sell forecast.",
            "No news-based future price deviation was applied because the prompt asked for the value on a current or past day.",
            "For future dates, use a forecast prompt such as: what will gold price be on 22 June 2026.",
        ),
        "research_sources": (value["source"],),
        "research_source_links": ({"source": value["source"], "url": value["source_url"]},),
        "analysis_sections": (
            {
                "title": "Actual Market Value",
                "rows": rows,
            },
        ),
    }
    return {
        "user_query": {
            "text": query.raw_text,
            "instrument_type": query.instrument_type,
            "stock_symbol": query.stock_symbol,
            "requested_datetime": query.requested_datetime_text,
            "certainty_label": "Actual/current or historical",
            "perspective": query.perspective,
            "data_source": "realtime",
        },
        "category_analysis": profile,
    }


def _date_interpretation(value: dict[str, Any]) -> str:
    requested = value.get("requested_date")
    observed = value.get("date")
    if requested and requested != observed:
        return "Requested day was not a trading day or quote was unavailable; showing the nearest previous available market close."
    if value.get("mode") == "current":
        return "Current-day value from the latest realtime quote available to the provider."
    return "Historical close for the requested market date."


def _realtime_unavailable_result(query: MarketQuery, error: Exception) -> dict[str, Any]:
    profile = {
        "title": "Realtime Data Availability Report",
        "direction": "Wait For Data",
        "signal": "Hold",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 0,
        "predicted_range": "Not calculated because realtime provider coverage was incomplete",
        "risk_score": 100,
        "reasons": (
            "The request was understood correctly, but the realtime market provider did not return enough live records to complete the calculation.",
            "No local sample data was used as a replacement.",
            "Run the prompt again after the realtime feed is reachable, or try a narrower prompt with a specific ticker.",
            "For top-stock prompts, the scanner now skips individual failed symbols, but it still requires enough successful realtime quotes to rank candidates.",
        ),
        "research_sources": (
            "Realtime public market/news feeds",
            "Yahoo Finance chart endpoint",
            "Trusted financial news source list",
        ),
        "research_source_links": (
            {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/"},
            {"source": "NSE India", "url": "https://www.nseindia.com/"},
            {"source": "BSE India", "url": "https://www.bseindia.com/"},
        ),
        "metadata": {"provider_message": str(error)},
    }
    return {
        "user_query": {
            "text": query.raw_text,
            "instrument_type": query.instrument_type,
            "perspective": query.perspective,
            "risk_profile": query.risk_profile,
            "investment_amount": query.investment_amount,
            "data_source": "realtime",
        },
        "category_analysis": profile,
    }


def _missing_symbol_result(query: MarketQuery) -> dict[str, Any]:
    profile = {
        "title": "Stock Symbol Required",
        "direction": "Waiting For Ticker",
        "signal": "Hold",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 0,
        "predicted_range": "Not calculated until a valid NSE/BSE ticker is provided",
        "risk_score": 100,
        "reasons": (
            "The prompt asks for a single-stock analysis, but no valid ticker was detected.",
            "Realtime stock analysis requires a precise symbol such as TCS, RELIANCE, INFY, HDFCBANK, or SBIN.",
            "For broad recommendations, use a prompt like: suggest me top 20 stocks to buy on 22 June 2026.",
            "No local sample data was used.",
        ),
        "research_sources": (
            "NSE listed equity symbols",
            "BSE listed equity symbols",
            "Realtime public market/news feeds",
        ),
        "research_source_links": (
            {"source": "NSE India", "url": "https://www.nseindia.com/"},
            {"source": "BSE India", "url": "https://www.bseindia.com/"},
            {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/"},
        ),
    }
    return {
        "user_query": {
            "text": query.raw_text,
            "instrument_type": query.instrument_type,
            "perspective": query.perspective,
            "data_source": "realtime",
        },
        "category_analysis": profile,
    }


def _unexpected_failure_result(query: MarketQuery, error: Exception) -> dict[str, Any]:
    profile = {
        "title": "Request Status Report",
        "direction": "Review Required",
        "signal": "Hold",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 0,
        "predicted_range": "Not calculated because the request did not complete normally",
        "risk_score": 100,
            "reasons": (
                "The prompt was received by the application, but the request did not complete normally.",
                "The UI is showing a direct fallback response instead of a stored HTML report.",
                "Re-run the prompt after refreshing the page; if the issue repeats, use a more specific asset or timeframe.",
            ),
        "research_sources": ("Application request handler", "Realtime market/news feed workflow"),
        "research_source_links": (),
        "analysis_sections": (
            {
                "title": "Request Handling",
                "rows": (
                    {
                        "metric": "Prompt Type",
                        "value": query.perspective,
                        "interpretation": "The application parsed the prompt and preserved the request context.",
                    },
                    {
                        "metric": "Completion Status",
                        "value": "Direct fallback response generated",
                        "interpretation": "The UI should display this structured result without requiring a stored report file.",
                    },
                ),
            },
        ),
        "metadata": {"provider_message": str(error)},
    }
    return {
        "user_query": {
            "text": query.raw_text,
            "instrument_type": query.instrument_type,
            "perspective": query.perspective,
            "risk_profile": query.risk_profile,
            "investment_amount": query.investment_amount,
            "data_source": "realtime",
        },
        "category_analysis": profile,
    }


def _query_payload(query: MarketQuery) -> dict[str, Any]:
    return {
        "text": query.raw_text,
        "instrument_type": query.instrument_type,
        "stock_symbol": query.stock_symbol,
        "perspective": query.perspective,
        "certainty_label": query.certainty_label,
        "requested_datetime": query.requested_datetime_text,
        "risk_profile": query.risk_profile,
        "top_n": query.top_n,
    }


def _summary_from_text(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for line in text.splitlines():
        if line.startswith("Predicted Direction:"):
            summary["direction"] = line.split(":", 1)[1].strip()
        elif line.startswith("Signal:") or line.startswith("Recommendation:"):
            summary["signal"] = line.split(":", 1)[1].strip()
        elif line.startswith("Buy Probability:"):
            summary["buy_probability"] = line.split(":", 1)[1].strip()
        elif line.startswith("Hold Probability:"):
            summary["hold_probability"] = line.split(":", 1)[1].strip()
        elif line.startswith("Sell Probability:"):
            summary["sell_probability"] = line.split(":", 1)[1].strip()
        elif line.startswith("Risk Score:"):
            summary["risk_score"] = line.split(":", 1)[1].strip()
        elif line.startswith("Predicted Range:"):
            summary["predicted_range"] = line.split(":", 1)[1].strip()
    return summary

class InvestmentWebHandler(BaseHTTPRequestHandler):
    server_version = "AIInvestmentWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path in {"/robots.txt", "/sitemap.xml"}:
            self._send_file(STATIC_DIR / parsed.path.removeprefix("/"))
            return
        if parsed.path == "/favicon.ico":
            self._send_empty_icon()
            return
        if parsed.path.startswith("/.well-known/"):
            self._send_empty_json()
            return
        if parsed.path.startswith("/static/"):
            self._send_static(unquote(parsed.path.removeprefix("/static/")))
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "AI Investment Intelligence Platform", "version": APP_VERSION})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        prompt = ""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                self._send_json({"ok": False, "error": "Prompt is required"}, HTTPStatus.BAD_REQUEST)
                return
            response = analyze_prompt(
                prompt,
                no_prompt_training=bool(payload.get("no_prompt_training", False)),
                prompt_dataset=payload.get("prompt_dataset") or None,
            )
            self._send_json(response)
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # Keep the web UI responsive with a readable failure.
            query = parse_market_query(prompt or "Investment research request")
            result = _unexpected_failure_result(query, exc)
            text = _format_category_prompt_text(result)
            self._send_json(
                {
                    "ok": True,
                    "query": _query_payload(query),
                    "text": text,
                    "error": "",
                    "analysis": result,
                    "summary": _summary_from_text(text),
                }
            )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_static(self, filename: str) -> None:
        safe_name = Path(filename).name
        static_path = (STATIC_DIR / safe_name).resolve()
        static_root = STATIC_DIR.resolve()
        if not str(static_path).startswith(str(static_root)) or not static_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
            return
        self._send_file(static_path)

    def _send_empty_icon(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def _send_empty_json(self) -> None:
        self._send_json({})

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", os.environ.get("CORS_ALLOW_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Investment Intelligence Platform web app")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
