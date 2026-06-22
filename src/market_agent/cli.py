from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from market_agent.services.agent import MarketAnalysisAgent
from market_agent.reports.html_report import save_html_report
from market_agent.prompts.dataset import (
    default_dataset_path,
    enhance_prompt_from_dataset,
    export_training_sample,
    search_prompt_dataset,
    summarize_prompt_dataset,
)
from market_agent.prompts.library import format_prompt_library, prompt_categories
from market_agent.interfaces.query_parser import MarketQuery, parse_market_query
from market_agent.data.realtime_sources import DataSourceError, RealtimeIndiaMarketDataSource
from market_agent.intelligence.nlp import NewsIntelligenceEngine

TOP_STOCK_WATCHLIST = (
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "SUNPHARMA",
    "CIPLA",
    "DRREDDY",
    "MARUTI",
    "TATAMOTORS",
    "M&M",
    "BAJAJ-AUTO",
    "BHARTIARTL",
    "INDUSINDBK",
    "ASIANPAINT",
    "TITAN",
    "ULTRACEMCO",
    "GRASIM",
    "HINDUNILVR",
    "NESTLEIND",
    "ITC",
    "LT",
    "TATASTEEL",
    "JSWSTEEL",
    "POWERGRID",
    "NTPC",
    "ONGC",
    "COALINDIA",
    "HCLTECH",
    "WIPRO",
    "TECHM",
    "RELIANCE",
)
SUPPORTED_SINGLE_ASSETS = {"gold", "stock", "portfolio"}
CATEGORY_PERSPECTIVES = {
    "mutual_funds",
    "sector_analysis",
    "gold_silver_compare",
    "wealth_plan",
    "crypto_analysis",
    "forex_analysis",
    "news_impact",
    "multi_news_intelligence",
    "real_estate",
    "ipo_analysis",
    "technology_investment",
    "macro_geopolitics",
    "macro_events",
    "market_summary",
    "sector_outlook",
    "precious_metals_technical",
    "multibagger_goal",
    "equity_research",
    "gold_intelligence",
    "silver_intelligence",
    "portfolio_strategy",
    "portfolio_advisor",
}
OFFICIAL_RESEARCH_LINKS = {
    "RBI Press Releases": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
    "RBI Notifications": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=0&Mode=0",
    "SEBI Updates": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=0&ssid=0&smid=0",
    "PIB Government Releases": "https://pib.gov.in/PressReleasePage.aspx",
    "NSE Circulars": "https://www.nseindia.com/resources/exchange-communication-circulars",
    "BSE Notices": "https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx",
    "AMFI Investor Information": "https://www.amfiindia.com/investor-corner/knowledge-center",
    "MoHUA RERA": "https://mohua.gov.in/cms/real-estate-regulation-and-development-act-rera.php",
    "DPIIT Startup India": "https://dpiit.gov.in/",
    "MeitY Updates": "https://www.meity.gov.in/",
    "India Budget": "https://www.indiabudget.gov.in/",
}
OFFICIAL_SOURCES_BY_PERSPECTIVE = {
    "mutual_funds": ("SEBI Updates", "AMFI Investor Information", "RBI Notifications", "PIB Government Releases"),
    "sector_analysis": ("NSE Circulars", "BSE Notices", "SEBI Updates", "MeitY Updates", "DPIIT Startup India"),
    "gold_silver_compare": ("RBI Press Releases", "RBI Notifications", "PIB Government Releases", "India Budget"),
    "wealth_plan": ("SEBI Updates", "AMFI Investor Information", "RBI Press Releases", "India Budget", "PIB Government Releases"),
    "crypto_analysis": ("RBI Press Releases", "SEBI Updates", "PIB Government Releases"),
    "forex_analysis": ("RBI Press Releases", "RBI Notifications", "PIB Government Releases"),
    "news_impact": ("PIB Government Releases", "RBI Press Releases", "SEBI Updates", "NSE Circulars", "BSE Notices"),
    "multi_news_intelligence": ("PIB Government Releases", "RBI Press Releases", "SEBI Updates", "NSE Circulars", "BSE Notices"),
    "real_estate": ("MoHUA RERA", "SEBI Updates", "RBI Notifications", "India Budget", "PIB Government Releases"),
    "ipo_analysis": ("SEBI Updates", "NSE Circulars", "BSE Notices", "PIB Government Releases"),
    "technology_investment": ("MeitY Updates", "DPIIT Startup India", "SEBI Updates", "PIB Government Releases", "India Budget"),
    "macro_geopolitics": ("PIB Government Releases", "RBI Press Releases", "SEBI Updates", "India Budget"),
    "macro_events": ("RBI Press Releases", "RBI Notifications", "PIB Government Releases", "India Budget", "SEBI Updates"),
    "market_summary": ("NSE Circulars", "BSE Notices", "RBI Press Releases", "SEBI Updates"),
    "sector_outlook": ("NSE Circulars", "BSE Notices", "SEBI Updates", "MeitY Updates", "DPIIT Startup India", "India Budget"),
    "precious_metals_technical": ("RBI Press Releases", "RBI Notifications", "PIB Government Releases", "India Budget"),
    "multibagger_goal": ("SEBI Updates", "AMFI Investor Information", "NSE Circulars", "BSE Notices", "India Budget"),
    "equity_research": ("NSE Circulars", "BSE Notices", "SEBI Updates", "PIB Government Releases"),
    "gold_intelligence": ("RBI Press Releases", "RBI Notifications", "PIB Government Releases", "India Budget"),
    "silver_intelligence": ("PIB Government Releases", "India Budget", "RBI Press Releases"),
    "portfolio_strategy": ("SEBI Updates", "AMFI Investor Information", "RBI Press Releases", "India Budget"),
    "portfolio_advisor": ("SEBI Updates", "AMFI Investor Information", "RBI Press Releases", "India Budget"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Investment Intelligence Platform")
    parser.add_argument("--stock", default=None, help="Indian stock symbol to analyze")
    parser.add_argument("--query", default=None, help="Natural-language market question")
    parser.add_argument(
        "--list-prompts",
        nargs="?",
        const="all",
        default=None,
        help="List built-in prompt templates. Optionally pass a category.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--prompt-dataset", default=None, help="Path to the Indian investment intelligence JSONL prompt dataset")
    parser.add_argument("--prompt-summary", action="store_true", help="Summarize the attached JSONL prompt dataset")
    parser.add_argument("--search-prompts", default=None, help="Search the JSONL prompt dataset for similar training prompts")
    parser.add_argument("--enhance-prompt", default=None, help="Enhance a prompt using the JSONL prompt dataset")
    parser.add_argument("--prompt-limit", type=int, default=10, help="Maximum prompt dataset results to return")
    parser.add_argument("--scan-limit", type=int, default=None, help="Optional max JSONL records to scan")
    parser.add_argument("--asset-class", default=None, help="Filter JSONL prompt search by asset class")
    parser.add_argument("--domain", default=None, help="Filter JSONL prompt search by domain")
    parser.add_argument("--risk-level", default=None, help="Filter JSONL prompt search by risk level")
    parser.add_argument("--export-training-sample", default=None, help="Export a fine-tuning-style JSONL sample to this path")
    parser.add_argument("--sample-size", type=int, default=1000, help="Records to export for --export-training-sample")
    parser.add_argument(
        "--use-prompt-training",
        action="store_true",
        help="Use the JSONL prompt corpus to enrich normal market-query reports. Enabled automatically when the default dataset exists.",
    )
    parser.add_argument(
        "--no-prompt-training",
        action="store_true",
        help="Disable automatic JSONL prompt-corpus enrichment for normal market-query reports.",
    )
    parser.add_argument(
        "--data-source",
        choices=("realtime",),
        default="realtime",
        help="Use live public market/news feeds. Offline offline data is not supported.",
    )
    args = parser.parse_args()

    if args.prompt_summary:
        summary = summarize_prompt_dataset(args.prompt_dataset, args.scan_limit)
        print(json.dumps(summary, indent=2, default=_json_default))
        return

    if args.search_prompts:
        matches = search_prompt_dataset(
            args.search_prompts,
            args.prompt_dataset,
            asset_class=args.asset_class,
            domain=args.domain,
            risk_level=args.risk_level,
            limit=args.prompt_limit,
            scan_limit=args.scan_limit,
        )
        print(json.dumps({"query": args.search_prompts, "matches": matches}, indent=2, default=_json_default))
        return

    if args.enhance_prompt:
        enhanced = enhance_prompt_from_dataset(
            args.enhance_prompt,
            args.prompt_dataset,
            limit=args.prompt_limit,
            scan_limit=args.scan_limit,
        )
        if args.format == "json":
            print(json.dumps(enhanced, indent=2, default=_json_default))
        else:
            print(_format_enhanced_prompt_text(enhanced))
        return

    if args.export_training_sample:
        path = export_training_sample(
            args.export_training_sample,
            args.prompt_dataset,
            sample_size=args.sample_size,
            scan_limit=args.scan_limit,
        )
        print(f"Training sample exported: {path}")
        return

    if args.list_prompts is not None:
        category = None if args.list_prompts == "all" else args.list_prompts
        try:
            print(format_prompt_library(category))
        except KeyError:
            print("Unknown prompt category. Available categories:")
            for item in prompt_categories():
                print(f"- {item}")
        return

    query_text = args.query
    if query_text is None and args.stock is None:
        query_text = input(
            "Ask your market question, e.g. 'What will be the stock price on 25 June 2026 at 12:03 PM?' "
        ).strip()

    query = parse_market_query(query_text or f"What is the outlook for {args.stock}?", args.stock)
    if (
        query.instrument_type == "stock"
        and query.perspective not in CATEGORY_PERSPECTIVES
        and query.perspective != "top_stocks"
        and not query.stock_symbol
    ):
        try:
            stock_symbol = input("Enter NSE stock symbol / ticker, e.g. RELIANCE or TCS: ").strip().upper()
        except EOFError:
            print(_format_missing_symbol_error(query))
            return
        if not stock_symbol:
            print(_format_missing_symbol_error(query))
            return
        query = parse_market_query(query.raw_text, stock_symbol)

    data_source = RealtimeIndiaMarketDataSource()
    agent = MarketAnalysisAgent(data_source=data_source)
    prompt_training = _prompt_training_context(query, args)
    if query.perspective == "top_stocks":
        try:
            result = _analyze_top_stocks(agent, query, args.data_source)
        except DataSourceError as exc:
            print(_format_data_source_error(exc, query))
            return
        _attach_prompt_training(result, prompt_training)
        report_path = save_html_report(result, "top_stocks")
        effective_format = "json" if query.output_json_requested else args.format
        if effective_format == "json":
            print(json.dumps(result, indent=2, default=_json_default))
        else:
            print(_format_top_stocks_text(result))
            print(f"\nHTML Report: {report_path}")
        return
    if query.instrument_type not in SUPPORTED_SINGLE_ASSETS or query.perspective in CATEGORY_PERSPECTIVES:
        result = _category_prompt_response(query)
        _attach_prompt_training(result, prompt_training)
        report_path = save_html_report(result, query.perspective)
        effective_format = "json" if query.output_json_requested else args.format
        if effective_format == "json":
            print(json.dumps(result, indent=2, default=_json_default))
        else:
            print(_format_category_prompt_text(result))
            print(f"\nHTML Report: {report_path}")
        return

    try:
        result = agent.analyze(query.stock_symbol or args.stock or "RELIANCE")
    except DataSourceError as exc:
        print(_format_data_source_error(exc, query))
        return
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
        "data_source": args.data_source,
    }
    if prompt_training:
        result["user_query"]["prompt_training"] = prompt_training
    result["perspective_analysis"] = _perspective_analysis(result, query)
    report_path = save_html_report(result, query.instrument_type)

    effective_format = "json" if query.output_json_requested else args.format
    if effective_format == "json":
        print(json.dumps(result, indent=2, default=_json_default))
    else:
        print(_format_text(result, query))
        print(f"\nHTML Report: {report_path}")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _format_data_source_error(error: Exception, query: MarketQuery) -> str:
    return "\n".join(
        [
            f"Question: {query.raw_text}",
            "",
            "Realtime Data Error:",
            f"- {error}",
            "- The question may have been interpreted as a market symbol, or a realtime provider did not return data.",
            "- Try using a valid NSE ticker such as TCS or RELIANCE for stock analysis.",
            "- For treaty, policy, or general news questions, include words like news, treaty, agreement, policy, or impact.",
        ]
    )


def _format_missing_symbol_error(query: MarketQuery) -> str:
    return "\n".join(
        [
            f"Question: {query.raw_text}",
            "",
            "Missing Stock Symbol:",
            "- Please provide a valid NSE ticker such as TCS, RELIANCE, INFY, or HDFCBANK.",
            "- For non-stock questions, include words like news, treaty, agreement, policy, gold, mutual fund, or portfolio.",
        ]
    )


def _format_enhanced_prompt_text(enhanced: dict[str, Any]) -> str:
    lines = [
        "Enhanced Training Prompt:",
        enhanced["enhanced_prompt"],
        "",
        "Recommended Agents:",
        *[f"- {agent}" for agent in enhanced.get("recommended_agents", [])[:8]],
        "",
        "Required Indicators:",
        *[f"- {indicator}" for indicator in enhanced.get("required_indicators", [])[:12]],
        "",
        "Expected Outputs:",
        *[f"- {output}" for output in enhanced.get("expected_outputs", [])[:12]],
        "",
        "Matched Training Prompts:",
    ]
    for index, match in enumerate(enhanced.get("matched_training_prompts", [])[:5], start=1):
        lines.extend(
            [
                f"{index}. {match.get('asset_class')} | {match.get('domain')} | {match.get('risk_level')} | score {match.get('score')}",
                f"   {match.get('prompt')}",
            ]
        )
    lines.extend(["", f"Safety Note: {enhanced.get('safety_note')}"])
    return "\n".join(lines)


def _prompt_training_context(query: MarketQuery, args: argparse.Namespace) -> dict[str, Any] | None:
    if args.no_prompt_training:
        return None
    dataset_path = args.prompt_dataset or default_dataset_path()
    if not args.use_prompt_training and dataset_path is None:
        return None
    try:
        enhanced = enhance_prompt_from_dataset(
            query.raw_text,
            dataset_path,
            limit=min(args.prompt_limit, 5),
            scan_limit=args.scan_limit,
        )
    except FileNotFoundError:
        return None
    return {
        "enhanced_prompt": enhanced.get("enhanced_prompt", ""),
        "recommended_agents": enhanced.get("recommended_agents", [])[:8],
        "required_indicators": enhanced.get("required_indicators", [])[:12],
        "expected_outputs": enhanced.get("expected_outputs", [])[:12],
        "dataset_path": str(dataset_path) if dataset_path else "",
        "matched_training_prompts": [
            {
                "asset_class": item.get("asset_class"),
                "domain": item.get("domain"),
                "time_horizon": item.get("time_horizon"),
                "risk_level": item.get("risk_level"),
                "score": item.get("score"),
                "prompt": item.get("prompt"),
            }
            for item in enhanced.get("matched_training_prompts", [])[:5]
        ],
        "safety_note": enhanced.get("safety_note", ""),
    }


def _attach_prompt_training(result: dict[str, Any], prompt_training: dict[str, Any] | None) -> None:
    if prompt_training:
        result.setdefault("user_query", {})["prompt_training"] = prompt_training


def _format_text(result: dict[str, Any], query: MarketQuery | None = None) -> str:
    gold = result["gold_prediction"]
    if query is None or query.instrument_type == "gold":
        prediction = gold
        title = "Gold Prediction"
    elif query.instrument_type == "portfolio":
        return _portfolio_text(result, query)
    else:
        stock = result["stock_prediction"]
        prediction = stock
        title = "Stock Prediction"

    lines = []
    if query is not None:
        lines.append(f"Question: {query.raw_text}")
        lines.append("")
    training_lines = _prompt_training_lines(result.get("user_query", {}).get("prompt_training"))
    if training_lines:
        lines.extend(training_lines)
        lines.append("")
    lines.extend(_prediction_lines(title, prediction))
    source_key = query.instrument_type if query is not None else None
    sources = (
        result.get("research_sources_by_instrument", {}).get(source_key, [])
        if source_key
        else result.get("research_sources", [])
    )
    if sources:
        lines.extend(["", "Research Sources:", *[f"- {source}" for source in sources[:8]]])
    else:
        lines.extend(["", "Research Sources:"])
    source_links = (
        result.get("research_source_links_by_instrument", {}).get(source_key, [])
        if source_key
        else result.get("research_source_links", [])
    )
    if source_links:
        lines.extend(["", "Research Source URLs:"])
        lines.extend(
            f"- {item['source']}: {item['url']}"
            for item in source_links[:8]
            if item.get("url")
        )
    return "\n".join(lines)


def _analyze_top_stocks(agent: MarketAnalysisAgent, query: MarketQuery, data_source_name: str = "realtime") -> dict[str, Any]:
    candidates = []
    skipped: list[str] = []

    def analyze_symbol(symbol: str) -> dict[str, Any]:
        analysis = agent.analyze(symbol)
        stock = analysis["stock_prediction"]
        rank_score = (
            stock["buy_probability"] * 1.2
            + stock["confidence_score"] * 0.8
            - stock["risk_score"] * 0.55
            - stock["sell_probability"] * 1.3
        )
        return {
            "rank_score": round(rank_score, 2),
            "prediction": stock,
            "research_sources": analysis.get("research_sources_by_instrument", {}).get("stock", []),
            "research_source_links": analysis.get("research_source_links_by_instrument", {}).get("stock", []),
        }

    worker_count = 8 if data_source_name == "realtime" else 4
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(analyze_symbol, symbol): symbol for symbol in TOP_STOCK_WATCHLIST}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                candidates.append(future.result())
            except DataSourceError:
                skipped.append(symbol)
            except Exception:
                skipped.append(symbol)
    if not candidates:
        candidates = _news_ranked_stock_candidates(query, agent.data_source)
        if not candidates:
            raise DataSourceError("Unable to fetch enough realtime stock data for the top-stock scan")
    ranked = sorted(
        candidates,
        key=lambda item: (
            item["prediction"]["signal"] == "Buy",
            item["prediction"]["buy_probability"],
            -item["prediction"]["risk_score"],
            item["prediction"]["confidence_score"],
            item["rank_score"],
        ),
        reverse=True,
    )
    buy_ranked = [
        item
        for item in ranked
        if item["prediction"]["signal"] == "Buy"
        or item["prediction"]["buy_probability"] >= 50
    ]
    selected = _fill_ranked_candidates(buy_ranked, ranked, query.top_n)
    return {
        "user_query": {
            "text": query.raw_text,
            "requested_datetime": query.requested_datetime_text,
            "certainty_label": query.certainty_label,
            "perspective": query.perspective,
            "top_n": query.top_n,
            "data_source": data_source_name,
            "skipped_symbols": tuple(skipped),
        },
        "top_buy_stocks": selected,
}


