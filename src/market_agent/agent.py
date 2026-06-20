from __future__ import annotations

from dataclasses import asdict
from typing import Any

from market_agent.data_sources import MarketDataSource, SampleIndiaMarketDataSource
from market_agent.models import Prediction
from market_agent.nlp import NewsIntelligenceEngine
from market_agent.predictors import GoldPredictor, StockPredictor


class MarketAnalysisAgent:
    def __init__(self, data_source: MarketDataSource | None = None) -> None:
        self.data_source = data_source or SampleIndiaMarketDataSource()
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
        stock_news = self.news_engine.analyze(
            [article for article in news_articles if stock.symbol in article.entities]
        )

        gold_prediction = self.gold_predictor.predict(indicators, gold, gold_news)
        stock_prediction = self.stock_predictor.predict(indicators, stock, stock_news)

        return {
            "economic_indicators": asdict(indicators),
            "gold_prediction": self._prediction_to_dict(gold_prediction),
            "stock_prediction": self._prediction_to_dict(stock_prediction),
            "alerts": self._alerts(gold_prediction, stock_prediction),
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
