import unittest
import argparse
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_agent import MarketAnalysisAgent
from market_agent.agents import (
    AUTONOMOUS_AGENT_SCHEDULE_IST,
    AutonomousCloudAgentConfig,
    AutonomousMarketIntelligenceOrchestrator,
)
from market_agent.cli import (
    _analyze_top_stocks,
    _category_prompt_response,
    _format_data_source_error,
    _format_category_prompt_text,
    _format_missing_symbol_error,
    _format_top_stocks_text,
    _format_text,
    _prompt_training_context,
    _trusted_master_links_for_perspective,
)
from market_agent.reports.html_report import save_html_report
from market_agent.core.models import (
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsAnalysis,
    NewsArticle,
    Sentiment,
    StockMarketSnapshot,
)
from market_agent.intelligence.nlp import NewsIntelligenceEngine
from market_agent.intelligence.predictors import GoldPredictor, StockPredictor
from market_agent.prompts.dataset import (
    enhance_prompt_from_dataset,
    export_training_sample,
    search_prompt_dataset,
    summarize_prompt_dataset,
)
from market_agent.prompts.library import prompt_categories, prompts_for_category
from market_agent.interfaces.query_parser import parse_market_query
from market_agent.data.realtime_sources import DataSourceError, RealtimeIndiaMarketDataSource
from market_agent.web import analyze_prompt
import market_agent.web as web_app


class RealtimeFixtureDataSource:
    def __init__(self) -> None:
        self._now = datetime.now(timezone.utc)

    def get_economic_indicators(self) -> EconomicIndicators:
        return EconomicIndicators(
            cpi_inflation=0.0,
            wpi_inflation=0.0,
            rbi_repo_rate=0.0,
            inr_usd=86.5,
            inr_usd_change_pct=0.6,
            gdp_growth=0.0,
            fiscal_deficit_pct_gdp=0.0,
            forex_reserves_usd_billion=0.0,
            fii_flow_crore=0.0,
            dii_flow_crore=0.0,
            gold_import_duty_pct=0.0,
            crude_oil_change_pct=-1.8,
            updated_at=self._now,
        )

    def get_gold_snapshot(self) -> GoldMarketSnapshot:
        return GoldMarketSnapshot(
            domestic_price_per_10g=131000.0,
            international_price_usd_oz=4710.0,
            domestic_demand_index=0.0,
            festival_demand_index=0.0,
            etf_flow_crore=0.0,
            central_bank_buying_tonnes=0.0,
            physical_consumption_index=0.0,
            price_change_30d_pct=-4.5,
            volatility_pct=24.0,
            avg_daily_move_pct=1.2,
            best_daily_move_pct=2.8,
            worst_daily_move_pct=-3.0,
        )

    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        normalized = symbol.upper()
        names = {
            "RELIANCE": "Reliance Industries",
            "TCS": "Tata Consultancy Services",
        }
        last_price = 2200.0 + (sum(ord(char) for char in normalized) % 800)
        return StockMarketSnapshot(
            symbol=normalized,
            company_name=names.get(normalized, normalized),
            last_price=last_price,
            price_change_30d_pct=(sum(ord(char) for char in normalized) % 12) - 4,
            nifty_change_30d_pct=1.6,
            sensex_change_30d_pct=1.4,
            sector="IT" if normalized in {"TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"} else "Broad Market",
            sector_change_30d_pct=2.1,
            volume_change_pct=10.0,
            volatility_pct=18.0 + (sum(ord(char) for char in normalized) % 12),
            earnings_surprise_pct=0.0,
            promoter_or_corporate_event_score=0.0,
            avg_daily_move_pct=0.9,
            best_daily_move_pct=2.2,
            worst_daily_move_pct=-2.0,
        )

    def get_news(self, symbols: tuple[str, ...]) -> list[NewsArticle]:
        articles: list[NewsArticle] = [
            NewsArticle(
                title="Federal Reserve live page fetched from 100-source master",
                source="Federal Reserve",
                body="USD interest rates liquidity inflation expectations global risk appetite positive market signals",
                published_at=self._now - timedelta(minutes=20),
                entities=("Gold",),
                url="https://www.federalreserve.gov",
            ),
            NewsArticle(
                title="RBI live page fetched from 100-source master",
                source="RBI",
                body="India monetary policy rupee forex inflation gold investment liquidity",
                published_at=self._now - timedelta(minutes=25),
                entities=("Gold",),
                url="https://www.rbi.org.in",
            ),
        ]
        for symbol in symbols:
            normalized = symbol.upper()
            if normalized != "GOLD":
                articles.append(
                    NewsArticle(
                        title=f"{normalized} NSE realtime source fetched",
                        source="NSE India",
                        body="stock equity market earnings sector positive volume volatility",
                        published_at=self._now - timedelta(minutes=10),
                        entities=(normalized,),
                        url="https://www.nseindia.com",
                    )
                )
        return articles


class OneStockFailureFixtureDataSource(RealtimeFixtureDataSource):
    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        if symbol.upper().replace(".NS", "") == "TATAMOTORS":
            raise DataSourceError("Fixture stock fetch failure")
        return super().get_stock_snapshot(symbol)


class StockQuoteOutageFixtureDataSource(RealtimeFixtureDataSource):
    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        raise DataSourceError("Fixture stock quote outage")


class AutonomousFixtureDataSource(RealtimeFixtureDataSource):
    def get_silver_price_on(self, requested_date: date | None = None) -> dict[str, object]:
        return {
            "instrument": "Silver",
            "date": (requested_date or date(2026, 6, 22)).isoformat(),
            "domestic_price": 232736.0,
            "domestic_unit": "INR per kg",
            "source": "Fixture Silver Rates",
            "source_url": "https://example.test/silver",
            "mode": "current",
            "rates": {"1 Kg": {"price": 232736.0, "unit": "INR per kg"}},
        }


