from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    UPWARD = "Upward"
    DOWNWARD = "Downward"
    SIDEWAYS = "Sideways"


class Signal(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class Sentiment(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    NEUTRAL = "Neutral"


@dataclass(frozen=True)
class EconomicIndicators:
    cpi_inflation: float
    wpi_inflation: float
    rbi_repo_rate: float
    inr_usd: float
    inr_usd_change_pct: float
    gdp_growth: float
    fiscal_deficit_pct_gdp: float
    forex_reserves_usd_billion: float
    fii_flow_crore: float
    dii_flow_crore: float
    gold_import_duty_pct: float
    crude_oil_change_pct: float
    updated_at: datetime


@dataclass(frozen=True)
class GoldMarketSnapshot:
    domestic_price_per_10g: float
    international_price_usd_oz: float
    domestic_demand_index: float
    festival_demand_index: float
    etf_flow_crore: float
    central_bank_buying_tonnes: float
    physical_consumption_index: float
    price_change_30d_pct: float
    volatility_pct: float = 0.0
    avg_daily_move_pct: float = 0.0
    best_daily_move_pct: float = 0.0
    worst_daily_move_pct: float = 0.0


@dataclass(frozen=True)
class StockMarketSnapshot:
    symbol: str
    company_name: str
    last_price: float
    price_change_30d_pct: float
    nifty_change_30d_pct: float
    sensex_change_30d_pct: float
    sector: str
    sector_change_30d_pct: float
    volume_change_pct: float
    volatility_pct: float
    earnings_surprise_pct: float
    promoter_or_corporate_event_score: float
    avg_daily_move_pct: float = 0.0
    best_daily_move_pct: float = 0.0
    worst_daily_move_pct: float = 0.0


@dataclass(frozen=True)
class NewsArticle:
    title: str
    source: str
    body: str
    published_at: datetime
    entities: tuple[str, ...] = field(default_factory=tuple)
    url: str = ""


@dataclass(frozen=True)
class NewsAnalysis:
    sentiment: Sentiment
    sentiment_score: float
    impact_score: float
    topics: tuple[str, ...]
    entities: tuple[str, ...]
    anomaly_flags: tuple[str, ...]
    keyword_hits: tuple[str, ...] = field(default_factory=tuple)
    keyword_categories: tuple[str, ...] = field(default_factory=tuple)
    seo_sentiment_score: float = 0.0
    article_count: int = 0
    source_count: int = 0


@dataclass(frozen=True)
class Prediction:
    instrument: str
    direction: Direction
    signal: Signal
    confidence_score: int
    buy_probability: int
    hold_probability: int
    sell_probability: int
    predicted_low: float
    predicted_high: float
    risk_score: int
    reasons: tuple[str, ...]
    news: NewsAnalysis
    metadata: dict[str, Any] = field(default_factory=dict)
