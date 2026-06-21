from __future__ import annotations

from typing import Protocol

from market_agent.core.models import (
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