class MarketAnalysisAgentTest(unittest.TestCase):
    def test_agent_returns_gold_and_stock_predictions(self) -> None:
        result = MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()).analyze("RELIANCE")

        self.assertEqual(result["gold_prediction"]["instrument"], "Gold")
        self.assertEqual(
            result["stock_prediction"]["instrument"],
            "Reliance Industries (RELIANCE)",
        )
        self.assertGreaterEqual(result["gold_prediction"]["confidence_score"], 50)
        self.assertEqual(
            result["gold_prediction"]["buy_probability"]
            + result["gold_prediction"]["hold_probability"]
            + result["gold_prediction"]["sell_probability"],
            100,
        )
        self.assertIn(result["stock_prediction"]["signal"], {"Buy", "Hold", "Sell"})
        self.assertTrue(
            any("Live market data:" in reason for reason in result["gold_prediction"]["reasons"])
        )
        self.assertTrue(result["news_evidence_by_instrument"]["gold"])

    def test_gold_only_analysis_does_not_require_stock_quote(self) -> None:
        result = MarketAnalysisAgent(data_source=StockQuoteOutageFixtureDataSource()).analyze_gold()
        query = parse_market_query("whats the gold price on 22 july 2026")
        text = _format_text(result, query)

        self.assertIn("gold_prediction", result)
        self.assertNotIn("stock_prediction", result)
        self.assertIn("Gold Prediction:", text)

    def test_unknown_stock_uses_generic_snapshot(self) -> None:
        result = MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()).analyze("ABC")

        self.assertEqual(result["stock_prediction"]["instrument"], "ABC (ABC)")
        self.assertEqual(result["stock_prediction"]["metadata"]["sector"], "Broad Market")

    def test_realtime_source_raises_when_network_unavailable(self) -> None:
        source = RealtimeIndiaMarketDataSource(timeout_seconds=0.001)
        with self.assertRaises(Exception):
            MarketAnalysisAgent(data_source=source).analyze("RELIANCE")

    def test_trusted_master_sources_are_loaded_for_realtime_source(self) -> None:
        source = RealtimeIndiaMarketDataSource(timeout_seconds=0.001)
        master_sources = source._ranked_trusted_master_sources("Gold")

        self.assertGreaterEqual(len(master_sources), 100)
        self.assertTrue(any(item["source_name"] == "Federal Reserve" for item in master_sources))
        self.assertTrue(any(item["source_name"] == "RBI" for item in master_sources))

    def test_market_query_parser_handles_gold_future_question(self) -> None:
        query = parse_market_query("What is the expected or actual Gold price on 21 June 2026?")

        self.assertEqual(query.instrument_type, "gold")
        self.assertTrue(query.is_prediction)
        self.assertEqual(query.requested_datetime_text, "21 June 2026")

    def test_market_query_parser_handles_stock_exact_time_question(self) -> None:
        query = parse_market_query(
            "What will be the RELIANCE stock price on 25 June 2026 at 12:03 PM?"
        )

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.stock_symbol, "RELIANCE")
        self.assertTrue(query.is_prediction)
        self.assertEqual(query.requested_datetime_text, "25 June 2026 12:03 PM")

    def test_market_query_parser_handles_gold_forecast_perspective(self) -> None:
        query = parse_market_query("Act as a Professional Gold Market Analyst. Estimate Gold Price for Today, Next 7 Days, Next 30 Days and Next 90 Days.")

        self.assertEqual(query.instrument_type, "gold")
        self.assertEqual(query.perspective, "gold_forecast")
        self.assertIn("Next 7 Days", query.horizons)
        self.assertIn("Next 90 Days", query.horizons)

    def test_market_query_parser_handles_buffett_perspective(self) -> None:
        query = parse_market_query("Act as Warren Buffett. Analyze stock TCS. Would Warren Buffett Buy This Stock?")

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.stock_symbol, "TCS")
        self.assertEqual(query.perspective, "buffett")

    def test_market_query_parser_handles_portfolio_perspective(self) -> None:
        query = parse_market_query("Act as a Portfolio Manager. Investment Amount: ₹5 lakh Risk Profile: High")

        self.assertEqual(query.instrument_type, "portfolio")
        self.assertEqual(query.perspective, "portfolio_advisor")
        self.assertEqual(query.risk_profile, "High")
        self.assertEqual(query.investment_amount, 500000)

    def test_market_query_parser_handles_top_stocks_prompt(self) -> None:
        query = parse_market_query("suggest me top stocks to buy on 22 June 2026")

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.perspective, "top_stocks")
        self.assertIsNone(query.stock_symbol)
        self.assertEqual(query.requested_datetime_text, "22 June 2026")
        self.assertEqual(query.top_n, 5)

    def test_market_query_parser_handles_top_10_stocks_prompt(self) -> None:
        query = parse_market_query("suggest me top 10 stocks to buy")

        self.assertEqual(query.perspective, "top_stocks")
        self.assertEqual(query.top_n, 10)

    def test_market_query_parser_handles_broad_intraday_stock_buy_prompt(self) -> None:
        query = parse_market_query("Which Intraday stock I can Buy on 22 June")

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.perspective, "top_stocks")
        self.assertIsNone(query.stock_symbol)

    def test_market_query_parser_handles_top_nse_intraday_movers_prompt(self) -> None:
        query = parse_market_query(
            "List top intraday movers on the NSE right now: ticker, % change, volume vs average, and a one-line reason for the move."
        )

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.perspective, "top_stocks")
        self.assertIsNone(query.stock_symbol)
        self.assertEqual(query.top_n, 5)

    def test_market_query_parser_handles_political_influence_prompt(self) -> None:
        query = parse_market_query(
            "Analyze political influence, beneficial ownership, PEP links, and government contract exposure for Indian listed companies."
        )

        self.assertEqual(query.instrument_type, "news")
        self.assertEqual(query.perspective, "political_influence")

    def test_market_query_parser_handles_single_stock_intraday_prompt(self) -> None:
        query = parse_market_query("Give intraday trading plan for TCS today")

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.stock_symbol, "TCS")
        self.assertEqual(query.perspective, "intraday_trading")
        self.assertTrue(query.is_prediction)

    def test_prompt_library_contains_money_categories(self) -> None:
        categories = prompt_categories()

        self.assertIn("gold_silver", categories)
        self.assertIn("mutual_funds", categories)
        self.assertIn("it_sector", categories)
        self.assertTrue(prompts_for_category("stocks")["stocks"])

    def test_prompt_dataset_search_summary_and_enhancement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = Path(tmp) / "prompts.jsonl"
            records = [
                {
                    "id": "gold-1",
                    "asset_class": "Gold",
                    "domain": "buy_sell_hold",
                    "market": "MCX",
                    "time_horizon": "1 week",
                    "risk_level": "medium",
                    "primary_event_or_driver": "inflation shock",
                    "recommended_agents": ["Gold Agent", "Risk Agent"],
                    "required_indicators": ["USDINR", "CPI inflation", "ETF flows"],
                    "expected_outputs": ["Buy/Hold/Sell recommendation", "risk score"],
                    "prompt": "Analyze gold buy or sell using inflation, USDINR, ETF flows, and risk score.",
                    "response_schema": {"decision": "BUY | HOLD | SELL"},
                    "safety_note": "Research only.",
                },
                {
                    "id": "stock-1",
                    "asset_class": "Stocks",
                    "domain": "intraday_trading",
                    "market": "NSE",
                    "time_horizon": "today",
                    "risk_level": "high",
                    "primary_event_or_driver": "volume breakout",
                    "recommended_agents": ["News Agent", "Risk Agent"],
                    "required_indicators": ["volume", "support resistance", "news sentiment"],
                    "expected_outputs": ["entry", "stop loss", "target price"],
                    "prompt": "Create intraday stock plan with entry, stop loss, target price, and sentiment.",
                    "response_schema": {"decision": "BUY | HOLD | SELL"},
                    "safety_note": "Research only.",
                },
            ]
            dataset_path.write_text(
                "\n".join(json.dumps(item) for item in records),
                encoding="utf-8",
            )

            summary = summarize_prompt_dataset(dataset_path)
            matches = search_prompt_dataset("gold inflation buy sell", dataset_path, limit=1)
            stock_matches = search_prompt_dataset("intraday stock entry stop loss", dataset_path, asset_class="Stocks", limit=1)
            enhanced = enhance_prompt_from_dataset("Should I buy gold this week?", dataset_path, limit=1)
            export_path = export_training_sample(Path(tmp) / "sample.jsonl", dataset_path, sample_size=1)

            self.assertEqual(summary["record_count"], 2)
            self.assertEqual(matches[0]["asset_class"], "Gold")
            self.assertEqual(stock_matches[0]["asset_class"], "Stocks")
            self.assertIn("Gold Agent", enhanced["recommended_agents"])
            self.assertTrue(export_path.exists())

    def test_prompt_training_context_uses_default_dataset_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = Path(tmp) / "prompts.jsonl"
            dataset_path.write_text(
                json.dumps(
                    {
                        "id": "gold-default",
                        "asset_class": "Gold",
                        "domain": "buy_sell_hold",
                        "market": "MCX",
                        "time_horizon": "1 week",
                        "risk_level": "medium",
                        "primary_event_or_driver": "inflation",
                        "recommended_agents": ["Gold Agent", "Risk Agent"],
                        "required_indicators": ["USDINR", "CPI inflation"],
                        "expected_outputs": ["Buy/Hold/Sell recommendation", "risk score"],
                        "prompt": "Analyze gold buy sell with USDINR and inflation.",
                        "response_schema": {"decision": "BUY | HOLD | SELL"},
                        "safety_note": "Research only.",
                    }
                ),
                encoding="utf-8",
            )
            old_env = os.environ.get("INDIAN_INVESTMENT_PROMPTS_JSONL")
            os.environ["INDIAN_INVESTMENT_PROMPTS_JSONL"] = str(dataset_path)
            try:
                args = argparse.Namespace(
                    no_prompt_training=False,
                    use_prompt_training=False,
                    prompt_dataset=None,
                    prompt_limit=3,
                    scan_limit=None,
                )
                context = _prompt_training_context(
                    parse_market_query("Should I buy gold this week?"),
                    args,
                )
            finally:
                if old_env is None:
                    os.environ.pop("INDIAN_INVESTMENT_PROMPTS_JSONL", None)
                else:
                    os.environ["INDIAN_INVESTMENT_PROMPTS_JSONL"] = old_env

            self.assertIsNotNone(context)
            self.assertEqual(context["dataset_path"], str(dataset_path))
            self.assertIn("Gold Agent", context["recommended_agents"])

    def test_parser_handles_new_financial_prompt_types(self) -> None:
        mutual_fund_query = parse_market_query("Suggest best mutual funds for SIP")
        self.assertEqual(mutual_fund_query.perspective, "mutual_funds")
        self.assertEqual(mutual_fund_query.instrument_type, "mutual_fund")
        self.assertIsNone(mutual_fund_query.stock_symbol)
        self.assertEqual(
            parse_market_query("Analyze the Indian IT sector ups and downs").perspective,
            "sector_analysis",
        )
        self.assertEqual(
            parse_market_query("Analyze Bitcoin and Ethereum trend").perspective,
            "crypto_analysis",
        )
        self.assertEqual(
            parse_market_query("Analyze IPO investment opportunity").perspective,
            "ipo_analysis",
        )
        self.assertEqual(
            parse_market_query("Should I invest in real estate or REIT").perspective,
            "real_estate",
        )
        self.assertEqual(
            parse_market_query("Analyze new technology investment in AI and semiconductor").perspective,
            "technology_investment",
        )
        self.assertEqual(
            parse_market_query("What is silver price outlook").perspective,
            "gold_silver_compare",
        )

    def test_policy_treaty_prompt_is_not_treated_as_stock_symbol(self) -> None:
        query = parse_market_query("what are the treaty signed between India and UK")

        self.assertEqual(query.instrument_type, "news")
        self.assertEqual(query.perspective, "news_impact")
        self.assertIsNone(query.stock_symbol)

        result = _category_prompt_response(query)
        text = _format_category_prompt_text(result)

        self.assertIn("India-UK Treaty / Agreement Summary", text)
        self.assertIn("Comprehensive Economic and Trade Agreement", text)
        self.assertIn("Double Contribution Convention", text)
        self.assertIn("GOV.UK", text)
        self.assertNotIn("UK.NS", text)

    def test_india_us_treaty_prompt_returns_specific_agreement_summary(self) -> None:
        query = parse_market_query("what are the treaty signed between India and US")

        self.assertEqual(query.instrument_type, "news")
        self.assertEqual(query.perspective, "news_impact")
        self.assertIsNone(query.stock_symbol)

        result = _category_prompt_response(query)
        text = _format_category_prompt_text(result)

        self.assertIn("India-US Treaty / Agreement Summary", text)
        self.assertIn("Civil Nuclear Agreement", text)
        self.assertIn("LEMOA", text)
        self.assertIn("COMCASA", text)
        self.assertIn("BECA", text)
        self.assertNotIn("US.NS", text)

    def test_generic_country_treaty_prompt_uses_research_profile(self) -> None:
        query = parse_market_query("what are the treaty signed between France and Germany")

        self.assertEqual(query.instrument_type, "news")
        self.assertEqual(query.perspective, "news_impact")
        self.assertIsNone(query.stock_symbol)

        result = _category_prompt_response(query)
        text = _format_category_prompt_text(result)

        self.assertIn("France-Germany Treaty / Agreement Research Summary", text)
        self.assertIn("UN Treaty Collection", text)
        self.assertIn("WTO Regional Trade Agreements Database", text)
        self.assertIn("signed, ratified, amended, terminated", text)
        self.assertNotIn(".NS", text)

    def test_data_source_error_is_user_friendly(self) -> None:
        query = parse_market_query("Analyze stock UNKNOWN")
        text = _format_data_source_error(Exception("Unable to fetch UNKNOWN.NS"), query)

        self.assertIn("Realtime Data Error", text)
        self.assertIn("valid NSE ticker", text)

    def test_missing_symbol_error_is_user_friendly(self) -> None:
        query = parse_market_query("Analyze stock UK")
        text = _format_missing_symbol_error(query)

        self.assertIn("Missing Stock Symbol", text)
        self.assertIn("valid NSE ticker", text)

    def test_wealth_plan_prompt_wins_over_sip_keyword(self) -> None:
        query = parse_market_query("Create a wealth plan to reach INR 1 crore in 10 years using SIP, stocks, gold, and ETFs.")

        self.assertEqual(query.instrument_type, "wealth")
        self.assertEqual(query.perspective, "wealth_plan")

    def test_forex_prompt_wins_over_it_stocks_keyword(self) -> None:
        query = parse_market_query("Analyze USD/INR movement and its impact on gold, IT stocks, importers, and exporters.")

        self.assertEqual(query.instrument_type, "forex")
        self.assertEqual(query.perspective, "forex_analysis")

    def test_return_multiple_goal_uses_multibagger_profile(self) -> None:
        query = parse_market_query("I want 3X profit in 5 years. Suggest investment strategy.")

        self.assertEqual(query.instrument_type, "wealth")
        self.assertEqual(query.perspective, "multibagger_goal")

        result = _category_prompt_response(query)
        text = _format_category_prompt_text(result)

        self.assertIn("3X Wealth Multiplication Plan", text)
        self.assertIn("required CAGR", text)
        self.assertIn("not a guaranteed price prediction", text)

    def test_prompt_library_routes_silver_macro_and_generic_stock_analysis(self) -> None:
        silver_query = parse_market_query("[Silver Intelligence] Analyze industrial demand for Silver in India.")
        macro_query = parse_market_query("[Macro & Geopolitics] Assess impact of Middle East conflict on Indian markets.")
        stock_query = parse_market_query("[Stock Analysis] Analyze earnings quality and growth sustainability.")
        forex_query = parse_market_query("[Gold Intelligence] Estimate price impact from currency weakness.")

        self.assertEqual(silver_query.perspective, "silver_intelligence")
        self.assertEqual(macro_query.perspective, "macro_geopolitics")
        self.assertEqual(stock_query.perspective, "equity_research")
        self.assertEqual(forex_query.perspective, "gold_intelligence")

    def test_autonomous_agent_schedule_matches_master_prompt(self) -> None:
        self.assertEqual(
            AUTONOMOUS_AGENT_SCHEDULE_IST,
            ("06:00", "10:00", "13:00", "18:00", "22:00"),
        )
        config = AutonomousCloudAgentConfig(watchlist=("RELIANCE",), max_stocks=1)
        orchestrator = AutonomousMarketIntelligenceOrchestrator(
            config=config,
            data_source=AutonomousFixtureDataSource(),
        )
        next_run = orchestrator.next_run_time(
            datetime(2026, 6, 22, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        )

        self.assertEqual(next_run.strftime("%H:%M"), "10:00")

    def test_autonomous_agent_run_cycle_generates_institutional_report(self) -> None:
        config = AutonomousCloudAgentConfig(watchlist=("RELIANCE", "TCS"), max_stocks=2)
        orchestrator = AutonomousMarketIntelligenceOrchestrator(
            config=config,
            data_source=AutonomousFixtureDataSource(),
        )
        report = orchestrator.run_cycle(
            now=datetime(2026, 6, 22, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            save=False,
        )

        self.assertEqual(report["agent_network"], "Autonomous Cloud Market Intelligence Agents")
        self.assertIn("gold_intelligence_report", report)
        self.assertIn("silver_intelligence_report", report)
        self.assertIn("indian_stock_market_summary", report)
        self.assertIn("top_opportunities", report)
        self.assertIn("top_risks", report)
        self.assertIn("tomorrow_forecast", report)
        self.assertIn("ai_recommendations", report)
        self.assertEqual(len(report["stock_intelligence_reports"]), 2)
        self.assertEqual(report["silver_intelligence_report"]["status"], "complete")
        self.assertTrue(report["executive_summary"])
        self.assertTrue(report["confidence_scores"])

    def test_autonomous_agent_saves_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AutonomousCloudAgentConfig(
                output_dir=Path(tmpdir),
                watchlist=("RELIANCE",),
                max_stocks=1,
            )
            orchestrator = AutonomousMarketIntelligenceOrchestrator(
                config=config,
                data_source=AutonomousFixtureDataSource(),
            )
            report = orchestrator.run_cycle(
                now=datetime(2026, 6, 22, 6, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
                save=True,
            )

            json_path = Path(report["output_files"]["json"])
            markdown_path = Path(report["output_files"]["markdown"])
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["platform"], "AI Investment Intelligence Platform")
            self.assertIn("Executive Summary", markdown_path.read_text(encoding="utf-8"))

    def test_phase2_prompt_library_families_return_data_provider_reports(self) -> None:
        prompts = {
            "Gold Intelligence Data Provider Report": "[Gold Intelligence] Calculate fair value using inflation-adjusted models.",
            "Silver Intelligence Data Provider Report": "[Silver Intelligence] Analyze industrial demand for Silver in India.",
            "Portfolio And Risk Data Provider Report": "[Portfolio & Risk] Stress-test portfolio against high inflation.",
            "Macro And Geopolitical Market Impact": "[Macro & Geopolitics] Generate geopolitical risk score.",
            "Equity Research And Expected Return": "[Stock Analysis] Compare valuation with industry peers.",
        }

        for expected_title, prompt in prompts.items():
            query = parse_market_query(prompt)
            result = _category_prompt_response(query)
            text = _format_category_prompt_text(result)

            self.assertIn(expected_title, text)
            self.assertIn("Research Sources:", text)
            self.assertNotIn("Realtime Data Availability Report", text)
            self.assertTrue(result["category_analysis"].get("analysis_sections") or query.perspective in {"macro_geopolitics", "equity_research"})

    def test_web_analyze_prompt_returns_direct_analysis_for_category_query(self) -> None:
        result = analyze_prompt(
            "I want 3X profit in 5 years. Suggest investment strategy.",
            no_prompt_training=True,
        )

        self.assertTrue(result["ok"])
        self.assertIn("3X Wealth Multiplication Plan", result["text"])
        self.assertNotIn("report_url", result)
        self.assertNotIn("report_path", result)
        self.assertEqual(result["analysis"]["category_analysis"]["title"], "3X Wealth Multiplication Plan")
        self.assertEqual(result["query"]["perspective"], "multibagger_goal")

    def test_web_analyze_prompt_returns_direct_analysis_for_realtime_failure(self) -> None:
        with patch.object(web_app, "_analyze_top_stocks", side_effect=DataSourceError("feed unavailable")):
            result = analyze_prompt(
                "suggest me top 20 stocks to buy on 22 June 2026",
                no_prompt_training=True,
            )

        self.assertTrue(result["ok"])
        self.assertIn("Realtime Data Availability Report", result["text"])
        self.assertNotIn("report_url", result)
        self.assertNotIn("report_path", result)
        self.assertEqual(result["analysis"]["category_analysis"]["signal"], "Hold")

    def test_web_analyze_prompt_returns_direct_analysis_for_missing_stock_symbol(self) -> None:
        result = analyze_prompt("Analyze this stock and tell me buy or sell", no_prompt_training=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["analysis"]["category_analysis"]["title"], "Stock Symbol Required")
        self.assertNotIn("report_url", result)
        self.assertNotIn("report_path", result)

    def test_web_broad_intraday_stock_prompt_uses_ranked_candidates(self) -> None:
        fake_result = {
            "user_query": {"text": "Which Intraday stock I can Buy on 22 June", "data_source": "realtime"},
            "top_buy_stocks": [
                {
                    "prediction": {
                        "instrument": "Tata Consultancy Services (TCS)",
                        "direction": "Upward",
                        "signal": "Buy",
                        "buy_probability": 70,
                        "hold_probability": 25,
                        "sell_probability": 5,
                        "confidence_score": 75,
                        "predicted_low": 3800,
                        "predicted_high": 3900,
                        "risk_score": 45,
                        "reasons": ["Intraday momentum is positive"],
                        "metadata": {"unit": "INR"},
                    },
                    "research_source_links": [{"source": "NSE India", "url": "https://www.nseindia.com/"}],
                }
            ],
        }
        with patch.object(web_app, "_analyze_top_stocks", return_value=fake_result):
            result = analyze_prompt("Which Intraday stock I can Buy on 22 June", no_prompt_training=True)

        self.assertTrue(result["ok"])
        self.assertIn("top_buy_stocks", result["analysis"])
        self.assertNotIn("Stock Symbol Required", result["text"])

    def test_web_top_nse_intraday_movers_prompt_uses_ranked_candidates(self) -> None:
        fake_result = {
            "user_query": {
                "text": "List top intraday movers on the NSE right now: ticker, % change, volume vs average, and a one-line reason for the move.",
                "data_source": "realtime",
            },
            "top_buy_stocks": [
                {
                    "prediction": {
                        "instrument": "State Bank of India (SBIN)",
                        "direction": "Upward",
                        "signal": "Buy",
                        "buy_probability": 66,
                        "hold_probability": 28,
                        "sell_probability": 6,
                        "confidence_score": 70,
                        "predicted_low": 820,
                        "predicted_high": 845,
                        "risk_score": 48,
                        "reasons": ["Intraday volume is above average"],
                        "metadata": {"unit": "INR"},
                    },
                    "research_source_links": [{"source": "NSE India", "url": "https://www.nseindia.com/"}],
                }
            ],
        }
        prompt = "List top intraday movers on the NSE right now: ticker, % change, volume vs average, and a one-line reason for the move."
        with patch.object(web_app, "_analyze_top_stocks", return_value=fake_result):
            result = analyze_prompt(prompt, no_prompt_training=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["query"]["perspective"], "top_stocks")
        self.assertIn("Top Intraday Movers:", result["text"])
        self.assertIn("top_buy_stocks", result["analysis"])
        self.assertNotIn("Stock Symbol Required", result["text"])

    def test_expert_broad_prompt_routing_does_not_require_stock_symbol(self) -> None:
        cases = {
            "Recommend the top 5 sectors in India for the next 6-12 months with rationale, top 3 stock picks per sector, and key catalysts to watch.": (
                "sector_outlook",
                "India Sector Outlook",
                "Top 5 Sector Ranking",
            ),
            "Give a live market summary for Indian markets: Sensex, Nifty performance, top gaining/losing sectors, FIIs/DII net flows, and 3 notable movers with reasons.": (
                "market_summary",
                "India Live Market Summary",
                "Market Dashboard",
            ),
            "List the top 5 macro or policy events affecting Indian markets currently (RBI decisions, CPI, GDP, FII flows, election/geo events) and the likely immediate impact on equities, bonds, and INR.": (
                "macro_events",
                "Top Macro And Policy Events",
                "Top 5 Event Impact Matrix",
            ),
            "Analyze the last 7 days of silver in INR (MCX): trend, key technical levels, volatility, and a 7-day outlook suited for Indian traders.": (
                "precious_metals_technical",
                "Silver 7-Day Technical Outlook",
                "Trader Playbook",
            ),
            "Analyze the last 7 days of gold in INR (MCX): trend, key support/resistance levels, volatility, and a 7-day outlook with expected range for Indian investors.": (
                "precious_metals_technical",
                "Gold 7-Day Technical Outlook",
                "7-Day Technical Framework",
            ),
        }

        for prompt, (perspective, title, section) in cases.items():
            with self.subTest(prompt=prompt):
                query = parse_market_query(prompt)
                result = analyze_prompt(prompt, no_prompt_training=True)
                text = result["text"]

                self.assertEqual(query.instrument_type, "news" if perspective in {"sector_outlook", "market_summary", "macro_events"} else query.instrument_type)
                self.assertEqual(query.perspective, perspective)
                self.assertTrue(result["ok"])
                self.assertEqual(result["query"]["perspective"], perspective)
                self.assertIn(title, text)
                self.assertIn(section, text)
                self.assertNotIn("Stock Symbol Required", text)

    def test_multibagger_goal_contains_expert_allocation_and_risk_checklist(self) -> None:
        prompt = (
            "Provide a SIP or allocation strategy for an Indian investor targeting 3X in 5 years: "
            "suggested asset allocation, sample mutual funds/stocks, expected returns assumptions, "
            "and a risk checklist specific to India."
        )

        result = analyze_prompt(prompt, no_prompt_training=True)
        text = result["text"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["query"]["perspective"], "multibagger_goal")
        self.assertIn("3X Wealth Multiplication Plan", text)
        self.assertIn("Financial Expert Allocation", text)
        self.assertIn("Risk Checklist", text)
        self.assertIn("required CAGR", text)
        self.assertNotIn("Stock Symbol Required", text)

    def test_web_attachment_context_routes_to_political_influence_profile(self) -> None:
        result = analyze_prompt(
            "Analyze the attached investment intelligence prompt.",
            no_prompt_training=True,
            attachments=[
                {
                    "name": "Political_Influence_Investment_Intelligence_Prompt.txt",
                    "text": "Act as a Political Influence, Beneficial Ownership, PEP, government contract exposure and investment intelligence AI.",
                }
            ],
        )
        text = result["text"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["query"]["perspective"], "political_influence")
        self.assertEqual(result["query"]["text"], "Analyze the attached investment intelligence prompt.")
        self.assertEqual(result["attachments"][0]["name"], "Political_Influence_Investment_Intelligence_Prompt.txt")
        self.assertIn("Political Influence Investment Intelligence", text)
        self.assertIn("Risk Scoring Model", text)
        self.assertNotIn("Stock Symbol Required", text)

    def test_web_direct_today_gold_prompt_returns_actual_value(self) -> None:
        with patch.object(
            web_app.RealtimeIndiaMarketDataSource,
            "get_gold_price_on",
            return_value={
                "instrument": "Gold 24K",
                "date": "2026-06-21",
                "domestic_price": 123456.78,
                "domestic_unit": "INR per 10g",
                "international_price": 4100.0,
                "international_unit": "USD per troy oz",
                "usd_inr": 86.25,
                "source": "Yahoo Finance realtime chart endpoint",
                "source_url": "https://finance.yahoo.com/quote/GC=F/",
                "mode": "current",
            },
        ):
            result = analyze_prompt("What's today's gold PRICE FOR 24k", no_prompt_training=True)

        profile = result["analysis"]["category_analysis"]
        self.assertTrue(result["ok"])
        self.assertEqual(profile["title"], "Actual Gold Market Value")
        self.assertEqual(profile["actual_value"], "123456.78 INR per 10g")
        self.assertIn("not a buy/sell forecast", result["text"])
        self.assertEqual(result["summary"]["predicted_range"], "123456.78 INR per 10g")

    def test_groww_gold_rates_are_parsed_for_current_actual_values(self) -> None:
        html = """
        <h1>Gold rate in India</h1>
        <div>24K Gold / 10gm</div><div>21 Jun '26</div><div>₹147239.00</div>
        <div>22K Gold / 10gm</div><div>21 Jun '26</div><div>₹135459.88</div>
        <div>18K Gold / 10gm</div><div>21 Jun '26</div><div>₹110429.25</div>
        """
        source = RealtimeIndiaMarketDataSource()
        with patch.object(source, "_fetch_raw_html", return_value=html):
            result = source.get_gold_price_on()

        self.assertEqual(result["source"], "Groww Gold Rates")
        self.assertEqual(result["date"], "2026-06-21")
        self.assertEqual(result["rates"]["24K"]["price"], 147239.0)
        self.assertEqual(result["rates"]["22K"]["price"], 135459.88)
        self.assertEqual(result["domestic_price"], 147239.0)

    def test_groww_silver_rates_are_parsed_for_historical_actual_values(self) -> None:
        html = """
        <h1>Silver rate in India</h1>
        <div>Today</div><div>Spot price</div><div>₹2,32,736.00</div>
        <h2>Historical Silver rates</h2>
        <div>Day Price</div><div>21 Jun 2026₹2,32,736.00</div><div>20 Jun 2026₹2,37,572.00</div>
        """
        source = RealtimeIndiaMarketDataSource()
        with patch.object(source, "_fetch_raw_html", return_value=html):
            result = source.get_silver_price_on(date(2026, 6, 20))

        self.assertEqual(result["source"], "Groww Silver Rates")
        self.assertEqual(result["date"], "2026-06-20")
        self.assertEqual(result["domestic_price"], 237572.0)
        self.assertEqual(result["rates"]["1 Kg"]["price"], 237572.0)

    def test_web_direct_today_silver_prompt_returns_actual_value(self) -> None:
        with patch.object(
            web_app.RealtimeIndiaMarketDataSource,
            "get_silver_price_on",
            return_value={
                "instrument": "Silver",
                "date": "2026-06-21",
                "domestic_price": 232736.0,
                "domestic_unit": "INR per kg",
                "source": "Groww Silver Rates",
                "source_url": "https://groww.in/silver-rates",
                "mode": "current",
                "rates": {"1 Kg": {"price": 232736.0, "unit": "INR per kg"}},
            },
        ):
            result = analyze_prompt("current silver price today", no_prompt_training=True)

        profile = result["analysis"]["category_analysis"]
        self.assertTrue(result["ok"])
        self.assertEqual(profile["title"], "Actual Silver Market Value")
        self.assertEqual(profile["actual_value"], "232736.0 INR per kg")

    def test_web_future_gold_prompt_stays_predictive(self) -> None:
        query = parse_market_query("what will be gold price on 23 June 2026")

        self.assertTrue(query.is_prediction)
        self.assertFalse(web_app._is_actual_value_query(query))

    def test_web_current_day_gold_prompt_uses_actual_even_with_will_wording(self) -> None:
        query = parse_market_query("what will be gold price on 21 June 2026")

        self.assertTrue(web_app._is_actual_value_query(query))

    def test_web_static_assets_are_cache_busted(self) -> None:
        html = Path("src/market_agent/web_static/index.html").read_text(encoding="utf-8")
        app_js = Path("src/market_agent/web_static/app.js").read_text(encoding="utf-8")

        self.assertIn("/static/app.js?v=", html)
        self.assertIn("/static/styles.css?v=", html)
        self.assertIn("v20260622_2015", html)
        self.assertIn("Live Analysis Result", html)
        self.assertIn("Recent Prompts", html)
        self.assertIn("recentToggleBtn", html)
        self.assertIn("attachmentInput", html)
        self.assertIn("Political Exposure Risk", html)
        self.assertNotIn("Stored HTML Report", html)
        self.assertNotIn("Try Again", app_js)
        self.assertNotIn("could not be completed", app_js)
        self.assertIn("ai-investment-recent-prompts", app_js)
        self.assertIn("toggleRecentMenu", app_js)

    def test_category_prompt_response_returns_recommendation_profile(self) -> None:
        query = parse_market_query("Suggest best mutual funds for SIP")
        result = _category_prompt_response(query)

        self.assertEqual(result["category_analysis"]["title"], "Mutual Fund Recommendation")
        self.assertGreater(result["category_analysis"]["buy_probability"], 0)
        self.assertNotEqual(result["category_analysis"]["signal"], "Research Required")
        self.assertIn("research_source_links", result["category_analysis"])
        self.assertTrue(
            any(
                item["source"] == "SEBI Updates"
                for item in result["category_analysis"]["research_source_links"]
            )
        )
        self.assertTrue(
            any(
                item["source"] in {"Bloomberg", "Reuters", "RBI", "Federal Reserve"}
                for item in result["category_analysis"]["research_source_links"]
            )
        )

    def test_trusted_master_links_are_added_to_category_reports(self) -> None:
        links = _trusted_master_links_for_perspective("gold_silver_compare")

        self.assertTrue(any(item["source"] == "Federal Reserve" for item in links))
        self.assertTrue(any(item["source"] in {"LBMA", "MCX India"} for item in links))

    def test_predicted_range_changes_with_news_research(self) -> None:
        source = RealtimeFixtureDataSource()
        indicators = source.get_economic_indicators()
        gold = source.get_gold_snapshot()
        positive_news = NewsAnalysis(
            sentiment=Sentiment.POSITIVE,
            sentiment_score=0.8,
            impact_score=0.9,
            topics=("Inflation",),
            entities=("Gold",),
            anomaly_flags=("High news impact concentration",),
        )
        negative_news = NewsAnalysis(
            sentiment=Sentiment.NEGATIVE,
            sentiment_score=-0.8,
            impact_score=0.9,
            topics=("Inflation",),
            entities=("Gold",),
            anomaly_flags=("High news impact concentration",),
        )

        positive = GoldPredictor().predict(indicators, gold, positive_news)
        negative = GoldPredictor().predict(indicators, gold, negative_news)

        self.assertGreater(positive.predicted_low, negative.predicted_low)
        self.assertIn("range_calibration", positive.metadata)
        self.assertIn("estimated_profit_pct", positive.metadata)
        self.assertIn("historical_volatility_pct", positive.metadata)
        self.assertIn("forecast_entry_reference", positive.metadata)
        self.assertIn("current_observed_price", positive.metadata)
        self.assertGreater(positive.metadata["reward_risk_ratio"], 0)

    def test_news_engine_uses_seo_keyword_sentiment(self) -> None:
        now = datetime.now(timezone.utc)
        analysis = NewsIntelligenceEngine().analyze(
            [
                NewsArticle(
                    title="Gold safe haven asset rises as inflation risk and war impact on gold dominate",
                    source="SEO Fixture",
                    body=(
                        "Gold Price Prediction and Central Bank Gold Buying improve demand. "
                        "Inflation Impact On Gold and Geopolitical Risk Analysis are major themes."
                    ),
                    published_at=now,
                    entities=("Gold",),
                    url="https://example.com/gold",
                )
            ]
        )

        self.assertIn("Gold", analysis.keyword_categories)
        self.assertIn("Inflation", analysis.keyword_categories)
        self.assertIn("Geopolitics", analysis.keyword_categories)
        self.assertIn("Gold Price Prediction", analysis.keyword_hits)
        self.assertGreater(analysis.impact_score, 0)

    def test_mutual_fund_text_uses_sip_allocation_format(self) -> None:
        query = parse_market_query("Suggest best mutual funds for SIP")
        text = _format_category_prompt_text(_category_prompt_response(query))

        self.assertIn("Suggested SIP Allocation:", text)
        self.assertIn("Fund Selection Criteria:", text)
        self.assertIn("Research Source URLs:", text)
        self.assertIn("https://www.sebi.gov.in", text)
        self.assertNotIn("Buy Probability:", text)

    def test_top_stocks_text_uses_screening_format(self) -> None:
        query = parse_market_query("suggest me top stocks to buy on 22 June 2026")
        result = _analyze_top_stocks(MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()), query, "realtime")
        text = _format_top_stocks_text(result)

        self.assertIn("Top Buy Stocks:", text)
        self.assertIn("Data Source: Realtime market/news feeds", text)
        self.assertIn("Entry Zone:", text)
        self.assertIn("Target Price:", text)
        self.assertIn("Stop Loss:", text)
        self.assertIn("Why This Stock:", text)
        self.assertNotIn("Predicted Range:", text)

    def test_top_20_stocks_returns_requested_count_when_available(self) -> None:
        query = parse_market_query("suggest me top 20 stocks to buy on 22 June 2026")
        result = _analyze_top_stocks(MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()), query, "realtime")

        self.assertEqual(query.top_n, 20)
        self.assertEqual(len(result["top_buy_stocks"]), 20)

    def test_top_stocks_skips_single_realtime_symbol_failure(self) -> None:
        query = parse_market_query("suggest me top 20 stocks to buy on 22 June 2026")
        result = _analyze_top_stocks(
            MarketAnalysisAgent(data_source=OneStockFailureFixtureDataSource()),
            query,
            "realtime",
        )

        self.assertEqual(len(result["top_buy_stocks"]), 20)
        self.assertIn("TATAMOTORS", result["user_query"]["skipped_symbols"])

    def test_top_stocks_returns_news_ranked_candidates_when_quotes_are_unavailable(self) -> None:
        query = parse_market_query("suggest me top 5 stocks to buy on 22 June 2026")
        result = _analyze_top_stocks(
            MarketAnalysisAgent(data_source=StockQuoteOutageFixtureDataSource()),
            query,
            "realtime",
        )
        text = _format_top_stocks_text(result)

        self.assertEqual(len(result["top_buy_stocks"]), 5)
        self.assertTrue(result["top_buy_stocks"][0]["prediction"]["metadata"]["quote_unavailable"])
        self.assertIn("Realtime quote unavailable in deployment", text)
        self.assertNotIn("Realtime Data Availability Report", text)

    def test_top_stocks_does_not_label_weak_hold_as_buy(self) -> None:
        result = {
            "user_query": {
                "text": "suggest me top stocks to buy",
                "data_source": "realtime",
            },
            "top_buy_stocks": [
                {
                    "prediction": {
                        "instrument": "Weak Candidate (WEAK)",
                        "direction": "Sideways",
                        "signal": "Hold",
                        "buy_probability": 6,
                        "hold_probability": 94,
                        "sell_probability": 0,
                        "confidence_score": 59,
                        "predicted_low": 100,
                        "predicted_high": 110,
                        "risk_score": 60,
                        "reasons": ("Low conviction",),
                        "metadata": {"unit": "INR"},
                    },
                    "research_sources": (),
                }
            ],
        }

        text = _format_top_stocks_text(result)

        self.assertIn("Recommendation: Hold", text)
        self.assertNotIn("Recommendation: Buy", text)

    def test_it_sector_prompt_is_not_treated_as_single_stock(self) -> None:
        query = parse_market_query("Analyze the Indian IT sector ups and downs")

        self.assertEqual(query.instrument_type, "stock")
        self.assertEqual(query.perspective, "sector_analysis")
        self.assertIsNone(query.stock_symbol)

    def test_html_report_is_saved_for_top_stocks(self) -> None:
        query = parse_market_query("suggest me top stocks to buy on 22 June 2026")
        result = _analyze_top_stocks(MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()), query, "realtime")
        path = save_html_report(result, "top_stocks")

        self.assertTrue(path.exists())
        html = path.read_text(encoding="utf-8")
        self.assertIn("AI Investment Intelligence Platform", html)
        self.assertIn("Ranked Buy Candidates", html)
        self.assertIn("bar", html)

    def test_html_report_renders_research_source_links(self) -> None:
        result = MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()).analyze("TCS")
        result["user_query"] = {"text": "Analyze TCS", "instrument_type": "stock"}
        path = save_html_report(result, "stock")

        html = path.read_text(encoding="utf-8")
        self.assertIn("href=", html)
        self.assertIn("Research Sources", html)
        self.assertIn("Realtime Article Evidence", html)
        self.assertIn("Fetched Text Used", html)
        self.assertIn("Institutional Research Summary", html)
        self.assertIn("Intraday Trading Plan", html)

    def test_html_report_renders_phase2_data_provider_sections(self) -> None:
        query = parse_market_query("[Silver Intelligence] Analyze industrial demand for Silver in India.")
        result = _category_prompt_response(query)
        path = save_html_report(result, query.perspective)

        html = path.read_text(encoding="utf-8")

        self.assertIn("Silver Intelligence Data Provider Report", html)
        self.assertIn("Silver Demand Matrix", html)
        self.assertIn("Realtime News Feed Analysis", html)
        self.assertIn("News Feed Evidence", html)

    def test_prompt_training_context_renders_in_text_but_not_html(self) -> None:
        result = MarketAnalysisAgent(data_source=RealtimeFixtureDataSource()).analyze("TCS")
        query = parse_market_query("Analyze TCS using institutional research prompts")
        result["user_query"] = {
            "text": query.raw_text,
            "instrument_type": "stock",
            "prompt_training": {
                "recommended_agents": ["News Agent", "Risk Agent"],
                "required_indicators": ["USDINR", "volume"],
                "expected_outputs": ["target price", "stop loss"],
                "matched_training_prompts": [
                    {
                        "asset_class": "NSE Stock",
                        "domain": "intraday_trading",
                        "time_horizon": "intraday",
                        "risk_level": "high",
                        "score": 42,
                    }
                ],
                "safety_note": "Training context only.",
            },
        }

        text = _format_text(result, query)
        path = save_html_report(result, "stock")
        html = path.read_text(encoding="utf-8")

        self.assertIn("Prompt Training Context", text)
        self.assertIn("News Agent", text)
        self.assertNotIn("Prompt Training Context", html)
        self.assertNotIn("Matched Training Prompt Patterns", html)


if __name__ == "__main__":
    unittest.main()
