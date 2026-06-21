from __future__ import annotations

from dataclasses import asdict
from typing import Any

from market_agent.core.data_sources import MarketDataSource
from market_agent.core.models import (
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsAnalysis,
    NewsArticle,
    Prediction,
    StockMarketSnapshot,
)
from market_agent.intelligence.nlp import NewsIntelligenceEngine
from market_agent.intelligence.predictors import GoldPredictor, StockPredictor


class MarketAnalysisAgent:
    def __init__(self, data_source: MarketDataSource | None = None) -> None:
        if data_source is None:
            from market_agent.data.realtime_sources import RealtimeIndiaMarketDataSource

            data_source = RealtimeIndiaMarketDataSource()
        self.data_source = data_source
        self.news_engine = NewsIntelligenceEngine()
        self.gold_predictor = GoldPredictor()
        self.stock_predictor = StockPredictor()

    def analyze(self, stock_symbol: str = "RELIANCE") -> dict[str, Any]:
        indicators = self.data_source.get_economic_indicators()
        gold = self.data_source.get_gold_snapshot()
        stock = self.data_source.get_stock_snapshot(stock_symbol)
        news_articles = self.data_source.get_news(("Gold", stock.symbol))
        gold_news = self.news_engine.analyze(
            [article for article in news_articles if "Gold" in article.entities]
        )
        gold_articles = [article for article in news_articles if "Gold" in article.entities]
        stock_articles = [article for article in news_articles if stock.symbol in article.entities]
        stock_news = self.news_engine.analyze(
            stock_articles
        )

        gold_prediction = self.gold_predictor.predict(indicators, gold, gold_news)
        stock_prediction = self.stock_predictor.predict(indicators, stock, stock_news)
        gold_prediction_data = self._prediction_to_dict(gold_prediction)
        stock_prediction_data = self._prediction_to_dict(stock_prediction)
        gold_prediction_data["reasons"] = self._merge_reasons(
            gold_prediction_data["reasons"],
            self._gold_realtime_reasons(indicators, gold, gold_news, gold_articles),
        )
        stock_prediction_data["reasons"] = self._merge_reasons(
            stock_prediction_data["reasons"],
            self._stock_realtime_reasons(indicators, stock, stock_news, stock_articles),
        )
        self._add_institutional_metadata(
            gold_prediction_data,
            gold_news,
            gold_articles,
            "Gold",
        )
        self._add_institutional_metadata(
            stock_prediction_data,
            stock_news,
            stock_articles,
            stock.symbol,
        )

        return {
            "economic_indicators": asdict(indicators),
            "gold_prediction": gold_prediction_data,
            "stock_prediction": stock_prediction_data,
            "research_sources": sorted({article.source for article in news_articles}),
            "research_source_links": self._source_links(news_articles),
            "research_sources_by_instrument": {
                "gold": sorted({article.source for article in gold_articles}),
                "stock": sorted({article.source for article in stock_articles}),
            },
            "research_source_links_by_instrument": {
                "gold": self._source_links(gold_articles),
                "stock": self._source_links(stock_articles),
            },
            "news_evidence_by_instrument": {
                "gold": self._news_evidence(gold_articles),
                "stock": self._news_evidence(stock_articles),
            },
            "alerts": self._alerts(gold_prediction, stock_prediction),
            "alerts_by_instrument": {
                "gold": self._alerts(gold_prediction),
                "stock": self._alerts(stock_prediction),
            },
        }

    def _alerts(self, *predictions: Prediction) -> list[str]:
        alerts: list[str] = []
        for prediction in predictions:
            if prediction.risk_score >= 70:
                alerts.append(f"{prediction.instrument}: high risk score {prediction.risk_score}")
            for flag in prediction.news.anomaly_flags:
                alerts.append(f"{prediction.instrument}: {flag}")
        return alerts

    def _prediction_to_dict(self, prediction: Prediction) -> dict[str, Any]:
        data = asdict(prediction)
        data["direction"] = prediction.direction.value
        data["signal"] = prediction.signal.value
        data["news"]["sentiment"] = prediction.news.sentiment.value
        return data

    def _source_links(self, articles: list[Any]) -> list[dict[str, str]]:
        links: dict[str, str] = {}
        for article in articles:
            if article.source not in links:
                links[article.source] = article.url
        return [
            {"source": source, "url": url}
            for source, url in sorted(links.items())
        ]

    def _merge_reasons(self, base: Any, extra: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for reason in [*list(base or ()), *extra]:
            normalized = " ".join(str(reason).split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
        return merged[:10]

    def _gold_realtime_reasons(
        self,
        indicators: EconomicIndicators,
        gold: GoldMarketSnapshot,
        news: NewsAnalysis,
        articles: list[NewsArticle],
    ) -> list[str]:
        reasons = [
            (
                "Live market data: gold futures 30-day move "
                f"{gold.price_change_30d_pct:+.2f}%, USD/INR 30-day move "
                f"{indicators.inr_usd_change_pct:+.2f}%, crude oil move "
                f"{indicators.crude_oil_change_pct:+.2f}%."
            ),
            (
                "Historical price reaction: recent gold volatility "
                f"{gold.volatility_pct:.2f}%, average daily move "
                f"{gold.avg_daily_move_pct:.2f}%, best/worst daily move "
                f"{gold.best_daily_move_pct:+.2f}%/{gold.worst_daily_move_pct:+.2f}%."
            ),
            (
                f"Realtime news sentiment is {news.sentiment.value} with "
                f"{int(news.impact_score * 100)}% impact score from {len(articles)} fetched articles."
            ),
            self._range_calibration_reason("Gold", news),
        ]
        reasons.extend(self._news_topic_reasons(news, articles))
        return reasons

    def _stock_realtime_reasons(
        self,
        indicators: EconomicIndicators,
        stock: StockMarketSnapshot,
        news: NewsAnalysis,
        articles: list[NewsArticle],
    ) -> list[str]:
        reasons = [
            (
                "Live market data: stock 30-day move "
                f"{stock.price_change_30d_pct:+.2f}% versus Nifty "
                f"{stock.nifty_change_30d_pct:+.2f}%, sector proxy "
                f"{stock.sector_change_30d_pct:+.2f}%, volume change "
                f"{stock.volume_change_pct:+.2f}%."
            ),
            (
                "Historical price reaction: recent stock volatility "
                f"{stock.volatility_pct:.2f}%, average daily move "
                f"{stock.avg_daily_move_pct:.2f}%, best/worst daily move "
                f"{stock.best_daily_move_pct:+.2f}%/{stock.worst_daily_move_pct:+.2f}%."
            ),
            (
                "Macro context: FII flow "
                f"{indicators.fii_flow_crore:+.0f} crore, DII flow "
                f"{indicators.dii_flow_crore:+.0f} crore, USD/INR move "
                f"{indicators.inr_usd_change_pct:+.2f}%."
            ),
            (
                f"Realtime news sentiment is {news.sentiment.value} with "
                f"{int(news.impact_score * 100)}% impact score from {len(articles)} fetched articles."
            ),
            self._range_calibration_reason(stock.symbol, news),
        ]
        reasons.extend(self._news_topic_reasons(news, articles))
        return reasons

    def _range_calibration_reason(self, label: str, news: NewsAnalysis) -> str:
        direction = "upward" if news.sentiment_score > 0.15 else "downward" if news.sentiment_score < -0.15 else "neutral"
        width = "widened" if news.impact_score >= 0.55 or news.anomaly_flags else "tightened" if news.impact_score < 0.35 else "moderately adjusted"
        return (
            f"Predicted range calibrated from realtime research: {label} news bias is "
            f"{direction}, and the range is {width} based on source impact and anomaly signals."
        )

    def _news_topic_reasons(self, news: NewsAnalysis, articles: list[NewsArticle]) -> list[str]:
        reasons: list[str] = []
        if news.topics:
            reasons.append(f"Detected realtime news topics: {', '.join(news.topics[:5])}.")
        if news.keyword_hits:
            reasons.append(f"SEO keyword sentiment themes: {', '.join(news.keyword_hits[:6])}.")
        if news.anomaly_flags:
            reasons.append(f"Realtime anomaly flags: {', '.join(news.anomaly_flags[:3])}.")
        for article in sorted(articles, key=lambda item: item.published_at, reverse=True)[:2]:
            title = article.title[:120].strip()
            if title:
                reasons.append(f"{article.source} article included in analysis: {title}")
        return reasons

    def _add_institutional_metadata(
        self,
        prediction: dict[str, Any],
        news: NewsAnalysis,
        articles: list[NewsArticle],
        symbol: str,
    ) -> None:
        metadata = prediction.setdefault("metadata", {})
        coverage_note = (
            f"{news.article_count or len(articles)} fetched items across "
            f"{news.source_count or len({article.source for article in articles})} sources"
        )
        institutional_view = self._institutional_view(prediction, news)
        top_keywords = list(news.keyword_hits[:10])
        categories = list(news.keyword_categories[:8])
        metadata["institutional_report"] = {
            "view": institutional_view,
            "coverage": coverage_note,
            "source_count": news.source_count or len({article.source for article in articles}),
            "article_count": news.article_count or len(articles),
            "news_sentiment": news.sentiment.value,
            "news_impact_pct": int(news.impact_score * 100),
            "seo_sentiment_score": news.seo_sentiment_score,
            "keyword_categories": categories,
            "top_keywords": top_keywords,
            "thesis": self._institutional_thesis(institutional_view, news, symbol),
        }
        metadata["intraday_plan"] = self._intraday_plan(prediction, news)

    def _institutional_view(self, prediction: dict[str, Any], news: NewsAnalysis) -> str:
        buy_probability = int(prediction.get("buy_probability", 0) or 0)
        sell_probability = int(prediction.get("sell_probability", 0) or 0)
        if buy_probability >= 55 and news.sentiment_score >= -0.2:
            return "Bullish"
        if sell_probability >= 45 or news.sentiment_score <= -0.35:
            return "Bearish"
        return "Neutral / Wait for confirmation"

    def _institutional_thesis(self, view: str, news: NewsAnalysis, symbol: str) -> str:
        categories = ", ".join(news.keyword_categories[:4]) if news.keyword_categories else "broad market"
        keywords = ", ".join(news.keyword_hits[:4]) if news.keyword_hits else "no dominant SEO keyword cluster"
        return (
            f"{symbol} view is {view.lower()} because realtime source coverage shows "
            f"{news.sentiment.value.lower()} sentiment, {int(news.impact_score * 100)}% news impact, "
            f"and keyword clusters around {categories}; leading signals: {keywords}."
        )

    def _intraday_plan(self, prediction: dict[str, Any], news: NewsAnalysis) -> dict[str, Any]:
        metadata = prediction.get("metadata", {})
        unit = metadata.get("profit_loss_unit") or metadata.get("unit", "")
        current = float(metadata.get("current_observed_price") or 0.0)
        low = float(prediction.get("predicted_low") or 0.0)
        high = float(prediction.get("predicted_high") or 0.0)
        midpoint = (low + high) / 2 if low and high else current
        width = max(0.01, high - low)
        buy_probability = int(prediction.get("buy_probability", 0) or 0)
        sell_probability = int(prediction.get("sell_probability", 0) or 0)
        if buy_probability >= sell_probability and news.sentiment_score >= -0.2:
            bias = "Long only above support"
            entry_low = max(low, midpoint - width * 0.18)
            entry_zone = f"{round(entry_low, 2)} - {round(midpoint, 2)} {unit}".strip()
            target_1 = f"{round(midpoint + (high - midpoint) * 0.55, 2)} {unit}".strip()
            target_2 = f"{round(high, 2)} {unit}".strip()
            stop_loss = f"{round(low, 2)} {unit}".strip()
            invalidation = "Avoid fresh long trades if price sustains below forecast downside guard."
        elif sell_probability > buy_probability or news.sentiment_score <= -0.35:
            bias = "Short / avoid long below resistance"
            entry_high = min(high, midpoint + width * 0.18)
            entry_zone = f"{round(midpoint, 2)} - {round(entry_high, 2)} {unit}".strip()
            target_1 = f"{round(midpoint - (midpoint - low) * 0.55, 2)} {unit}".strip()
            target_2 = f"{round(low, 2)} {unit}".strip()
            stop_loss = f"{round(high, 2)} {unit}".strip()
            invalidation = "Short bias weakens if price sustains above forecast upside resistance."
        else:
            bias = "Wait for breakout"
            entry_zone = f"Above {round(high, 2)} or below {round(low, 2)} {unit}".strip()
            target_1 = "Use opening range breakout confirmation"
            target_2 = "Trail after first target"
            stop_loss = "Opening range invalidation"
            invalidation = "No trade while price remains inside range with weak volume."
        return {
            "bias": bias,
            "entry_zone": entry_zone,
            "target_1": target_1,
            "target_2": target_2,
            "stop_loss": stop_loss,
            "risk_note": "Use small position size; cap single-trade risk near 0.5%-1.0% of capital.",
            "invalidation": invalidation,
        }

    def _news_evidence(self, articles: list[NewsArticle]) -> list[dict[str, str]]:
        evidence: list[dict[str, str]] = []
        for article in sorted(articles, key=lambda item: item.published_at, reverse=True)[:6]:
            evidence.append(
                {
                    "source": article.source,
                    "title": article.title,
                    "url": article.url,
                    "published_at": article.published_at.isoformat(),
                    "snippet": self._snippet(article.body),
                }
            )
        return evidence

    def _snippet(self, value: str, limit: int = 240) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."
