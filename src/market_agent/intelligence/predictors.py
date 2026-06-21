from __future__ import annotations

from market_agent.core.models import (
    Direction,
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsAnalysis,
    Prediction,
    Signal,
    StockMarketSnapshot,
)


def probabilities_from_score(score: float, buy_threshold: float, sell_threshold: float) -> tuple[int, int, int]:
    buy_strength = max(0.0, score / max(buy_threshold, 0.1))
    sell_strength = max(0.0, abs(score) / max(abs(sell_threshold), 0.1)) if score < 0 else 0.0
    hold_strength = max(0.15, 1.0 - abs(score) / (max(buy_threshold, abs(sell_threshold)) * 1.8))
    total = buy_strength + hold_strength + sell_strength
    buy = round((buy_strength / total) * 100)
    sell = round((sell_strength / total) * 100)
    hold = max(0, 100 - buy - sell)
    return buy, hold, sell


def news_range_adjustment(
    news: NewsAnalysis,
    sentiment_shift_scale: float,
    impact_width_scale: float,
) -> tuple[float, float, str]:
    sentiment_shift = news.sentiment_score * sentiment_shift_scale * (0.35 + news.impact_score)
    width_multiplier = 1 + news.impact_score * impact_width_scale
    if news.anomaly_flags:
        width_multiplier += min(0.3, len(news.anomaly_flags) * 0.08)
    if abs(news.sentiment_score) < 0.15 and news.impact_score < 0.35:
        width_multiplier *= 0.88
    width_multiplier = max(0.72, min(1.75, width_multiplier))
    label = (
        f"news shift {sentiment_shift * 100:+.2f}%, "
        f"range width {width_multiplier:.2f}x"
    )
    return sentiment_shift, width_multiplier, label


def profit_loss_metadata(entry: float, target: float, stop: float, unit: str) -> dict[str, float | str]:
    upside_pct = ((target - entry) / entry) * 100 if entry else 0.0
    downside_pct = ((entry - stop) / entry) * 100 if entry else 0.0
    reward_risk = upside_pct / downside_pct if downside_pct else 0.0
    return {
        "forecast_entry_reference": round(entry, 2),
        "forecast_target_price": round(target, 2),
        "forecast_downside_guard": round(stop, 2),
        "estimated_profit_pct": round(upside_pct, 2),
        "estimated_loss_pct": round(downside_pct, 2),
        "reward_risk_ratio": round(reward_risk, 2),
        "profit_loss_unit": unit,
    }


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
        buy_probability, hold_probability, sell_probability = probabilities_from_score(score, 2.0, -2.0)
        confidence = int(min(92, max(52, 58 + abs(score) * 9 + news.impact_score * 10)))
        news_shift, width_multiplier, range_calibration = news_range_adjustment(news, 0.018, 0.32)
        base_width_pct = 0.012 + news.impact_score * 0.012 + abs(news.sentiment_score) * 0.006
        range_width = gold.domestic_price_per_10g * base_width_pct * width_multiplier
        midpoint = gold.domestic_price_per_10g * (1 + news_shift)
        predicted_low = round(midpoint - range_width, 2)
        predicted_high = round(midpoint + range_width, 2)
        entry = round((predicted_low + predicted_high) / 2, 2)
        pl = profit_loss_metadata(entry, predicted_high, predicted_low, "INR per 10g")
        risk = int(min(95, 35 + abs(indicators.inr_usd_change_pct) * 5 + news.impact_score * 25))

        return Prediction(
            instrument="Gold",
            direction=direction,
            signal=signal,
            confidence_score=confidence,
            buy_probability=buy_probability,
            hold_probability=hold_probability,
            sell_probability=sell_probability,
            predicted_low=predicted_low,
            predicted_high=predicted_high,
            risk_score=risk,
            reasons=tuple(reasons[:6]),
            news=news,
            metadata={
                "unit": "INR per 10g",
                "model": "heuristic-ensemble-v0",
                "range_basis": "Future forecast only; current and historical prices are observed context and are not modified.",
                "current_observed_price": gold.domestic_price_per_10g,
                "range_calibration": range_calibration,
                "historical_30d_change_pct": gold.price_change_30d_pct,
                "historical_volatility_pct": gold.volatility_pct,
                "avg_daily_move_pct": gold.avg_daily_move_pct,
                "best_daily_move_pct": gold.best_daily_move_pct,
                "worst_daily_move_pct": gold.worst_daily_move_pct,
                **pl,
            },
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
        buy_probability, hold_probability, sell_probability = probabilities_from_score(score, 1.5, -1.5)
        confidence = int(min(90, max(50, 56 + abs(score) * 11 + news.impact_score * 8)))
        news_shift, width_multiplier, range_calibration = news_range_adjustment(news, 0.022, 0.45)
        volatility_factor = max(0.018, stock.volatility_pct / 1300)
        base_width_pct = max(0.012, min(0.055, news.impact_score * 0.018 + abs(news.sentiment_score) * 0.012))
        midpoint = stock.last_price * (1 + news_shift)
        range_width = stock.last_price * max(volatility_factor, base_width_pct) * width_multiplier
        predicted_low = round(midpoint - range_width, 2)
        predicted_high = round(midpoint + range_width, 2)
        entry = round((predicted_low + predicted_high) / 2, 2)
        pl = profit_loss_metadata(entry, predicted_high, predicted_low, "INR")
        risk = int(min(95, 32 + stock.volatility_pct * 1.2 + news.impact_score * 18))

        return Prediction(
            instrument=f"{stock.company_name} ({stock.symbol})",
            direction=direction,
            signal=signal,
            confidence_score=confidence,
            buy_probability=buy_probability,
            hold_probability=hold_probability,
            sell_probability=sell_probability,
            predicted_low=predicted_low,
            predicted_high=predicted_high,
            risk_score=risk,
            reasons=tuple(reasons[:7]),
            news=news,
            metadata={
                "unit": "INR",
                "sector": stock.sector,
                "model": "heuristic-ensemble-v0",
                "range_basis": "Future forecast only; current and historical prices are observed context and are not modified.",
                "current_observed_price": stock.last_price,
                "range_calibration": range_calibration,
                "historical_30d_change_pct": stock.price_change_30d_pct,
                "historical_volatility_pct": stock.volatility_pct,
                "avg_daily_move_pct": stock.avg_daily_move_pct,
                "best_daily_move_pct": stock.best_daily_move_pct,
                "worst_daily_move_pct": stock.worst_daily_move_pct,
                **pl,
            },
        )

    def _direction(self, score: float) -> Direction:
        if score >= 0.7:
            return Direction.UPWARD
        if score <= -0.7:
            return Direction.DOWNWARD
        return Direction.SIDEWAYS
