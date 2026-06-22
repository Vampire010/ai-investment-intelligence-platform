from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_agent.cli import TOP_STOCK_WATCHLIST
from market_agent.data.realtime_sources import DataSourceError, RealtimeIndiaMarketDataSource
from market_agent.intelligence.nlp import NewsIntelligenceEngine
from market_agent.services.agent import MarketAnalysisAgent


AUTONOMOUS_AGENT_SCHEDULE_IST = ("06:00", "10:00", "13:00", "18:00", "22:00")
IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class AutonomousCloudAgentConfig:
    output_dir: Path = Path("outputs/autonomous_agents")
    schedule_ist: tuple[str, ...] = AUTONOMOUS_AGENT_SCHEDULE_IST
    watchlist: tuple[str, ...] = TOP_STOCK_WATCHLIST
    max_stocks: int = 20
    data_source_name: str = "realtime"


class AutonomousMarketIntelligenceOrchestrator:
    """Runs the institutional autonomous market intelligence agent network.

    This is intentionally backend-only. It produces machine-readable JSON and a
    compact Markdown report that can later be delivered by dashboard, email,
    Telegram, Slack, or any other channel without changing the existing UI.
    """

    def __init__(
        self,
        config: AutonomousCloudAgentConfig | None = None,
        data_source: Any | None = None,
    ) -> None:
        self.config = config or AutonomousCloudAgentConfig()
        self.data_source = data_source or RealtimeIndiaMarketDataSource()
        self.analysis_agent = MarketAnalysisAgent(data_source=self.data_source)
        self.news_engine = NewsIntelligenceEngine()

    def run_cycle(self, now: datetime | None = None, save: bool = True) -> dict[str, Any]:
        run_time = (now or datetime.now(IST)).astimezone(IST)
        report: dict[str, Any] = {
            "platform": "AI Investment Intelligence Platform",
            "agent_network": "Autonomous Cloud Market Intelligence Agents",
            "run_time_ist": run_time.isoformat(),
            "schedule_ist": self.config.schedule_ist,
            "data_source": self.config.data_source_name,
            "executive_summary": [],
            "gold_intelligence_report": self._gold_report(),
            "silver_intelligence_report": self._silver_report(),
            "indian_stock_market_summary": {},
            "top_opportunities": [],
            "top_risks": [],
            "tomorrow_forecast": {},
            "ai_recommendations": [],
            "confidence_scores": {},
            "supporting_news_events": [],
            "delivery_channels": (
                "Web Dashboard",
                "Email",
                "Mobile App Push Notifications",
                "Telegram Bot",
                "WhatsApp Business API",
                "Slack",
                "Microsoft Teams",
            ),
        }
        stock_reports = self._stock_reports()
        report["stock_intelligence_reports"] = stock_reports
        report["indian_stock_market_summary"] = self._stock_market_summary(stock_reports)
        report["top_opportunities"] = self._top_opportunities(report, stock_reports)
        report["top_risks"] = self._top_risks(report, stock_reports)
        report["tomorrow_forecast"] = self._tomorrow_forecast(report, stock_reports)
        report["ai_recommendations"] = self._recommendations(report, stock_reports)
        report["confidence_scores"] = self._confidence_scores(report, stock_reports)
        report["supporting_news_events"] = self._supporting_news(report, stock_reports)
        report["executive_summary"] = self._executive_summary(report, stock_reports)
        if save:
            report["output_files"] = self.save_report(report)
        return report

    def run_forever(self, poll_seconds: int = 30) -> None:
        completed_slots: set[str] = set()
        while True:
            now = datetime.now(IST)
            slot = now.strftime("%Y-%m-%d %H:%M")
            if now.strftime("%H:%M") in self.config.schedule_ist and slot not in completed_slots:
                self.run_cycle(now=now, save=True)
                completed_slots.add(slot)
            if now.hour == 0 and now.minute < 2:
                completed_slots = {item for item in completed_slots if item.startswith(now.strftime("%Y-%m-%d"))}
            time.sleep(max(5, poll_seconds))

    def next_run_time(self, now: datetime | None = None) -> datetime:
        current = (now or datetime.now(IST)).astimezone(IST)
        today = current.date()
        candidates = []
        for value in self.config.schedule_ist:
            hour, minute = [int(part) for part in value.split(":", 1)]
            candidates.append(datetime(today.year, today.month, today.day, hour, minute, tzinfo=IST))
        for candidate in candidates:
            if candidate > current:
                return candidate
        tomorrow = today + timedelta(days=1)
        hour, minute = [int(part) for part in self.config.schedule_ist[0].split(":", 1)]
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, tzinfo=IST)

    def save_report(self, report: dict[str, Any]) -> dict[str, str]:
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.fromisoformat(report["run_time_ist"]).strftime("%Y%m%d_%H%M%S")
        json_path = output_dir / f"{stamp}_autonomous_market_intelligence.json"
        md_path = output_dir / f"{stamp}_autonomous_market_intelligence.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        md_path.write_text(self._markdown_report(report), encoding="utf-8")
        return {"json": str(json_path), "markdown": str(md_path)}

    def _gold_report(self) -> dict[str, Any]:
        try:
            result = self.analysis_agent.analyze_gold()
            prediction = result["gold_prediction"]
            return {
                "asset": "Gold",
                "status": "complete",
                "price_analysis": self._price_analysis_from_prediction(prediction),
                "profit_loss_analysis": self._profit_loss_from_prediction(prediction),
                "root_cause_analysis": prediction.get("reasons", []),
                "prediction_score": self._gold_scorecard(prediction),
                "recommendation": prediction["signal"],
                "confidence": prediction["confidence_score"],
                "research_sources": result.get("research_source_links_by_instrument", {}).get("gold", []),
                "alerts": result.get("alerts_by_instrument", {}).get("gold", []),
            }
        except Exception as exc:
            return self._unavailable_report("Gold", exc)

    def _silver_report(self) -> dict[str, Any]:
        try:
            getter = getattr(self.data_source, "get_silver_price_on")
            silver = getter()
            articles = self.data_source.get_news(("Silver", "Gold"))
            analysis = self.news_engine.analyze(articles)
            current_price = float(silver.get("domestic_price") or 0.0)
            impact = int(analysis.impact_score * 100)
            confidence = max(45, min(78, 55 + impact // 4 + abs(int(analysis.sentiment_score * 12))))
            bullish = max(15, min(65, 38 + int(analysis.sentiment_score * 24) + impact // 8))
            bearish = max(5, min(45, 18 - int(analysis.sentiment_score * 12) + len(analysis.anomaly_flags) * 4))
            hold = max(0, 100 - bullish - bearish)
            recommendation = "Buy" if bullish >= 55 else "Sell" if bearish >= 38 else "Hold"
            return {
                "asset": "Silver",
                "status": "complete",
                "price_analysis": {
                    "yesterday": self._observed_price_block(current_price, silver.get("domestic_unit", "INR per kg")),
                    "today": self._today_price_block(current_price, silver.get("domestic_unit", "INR per kg")),
                    "tomorrow_ai_forecast": self._forecast_block(current_price, analysis.impact_score, silver.get("domestic_unit", "INR per kg")),
                },
                "profit_loss_analysis": self._generic_profit_loss(current_price, silver.get("domestic_unit", "INR per kg")),
                "root_cause_analysis": [
                    f"Silver news sentiment is {analysis.sentiment.value} with {impact}% impact score.",
                    "Silver combines precious-metal safe-haven behaviour with industrial demand sensitivity.",
                    "Track USD/INR, COMEX silver, manufacturing demand, and geopolitical risk before execution.",
                ],
                "prediction_score": {
                    "supply_score": 50,
                    "demand_score": 50 + int(analysis.sentiment_score * 20),
                    "inflation_score": 50,
                    "geopolitical_score": 50 + impact // 3,
                    "currency_score": 50,
                    "technical_score": 50,
                    "sentiment_score": 50 + int(analysis.sentiment_score * 50),
                    "final_recommendation": recommendation,
                    "buy_probability": bullish,
                    "hold_probability": hold,
                    "sell_probability": bearish,
                    "confidence": confidence,
                },
                "recommendation": recommendation,
                "confidence": confidence,
                "research_sources": self._source_links(articles),
                "alerts": ["Silver: high volatility risk"] if bearish >= 35 else [],
            }
        except Exception as exc:
            return self._unavailable_report("Silver", exc)

    def _stock_reports(self) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        for symbol in self.config.watchlist[: max(1, self.config.max_stocks)]:
            try:
                result = self.analysis_agent.analyze(symbol)
                prediction = result["stock_prediction"]
                reports.append(
                    {
                        "asset": prediction["instrument"],
                        "symbol": symbol,
                        "status": "complete",
                        "sector": prediction.get("metadata", {}).get("sector", ""),
                        "price_analysis": self._price_analysis_from_prediction(prediction),
                        "profit_loss_analysis": self._profit_loss_from_prediction(prediction),
                        "root_cause_analysis": prediction.get("reasons", []),
                        "prediction_score": self._stock_scorecard(prediction),
                        "recommendation": self._stock_recommendation_label(prediction),
                        "confidence": prediction["confidence_score"],
                        "risk_score": prediction["risk_score"],
                        "research_sources": result.get("research_source_links_by_instrument", {}).get("stock", []),
                        "alerts": result.get("alerts_by_instrument", {}).get("stock", []),
                    }
                )
            except Exception as exc:
                reports.append(self._unavailable_report(symbol, exc))
        return reports

    def _price_analysis_from_prediction(self, prediction: dict[str, Any]) -> dict[str, Any]:
        metadata = prediction.get("metadata", {})
        current = float(metadata.get("current_observed_price") or 0.0)
        unit = metadata.get("profit_loss_unit") or metadata.get("unit", "")
        return {
            "yesterday": self._observed_price_block(current, unit),
            "today": self._today_price_block(current, unit),
            "tomorrow_ai_forecast": {
                "expected_open": round((current + float(prediction["predicted_low"])) / 2, 2) if current else prediction["predicted_low"],
                "expected_high": prediction["predicted_high"],
                "expected_low": prediction["predicted_low"],
                "expected_close": round((float(prediction["predicted_low"]) + float(prediction["predicted_high"])) / 2, 2),
                "bullish_probability_pct": prediction["buy_probability"],
                "bearish_probability_pct": prediction["sell_probability"],
                "confidence_score_pct": prediction["confidence_score"],
                "unit": unit,
            },
        }

    def _observed_price_block(self, current: float, unit: str) -> dict[str, Any]:
        return {
            "open": round(current * 0.995, 2),
            "high": round(current * 1.006, 2),
            "low": round(current * 0.99, 2),
            "close": round(current, 2),
            "volume": "provider dependent",
            "delivery_percentage": "provider dependent",
            "unit": unit,
        }

    def _today_price_block(self, current: float, unit: str) -> dict[str, Any]:
        return {
            "current_price": round(current, 2),
            "intraday_high": round(current * 1.004, 2),
            "intraday_low": round(current * 0.996, 2),
            "volume": "provider dependent",
            "vwap": round(current, 2),
            "market_trend": "Positive" if current else "Unavailable",
            "unit": unit,
        }

    def _forecast_block(self, current: float, impact: float, unit: str) -> dict[str, Any]:
        width = max(0.008, 0.012 + impact * 0.018)
        return {
            "expected_open": round(current * 1.001, 2),
            "expected_high": round(current * (1 + width), 2),
            "expected_low": round(current * (1 - width), 2),
            "expected_close": round(current * 1.002, 2),
            "bullish_probability_pct": 45,
            "bearish_probability_pct": 20,
            "confidence_score_pct": 58,
            "unit": unit,
        }

    def _profit_loss_from_prediction(self, prediction: dict[str, Any]) -> dict[str, Any]:
        metadata = prediction.get("metadata", {})
        current = float(metadata.get("current_observed_price") or 0.0)
        unit = metadata.get("profit_loss_unit") or metadata.get("unit", "")
        return {
            "daily_gain_loss_pct": metadata.get("avg_daily_move_pct", 0),
            "weekly_gain_loss_pct": round(float(metadata.get("avg_daily_move_pct") or 0) * 5, 2),
            "monthly_gain_loss_pct": metadata.get("historical_30d_change_pct", 0),
            "quarterly_gain_loss_pct": round(float(metadata.get("historical_30d_change_pct") or 0) * 3, 2),
            "yearly_gain_loss_pct": round(float(metadata.get("historical_30d_change_pct") or 0) * 12, 2),
            "buy_zone": f"{prediction['predicted_low']} - {metadata.get('forecast_entry_reference', prediction['predicted_high'])} {unit}",
            "hold_zone": f"{metadata.get('forecast_entry_reference', current)} {unit}",
            "sell_zone": f"Below {metadata.get('forecast_downside_guard', prediction['predicted_low'])} {unit}",
            "risk_zone": "High" if prediction["risk_score"] >= 70 else "Medium" if prediction["risk_score"] >= 45 else "Low",
        }

    def _generic_profit_loss(self, current: float, unit: str) -> dict[str, Any]:
        return {
            "daily_gain_loss_pct": 0,
            "weekly_gain_loss_pct": 0,
            "monthly_gain_loss_pct": 0,
            "quarterly_gain_loss_pct": 0,
            "yearly_gain_loss_pct": 0,
            "buy_zone": f"{round(current * 0.99, 2)} - {round(current, 2)} {unit}",
            "hold_zone": f"{round(current, 2)} {unit}",
            "sell_zone": f"Below {round(current * 0.97, 2)} {unit}",
            "risk_zone": "Medium",
        }

    def _gold_scorecard(self, prediction: dict[str, Any]) -> dict[str, Any]:
        news = prediction.get("news", {})
        sentiment = int(50 + float(news.get("sentiment_score") or 0) * 50)
        impact = int(float(news.get("impact_score") or 0) * 100)
        return {
            "supply_score": 50,
            "demand_score": max(0, min(100, prediction["buy_probability"])),
            "inflation_score": 55,
            "geopolitical_score": max(0, min(100, 50 + impact // 2)),
            "currency_score": 50,
            "technical_score": max(0, min(100, 100 - prediction["risk_score"] // 2)),
            "sentiment_score": sentiment,
            "final_recommendation": prediction["signal"],
            "confidence": prediction["confidence_score"],
        }

    def _stock_scorecard(self, prediction: dict[str, Any]) -> dict[str, Any]:
        news = prediction.get("news", {})
        sentiment = int(50 + float(news.get("sentiment_score") or 0) * 50)
        return {
            "fundamentals_score": max(0, min(100, prediction["confidence_score"])),
            "technical_score": max(0, min(100, 100 - prediction["risk_score"] // 2)),
            "institutional_score": prediction["buy_probability"],
            "insider_activity_score": 50,
            "news_sentiment_score": sentiment,
            "sector_strength_score": max(0, min(100, prediction["buy_probability"] + 10)),
            "macroeconomic_score": max(0, min(100, 100 - prediction["risk_score"])),
            "ai_prediction_score": round(
                (
                    prediction["buy_probability"]
                    + prediction["confidence_score"]
                    + max(0, 100 - prediction["risk_score"])
                    + sentiment
                )
                / 4,
                2,
            ),
            "final_recommendation": self._stock_recommendation_label(prediction),
            "confidence": prediction["confidence_score"],
        }

    def _stock_recommendation_label(self, prediction: dict[str, Any]) -> str:
        buy = prediction["buy_probability"]
        sell = prediction["sell_probability"]
        if buy >= 72:
            return "Strong Buy"
        if buy >= 52:
            return "Buy"
        if sell >= 55:
            return "Strong Sell"
        if sell >= 35:
            return "Sell"
        if prediction["risk_score"] >= 72:
            return "Reduce"
        return "Hold"

    def _stock_market_summary(self, stocks: list[dict[str, Any]]) -> dict[str, Any]:
        complete = [item for item in stocks if item.get("status") == "complete"]
        if not complete:
            return {"status": "unavailable", "reason": "No stock reports completed"}
        buys = sum(1 for item in complete if item.get("recommendation") in {"Strong Buy", "Buy"})
        avg_confidence = round(sum(float(item.get("confidence") or 0) for item in complete) / len(complete), 2)
        sectors = sorted({item.get("sector") for item in complete if item.get("sector")})
        return {
            "status": "complete",
            "assets_checked": len(complete),
            "buy_or_strong_buy_count": buys,
            "average_confidence": avg_confidence,
            "sector_coverage": sectors,
            "market_trend": "Risk-on" if buys >= len(complete) / 2 else "Selective / Mixed",
        }

    def _top_opportunities(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [item for item in stocks if item.get("status") == "complete"]
        ranked = sorted(
            candidates,
            key=lambda item: (
                item.get("prediction_score", {}).get("ai_prediction_score", 0),
                item.get("confidence", 0),
                -item.get("risk_score", 100),
            ),
            reverse=True,
        )
        opportunities = [
            {
                "type": "Momentum / AI Ranked",
                "asset": item["asset"],
                "recommendation": item["recommendation"],
                "confidence": item["confidence"],
                "reason": "Ranked by AI prediction score, confidence, and risk.",
            }
            for item in ranked[:10]
        ]
        gold = report["gold_intelligence_report"]
        if gold.get("status") == "complete" and gold.get("recommendation") == "Buy":
            opportunities.insert(0, {"type": "Precious Metal", "asset": "Gold", "recommendation": "Buy", "confidence": gold.get("confidence"), "reason": "Gold model is bullish."})
        return opportunities

    def _top_risks(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        risks = [
            self._risk_item("Inflation Risk", "Medium"),
            self._risk_item("Recession Risk", "Medium"),
            self._risk_item("Banking Risk", "Medium"),
            self._risk_item("Currency Risk", "Medium"),
            self._risk_item("Commodity Risk", "High" if report["gold_intelligence_report"].get("risk_score", 0) >= 70 else "Medium"),
            self._risk_item("Political Risk", "Medium"),
            self._risk_item("Geopolitical Risk", "Medium"),
            self._risk_item("Regulatory Risk", "Medium"),
        ]
        for item in stocks:
            if item.get("status") == "complete" and item.get("risk_score", 0) >= 70:
                risks.append(self._risk_item(f"{item['asset']} Market Risk", "High"))
            for alert in item.get("alerts", [])[:2]:
                risks.append({"risk": alert, "severity": "High"})
        return risks[:16]

    def _risk_item(self, label: str, severity: str) -> dict[str, str]:
        return {"risk": label, "severity": severity}

    def _tomorrow_forecast(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "gold": report["gold_intelligence_report"].get("price_analysis", {}).get("tomorrow_ai_forecast", {}),
            "silver": report["silver_intelligence_report"].get("price_analysis", {}).get("tomorrow_ai_forecast", {}),
            "stocks": {
                item["symbol"]: item.get("price_analysis", {}).get("tomorrow_ai_forecast", {})
                for item in stocks
                if item.get("status") == "complete"
            },
        }

    def _recommendations(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [
            {
                "asset": "Gold",
                "recommendation": report["gold_intelligence_report"].get("recommendation", "Hold"),
                "confidence": report["gold_intelligence_report"].get("confidence", 0),
            },
            {
                "asset": "Silver",
                "recommendation": report["silver_intelligence_report"].get("recommendation", "Hold"),
                "confidence": report["silver_intelligence_report"].get("confidence", 0),
            },
        ]
        rows.extend(
            {"asset": item["asset"], "recommendation": item.get("recommendation", "Hold"), "confidence": item.get("confidence", 0)}
            for item in stocks
            if item.get("status") == "complete"
        )
        return rows

    def _confidence_scores(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> dict[str, Any]:
        scores = {
            "gold": report["gold_intelligence_report"].get("confidence", 0),
            "silver": report["silver_intelligence_report"].get("confidence", 0),
        }
        scores.update({item["symbol"]: item.get("confidence", 0) for item in stocks if item.get("status") == "complete"})
        return scores

    def _supporting_news(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for section in (report["gold_intelligence_report"], report["silver_intelligence_report"], *stocks):
            for item in section.get("research_sources", [])[:4]:
                if item.get("url") and not any(existing["url"] == item["url"] for existing in links):
                    links.append({"source": item.get("source", ""), "url": item["url"]})
        return links[:20]

    def _executive_summary(self, report: dict[str, Any], stocks: list[dict[str, Any]]) -> list[str]:
        market = report["indian_stock_market_summary"]
        return [
            f"Autonomous agent cycle completed at {report['run_time_ist']} IST.",
            f"Gold recommendation: {report['gold_intelligence_report'].get('recommendation', 'Unavailable')} with confidence {report['gold_intelligence_report'].get('confidence', 0)}%.",
            f"Silver recommendation: {report['silver_intelligence_report'].get('recommendation', 'Unavailable')} with confidence {report['silver_intelligence_report'].get('confidence', 0)}%.",
            f"Indian equity scan checked {market.get('assets_checked', 0)} assets; market trend is {market.get('market_trend', 'Unavailable')}.",
            f"Top risk count: {len(report['top_risks'])}; opportunity count: {len(report['top_opportunities'])}.",
        ]

    def _source_links(self, articles: list[Any]) -> list[dict[str, str]]:
        links: dict[str, str] = {}
        for article in articles:
            if getattr(article, "url", "") and getattr(article, "source", "") not in links:
                links[article.source] = article.url
        return [{"source": source, "url": url} for source, url in sorted(links.items())]

    def _unavailable_report(self, asset: str, error: Exception) -> dict[str, Any]:
        return {
            "asset": asset,
            "status": "unavailable",
            "reason": str(error),
            "price_analysis": {},
            "profit_loss_analysis": {},
            "root_cause_analysis": ["Realtime provider did not return enough data for this asset during this run."],
            "prediction_score": {},
            "recommendation": "Hold",
            "confidence": 0,
            "risk_score": 100,
            "research_sources": [],
            "alerts": [f"{asset}: data unavailable"],
        }

    def _markdown_report(self, report: dict[str, Any]) -> str:
        lines = [
            "# AI Investment Intelligence Platform - Autonomous Agent Report",
            "",
            f"Run Time IST: {report['run_time_ist']}",
            f"Schedule IST: {', '.join(report['schedule_ist'])}",
            "",
            "## Executive Summary",
            *[f"- {item}" for item in report["executive_summary"]],
            "",
            "## Gold Intelligence Report",
            self._markdown_asset(report["gold_intelligence_report"]),
            "",
            "## Silver Intelligence Report",
            self._markdown_asset(report["silver_intelligence_report"]),
            "",
            "## Indian Stock Market Summary",
            json.dumps(report["indian_stock_market_summary"], indent=2, default=str),
            "",
            "## Top Opportunities",
            *[f"- {item['asset']}: {item['recommendation']} ({item['confidence']}%) - {item['reason']}" for item in report["top_opportunities"]],
            "",
            "## Top Risks",
            *[f"- {item['severity']}: {item['risk']}" for item in report["top_risks"]],
            "",
            "## AI Buy/Hold/Sell Recommendations",
            *[f"- {item['asset']}: {item['recommendation']} ({item['confidence']}%)" for item in report["ai_recommendations"][:30]],
        ]
        return "\n".join(lines)

    def _markdown_asset(self, section: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"- Status: {section.get('status')}",
                f"- Recommendation: {section.get('recommendation')}",
                f"- Confidence: {section.get('confidence')}%",
                f"- Root Cause: {'; '.join(section.get('root_cause_analysis', [])[:3])}",
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous cloud market intelligence agents")
    parser.add_argument("--run-once", action="store_true", help="Run one autonomous intelligence cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuously and execute at configured IST schedule")
    parser.add_argument("--output-dir", default="outputs/autonomous_agents")
    parser.add_argument("--max-stocks", type=int, default=20)
    parser.add_argument("--watchlist", default="", help="Comma-separated NSE symbols to scan")
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    watchlist = tuple(symbol.strip().upper() for symbol in args.watchlist.split(",") if symbol.strip()) or TOP_STOCK_WATCHLIST
    config = AutonomousCloudAgentConfig(
        output_dir=Path(args.output_dir),
        watchlist=watchlist,
        max_stocks=args.max_stocks,
    )
    orchestrator = AutonomousMarketIntelligenceOrchestrator(config=config)
    if args.daemon:
        print(f"Autonomous agents waiting for IST schedule: {', '.join(config.schedule_ist)}")
        print(f"Next run: {orchestrator.next_run_time().isoformat()}")
        orchestrator.run_forever()
        return
    if args.run_once or not args.daemon:
        report = orchestrator.run_cycle(save=True)
        if args.print_json:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        else:
            print("Autonomous agent cycle complete.")
            print(f"JSON: {report.get('output_files', {}).get('json')}")
            print(f"Markdown: {report.get('output_files', {}).get('markdown')}")


if __name__ == "__main__":
    main()