def _news_ranked_stock_candidates(query: MarketQuery, data_source: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, symbol in enumerate(TOP_STOCK_WATCHLIST[: max(query.top_n * 2, 20)]):
        try:
            articles = data_source.get_news((symbol,))
        except Exception:
            articles = []
        analysis = NewsIntelligenceEngine().analyze(articles)
        buy_probability = max(15, min(62, 36 + int(analysis.sentiment_score * 25) + min(14, len(articles) // 3)))
        sell_probability = max(3, min(35, 12 - int(analysis.sentiment_score * 12) + len(analysis.anomaly_flags) * 3))
        hold_probability = max(0, 100 - buy_probability - sell_probability)
        risk_score = max(45, min(88, 62 + len(analysis.anomaly_flags) * 5 - int(analysis.sentiment_score * 10)))
        confidence = max(35, min(72, 45 + min(20, len(articles) // 2) + int(abs(analysis.sentiment_score) * 10)))
        direction = "Upward" if buy_probability >= 50 else "Downward" if sell_probability >= 30 else "Sideways"
        signal = "Buy" if buy_probability >= 50 and buy_probability > sell_probability else "Hold"
        reasons = [
            "Realtime quote endpoint was unavailable in this deployment run; candidate is ranked by realtime news/source coverage.",
            f"Fetched {len(articles)} realtime news/source items for {symbol}.",
            f"News sentiment is {analysis.sentiment.value} with {int(analysis.impact_score * 100)}% impact score.",
        ]
        if analysis.topics:
            reasons.append(f"Detected topics: {', '.join(analysis.topics[:4])}.")
        if analysis.keyword_hits:
            reasons.append(f"SEO keyword themes: {', '.join(analysis.keyword_hits[:4])}.")
        prediction = {
            "instrument": f"{symbol} ({symbol})",
            "direction": direction,
            "signal": signal,
            "buy_probability": buy_probability,
            "hold_probability": hold_probability,
            "sell_probability": sell_probability,
            "confidence_score": confidence,
            "predicted_range": "Realtime quote unavailable; ranked by live news/source signals",
            "risk_score": risk_score,
            "reasons": reasons,
            "metadata": {
                "unit": "INR",
                "quote_unavailable": True,
                "source_count": analysis.source_count,
                "article_count": len(articles),
            },
        }
        candidates.append(
            {
                "rank_score": round(buy_probability * 1.2 + confidence * 0.5 - risk_score * 0.35, 2),
                "prediction": prediction,
                "research_sources": sorted({article.source for article in articles}),
                "research_source_links": _source_links_from_articles(articles),
            }
        )
    return sorted(candidates, key=lambda item: item["rank_score"], reverse=True)


def _source_links_from_articles(articles: list[Any]) -> list[dict[str, str]]:
    links: dict[str, str] = {}
    for article in articles[:12]:
        if article.url and article.source not in links:
            links[article.source] = article.url
    return [{"source": source, "url": url} for source, url in sorted(links.items())]


def _fill_ranked_candidates(
    preferred: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*preferred, *ranked]:
        instrument = item["prediction"]["instrument"]
        if instrument in seen:
            continue
        seen.add(instrument)
        selected.append(item)
        if len(selected) >= count:
            break
    return selected


def _format_top_stocks_text(result: dict[str, Any]) -> str:
    query = result["user_query"]
    lines = [
        f"Question: {query['text']}",
        "Data Source: Realtime market/news feeds",
        "",
        "Top Buy Stocks:",
    ]
    training_lines = _prompt_training_lines(query.get("prompt_training"))
    if training_lines:
        lines = [
            f"Question: {query['text']}",
            "Data Source: Realtime market/news feeds",
            "",
            *training_lines,
            "",
            "Top Buy Stocks:",
        ]
    for index, item in enumerate(result["top_buy_stocks"], start=1):
        prediction = item["prediction"]
        display_signal = (
            "Buy"
            if prediction["signal"] == "Buy" or prediction["buy_probability"] >= 50
            else prediction["signal"]
        )
        quote_unavailable = prediction.get("metadata", {}).get("quote_unavailable")
        if quote_unavailable:
            trade_lines = [
                "Entry Zone: Realtime quote unavailable in deployment",
                "Target Price: Re-run when quote endpoint is reachable",
                "Stop Loss: Use broker/live exchange quote before any trade",
                "Estimated Upside: Not calculated without live quote",
            ]
        else:
            entry_low, entry_high, target_price, stop_loss, upside_pct = _stock_trade_levels(prediction)
            trade_lines = [
                f"Entry Zone: {entry_low} - {entry_high} {prediction['metadata']['unit']}",
                f"Target Price: {target_price} {prediction['metadata']['unit']}",
                f"Stop Loss: {stop_loss} {prediction['metadata']['unit']}",
                f"Estimated Upside: {upside_pct}%",
            ]
        lines.extend(
            [
                "",
                f"{index}. {prediction['instrument']}",
                f"Recommendation: {display_signal}",
                f"Buy Probability: {prediction['buy_probability']}%",
                f"Hold Probability: {prediction['hold_probability']}%",
                f"Sell Probability: {prediction['sell_probability']}%",
                f"Confidence Score to {display_signal}: {prediction['confidence_score']}%",
                *trade_lines,
                f"Risk Score: {prediction['risk_score']}%",
                "Why This Stock:",
                *[f"- {reason}" for reason in prediction["reasons"][:4]],
            ]
        )
        sources = item.get("research_sources", [])
        if sources:
            lines.extend(["Research Sources:", *[f"- {source}" for source in sources[:5]]])
        else:
            lines.append("Research Sources:")
        source_links = item.get("research_source_links", [])
        if source_links:
            lines.extend(["Research Source URLs:"])
            lines.extend(
                f"- {source['source']}: {source['url']}"
                for source in source_links[:5]
                if source.get("url")
            )
    return "\n".join(lines)


def _stock_trade_levels(prediction: dict[str, Any]) -> tuple[float, float, float, float, float]:
    metadata = prediction.get("metadata", {})
    if metadata.get("forecast_entry_reference") is not None:
        entry = float(metadata["forecast_entry_reference"])
        entry_low = round(float(prediction["predicted_low"]), 2)
        entry_high = round(entry, 2)
        target_price = round(float(metadata["forecast_target_price"]), 2)
        stop_loss = round(float(metadata["forecast_downside_guard"]), 2)
        upside_pct = round(float(metadata.get("estimated_profit_pct", 0.0)), 2)
        return entry_low, entry_high, target_price, stop_loss, upside_pct
    low = float(prediction["predicted_low"])
    high = float(prediction["predicted_high"])
    midpoint = round((low + high) / 2, 2)
    width = max(0.01, high - low)
    entry_low = round(low, 2)
    entry_high = round(midpoint, 2)
    target_price = round(high, 2)
    stop_loss = round(low - width * 0.25, 2)
    upside_pct = round(((target_price - midpoint) / midpoint) * 100, 2) if midpoint else 0.0
    return entry_low, entry_high, target_price, stop_loss, upside_pct


def _category_prompt_response(query: MarketQuery) -> dict[str, Any]:
    profile = _category_profile(query)
    profile = _attach_category_news_context(profile, query)
    links = [
        *_official_research_links_for_perspective(query.perspective),
        *_trusted_master_links_for_perspective(query.perspective),
    ]
    if links:
        profile = dict(profile)
        existing_links = list(profile.get("research_source_links", ()))
        merged_links = [*existing_links]
        for item in links:
            if not any(link.get("source") == item["source"] for link in merged_links):
                merged_links.append(item)
        profile["research_sources"] = tuple(
            dict.fromkeys([*profile.get("research_sources", ()), *(item["source"] for item in merged_links)])
        )
        profile["research_source_links"] = merged_links
    return {
        "user_query": {
            "text": query.raw_text,
            "instrument_type": query.instrument_type,
            "perspective": query.perspective,
            "risk_profile": query.risk_profile,
            "investment_amount": query.investment_amount,
        },
        "category_analysis": profile,
    }


def _attach_category_news_context(profile: dict[str, Any], query: MarketQuery) -> dict[str, Any]:
    entities = _category_news_entities(query)
    if not entities:
        return profile
    data_source = RealtimeIndiaMarketDataSource(timeout_seconds=2.0)
    try:
        articles = data_source.get_news(entities)
    except Exception:
        articles = []
    if not articles:
        profile = dict(profile)
        profile["news_context"] = {
            "article_count": 0,
            "sentiment": "Neutral",
            "sentiment_score": 0,
            "impact_score_pct": 0,
            "topics": (),
            "entities": entities,
            "keyword_categories": (),
            "keyword_hits": (),
            "anomaly_flags": ("Realtime feed returned no article text during this run",),
        }
        profile["news_evidence"] = (
            {
                "source": "Realtime Feed Status",
                "title": "Trusted news feeds checked; no realtime article text returned in this run",
                "url": "",
                "published_at": datetime.now().isoformat(),
                "snippet": "The report still uses the configured official/trusted source list and data-provider framework. Re-run when network feeds are reachable for article-level evidence.",
            },
        )
        return profile
    analysis = NewsIntelligenceEngine().analyze(articles)
    profile = dict(profile)
    source_links = list(profile.get("research_source_links", ()))
    for article in articles[:16]:
        if article.url and not any(item.get("source") == article.source for item in source_links):
            source_links.append({"source": article.source, "url": article.url})
    profile["research_sources"] = tuple(
        dict.fromkeys([*profile.get("research_sources", ()), *(article.source for article in articles[:24])])
    )
    profile["research_source_links"] = source_links
    profile["news_context"] = {
        "article_count": len(articles),
        "sentiment": analysis.sentiment.value,
        "sentiment_score": round(analysis.sentiment_score, 2),
        "impact_score_pct": int(analysis.impact_score * 100),
        "topics": analysis.topics[:8],
        "entities": analysis.entities[:8],
        "keyword_categories": analysis.keyword_categories[:8],
        "keyword_hits": analysis.keyword_hits[:10],
        "anomaly_flags": analysis.anomaly_flags[:6],
    }
    profile["news_evidence"] = [
        {
            "source": article.source,
            "title": article.title,
            "url": article.url,
            "published_at": article.published_at.isoformat(),
            "snippet": article.body[:260],
        }
        for article in articles[:10]
    ]
    return profile


def _category_news_entities(query: MarketQuery) -> tuple[str, ...]:
    perspective_entities = {
        "gold_intelligence": ("gold",),
        "silver_intelligence": ("silver", "gold"),
        "gold_silver_compare": ("silver", "gold"),
        "macro_geopolitics": ("gold", "stock", "investment"),
        "macro_events": ("stock", "investment", "gold"),
        "market_summary": ("stock", "nifty", "sensex"),
        "sector_outlook": ("stock", "technology", "banking", "pharma", "auto"),
        "precious_metals_technical": ("gold", "silver"),
        "portfolio_strategy": ("mutual fund", "stock", "gold", "investment"),
        "portfolio_advisor": ("mutual fund", "stock", "gold", "investment"),
        "equity_research": (query.stock_symbol or "stock",),
        "mutual_funds": ("mutual fund", "sip", "investment"),
        "wealth_plan": ("wealth", "mutual fund", "gold", "stock"),
        "multibagger_goal": ("stock", "mutual fund", "investment"),
        "technology_investment": ("technology", "startup", "investment"),
        "ipo_analysis": ("ipo", "stock"),
        "real_estate": ("real estate", "reit"),
        "forex_analysis": ("currency", "gold", "stock"),
    }
    return perspective_entities.get(query.perspective, ())


def _format_category_prompt_text(result: dict[str, Any]) -> str:
    query = result["user_query"]
    prompt = result["category_analysis"]
    if prompt.get("type") == "policy_treaty":
        return _prepend_prompt_training(_format_policy_treaty_text(query, prompt), query.get("prompt_training"))
    if prompt.get("type") == "mutual_funds":
        return _prepend_prompt_training(_format_mutual_fund_text(query, prompt), query.get("prompt_training"))
    if prompt.get("type") == "wealth_plan":
        return _prepend_prompt_training(_format_wealth_plan_text(query, prompt), query.get("prompt_training"))
    confidence_target = prompt["signal"]
    lines = [
        f"Question: {query['text']}",
        "",
        f"{prompt['title']}:",
        f"Predicted Direction: {prompt['direction']}",
        f"Signal: {prompt['signal']}",
        f"Buy Probability: {prompt['buy_probability']}%",
        f"Hold Probability: {prompt['hold_probability']}%",
        f"Sell Probability: {prompt['sell_probability']}%",
        f"Confidence Score to {confidence_target}: {prompt['confidence_score']}%",
        f"Predicted Range: {prompt['predicted_range']}",
        f"Risk Score: {prompt['risk_score']}%",
        "Reason:",
        *[f"- {reason}" for reason in prompt["reasons"]],
    ]
    for section in prompt.get("analysis_sections", ()):
        lines.extend(["", f"{section.get('title', 'Analysis')}:"])
        for row in section.get("rows", ()):
            lines.append(
                f"- {row.get('metric', 'Metric')}: {row.get('value', '')} | {row.get('interpretation', '')}"
            )
    news_context = prompt.get("news_context") or {}
    if news_context:
        lines.extend(
            [
                "",
                "Realtime News Feed Analysis:",
                f"- Articles Checked: {news_context.get('article_count', 0)}",
                f"- Sentiment: {news_context.get('sentiment', '')} ({news_context.get('sentiment_score', 0)})",
                f"- Impact Score: {news_context.get('impact_score_pct', 0)}%",
                f"- Topics: {', '.join(news_context.get('topics', []))}",
                f"- SEO Keyword Categories: {', '.join(news_context.get('keyword_categories', []))}",
            ]
        )
    lines.extend(["", "Research Sources:", *[f"- {source}" for source in prompt["research_sources"]]])
    if prompt.get("research_source_links"):
        lines.extend(["", "Research Source URLs:"])
        lines.extend(
            f"- {item['source']}: {item['url']}"
            for item in prompt["research_source_links"]
        )
    return _prepend_prompt_training("\n".join(lines), query.get("prompt_training"))


def _format_policy_treaty_text(query: dict[str, Any], prompt: dict[str, Any]) -> str:
    lines = [
        f"Question: {query['text']}",
        "",
        f"{prompt['title']}:",
        f"Short Answer: {prompt['summary']}",
        "",
        "Signed / Announced Agreements:",
    ]
    for index, agreement in enumerate(prompt.get("agreements", ()), start=1):
        lines.extend(
            [
                f"{index}. {agreement['name']}",
                f"   Status: {agreement['status']}",
                f"   Date: {agreement['date']}",
                f"   Coverage: {agreement['coverage']}",
                f"   Why It Matters: {agreement['impact']}",
            ]
        )
    lines.extend(["", "Key Impact:"])
    lines.extend(f"- {item}" for item in prompt.get("reasons", ()))
    lines.extend(["", "Research Sources:"])
    lines.extend(f"- {source}" for source in prompt.get("research_sources", ()))
    if prompt.get("research_source_links"):
        lines.extend(["", "Research Source URLs:"])
        lines.extend(f"- {item['source']}: {item['url']}" for item in prompt["research_source_links"])
    return "\n".join(lines)


def _prepend_prompt_training(text: str, prompt_training: dict[str, Any] | None) -> str:
    training_lines = _prompt_training_lines(prompt_training)
    if not training_lines:
        return text
    lines = text.splitlines()
    if len(lines) >= 2:
        return "\n".join([lines[0], "", *training_lines, "", *lines[1:]])
    return "\n".join([*training_lines, "", text])


def _prompt_training_lines(prompt_training: dict[str, Any] | None) -> list[str]:
    if not prompt_training:
        return []
    lines = [
        "Prompt Training Context:",
        f"- Dataset: {prompt_training.get('dataset_path', 'Auto-detected JSONL corpus')}",
        f"- Agents: {', '.join(prompt_training.get('recommended_agents', [])[:6])}",
        f"- Indicators: {', '.join(prompt_training.get('required_indicators', [])[:8])}",
        f"- Expected Outputs: {', '.join(prompt_training.get('expected_outputs', [])[:8])}",
    ]
    matches = prompt_training.get("matched_training_prompts", [])
    if matches:
        lines.append("- Matched Prompt Patterns:")
        for match in matches[:3]:
            lines.append(
                "  "
                f"{match.get('asset_class')} | {match.get('domain')} | "
                f"{match.get('time_horizon')} | score {match.get('score')}"
            )
    return lines


def _format_mutual_fund_text(query: dict[str, Any], prompt: dict[str, Any]) -> str:
    lines = [
        f"Question: {query['text']}",
        "",
        "Mutual Fund SIP Recommendation:",
        f"Risk Profile: {prompt['risk_profile']}",
        f"Investment Horizon: {prompt['investment_horizon']}",
        f"Recommendation: {prompt['signal']}",
        f"Confidence Score: {prompt['confidence_score']}%",
        f"Risk Score: {prompt['risk_score']}%",
        "",
        "Suggested SIP Allocation:",
    ]
    lines.extend(
        f"- {item['category']}: {item['allocation_pct']}% - {item['purpose']}"
        for item in prompt["allocations"]
    )
    lines.extend(["", "Fund Selection Criteria:"])
    lines.extend(f"- {item}" for item in prompt["selection_criteria"])
    lines.extend(["", "Reason:"])
    lines.extend(f"- {reason}" for reason in prompt["reasons"])
    lines.extend(["", "Research Sources:"])
    lines.extend(f"- {source}" for source in prompt["research_sources"])
    if prompt.get("research_source_links"):
        lines.extend(["", "Research Source URLs:"])
        lines.extend(
            f"- {item['source']}: {item['url']}"
            for item in prompt["research_source_links"]
        )
    return "\n".join(lines)


def _format_wealth_plan_text(query: dict[str, Any], prompt: dict[str, Any]) -> str:
    lines = [
        f"Question: {query['text']}",
        "",
        "Wealth Plan:",
        f"Predicted Direction: {prompt['direction']}",
        f"Signal: {prompt['signal']}",
        f"Confidence Score: {prompt['confidence_score']}%",
        f"Risk Score: {prompt['risk_score']}%",
        "",
        "Suggested Allocation:",
    ]
    lines.extend(
        f"- {item['asset']}: {item['allocation_pct']}% - {item['purpose']}"
        for item in prompt["allocations"]
    )
    lines.extend(["", "Reason:"])
    lines.extend(f"- {reason}" for reason in prompt["reasons"])
    lines.extend(["", "Research Sources:"])
    lines.extend(f"- {source}" for source in prompt["research_sources"])
    if prompt.get("research_source_links"):
        lines.extend(["", "Research Source URLs:"])
        lines.extend(
            f"- {item['source']}: {item['url']}"
            for item in prompt["research_source_links"]
        )
    return "\n".join(lines)


def _official_research_links_for_perspective(perspective: str) -> list[dict[str, str]]:
    names = OFFICIAL_SOURCES_BY_PERSPECTIVE.get(perspective, ())
    return [
        {"source": name, "url": OFFICIAL_RESEARCH_LINKS[name]}
        for name in names
        if name in OFFICIAL_RESEARCH_LINKS
    ]


def _trusted_master_links_for_perspective(perspective: str) -> list[dict[str, str]]:
    impact_key = {
        "mutual_funds": "stock_impact_score",
        "sector_analysis": "stock_impact_score",
        "gold_silver_compare": "gold_impact_score",
        "wealth_plan": "ai_weighting_score",
        "crypto_analysis": "currency_impact_score",
        "forex_analysis": "currency_impact_score",
        "news_impact": "crisis_impact_score",
        "multi_news_intelligence": "ai_weighting_score",
        "real_estate": "stock_impact_score",
        "ipo_analysis": "stock_impact_score",
        "technology_investment": "ai_weighting_score",
        "macro_geopolitics": "crisis_impact_score",
        "macro_events": "crisis_impact_score",
        "market_summary": "stock_impact_score",
        "sector_outlook": "stock_impact_score",
        "precious_metals_technical": "gold_impact_score",
        "multibagger_goal": "ai_weighting_score",
        "equity_research": "stock_impact_score",
        "gold_intelligence": "gold_impact_score",
        "silver_intelligence": "silver_impact_score",
        "portfolio_strategy": "ai_weighting_score",
        "portfolio_advisor": "ai_weighting_score",
    }.get(perspective, "ai_weighting_score")
    links: list[dict[str, str]] = []
    for source in _ranked_trusted_master_sources(impact_key)[:8]:
        name = str(source.get("source_name") or "").strip()
        url = str(source.get("official_website") or "").strip()
        if name and url and not any(item["source"] == name for item in links):
            links.append({"source": name, "url": url})
    return links


def _ranked_trusted_master_sources(impact_key: str) -> list[dict[str, Any]]:
    return sorted(
        _trusted_master_sources(),
        key=lambda source: (
            _source_score(source, impact_key),
            _source_score(source, "trust_score"),
            _source_score(source, "ai_weighting_score"),
        ),
        reverse=True,
    )


def _trusted_master_sources() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent / "resources" / "trusted_financial_sources.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _source_score(source: dict[str, Any], key: str) -> float:
    try:
        return float(source.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


COUNTRY_ALIASES = {
    "uk": "United Kingdom",
    "u.k": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "united kingdom": "United Kingdom",
    "us": "United States",
    "u.s": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "america": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "india": "India",
}


def _treaty_country_pair(text: str) -> tuple[str, str] | None:
    lower = text.lower().strip()
    patterns = (
        r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:[?.!,]|$)",
        r"\bbetween\s+(.+?)\s*&\s*(.+?)(?:[?.!,]|$)",
        r"\b(.+?)\s*[-/]\s*(.+?)\s+(?:treaty|agreement|fta|trade deal|pact)",
    )
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        first = _normalize_country_name(match.group(1))
        second = _normalize_country_name(match.group(2))
        if first and second and first != second:
            return first, second
    return None


def _normalize_country_name(value: str) -> str:
    cleaned = re.sub(r"\b(the|government of|republic of|kingdom of)\b", " ", value.lower())
    cleaned = re.sub(r"[^a-z.\s-]", " ", cleaned)
    cleaned = " ".join(cleaned.replace("-", " ").split())
    if not cleaned:
        return ""
    if cleaned in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[cleaned]
    words = cleaned.split()
    if len(words) > 5:
        return ""
    return " ".join(word.capitalize() for word in words)


def _treaty_pair_key(pair: tuple[str, str]) -> tuple[str, str]:
    return tuple(sorted(pair))  # type: ignore[return-value]


def _treaty_profile_for_pair(pair: tuple[str, str]) -> dict[str, Any]:
    key = _treaty_pair_key(pair)
    if key == ("India", "United Kingdom"):
        return _india_uk_treaty_profile()
    if key == ("India", "United States"):
        return _india_us_treaty_profile()
    return _generic_treaty_profile(pair)


def _generic_treaty_profile(pair: tuple[str, str]) -> dict[str, Any]:
    first, second = pair
    pair_title = f"{first}-{second}"
    return {
        "type": "policy_treaty",
        "title": f"{pair_title} Treaty / Agreement Research Summary",
        "summary": (
            f"I do not have a verified built-in signed treaty list for {first} and {second} yet. "
            "This response is a structured research workflow, not a final treaty register. "
            "Validate signed, ratified, amended, terminated, and in-force agreements through official treaty databases "
            "and the two governments' foreign ministry or trade ministry records."
        ),
        "direction": "Research Required",
        "signal": "Verify",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 58,
        "predicted_range": "Not price-based; treaty, policy, and investment-impact research",
        "risk_score": 50,
        "agreements": (
            {
                "name": "Official bilateral treaty database search",
                "status": "To be verified",
                "date": "Use official treaty records",
                "coverage": "Search both country names, short names, predecessor states, amendments, protocols, and exchange-of-notes records.",
                "impact": "Prevents confusing negotiated, signed, ratified, and in-force agreements.",
            },
            {
                "name": "Trade, customs, tax, and investment agreements",
                "status": "To be verified",
                "date": "Use WTO, tax treaty, investment treaty, and trade ministry records",
                "coverage": "FTA/RTA, double-taxation agreements, bilateral investment treaties, customs cooperation, and market-access protocols.",
                "impact": "These agreements usually have the clearest effect on companies, tariffs, capital flows, and sector opportunities.",
            },
            {
                "name": "Defence, security, technology, and mobility agreements",
                "status": "To be verified",
                "date": "Use foreign ministry, defence ministry, and official gazette releases",
                "coverage": "Defence logistics, security cooperation, migration, education, digital, science, energy, and technology MoUs.",
                "impact": "Useful for sector impact analysis across defence, technology, education, travel, and services.",
            },
        ),
        "reasons": (
            "Treaty prompts are now routed as policy/news research instead of NSE stock symbols.",
            "The same prompt pattern works for different country pairs; known pairs can return curated summaries, while unknown pairs return a verification-first institutional checklist.",
            "Separate signed documents from announced negotiations, MoUs, ratification status, effective dates, and later amendments.",
            "For market impact, classify each agreement by affected sectors, implementation timeline, tariff or regulatory change, and investor risk.",
        ),
        "research_sources": (
            "UN Treaty Collection",
            "WTO Regional Trade Agreements Database",
            "OECD Tax Treaties",
            "WIPO Lex",
        ),
        "research_source_links": (
            {"source": "UN Treaty Collection", "url": "https://treaties.un.org/"},
            {"source": "WTO Regional Trade Agreements Database", "url": "https://rtais.wto.org/"},
            {"source": "OECD Tax Treaties", "url": "https://www.oecd.org/tax/treaties/"},
            {"source": "WIPO Lex", "url": "https://www.wipo.int/wipolex/"},
        ),
    }


def _india_uk_treaty_profile() -> dict[str, Any]:
    return {
        "type": "policy_treaty",
        "title": "India-UK Treaty / Agreement Summary",
        "summary": (
            "The main India-UK agreement is the Comprehensive Economic and Trade Agreement "
            "(CETA), also called the India-UK Free Trade Agreement. It was signed in July 2025. "
            "The wider package also includes social-security/mobility cooperation through a "
            "Double Contribution Convention arrangement and a renewed Comprehensive and Strategic Partnership."
        ),
        "direction": "Upward",
        "signal": "Watchlist",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 82,
        "predicted_range": "Not price-based; policy and trade impact analysis",
        "risk_score": 38,
        "agreements": (
            {
                "name": "India-UK Comprehensive Economic and Trade Agreement (CETA) / Free Trade Agreement",
                "status": "Signed; implementation depends on ratification/legal procedures",
                "date": "24 July 2025",
                "coverage": "Goods, services, tariff cuts, investment, public procurement, intellectual property, digital trade, and business access.",
                "impact": "Designed to reduce trade barriers, expand bilateral trade, and improve market access for exporters and investors.",
            },
            {
                "name": "Double Contribution Convention / social-security contribution arrangement",
                "status": "Associated with the India-UK trade package",
                "date": "Announced/concluded alongside the 2025 FTA package",
                "coverage": "Aims to reduce double social-security contribution burden for eligible temporary professionals.",
                "impact": "Supports skilled-worker mobility and lowers assignment costs for companies and employees.",
            },
            {
                "name": "Renewed Comprehensive and Strategic Partnership",
                "status": "Signed/renewed during the trade-deal visit",
                "date": "July 2025",
                "coverage": "Defence, education, climate, technology, innovation, migration cooperation, and security collaboration.",
                "impact": "Extends the relationship beyond trade into strategic, technology, education, and security cooperation.",
            },
        ),
        "reasons": (
            "CETA is the core signed trade agreement between India and the UK.",
            "Tariff reductions may benefit Indian textiles, food products, gems/jewellery, engineering goods, pharmaceuticals, and UK whisky, autos, medical devices, aerospace, and machinery.",
            "The UK government estimated long-run gains including higher bilateral trade and regional economic benefits.",
            "Track ratification, implementation dates, product-level tariff schedules, and sector exclusions before making business or investment decisions.",
        ),
        "research_sources": (
            "GOV.UK India trade deal press release",
            "UK-India CETA / FTA public reporting",
            "India-UK trade and social-security reporting",
        ),
        "research_source_links": (
            {
                "source": "GOV.UK - Historic trade deal with India signed",
                "url": "https://www.gov.uk/government/news/prime-minister-secures-thousands-of-british-jobs-and-6-billion-in-investment-and-export-wins-as-historic-trade-deal-with-india-signed",
            },
            {
                "source": "The Guardian - UK-India trade deal signed",
                "url": "https://www.theguardian.com/politics/2025/jul/24/starmer-modi-uk-india-free-trade-agreement-deal-signed",
            },
            {
                "source": "Economic Times - India-UK pact details",
                "url": "https://economictimes.indiatimes.com/news/economy/foreign-trade/indiauk-pact-aims-to-double-trade-to-112-billion-by-2030-heres-who-will-benefit-what-will-become-cheaper-how-it-will-change-jobs/articleshow/122884882.cms",
            },
        ),
    }


def _india_us_treaty_profile() -> dict[str, Any]:
    return {
        "type": "policy_treaty",
        "title": "India-US Treaty / Agreement Summary",
        "summary": (
            "India and the United States have several major signed strategic, defence, nuclear, "
            "technology, and logistics agreements. As of the latest available reporting, a broad "
            "India-US free trade agreement/trade pact has been discussed and negotiated, but it is "
            "not the same as a fully signed comprehensive FTA like India-UK CETA."
        ),
        "direction": "Selective",
        "signal": "Watchlist",
        "buy_probability": 0,
        "hold_probability": 100,
        "sell_probability": 0,
        "confidence_score": 80,
        "predicted_range": "Not price-based; bilateral policy and trade impact analysis",
        "risk_score": 42,
        "agreements": (
            {
                "name": "India-US Civil Nuclear Agreement / 123 Agreement",
                "status": "Signed and implemented through legal/IAEA/NSG processes",
                "date": "Framework announced 18 July 2005; operational steps completed across 2008-2009",
                "coverage": "Civil nuclear cooperation, safeguards, and opening civilian nuclear commerce with India.",
                "impact": "A landmark strategic agreement that transformed India-US relations and enabled civil nuclear cooperation.",
            },
            {
                "name": "LEMOA - Logistics Exchange Memorandum of Agreement",
                "status": "Signed",
                "date": "2016",
                "coverage": "Mutual logistics support, refuelling, replenishment, and access for military cooperation.",
                "impact": "Improves interoperability and practical defence cooperation between both militaries.",
            },
            {
                "name": "COMCASA - Communications Compatibility and Security Agreement",
                "status": "Signed",
                "date": "2018",
                "coverage": "Secure communications and access to advanced encrypted defence communication systems.",
                "impact": "Enables closer defence technology integration and secure operational communication.",
            },
            {
                "name": "BECA - Basic Exchange and Cooperation Agreement",
                "status": "Signed",
                "date": "2020",
                "coverage": "Geospatial intelligence, mapping, navigation, and defence data sharing.",
                "impact": "Strengthens precision, situational awareness, and defence cooperation.",
            },
            {
                "name": "Security of Supply Arrangement (SOSA)",
                "status": "Signed",
                "date": "2024",
                "coverage": "Defence supply-chain priority support and industrial cooperation.",
                "impact": "Supports resilient defence supply chains and defence-industrial collaboration.",
            },
            {
                "name": "India-US trade agreement / BTA / FTA discussions",
                "status": "Under negotiation / framework discussions; not a fully signed comprehensive FTA in this app's current source set",
                "date": "Negotiations active through 2025-2026 reporting",
                "coverage": "Tariffs, market access, trade competitiveness, and commercial terms.",
                "impact": "Could materially affect exporters, importers, pharma, textiles, technology, agriculture, and manufacturing if finalized.",
            },
        ),
        "reasons": (
            "There is no single India-US comprehensive FTA equivalent to India-UK CETA currently treated here as signed.",
            "The strongest signed India-US agreements are strategic and defence/nuclear agreements: Civil Nuclear/123, LEMOA, COMCASA, BECA, and SOSA.",
            "Recent India-US trade-pact reporting suggests negotiations/framework discussions, but implementation depends on unresolved commercial/tariff terms.",
            "For investment impact, separate defence/technology beneficiaries from tariff-sensitive exporters before making decisions.",
        ),
        "research_sources": (
            "US-India Civil Nuclear Agreement public record",
            "India-US foundational defence agreements public record",
            "India-US trade pact reporting",
        ),
        "research_source_links": (
            {
                "source": "India-US Civil Nuclear Agreement overview",
                "url": "https://en.wikipedia.org/wiki/India%E2%80%93United_States_Civil_Nuclear_Agreement",
            },
            {
                "source": "India-US Foundational Agreements overview",
                "url": "https://en.wikipedia.org/wiki/Foundational_agreement",
            },
            {
                "source": "Times of India - India-US trade deal status",
                "url": "https://timesofindia.indiatimes.com/business/india-business/india-us-trade-deal-piyush-goyal-reveals-whats-holding-up-the-pact/articleshow/131876706.cms",
            },
        ),
    }


def _multibagger_goal_profile(query: MarketQuery) -> dict[str, Any]:
    multiple = _requested_return_multiple(query.raw_text)
    horizon_years = _requested_horizon_years(query.raw_text)
    required_cagr = (multiple ** (1 / horizon_years) - 1) * 100 if horizon_years else 0.0
    risk_score = min(95, 50 + int(required_cagr * 0.8))
    buy_probability = max(18, min(48, int(62 - required_cagr * 0.8)))
    hold_probability = max(34, min(58, 100 - buy_probability - 22))
    sell_probability = 100 - buy_probability - hold_probability
    return {
        "type": "wealth_multiplier",
        "title": f"{multiple:g}X Wealth Multiplication Plan",
        "direction": "High Growth",
        "signal": "Accumulate Selectively",
        "buy_probability": buy_probability,
        "hold_probability": hold_probability,
        "sell_probability": sell_probability,
        "confidence_score": max(48, min(76, 86 - int(required_cagr * 0.45))),
        "predicted_range": (
            f"To target {multiple:g}X in {horizon_years:g} years, required CAGR is about {required_cagr:.1f}% before taxes/costs"
        ),
        "risk_score": risk_score,
        "reasons": (
            f"{multiple:g}X in {horizon_years:g} years needs about {required_cagr:.1f}% CAGR before tax, expense ratio, slippage, and bad-year drawdowns.",
            "This is not a guaranteed price prediction; it is a high-growth allocation framework with explicit risk controls.",
            "An ordinary diversified SIP is unlikely to reliably deliver this target alone; the plan needs high-growth equity exposure plus disciplined risk controls.",
            "Use a core-satellite structure: index/flexi-cap core, mid/small-cap and quality direct-equity satellites, and a small tactical reserve.",
            "For higher multiples, focus on earnings growth, reinvestment runway, balance-sheet quality, valuation discipline, and catalyst timing.",
            "Control downside with position sizing, staged buying, review triggers, and exit rules when thesis, earnings trend, or leverage quality breaks.",
        ),
        "analysis_sections": (
            {
                "title": "Financial Expert Allocation",
                "rows": (
                    {"metric": "Core Equity SIP", "value": "35% index/flexi-cap/large-mid funds", "interpretation": "Compounding base; less fragile than concentrated stocks."},
                    {"metric": "Growth Satellite", "value": "30% mid/small-cap funds or quality growth basket", "interpretation": "Needed for 3X ambition, but should be reviewed quarterly."},
                    {"metric": "Direct Equity Themes", "value": "20% sector leaders in banking, capex, pharma, IT recovery, autos", "interpretation": "Use only with stock-level research and stop/review rules."},
                    {"metric": "Gold/Debt/Cash", "value": "15% hedge and opportunity reserve", "interpretation": "Reduces forced selling during corrections."},
                ),
            },
            {
                "title": "Risk Checklist",
                "rows": (
                    {"metric": "Feasibility", "value": "High risk", "interpretation": "3X in 5 years is aggressive; plan for 25-35% interim drawdowns."},
                    {"metric": "Review Triggers", "value": "Earnings downgrade, valuation excess, leverage increase, policy shock", "interpretation": "Exit or reduce exposure if thesis breaks."},
                    {"metric": "Tax/Cost", "value": "LTCG/STCG, expense ratio, brokerage, slippage", "interpretation": "Net return target is higher than headline CAGR."},
                ),
            },
        ),
        "research_sources": (
            "NSE/BSE disclosures",
            "SEBI filings",
            "AMFI and index fund category data",
            "Trusted financial news feeds",
            "Compounding and risk model",
        ),
    }


def _requested_return_multiple(text: str) -> float:
    lower = text.lower()
    match = re.search(r"\b([2-9])\s*x\b", lower)
    if not match:
        match = re.search(r"\b([2-9])x\b", lower)
    if match:
        return float(match.group(1))
    if "triple" in lower:
        return 3.0
    if "double" in lower:
        return 2.0
    return 2.0


def _requested_horizon_years(text: str) -> float:
    lower = text.lower()
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(year|years|yr|yrs)\b", lower)
    if match:
        return max(0.25, float(match.group(1)))
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(month|months)\b", lower)
    if match:
        return max(0.25, float(match.group(1)) / 12)
    return 5.0


def _prompt_focus(text: str) -> str:
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*", "", text).strip()
    return cleaned[:140] or "Investment research request"


def _gold_intelligence_profile(query: MarketQuery) -> dict[str, Any]:
    focus = _prompt_focus(query.raw_text)
    return {
        "type": "gold_intelligence",
        "title": "Gold Intelligence Data Provider Report",
        "summary": f"Research focus: {focus}. This report combines macro, currency, demand/supply, sentiment, and policy-feed signals.",
        "direction": "Data Dependent",
        "signal": "Hold",
        "buy_probability": 42,
        "hold_probability": 46,
        "sell_probability": 12,
        "confidence_score": 64,
        "predicted_range": "Scenario-based; use live gold, USD/INR, inflation, ETF/central-bank demand, and news sentiment",
        "risk_score": 61,
        "analysis_sections": (
            {
                "title": "Gold Data Inputs",
                "rows": (
                    {"metric": "Price Drivers", "value": "MCX/domestic gold, COMEX gold, USD/INR, crude oil, real yields", "interpretation": "Direction and volatility base"},
                    {"metric": "Demand Drivers", "value": "ETF flow, jewellery demand, festival demand, central-bank buying", "interpretation": "Accumulation or distribution signal"},
                    {"metric": "Macro Drivers", "value": "Inflation, RBI/US rates, fiscal policy, import duty", "interpretation": "Fair-value and risk premium"},
                    {"metric": "News Drivers", "value": "Trusted RSS, official feeds, geopolitical and currency news", "interpretation": "Sentiment and surprise impact"},
                ),
            },
            {
                "title": "Investor Interpretation",
                "rows": (
                    {"metric": "Bullish Setup", "value": "INR weakness, inflation pressure, safe-haven demand, central-bank buying", "interpretation": "Accumulation can be considered in stages"},
                    {"metric": "Bearish Setup", "value": "Strong USD risk-on rally, lower inflation, weaker ETF flow", "interpretation": "Avoid chasing; prefer hedged allocation"},
                    {"metric": "Execution", "value": "Use staggered entry, target range, stop-loss/review level", "interpretation": "Protect capital during high volatility"},
                ),
            },
        ),
        "reasons": (
            "Gold prompts require macro, currency, demand, and sentiment data, not only a spot price.",
            "Inflation-adjusted fair value should be cross-checked against USD/INR and real-yield direction.",
            "News sentiment can change the expected range by widening or narrowing the risk premium.",
            "Future prices remain probabilistic; output should show scenario ranges and risk score.",
        ),
        "research_sources": ("RBI", "PIB", "India Budget", "Trusted gold and commodity news feeds", "Market trend model"),
    }


def _silver_intelligence_profile(query: MarketQuery) -> dict[str, Any]:
    focus = _prompt_focus(query.raw_text)
    return {
        "type": "silver_intelligence",
        "title": "Silver Intelligence Data Provider Report",
        "summary": f"Research focus: {focus}. Silver is analyzed as both precious metal and industrial input.",
        "direction": "High Beta",
        "signal": "Hold",
        "buy_probability": 44,
        "hold_probability": 42,
        "sell_probability": 14,
        "confidence_score": 62,
        "predicted_range": "Scenario-based; use silver price, gold/silver ratio, solar demand, industrial cycle, and USD/INR",
        "risk_score": 72,
        "analysis_sections": (
            {
                "title": "Silver Demand Matrix",
                "rows": (
                    {"metric": "Industrial Demand", "value": "Solar, electronics, EV, 5G and manufacturing indicators", "interpretation": "Primary growth driver"},
                    {"metric": "Precious-Metal Demand", "value": "Gold comparison, safe-haven flows, currency weakness", "interpretation": "Macro hedge component"},
                    {"metric": "Supply Risk", "value": "Mine supply, recycling, import flow, inventory tightness", "interpretation": "Volatility and shortage signal"},
                    {"metric": "Relative Value", "value": "Gold/silver ratio and recent relative performance", "interpretation": "Accumulation timing"},
                ),
            },
            {
                "title": "Investor Interpretation",
                "rows": (
                    {"metric": "Accumulation Case", "value": "Industrial demand rising with supportive macro sentiment", "interpretation": "Higher upside but staggered entry needed"},
                    {"metric": "Risk Case", "value": "Economic slowdown or risk-off liquidity shock", "interpretation": "Silver can underperform gold sharply"},
                    {"metric": "Position Sizing", "value": "Smaller than gold for conservative investors", "interpretation": "Controls drawdown risk"},
                ),
            },
        ),
        "reasons": (
            "Silver has higher volatility than gold because industrial demand and liquidity cycles matter.",
            "Solar manufacturing and electronics demand can support medium-term accumulation scores.",
            "Supply shortage news can create sharp upside spikes but also reversal risk.",
            "Compare silver with gold before deciding allocation size.",
        ),
        "research_sources": ("Commodity news feeds", "PIB and policy feeds", "Industrial demand indicators", "Gold/silver comparison model"),
    }


def _portfolio_strategy_profile(query: MarketQuery) -> dict[str, Any]:
    focus = _prompt_focus(query.raw_text)
    return {
        "type": "portfolio_strategy",
        "title": "Portfolio And Risk Data Provider Report",
        "summary": f"Research focus: {focus}. The output is designed for allocation, stress testing, and risk-adjusted return decisions.",
        "direction": "Balanced",
        "signal": "Accumulate Selectively",
        "buy_probability": 58,
        "hold_probability": 34,
        "sell_probability": 8,
        "confidence_score": 70,
        "predicted_range": "Goal-based; optimize allocation by risk profile, return target, drawdown tolerance, and timeline",
        "risk_score": 48,
        "allocations": (
            {"asset": "Index / Large-cap Equity", "allocation_pct": 35, "purpose": "core compounding and liquidity"},
            {"asset": "Flexi/Mid-cap Equity", "allocation_pct": 20, "purpose": "growth and alpha potential"},
            {"asset": "Debt / Short Duration", "allocation_pct": 20, "purpose": "stability and rebalancing reserve"},
            {"asset": "Gold / Silver ETF", "allocation_pct": 15, "purpose": "inflation and currency hedge"},
            {"asset": "Cash / Tactical Reserve", "allocation_pct": 10, "purpose": "volatility buffer and opportunity fund"},
        ),
        "analysis_sections": (
            {
                "title": "Portfolio Data Inputs",
                "rows": (
                    {"metric": "Return Model", "value": "Expected return, CAGR need, valuation and earnings trend", "interpretation": "Defines target feasibility"},
                    {"metric": "Risk Model", "value": "Volatility, drawdown, asset correlation, liquidity", "interpretation": "Controls allocation size"},
                    {"metric": "Stress Tests", "value": "Inflation, recession, bull market, slowdown, rate hike", "interpretation": "Shows portfolio resilience"},
                    {"metric": "Rebalancing", "value": "Quarterly review or 5% allocation drift", "interpretation": "Locks gains and reduces concentration"},
                ),
            },
        ),
        "reasons": (
            "Portfolio prompts require allocation and risk-adjusted return logic, not a single stock or commodity price.",
            "Income, preservation, low-volatility, and growth goals should produce different allocation tilts.",
            "Stress testing protects the investor from overfitting to the current market mood.",
            "Use staged deployment and rebalance when asset weights drift materially.",
        ),
        "research_sources": ("SEBI", "AMFI", "RBI", "Trusted financial news feeds", "Portfolio risk model"),
    }


def _sector_outlook_profile(query: MarketQuery) -> dict[str, Any]:
    return {
        "type": "sector_outlook",
        "title": "India Sector Outlook - 6 to 12 Months",
        "direction": "Selective Uptrend",
        "signal": "Accumulate Selectively",
        "buy_probability": 61,
        "hold_probability": 31,
        "sell_probability": 8,
        "confidence_score": 71,
        "predicted_range": "Sector rotation framework; use stock-specific valuation and earnings confirmation before execution",
        "risk_score": 57,
        "analysis_sections": (
            {
                "title": "Top 5 Sector Ranking",
                "rows": (
                    {"metric": "1. Banking & Financials", "value": "HDFCBANK, ICICIBANK, SBIN", "interpretation": "Credit growth, asset-quality normalization, rate-cut optionality; watch NIM compression and credit costs."},
                    {"metric": "2. Capital Goods / Infrastructure", "value": "LT, ABB, SIEMENS", "interpretation": "Order-book visibility, capex cycle, defence/railways/power spend; watch execution and valuation."},
                    {"metric": "3. Pharma & Healthcare", "value": "SUNPHARMA, CIPLA, DRREDDY", "interpretation": "Defensive earnings, US generics, domestic chronic therapies; watch USFDA and pricing risk."},
                    {"metric": "4. IT Services", "value": "TCS, INFY, HCLTECH", "interpretation": "Rate-cut cycle and AI/cloud spending recovery; watch weak discretionary tech budgets."},
                    {"metric": "5. Autos & EV Supply Chain", "value": "MARUTI, TATAMOTORS, M&M", "interpretation": "Premiumization, EV adoption, rural recovery; watch commodity and demand cyclicality."},
                ),
            },
            {
                "title": "Key Catalysts To Watch",
                "rows": (
                    {"metric": "Rates", "value": "RBI liquidity, repo guidance, bond yields", "interpretation": "Supports banks, NBFCs, real estate, and rate-sensitive consumption."},
                    {"metric": "Earnings", "value": "Margin expansion, order inflow, revenue growth", "interpretation": "Confirms whether sector momentum is fundamental or only narrative-driven."},
                    {"metric": "Policy", "value": "Budget capex, PLI, defence, power, infrastructure awards", "interpretation": "Can create multi-quarter earnings visibility."},
                    {"metric": "Flows", "value": "FII/DII allocation and sector rotation", "interpretation": "High-quality sectors outperform when flows and earnings align."},
                ),
            },
        ),
        "reasons": (
            "A 6-12 month sector call should rank sectors by earnings visibility, policy support, valuation comfort, and liquidity flows.",
            "Do not buy an entire sector blindly; select leaders with balance-sheet strength and earnings upgrades.",
            "Use staggered allocation because high-quality sectors can still correct if valuations are stretched.",
        ),
        "research_sources": ("NSE/BSE sector data", "SEBI filings", "RBI policy updates", "Budget/PIB policy releases", "Trusted financial news feeds"),
    }


def _market_summary_profile(query: MarketQuery) -> dict[str, Any]:
    return {
        "type": "market_summary",
        "title": "India Live Market Summary",
        "direction": "Mixed / Breadth Dependent",
        "signal": "Hold",
        "buy_probability": 43,
        "hold_probability": 45,
        "sell_probability": 12,
        "confidence_score": 64,
        "predicted_range": "Market breadth report; verify live Sensex/Nifty levels and sector heatmap before intraday execution",
        "risk_score": 54,
        "analysis_sections": (
            {
                "title": "Market Dashboard",
                "rows": (
                    {"metric": "Nifty / Sensex", "value": "Check live index trend, gap direction, and previous-day close", "interpretation": "Positive if index holds above VWAP/previous close with broad participation."},
                    {"metric": "Market Breadth", "value": "Advance/decline ratio, midcap/smallcap breadth", "interpretation": "Healthy breadth confirms risk-on; narrow breadth warns against chasing index strength."},
                    {"metric": "Sector Heatmap", "value": "Banks, IT, pharma, autos, metals, energy, FMCG", "interpretation": "Sector leadership matters more than index headline for trade selection."},
                    {"metric": "FII/DII Flows", "value": "Use latest exchange/provisional data where available", "interpretation": "FII selling with DII support often creates stock-specific rather than broad-market opportunities."},
                ),
            },
            {
                "title": "Notable Movers Framework",
                "rows": (
                    {"metric": "Momentum Movers", "value": "High volume plus price breakout", "interpretation": "Trade only if price sustains above opening range/VWAP."},
                    {"metric": "News Movers", "value": "Earnings, order wins, policy, management commentary", "interpretation": "Prefer news with revenue/earnings impact, not only headlines."},
                    {"metric": "Avoid List", "value": "High leverage, weak results, regulatory stress, abnormal volume reversal", "interpretation": "Avoid low-quality spikes without institutional confirmation."},
                ),
            },
        ),
        "reasons": (
            "A live market summary should separate index trend, breadth, sector rotation, flows, and stock-specific catalysts.",
            "Intraday conviction improves only when index direction, sector leadership, and volume all agree.",
            "Without licensed exchange ticks, this app gives a research dashboard and evidence framework, not an executable exchange quote.",
        ),
        "research_sources": ("NSE/BSE market data", "Exchange circulars", "FII/DII flow reports", "Trusted market news feeds"),
    }


def _macro_events_profile(query: MarketQuery) -> dict[str, Any]:
    return {
        "type": "macro_events",
        "title": "Top Macro And Policy Events Impacting Indian Markets",
        "direction": "Event Driven",
        "signal": "Hold",
        "buy_probability": 38,
        "hold_probability": 48,
        "sell_probability": 14,
        "confidence_score": 68,
        "predicted_range": "Event-impact matrix; map each event to equities, bonds, INR, gold, and sector rotation",
        "risk_score": 64,
        "analysis_sections": (
            {
                "title": "Top 5 Event Impact Matrix",
                "rows": (
                    {"metric": "1. RBI Policy / Liquidity", "value": "Repo guidance, CRR/OMO/liquidity stance", "interpretation": "Dovish liquidity supports banks, NBFCs, bonds; hawkish stance pressures duration and cyclicals."},
                    {"metric": "2. CPI / Inflation", "value": "Food inflation, core CPI, fuel pass-through", "interpretation": "High CPI supports gold/defensives, pressures rate-sensitive equities and bonds."},
                    {"metric": "3. GDP / Earnings Cycle", "value": "Growth momentum, capex, consumption, PMI", "interpretation": "Strong growth supports cyclicals; slowdown favors defensives and quality large caps."},
                    {"metric": "4. FII/DII Flows", "value": "Foreign selling/buying versus domestic support", "interpretation": "FII selling pressures INR/equities; DII buying can cushion large-cap drawdowns."},
                    {"metric": "5. Election / Geopolitical Risk", "value": "Policy continuity, oil shock, war risk, tariffs", "interpretation": "Raises volatility, supports gold/energy hedges, can weaken INR if oil rises."},
                ),
            },
            {
                "title": "Asset Impact",
                "rows": (
                    {"metric": "Equities", "value": "Positive if liquidity, earnings, and flows align", "interpretation": "Prefer quality sectors during event uncertainty."},
                    {"metric": "Bonds", "value": "Benefit from lower inflation and dovish RBI", "interpretation": "Duration risk rises if CPI surprises higher."},
                    {"metric": "INR", "value": "Sensitive to crude, FII flows, USD strength", "interpretation": "Weak INR supports IT/gold, hurts importers."},
                ),
            },
        ),
        "reasons": (
            "Macro event analysis must show transmission into equities, bonds, INR, commodities, and sector rotation.",
            "Policy surprises matter more than expected events already priced by the market.",
            "Risk management should be tighter around CPI, RBI, election, crude, and geopolitical event windows.",
        ),
        "research_sources": ("RBI", "MOSPI/CPI releases", "GDP releases", "Exchange FII/DII data", "PIB and trusted macro news feeds"),
    }


def _precious_metals_technical_profile(query: MarketQuery) -> dict[str, Any]:
    metal = "Silver" if "silver" in query.raw_text.lower() else "Gold"
    unit = "INR per kg" if metal == "Silver" else "INR per 10g"
    risk = 71 if metal == "Silver" else 58
    return {
        "type": "precious_metals_technical",
        "title": f"{metal} 7-Day Technical Outlook",
        "direction": "Range Bound With Breakout Bias" if metal == "Gold" else "High Beta Range",
        "signal": "Hold",
        "buy_probability": 45 if metal == "Gold" else 42,
        "hold_probability": 45 if metal == "Gold" else 40,
        "sell_probability": 10 if metal == "Gold" else 18,
        "confidence_score": 67 if metal == "Gold" else 61,
        "predicted_range": f"7-day technical range requires live {metal.lower()} quote; use support/resistance bands and volatility buffer in {unit}",
        "risk_score": risk,
        "analysis_sections": (
            {
                "title": "7-Day Technical Framework",
                "rows": (
                    {"metric": "Trend", "value": "Compare current price with 7-day high/low and 20-period moving average", "interpretation": "Above moving average with rising volume is bullish; below support is defensive."},
                    {"metric": "Support", "value": "Prior swing low minus 0.5x average daily move", "interpretation": "Fresh longs should not be added below support without reversal confirmation."},
                    {"metric": "Resistance", "value": "Prior swing high plus 0.5x average daily move", "interpretation": "Breakout is valid only if price sustains above resistance with volume/news support."},
                    {"metric": "Volatility", "value": "Use average daily move and worst daily move", "interpretation": "Position size should shrink when volatility expands."},
                ),
            },
            {
                "title": "Trader Playbook",
                "rows": (
                    {"metric": "Bullish Entry", "value": "Buy on close above resistance or pullback to support with positive news", "interpretation": "Use staggered entries; avoid all-in trades."},
                    {"metric": "Stop / Review", "value": "Below support or below prior day low after breakout failure", "interpretation": "Protect capital first; metals can reverse sharply."},
                    {"metric": "Risk Notes", "value": "Track USD/INR, COMEX trend, RBI/US rates, CPI, geopolitical risk", "interpretation": "Macro confirmation improves technical reliability."},
                ),
            },
        ),
        "reasons": (
            f"{metal} 7-day trading should combine current INR price, recent trend, volatility, and macro/news confirmation.",
            "Do not treat a 7-day outlook as certainty; it is a tactical range with invalidation levels.",
            "Indian traders should account for USD/INR and global futures movement before execution.",
        ),
        "research_sources": ("Groww precious-metal rates", "Yahoo/commodity historical fallback", "RBI/USDINR context", "Trusted commodity news feeds"),
    }


def _category_profile(query: MarketQuery) -> dict[str, Any]:
    treaty_pair = _treaty_country_pair(query.raw_text)
    if treaty_pair:
        return _treaty_profile_for_pair(treaty_pair)
    profiles = {
        "mutual_funds": {
            "type": "mutual_funds",
            "title": "Mutual Fund Recommendation",
            "direction": "Upward",
            "signal": "Buy",
            "buy_probability": 72,
            "hold_probability": 24,
            "sell_probability": 4,
            "confidence_score": 76,
            "predicted_range": "Not price-based; use SIP allocation and fund category mix",
            "risk_score": 46 if query.risk_profile != "High" else 62,
            "risk_profile": query.risk_profile or "Medium",
            "investment_horizon": "5 years or more",
            "allocations": (
                {
                    "category": "Nifty 50 / Sensex Index Fund",
                    "allocation_pct": 30,
                    "purpose": "low-cost core equity exposure",
                },
                {
                    "category": "Flexi Cap Fund",
                    "allocation_pct": 25,
                    "purpose": "active allocation across market caps",
                },
                {
                    "category": "Large & Mid Cap Fund",
                    "allocation_pct": 20,
                    "purpose": "growth with relatively balanced risk",
                },
                {
                    "category": "Mid Cap Fund",
                    "allocation_pct": 15,
                    "purpose": "higher growth potential with higher volatility",
                },
                {
                    "category": "Short Duration / Debt Fund",
                    "allocation_pct": 10,
                    "purpose": "stability and rebalancing reserve",
                },
            ),
            "selection_criteria": (
                "Prefer Direct Plan - Growth option for long-term SIPs.",
                "Check 5-year and 10-year rolling returns, not only recent 1-year performance.",
                "Prefer consistent funds with reasonable expense ratio and stable fund manager process.",
                "Avoid over-concentration in too many funds from the same category.",
                "Review overlap between flexi-cap, large-cap, and index funds before investing.",
            ),
            "reasons": (
                "SIP approach reduces timing risk through rupee-cost averaging.",
                "Diversified large-cap, flexi-cap, index, and balanced allocation can reduce single-stock risk.",
                "Medium-to-long horizon supports equity mutual fund exposure with periodic review.",
                "Debt or hybrid allocation should increase if the investor has low risk tolerance.",
            ),
            "research_sources": ("AMFI category data", "SEBI mutual fund framework", "Market trend and risk model"),
        },
        "sector_analysis": {
            "title": "IT Sector Analysis",
            "direction": "Sideways",
            "signal": "Hold",
            "buy_probability": 42,
            "hold_probability": 48,
            "sell_probability": 10,
            "confidence_score": 68,
            "predicted_range": "Sector-level; compare TCS, INFY, HCLTECH, WIPRO, TECHM individually",
            "risk_score": 58,
            "reasons": (
                "Indian IT performance depends heavily on US/EU technology spending and deal pipeline.",
                "USD/INR movement can support export earnings when INR weakens.",
                "Margin pressure, delayed client decisions, and global slowdown risk can cap upside.",
                "Prefer stronger large-cap IT names until earnings momentum improves.",
            ),
            "research_sources": ("NSE/BSE sector trends", "Company news feeds", "Global technology demand indicators"),
        },
        "gold_silver_compare": {
            "title": "Gold And Silver Comparison",
            "direction": "Upward",
            "signal": "Hold",
            "buy_probability": 54,
            "hold_probability": 38,
            "sell_probability": 8,
            "confidence_score": 66,
            "predicted_range": "Use gold/silver instrument-specific live quotes before execution",
            "risk_score": 63,
            "reasons": (
                "Gold is usually more defensive during inflation, currency weakness, and geopolitical stress.",
                "Silver has higher industrial-demand sensitivity and can move more sharply than gold.",
                "Silver may outperform in risk-on commodity cycles, but volatility is higher.",
                "A split allocation can balance safe-haven and industrial-metal exposure.",
            ),
            "research_sources": ("Commodity market trend model", "USD/INR and inflation factors", "Global demand indicators"),
        },
        "crypto_analysis": {
            "title": "Crypto Research",
            "direction": "Volatile",
            "signal": "Hold",
            "buy_probability": 32,
            "hold_probability": 44,
            "sell_probability": 24,
            "confidence_score": 52,
            "predicted_range": "Not available without crypto exchange connector",
            "risk_score": 88,
            "reasons": (
                "Crypto assets have high volatility and can move sharply on liquidity and regulatory news.",
                "Position size should be small relative to total portfolio risk.",
                "Use stop-loss and avoid leverage unless a dedicated crypto strategy exists.",
            ),
            "research_sources": ("Crypto market risk model", "Global liquidity indicators"),
        },
        "real_estate": {
            "title": "Real Estate And REIT Research",
            "direction": "Sideways",
            "signal": "Hold",
            "buy_probability": 38,
            "hold_probability": 52,
            "sell_probability": 10,
            "confidence_score": 62,
            "predicted_range": "Location and project specific; validate RERA registration and local price trend",
            "risk_score": 61,
            "reasons": (
                "Real estate decisions depend on location liquidity, rental yield, loan rates, and project completion risk.",
                "RERA registration, builder track record, title clarity, and occupancy certificate status should be verified.",
                "REITs can provide listed real-estate exposure with better liquidity than direct property.",
                "Interest-rate and budget policy changes can materially affect affordability and demand.",
            ),
            "research_sources": ("RERA and MoHUA policy sources", "SEBI REIT framework", "RBI interest-rate context"),
        },
        "ipo_analysis": {
            "title": "IPO Research",
            "direction": "Selective",
            "signal": "Hold",
            "buy_probability": 40,
            "hold_probability": 48,
            "sell_probability": 12,
            "confidence_score": 59,
            "predicted_range": "IPO-specific; check DRHP/RHP, valuation, GMP risk, and listing-date liquidity",
            "risk_score": 68,
            "reasons": (
                "IPO quality depends on business durability, promoter history, use of proceeds, valuation, and subscription data.",
                "SEBI filings, exchange notices, and RHP/DRHP disclosures should be checked before applying.",
                "Grey-market premium is unofficial and should not override fundamentals.",
                "Listing gains can differ sharply from long-term investment suitability.",
            ),
            "research_sources": ("SEBI offer document filings", "NSE/BSE IPO notices", "Capital market risk model"),
        },
        "technology_investment": {
            "title": "New Technology Investment Research",
            "direction": "Upward",
            "signal": "Hold",
            "buy_probability": 50,
            "hold_probability": 42,
            "sell_probability": 8,
            "confidence_score": 64,
            "predicted_range": "Theme-level; evaluate AI, semiconductor, digital public infrastructure, and startup exposure separately",
            "risk_score": 66,
            "reasons": (
                "Technology themes can compound strongly but are sensitive to valuation, execution, and policy support.",
                "Government incentives, MeitY policy, DPIIT startup updates, and semiconductor programs can affect opportunity size.",
                "Prefer diversified exposure unless a company has clear revenue, margins, and competitive advantages.",
                "Avoid over-concentration in hype-driven themes without cash-flow visibility.",
            ),
            "research_sources": ("MeitY policy updates", "DPIIT startup updates", "SEBI/NSE/BSE market disclosures"),
        },
        "forex_analysis": {
            "title": "Forex Research",
            "direction": "Sideways",
            "signal": "Hold",
            "buy_probability": 36,
            "hold_probability": 52,
            "sell_probability": 12,
            "confidence_score": 61,
            "predicted_range": "Use USD/INR live quote before execution",
            "risk_score": 57,
            "reasons": (
                "USD/INR affects gold, IT exporters, importers, and commodity-linked sectors.",
                "RBI policy, US rates, crude oil, and capital flows are key drivers.",
                "Currency exposure should be evaluated together with equity and commodity positions.",
            ),
            "research_sources": ("USD/INR market data", "RBI and macro indicators", "Crude oil trend model"),
        },
        "wealth_plan": {
            "type": "wealth_plan",
            "title": "Wealth Plan",
            "direction": "Upward",
            "signal": "Buy",
            "buy_probability": 70,
            "hold_probability": 25,
            "sell_probability": 5,
            "confidence_score": 72,
            "predicted_range": "Goal-based; depends on capital, SIP, horizon, and risk profile",
            "risk_score": 45,
            "allocations": (
                {"asset": "Equity Mutual Funds / Index Funds", "allocation_pct": 45, "purpose": "long-term wealth creation"},
                {"asset": "Direct Equity / ETFs", "allocation_pct": 20, "purpose": "growth and market participation"},
                {"asset": "Gold / Gold ETF", "allocation_pct": 15, "purpose": "inflation and currency hedge"},
                {"asset": "Debt Funds / Fixed Income", "allocation_pct": 15, "purpose": "stability and emergency rebalancing"},
                {"asset": "Cash Reserve", "allocation_pct": 5, "purpose": "liquidity for opportunities"},
            ),
            "reasons": (
                "Wealth creation improves with diversified allocation across equity, gold, ETFs, and debt.",
                "Monthly SIP and annual step-up contributions can materially improve long-term outcome.",
                "Emergency fund and insurance should come before aggressive investing.",
                "Review allocation quarterly and rebalance when drift exceeds 5 percentage points.",
            ),
            "research_sources": ("Portfolio allocation model", "Risk profile rules", "Long-term compounding assumptions"),
        },
        "news_impact": {
            "title": "News Impact Analysis",
            "direction": "Sideways",
            "signal": "Hold",
            "buy_probability": 34,
            "hold_probability": 52,
            "sell_probability": 14,
            "confidence_score": 58,
            "predicted_range": "Depends on article content and affected asset",
            "risk_score": 55,
            "reasons": (
                "News impact depends on affected sector, surprise level, source reliability, and market context.",
                "Immediate reaction can differ from medium-term trend.",
                "Use sentiment, topic, and anomaly detection before acting.",
            ),
            "research_sources": ("Trusted news feeds", "NLP sentiment engine", "Market anomaly model"),
        },
        "multi_news_intelligence": {
            "title": "AI Investment Intelligence Platform",
            "direction": "Sideways",
            "signal": "Hold",
            "buy_probability": 40,
            "hold_probability": 48,
            "sell_probability": 12,
            "confidence_score": 60,
            "predicted_range": "Basket-level; rank assets after ingesting news batch",
            "risk_score": 54,
            "reasons": (
                "Multi-news intelligence should remove duplicates and identify recurring themes.",
                "Bullish and bearish sector ranking depends on theme frequency, sentiment, and source quality.",
                "Use this as a screening layer before instrument-level analysis.",
            ),
            "research_sources": ("Trusted news feeds", "Topic modeling", "Sentiment scoring"),
        },
        "gold_intelligence": _gold_intelligence_profile(query),
        "silver_intelligence": _silver_intelligence_profile(query),
        "portfolio_strategy": _portfolio_strategy_profile(query),
        "portfolio_advisor": _portfolio_strategy_profile(query),
        "macro_events": _macro_events_profile(query),
        "market_summary": _market_summary_profile(query),
        "sector_outlook": _sector_outlook_profile(query),
        "precious_metals_technical": _precious_metals_technical_profile(query),
        "macro_geopolitics": {
            "title": "Macro And Geopolitical Market Impact",
            "direction": "Event Driven",
            "signal": "Hold",
            "buy_probability": 36,
            "hold_probability": 50,
            "sell_probability": 14,
            "confidence_score": 63,
            "predicted_range": "Scenario-based; map event impact to equities, gold, crude, INR, and rates",
            "risk_score": 70,
            "reasons": (
                "Conflict, trade-war, recession, inflation, and supply-shock prompts require cross-asset scenario analysis.",
                "Gold and defensive sectors can benefit from fear, inflation, and currency weakness, while cyclicals may face drawdown risk.",
                "Crude oil, USD/INR, FII flows, and RBI/US rate expectations should be checked before taking directional positions.",
                "Investor action should be staggered: avoid full allocation before the event impact is visible in price, volume, and policy response.",
            ),
            "research_sources": (
                "Government and central-bank releases",
                "Trusted geopolitical news feeds",
                "Commodity and currency market data",
                "Risk scenario model",
            ),
        },
        "equity_research": {
            "title": "Equity Research And Expected Return",
            "direction": "Selective",
            "signal": "Hold",
            "buy_probability": 46,
            "hold_probability": 44,
            "sell_probability": 10,
            "confidence_score": 65,
            "predicted_range": "Company-specific; use live price, valuation, earnings, peers, and news sentiment",
            "risk_score": 58,
            "reasons": (
                "Stock-analysis prompts should evaluate fundamentals, intrinsic value, earnings quality, growth durability, and peer valuation.",
                "Expected return should be split into earnings growth, valuation re-rating, dividend yield, and downside risk.",
                "For named companies, run ticker-level realtime analysis; for generic prompts, screen a sector or watchlist before selecting stocks.",
                "A valid buy thesis needs margin of safety, positive news/earnings trend, acceptable debt, and clear stop-loss or review trigger.",
            ),
            "research_sources": (
                "NSE/BSE company disclosures",
                "SEBI filings",
                "Company earnings and investor presentations",
                "Trusted equity news feeds",
            ),
        },
        "multibagger_goal": _multibagger_goal_profile(query),
    }
    return profiles.get(
        query.perspective,
        {
            "title": "Financial Research",
            "direction": "Research Required",
            "signal": "Hold",
            "buy_probability": 0,
            "hold_probability": 100,
            "sell_probability": 0,
            "confidence_score": 0,
            "predicted_range": "Not available",
            "risk_score": 0,
            "reasons": (
                f"Prompt category recognized as {query.perspective}.",
                "A dedicated model can be added for this category.",
            ),
            "research_sources": (),
        },
    )


def _prediction_lines(title: str, prediction: dict[str, Any], label: str | None = None) -> list[str]:
    confidence_target = prediction["signal"]
    lines = [
        title + ":",
    ]
    if label:
        lines.append(label)
    lines.extend(
        [
            f"Predicted Direction: {prediction['direction']}",
            f"Signal: {prediction['signal']}",
            f"Buy Probability: {prediction['buy_probability']}%",
            f"Hold Probability: {prediction['hold_probability']}%",
            f"Sell Probability: {prediction['sell_probability']}%",
            f"Confidence Score to {confidence_target}: {prediction['confidence_score']}%",
            f"Predicted Range: {prediction['predicted_low']} - {prediction['predicted_high']} {prediction['metadata']['unit']}",
            f"Risk Score: {prediction['risk_score']}%",
            "Reason:",
            *[f"- {reason}" for reason in prediction["reasons"]],
        ]
    )
    metadata = prediction.get("metadata", {})
    institutional = metadata.get("institutional_report") or {}
    if institutional:
        lines.extend(
            [
                "",
                "Institutional Research Summary:",
                f"- View: {institutional.get('view')}",
                f"- Source Coverage: {institutional.get('coverage')}",
                f"- News Impact: {institutional.get('news_impact_pct')}%",
                f"- Keyword Categories: {', '.join(institutional.get('keyword_categories', []))}",
                f"- Top SEO Keywords: {', '.join(institutional.get('top_keywords', [])[:8])}",
                f"- Thesis: {institutional.get('thesis')}",
            ]
        )
    intraday = metadata.get("intraday_plan") or {}
    if intraday:
        lines.extend(
            [
                "",
                "Intraday Trading Plan:",
                f"- Bias: {intraday.get('bias')}",
                f"- Entry Zone: {intraday.get('entry_zone')}",
                f"- Target 1: {intraday.get('target_1')}",
                f"- Target 2: {intraday.get('target_2')}",
                f"- Stop Loss: {intraday.get('stop_loss')}",
                f"- Invalidation: {intraday.get('invalidation')}",
                f"- Risk Control: {intraday.get('risk_note')}",
            ]
        )
    if metadata.get("forecast_entry_reference") is not None:
        unit = metadata.get("profit_loss_unit") or metadata.get("unit", "")
        lines.extend(
            [
                "",
                "Observed Current And Historical Context:",
                f"- {metadata.get('range_basis')}",
                f"- Current Observed Price: {metadata.get('current_observed_price')} {unit}",
                f"- Historical 30D Move: {metadata.get('historical_30d_change_pct')}%",
                f"- Historical Volatility: {metadata.get('historical_volatility_pct')}%",
                f"- Avg Daily Move: {metadata.get('avg_daily_move_pct')}%",
                f"- Best/Worst Daily Move: {metadata.get('best_daily_move_pct')}% / {metadata.get('worst_daily_move_pct')}%",
                "",
                "Future Forecast Profit/Loss:",
                f"- Forecast Entry Reference: {metadata.get('forecast_entry_reference')} {unit}",
                f"- Forecast Upside Target: {metadata.get('forecast_target_price')} {unit}",
                f"- Forecast Downside Guard: {metadata.get('forecast_downside_guard')} {unit}",
                f"- Estimated Profit/Loss: +{metadata.get('estimated_profit_pct')}% / -{metadata.get('estimated_loss_pct')}%",
                f"- Reward/Risk: {metadata.get('reward_risk_ratio')}x",
            ]
        )
    return lines


def _portfolio_text(result: dict[str, Any], query: MarketQuery) -> str:
    analysis = result.get("perspective_analysis", {})
    lines = [f"Question: {query.raw_text}", "", "Portfolio Allocation:"]
    for row in analysis.get("allocations", []):
        amount = f", Amount INR: {row['amount_inr']}" if "amount_inr" in row else ""
        lines.append(f"- {row['asset']}: {row['allocation_pct']}%{amount}")
    if analysis.get("rebalancing_strategy"):
        lines.extend(["", "Reason:", f"- {analysis['rebalancing_strategy']}"])
    lines.extend(["", "Research Sources:"])
    return "\n".join(lines)


def _perspective_analysis(result: dict[str, Any], query: MarketQuery) -> dict[str, Any]:
    prediction = (
        result["gold_prediction"]
        if query.instrument_type == "gold"
        else result["stock_prediction"]
    )
    if query.perspective == "portfolio_advisor" or query.instrument_type == "portfolio":
        return _portfolio_analysis(query)
    if query.perspective == "buffett":
        return _buffett_analysis(prediction)
    if query.perspective == "intraday_trading":
        return _intraday_analysis(prediction)
    if query.perspective == "swing_trading":
        return _swing_analysis(prediction)
    if query.perspective in {"gold_forecast", "equity_research", "master_platform"}:
        return _research_analysis(prediction, query)
    if query.perspective in {"news_impact", "multi_news_intelligence"}:
        return _news_impact_analysis(prediction, query)
    return {}


def _intraday_analysis(prediction: dict[str, Any]) -> dict[str, Any]:
    metadata = prediction.get("metadata", {})
    plan = metadata.get("intraday_plan", {})
    return {
        "type": "intraday_trading",
        "bias": plan.get("bias", "Wait for confirmation"),
        "entry_zone": plan.get("entry_zone", ""),
        "target_1": plan.get("target_1", ""),
        "target_2": plan.get("target_2", ""),
        "stop_loss": plan.get("stop_loss", ""),
        "invalidation": plan.get("invalidation", ""),
        "risk_control": plan.get("risk_note", "Keep single-trade risk limited and avoid overtrading."),
    }


def _research_analysis(prediction: dict[str, Any], query: MarketQuery) -> dict[str, Any]:
    bullish = prediction["buy_probability"]
    bearish = prediction["sell_probability"]
    sentiment = max(0, min(100, int(50 + prediction["news"]["sentiment_score"] * 50)))
    technical = max(0, min(100, int(100 - prediction["risk_score"] * 0.45 + bullish * 0.35)))
    fundamental = max(0, min(100, int(prediction["confidence_score"] * 0.65 + bullish * 0.35)))
    horizons = query.horizons or ("1 Week", "1 Month", "3 Months")
    targets = _targets(prediction, horizons)
    return {
        "type": "research",
        "bullish_score": bullish,
        "bearish_score": bearish,
        "fundamental_score": fundamental,
        "technical_score": technical,
        "sentiment_score": sentiment,
        "risk_score": prediction["risk_score"],
        "recommendation": prediction["signal"].upper(),
        "target_prices": targets,
        "short_term_outlook": _outlook(prediction, "short"),
        "long_term_outlook": _outlook(prediction, "long"),
    }


def _swing_analysis(prediction: dict[str, Any]) -> dict[str, Any]:
    entry = round((prediction["predicted_low"] + prediction["predicted_high"]) / 2, 2)
    width = max(0.01, prediction["predicted_high"] - prediction["predicted_low"])
    stop_loss = round(prediction["predicted_low"] - width * 0.25, 2)
    target_1 = round(entry + width * 0.35, 2)
    target_2 = round(entry + width * 0.65, 2)
    target_3 = round(entry + width, 2)
    reward = target_2 - entry
    risk = max(0.01, entry - stop_loss)
    return {
        "type": "swing_trading",
        "entry_price": entry,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "target_3": target_3,
        "risk_reward_ratio": round(reward / risk, 2),
        "action": "BUY" if prediction["signal"] == "Buy" else "SELL" if prediction["signal"] == "Sell" else "WAIT",
    }


def _buffett_analysis(prediction: dict[str, Any]) -> dict[str, Any]:
    long_term_score = max(0, min(100, prediction["confidence_score"] - prediction["risk_score"] // 3 + prediction["buy_probability"] // 2))
    return {
        "type": "buffett",
        "would_buy": "YES" if long_term_score >= 65 and prediction["signal"] != "Sell" else "NO",
        "business_quality_score": long_term_score,
        "valuation_discipline": "Favorable" if prediction["buy_probability"] > prediction["sell_probability"] else "Not compelling",
        "reasoning": "Long-term style favors high confidence, lower risk, durable positive trend, and valuation margin of safety.",
    }


def _portfolio_analysis(query: MarketQuery) -> dict[str, Any]:
    profile = query.risk_profile or "Medium"
    amount = query.investment_amount
    allocations = {
        "Low": {"Gold": 20, "Large Cap Stocks": 35, "Mid Cap Stocks": 10, "Small Cap Stocks": 0, "ETFs": 15, "Debt Funds": 20},
        "Medium": {"Gold": 15, "Large Cap Stocks": 35, "Mid Cap Stocks": 20, "Small Cap Stocks": 10, "ETFs": 15, "Debt Funds": 5},
        "High": {"Gold": 10, "Large Cap Stocks": 25, "Mid Cap Stocks": 25, "Small Cap Stocks": 20, "ETFs": 15, "Debt Funds": 5},
    }[profile]
    rows = []
    for asset, pct in allocations.items():
        row = {"asset": asset, "allocation_pct": pct}
        if amount is not None:
            row["amount_inr"] = round(amount * pct / 100, 2)
        rows.append(row)
    return {
        "type": "portfolio",
        "risk_profile": profile,
        "investment_amount": amount,
        "allocations": rows,
        "rebalancing_strategy": "Review monthly; rebalance when any allocation drifts more than 5 percentage points.",
    }


def _news_impact_analysis(prediction: dict[str, Any], query: MarketQuery) -> dict[str, Any]:
    if prediction["buy_probability"] >= 70:
        impact = "Very Bullish"
    elif prediction["buy_probability"] >= 55:
        impact = "Bullish"
    elif prediction["sell_probability"] >= 70:
        impact = "Very Bearish"
    elif prediction["sell_probability"] >= 55:
        impact = "Bearish"
    else:
        impact = "Neutral"
    return {
        "type": "news_impact",
        "affected_asset": query.instrument_type.title(),
        "impact_score": impact,
        "expected_market_reaction": "Short-Term" if prediction["news"]["impact_score"] >= 0.3 else "Medium-Term",
        "detected_topics": prediction["news"]["topics"],
        "detected_anomalies": prediction["news"]["anomaly_flags"],
    }


def _targets(prediction: dict[str, Any], horizons: tuple[str, ...]) -> dict[str, float]:
    midpoint = (prediction["predicted_low"] + prediction["predicted_high"]) / 2
    multipliers = {
        "Today": 0.25,
        "Next 7 Days": 0.55,
        "1 Week": 0.55,
        "Next 30 Days": 1.0,
        "1 Month": 1.0,
        "3 Months": 1.8,
        "Next 90 Days": 1.8,
        "6 Months": 2.6,
        "1 Year": 4.0,
    }
    bias = (prediction["buy_probability"] - prediction["sell_probability"]) / 10000
    return {
        horizon: round(midpoint * (1 + bias * multipliers.get(horizon, 1.0)), 2)
        for horizon in horizons
    }


def _outlook(prediction: dict[str, Any], term: str) -> str:
    risk = prediction["risk_score"]
    direction = prediction["direction"].lower()
    if term == "short":
        return f"{direction} bias with {'high' if risk >= 70 else 'moderate'} near-term risk"
    return f"{direction} trend estimate; validate with fundamentals and updated news before investing"


def _perspective_lines(analysis: dict[str, Any]) -> list[str]:
    if not analysis:
        return []
    title = analysis["type"].replace("_", " ").title()
    lines = [f"{title} View:"]
    for key, value in analysis.items():
        if key == "type":
            continue
        label = key.replace("_", " ").title()
        if isinstance(value, dict):
            lines.append(f"{label}:")
            lines.extend(f"- {item_key}: {item_value}" for item_key, item_value in value.items())
        elif isinstance(value, list):
            lines.append(f"{label}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append("- " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    lines.append(f"- {item}")
        else:
            lines.append(f"{label}: {value}")
    return lines


if __name__ == "__main__":
    main()
