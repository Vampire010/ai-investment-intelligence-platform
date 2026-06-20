from __future__ import annotations

from market_agent.models import (
    Direction,
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsAnalysis,
    Prediction,
    Signal,
    StockMarketSnapshot,
)


class GoldPredictor:
    def predict(
        self,
        indicators: EconomicIndicators,
        gold: GoldMarketSnapshot,
        news: NewsAnalysis,
    ) -> Prediction:
        score = 0.0
        reasons: list[str] = []

        if gold.festival_demand_index >= 70:
            score += 1.4
            reasons.append("Gold demand is increasing due to festival and wedding season")
        if indicators.cpi_inflation >= 5.0:
            score += 1.0
            reasons.append("Inflation is elevated, increasing demand for inflation hedges")
        if indicators.inr_usd_change_pct > 0:
            score += 1.0
            reasons.append("INR is weakening against USD, raising domestic landed gold cost")
        if gold.etf_flow_crore > 0:
            score += 0.6
            reasons.append("Gold ETF flows are positive")
        if gold.central_bank_buying_tonnes > 0:
            score += 0.5
            reasons.append("Central bank gold buying remains supportive")
        if news.sentiment_score < -0.2 and "Geopolitics" in news.topics:
            score += 0.8
            reasons.append("Global geopolitical tension is increasing safe-haven demand")
        if indicators.gold_import_duty_pct > 8:
            score -= 0.7
            reasons.append("High import duty can suppress physical gold demand")

        direction = self._direction(score)
        signal = Signal.BUY if score >= 2.0 else Signal.SELL if score <= -2.0 else Signal.HOLD
        confidence = int(min(92, max(52, 58 + abs(score) * 9 + news.impact_score * 10)))
        range_width = gold.domestic_price_per_10g * (0.018 + min(0.025, abs(score) * 0.004))
        midpoint = gold.domestic_price_per_10g * (1 + score * 0.006)
        risk = int(min(95, 35 + abs(indicators.inr_usd_change_pct) * 5 + news.impact_score * 25))

        return Prediction(
            instrument="Gold",
            direction=direction,
            signal=signal,
            confidence_score=confidence,
            predicted_low=round(midpoint - range_width, 2),
            predicted_high=round(midpoint + range_width, 2),
            risk_score=risk,
            reasons=tuple(reasons[:6]),
            news=news,
            metadata={"unit": "INR per 10g", "model": "heuristic-ensemble-v0"},
        )

    def _direction(self, score: float) -> Direction:
        if score >= 1.0:
            return Direction.UPWARD
        if score <= -1.0:
            return Direction.DOWNWARD
        return Direction.SIDEWAYS


class StockPredictor:
    def predict(
        self,
        indicators: EconomicIndicators,
        stock: StockMarketSnapshot,
        news: NewsAnalysis,
    ) -> Prediction:
        score = 0.0
        reasons: list[str] = []

        if stock.price_change_30d_pct > stock.nifty_change_30d_pct:
            score += 0.8
            reasons.append("Stock momentum is stronger than Nifty")
        else:
            score -= 0.7
            reasons.append("Stock momentum is weaker than Nifty")

        if stock.sector_change_30d_pct > 1.5:
            score += 0.8
            reasons.append(f"{stock.sector} sector performance is positive")
        elif stock.sector_change_30d_pct < -1.5:
            score -= 0.8
            reasons.append(f"{stock.sector} sector weakness is visible")

        if stock.earnings_surprise_pct > 1:
            score += 0.9
            reasons.append("Earnings sentiment is positive")
        elif stock.earnings_surprise_pct < -1:
            score -= 0.9
            reasons.append("Negative earnings sentiment is weighing on the stock")

        if indicators.fii_flow_crore < 0:
            score -= 0.5
            reasons.append("FII selling pressure is present")
        if indicators.dii_flow_crore > 0:
            score += 0.3
            reasons.append("DII buying provides some domestic support")
        if stock.volatility_pct > 25:
            score -= 0.4
            reasons.append("Market volatility is elevated")

        score += stock.promoter_or_corporate_event_score
        score += news.sentiment_score * 0.8

        direction = self._direction(score)
        signal = Signal.BUY if score >= 1.5 else Signal.SELL if score <= -1.5 else Signal.HOLD
        confidence = int(min(90, max(50, 56 + abs(score) * 11 + news.impact_score * 8)))
        volatility_factor = max(0.025, stock.volatility_pct / 1000)
        midpoint = stock.last_price * (1 + score * 0.008)
        range_width = stock.last_price * (volatility_factor + abs(score) * 0.003)
        risk = int(min(95, 32 + stock.volatility_pct * 1.2 + news.impact_score * 18))

        return Prediction(
            instrument=f"{stock.company_name} ({stock.symbol})",
            direction=direction,
            signal=signal,
            confidence_score=confidence,
            predicted_low=round(midpoint - range_width, 2),
            predicted_high=round(midpoint + range_width, 2),
            risk_score=risk,
            reasons=tuple(reasons[:7]),
            news=news,
            metadata={
                "unit": "INR",
                "sector": stock.sector,
                "model": "heuristic-ensemble-v0",
            },
        )

    def _direction(self, score: float) -> Direction:
        if score >= 0.7:
            return Direction.UPWARD
        if score <= -0.7:
            return Direction.DOWNWARD
        return Direction.SIDEWAYS
