from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from market_agent.models import (
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsArticle,
    StockMarketSnapshot,
)


class MarketDataSource(Protocol):
    def get_economic_indicators(self) -> EconomicIndicators:
        ...

    def get_gold_snapshot(self) -> GoldMarketSnapshot:
        ...

    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        ...

    def get_news(self, symbols: tuple[str, ...]) -> list[NewsArticle]:
        ...


class SampleIndiaMarketDataSource:
    """Offline data source for local development and deterministic tests."""

    def __init__(self) -> None:
        self._now = datetime.now(timezone.utc)

    def get_economic_indicators(self) -> EconomicIndicators:
        return EconomicIndicators(
            cpi_inflation=5.4,
            wpi_inflation=3.1,
            rbi_repo_rate=6.5,
            inr_usd=84.25,
            inr_usd_change_pct=1.2,
            gdp_growth=7.0,
            fiscal_deficit_pct_gdp=5.6,
            forex_reserves_usd_billion=650.0,
            fii_flow_crore=-2100.0,
            dii_flow_crore=3200.0,
            gold_import_duty_pct=6.0,
            crude_oil_change_pct=2.4,
            updated_at=self._now,
        )

    def get_gold_snapshot(self) -> GoldMarketSnapshot:
        return GoldMarketSnapshot(
            domestic_price_per_10g=72450.0,
            international_price_usd_oz=2375.0,
            domestic_demand_index=72.0,
            festival_demand_index=81.0,
            etf_flow_crore=450.0,
            central_bank_buying_tonnes=18.0,
            physical_consumption_index=76.0,
            price_change_30d_pct=3.8,
        )

    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        normalized = symbol.upper()
        stocks = {
            "RELIANCE": StockMarketSnapshot(
                symbol="RELIANCE",
                company_name="Reliance Industries",
                last_price=2915.0,
                price_change_30d_pct=-4.2,
                nifty_change_30d_pct=1.1,
                sensex_change_30d_pct=1.0,
                sector="Energy",
                sector_change_30d_pct=-2.6,
                volume_change_pct=34.0,
                volatility_pct=28.0,
                earnings_surprise_pct=-3.2,
                promoter_or_corporate_event_score=-0.3,
            ),
            "TCS": StockMarketSnapshot(
                symbol="TCS",
                company_name="Tata Consultancy Services",
                last_price=3890.0,
                price_change_30d_pct=2.8,
                nifty_change_30d_pct=1.1,
                sensex_change_30d_pct=1.0,
                sector="IT",
                sector_change_30d_pct=3.4,
                volume_change_pct=12.0,
                volatility_pct=19.0,
                earnings_surprise_pct=2.5,
                promoter_or_corporate_event_score=0.2,
            ),
        }
        return stocks.get(
            normalized,
            StockMarketSnapshot(
                symbol=normalized,
                company_name=normalized,
                last_price=1000.0,
                price_change_30d_pct=0.4,
                nifty_change_30d_pct=1.1,
                sensex_change_30d_pct=1.0,
                sector="Broad Market",
                sector_change_30d_pct=0.7,
                volume_change_pct=5.0,
                volatility_pct=18.0,
                earnings_surprise_pct=0.0,
                promoter_or_corporate_event_score=0.0,
            ),
        )

    def get_news(self, symbols: tuple[str, ...]) -> list[NewsArticle]:
        requested = {symbol.upper() for symbol in symbols}
        articles = [
            NewsArticle(
                title="Gold demand strengthens before festival season as rupee weakens",
                source="Sample Business Desk",
                body=(
                    "Domestic jewellers report strong festival and wedding demand. "
                    "Inflation remains sticky, geopolitical tension is elevated, and "
                    "the rupee weakened against the dollar, supporting gold prices."
                ),
                published_at=self._now - timedelta(hours=2),
                entities=("Gold", "RBI", "INR", "USD"),
            ),
            NewsArticle(
                title="Reliance faces pressure after weaker refining margin commentary",
                source="Sample Market Wire",
                body=(
                    "Reliance Industries saw negative earnings sentiment after analysts "
                    "flagged sector weakness, FII selling pressure, and rising oil volatility."
                ),
                published_at=self._now - timedelta(hours=5),
                entities=("RELIANCE", "FII", "Oil"),
            ),
            NewsArticle(
                title="IT sector improves after strong deal wins and positive outlook",
                source="Sample Equity News",
                body=(
                    "Large IT companies reported positive order books, stable margins, "
                    "and better global technology spending outlook."
                ),
                published_at=self._now - timedelta(hours=7),
                entities=("TCS", "IT"),
            ),
        ]
        return [
            article
            for article in articles
            if "Gold" in article.entities or requested.intersection(article.entities)
        ]
