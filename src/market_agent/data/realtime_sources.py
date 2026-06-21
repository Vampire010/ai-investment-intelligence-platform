from __future__ import annotations

import html
import json
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import stdev
from typing import Any

from market_agent.core.models import (
    EconomicIndicators,
    GoldMarketSnapshot,
    NewsArticle,
    StockMarketSnapshot,
)


class RealtimeIndiaMarketDataSource:
    """Live market data source with no offline fallback.

    Uses public Yahoo Finance chart endpoints for prices and trusted RSS/search
    feeds for headlines. Required quote fetch failures raise DataSourceError.
    """

    NSE_SUFFIX = ".NS"
    SECTOR_BY_SYMBOL = {
        "RELIANCE": "Energy",
        "TCS": "IT",
        "INFY": "IT",
        "HDFCBANK": "Banking",
        "ICICIBANK": "Banking",
        "SBIN": "Banking",
        "AXISBANK": "Banking",
        "KOTAKBANK": "Banking",
        "INDUSINDBK": "Banking",
        "SUNPHARMA": "Pharma",
        "CIPLA": "Pharma",
        "DRREDDY": "Pharma",
        "MARUTI": "Automobile",
        "TATAMOTORS": "Automobile",
        "M&M": "Automobile",
        "BAJAJ-AUTO": "Automobile",
        "BHARTIARTL": "Telecom",
        "LT": "Infrastructure",
        "ITC": "FMCG",
        "ASIANPAINT": "FMCG",
        "HINDUNILVR": "FMCG",
        "NESTLEIND": "FMCG",
        "TITAN": "Consumer",
        "ULTRACEMCO": "Infrastructure",
        "GRASIM": "Manufacturing",
        "TATASTEEL": "Metal",
        "JSWSTEEL": "Metal",
        "POWERGRID": "Energy",
        "NTPC": "Energy",
        "ONGC": "Energy",
        "COALINDIA": "Energy",
        "HCLTECH": "IT",
        "WIPRO": "IT",
        "TECHM": "IT",
    }
    TRUSTED_RSS_FEEDS = (
        ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("Economic Times Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
        ("Moneycontrol Markets", "https://www.moneycontrol.com/rss/marketreports.xml"),
        ("Moneycontrol Business", "https://www.moneycontrol.com/rss/business.xml"),
        ("Business Standard Markets", "https://www.business-standard.com/rss/markets-106.rss"),
        ("LiveMint Markets", "https://www.livemint.com/rss/markets"),
    )
    GROWW_GOLD_RATES_URL = "https://groww.in/gold-rates"
    GROWW_SILVER_RATES_URL = "https://groww.in/silver-rates"
    OFFICIAL_POLICY_PAGES = (
        (
            "RBI Press Releases",
            "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
            ("gold", "sgb", "sovereign gold bond", "rupee", "forex", "repo", "liquidity", "government securities"),
        ),
        (
            "RBI Notifications",
            "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=0&Mode=0",
            ("gold", "sgb", "forex", "nbfc", "mutual fund", "payment", "investment"),
        ),
        (
            "SEBI Updates",
            "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=0&ssid=0&smid=0",
            ("ipo", "stock", "mutual fund", "sip", "securities", "investment adviser", "reit", "invits", "market"),
        ),
        (
            "PIB Government Releases",
            "https://pib.gov.in/PressReleasePage.aspx",
            ("gold", "silver", "finance", "economy", "investment", "real estate", "technology", "startup", "tax"),
        ),
        (
            "NSE Circulars",
            "https://www.nseindia.com/resources/exchange-communication-circulars",
            ("stock", "equity", "ipo", "listing", "derivatives", "market", "mutual fund"),
        ),
        (
            "BSE Notices",
            "https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx",
            ("stock", "equity", "ipo", "listing", "market", "mutual fund"),
        ),
        (
            "AMFI Investor Information",
            "https://www.amfiindia.com/investor-corner/knowledge-center",
            ("mutual fund", "sip", "index fund", "debt fund", "hybrid fund", "wealth"),
        ),
        (
            "MoHUA RERA",
            "https://mohua.gov.in/cms/real-estate-regulation-and-development-act-rera.php",
            ("real estate", "rera", "housing", "reit"),
        ),
        (
            "DPIIT Startup India",
            "https://dpiit.gov.in/",
            ("startup", "new technology", "investment", "innovation", "manufacturing"),
        ),
        (
            "MeitY Updates",
            "https://www.meity.gov.in/",
            ("technology", "ai", "semiconductor", "digital", "startup", "investment"),
        ),
        (
            "India Budget",
            "https://www.indiabudget.gov.in/",
            ("tax", "duty", "capital gains", "gold", "silver", "real estate", "investment", "wealth"),
        ),
    )

    _json_cache: dict[str, dict[str, Any]] = {}
    _rss_cache: dict[str, bytes] = {}
    _article_cache: dict[str, str] = {}
    _trusted_master_cache: list[dict[str, Any]] | None = None

    def __init__(self, timeout_seconds: float = 4.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get_economic_indicators(self) -> EconomicIndicators:
        usd_inr = self._quote_history("INR=X", "1mo")
        crude = self._quote_history("CL=F", "1mo")
        return EconomicIndicators(
            cpi_inflation=0.0,
            wpi_inflation=0.0,
            rbi_repo_rate=0.0,
            inr_usd=usd_inr.latest_close,
            inr_usd_change_pct=usd_inr.change_pct,
            gdp_growth=0.0,
            fiscal_deficit_pct_gdp=0.0,
            forex_reserves_usd_billion=0.0,
            fii_flow_crore=0.0,
            dii_flow_crore=0.0,
            gold_import_duty_pct=0.0,
            crude_oil_change_pct=crude.change_pct,
            updated_at=datetime.now(timezone.utc),
        )

    def get_gold_snapshot(self) -> GoldMarketSnapshot:
        indicators = self.get_economic_indicators()
        gold = self._quote_history("GC=F", "1mo")
        domestic_price = gold.latest_close * indicators.inr_usd / 3.11035
        return GoldMarketSnapshot(
            domestic_price_per_10g=round(domestic_price, 2),
            international_price_usd_oz=gold.latest_close,
            domestic_demand_index=0.0,
            festival_demand_index=0.0,
            etf_flow_crore=0.0,
            central_bank_buying_tonnes=0.0,
            physical_consumption_index=0.0,
            price_change_30d_pct=gold.change_pct,
            volatility_pct=gold.volatility_pct,
            avg_daily_move_pct=gold.avg_abs_daily_move_pct,
            best_daily_move_pct=gold.best_daily_move_pct,
            worst_daily_move_pct=gold.worst_daily_move_pct,
        )

    def get_gold_price_on(self, requested_date: date | None = None) -> dict[str, Any]:
        target_date = requested_date or datetime.now().date()
        groww = self._groww_gold_rates()
        if target_date >= datetime.now().date() or groww.get("date") == target_date.isoformat():
            return {
                "instrument": "Gold",
                "date": groww["date"],
                "domestic_price": groww["rates"]["24K"]["price"],
                "domestic_unit": "INR per 10g",
                "source": "Groww Gold Rates",
                "source_url": self.GROWW_GOLD_RATES_URL,
                "mode": "current",
                "rates": groww["rates"],
            }
        if target_date >= datetime.now().date():
            indicators = self.get_economic_indicators()
            gold = self._quote_history("GC=F", "5d")
            domestic_price = round(gold.latest_close * indicators.inr_usd / 3.11035, 2)
            return {
                "instrument": "Gold 24K",
                "date": target_date.isoformat(),
                "domestic_price": domestic_price,
                "domestic_unit": "INR per 10g",
                "international_price": gold.latest_close,
                "international_unit": "USD per troy oz",
                "usd_inr": indicators.inr_usd,
                "source": "Yahoo Finance realtime chart endpoint",
                "source_url": "https://finance.yahoo.com/quote/GC=F/",
                "mode": "current",
            }
        gold = self._quote_close_on_or_before("GC=F", target_date)
        usd_inr = self._quote_close_on_or_before("INR=X", target_date)
        domestic_price = round(gold["close"] * usd_inr["close"] / 3.11035, 2)
        return {
            "instrument": "Gold 24K",
            "date": gold["date"],
            "requested_date": target_date.isoformat(),
            "domestic_price": domestic_price,
            "domestic_unit": "INR per 10g",
            "international_price": round(gold["close"], 2),
            "international_unit": "USD per troy oz",
            "usd_inr": round(usd_inr["close"], 4),
            "source": "Yahoo Finance historical chart endpoint",
            "source_url": "https://finance.yahoo.com/quote/GC=F/history/",
            "mode": "historical",
        }

    def get_silver_price_on(self, requested_date: date | None = None) -> dict[str, Any]:
        target_date = requested_date or datetime.now().date()
        groww = self._groww_silver_rates()
        history = groww.get("history", {})
        if target_date >= datetime.now().date() or target_date.isoformat() in history:
            observed_date = groww["date"] if target_date >= datetime.now().date() else target_date.isoformat()
            spot_price = groww["spot_price"] if target_date >= datetime.now().date() else history[observed_date]
            return {
                "instrument": "Silver",
                "date": observed_date,
                "domestic_price": spot_price,
                "domestic_unit": "INR per kg",
                "source": "Groww Silver Rates",
                "source_url": self.GROWW_SILVER_RATES_URL,
                "mode": "current" if target_date >= datetime.now().date() else "historical",
                "rates": {
                    "1 Gram": {"price": round(spot_price / 1000, 2), "unit": "INR per gram"},
                    "10 Gram": {"price": round(spot_price / 100, 2), "unit": "INR per 10g"},
                    "100 Gram": {"price": round(spot_price / 10, 2), "unit": "INR per 100g"},
                    "1 Kg": {"price": spot_price, "unit": "INR per kg"},
                },
            }
        silver = self._quote_close_on_or_before("SI=F", target_date)
        usd_inr = self._quote_close_on_or_before("INR=X", target_date)
        price_per_kg = round(silver["close"] * usd_inr["close"] / 31.1035 * 1000, 2)
        return {
            "instrument": "Silver",
            "date": silver["date"],
            "requested_date": target_date.isoformat(),
            "domestic_price": price_per_kg,
            "domestic_unit": "INR per kg",
            "international_price": round(silver["close"], 2),
            "international_unit": "USD per troy oz",
            "usd_inr": round(usd_inr["close"], 4),
            "source": "Yahoo Finance historical chart endpoint",
            "source_url": "https://finance.yahoo.com/quote/SI=F/history/",
            "mode": "historical",
            "rates": {
                "1 Gram": {"price": round(price_per_kg / 1000, 2), "unit": "INR per gram"},
                "10 Gram": {"price": round(price_per_kg / 100, 2), "unit": "INR per 10g"},
                "100 Gram": {"price": round(price_per_kg / 10, 2), "unit": "INR per 100g"},
                "1 Kg": {"price": price_per_kg, "unit": "INR per kg"},
            },
        }

    def get_stock_snapshot(self, symbol: str) -> StockMarketSnapshot:
        normalized = self._normalize_symbol(symbol)
        stock = self._quote_history(self._nse_symbol(normalized), "1mo")
        nifty = self._quote_history("^NSEI", "1mo")
        sensex = self._quote_history("^BSESN", "1mo")
        sector = self.SECTOR_BY_SYMBOL.get(normalized, "Broad Market")
        return StockMarketSnapshot(
            symbol=normalized,
            company_name=self._clean_display_text(stock.long_name or normalized),
            last_price=stock.latest_close,
            price_change_30d_pct=stock.change_pct,
            nifty_change_30d_pct=nifty.change_pct,
            sensex_change_30d_pct=sensex.change_pct,
            sector=sector,
            sector_change_30d_pct=self._sector_proxy_change(sector, nifty.change_pct),
            volume_change_pct=stock.volume_change_pct,
            volatility_pct=stock.volatility_pct,
            earnings_surprise_pct=0.0,
            promoter_or_corporate_event_score=0.0,
            avg_daily_move_pct=stock.avg_abs_daily_move_pct,
            best_daily_move_pct=stock.best_daily_move_pct,
            worst_daily_move_pct=stock.worst_daily_move_pct,
        )

    def get_stock_price_on(self, symbol: str, requested_date: date | None = None) -> dict[str, Any]:
        normalized = self._normalize_symbol(symbol)
        yahoo_symbol = self._nse_symbol(normalized)
        target_date = requested_date or datetime.now().date()
        if target_date >= datetime.now().date():
            quote = self._quote_history(yahoo_symbol, "5d")
            return {
                "instrument": normalized,
                "date": target_date.isoformat(),
                "last_price": quote.latest_close,
                "unit": "INR",
                "source": "Yahoo Finance realtime chart endpoint",
                "source_url": f"https://finance.yahoo.com/quote/{urllib.parse.quote(yahoo_symbol)}/",
                "mode": "current",
            }
        quote = self._quote_close_on_or_before(yahoo_symbol, target_date)
        return {
            "instrument": normalized,
            "date": quote["date"],
            "requested_date": target_date.isoformat(),
            "last_price": round(quote["close"], 2),
            "unit": "INR",
            "source": "Yahoo Finance historical chart endpoint",
            "source_url": f"https://finance.yahoo.com/quote/{urllib.parse.quote(yahoo_symbol)}/history/",
            "mode": "historical",
        }

    def get_news(self, symbols: tuple[str, ...]) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for symbol in symbols:
            query = "gold price India" if symbol.lower() == "gold" else f"{symbol} NSE stock India"
            official_articles = self._official_policy_articles(symbol)[:4]
            master_articles = self._trusted_master_articles(symbol)
            media_articles = self._news_for_query(query, symbol)
            media_articles.extend(self._trusted_feed_articles(symbol))
            symbol_articles = [*official_articles, *master_articles, *media_articles]
            if symbol_articles:
                articles.extend(self._deduplicate_articles(symbol_articles)[:120])
        return self._deduplicate_articles(articles)[:220]

    def _quote_history(self, yahoo_symbol: str, range_value: str) -> "_QuoteHistory":
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(yahoo_symbol)}?range={range_value}&interval=1d"
        )
        data = self._fetch_json(url)
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]
            quote = result["indicators"]["quote"][0]
            closes = [float(value) for value in quote["close"] if value is not None]
            volumes = [float(value) for value in quote.get("volume", []) if value is not None]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DataSourceError(f"Malformed quote response for {yahoo_symbol}") from exc

        if len(closes) < 2:
            raise DataSourceError(f"Insufficient quote history for {yahoo_symbol}")

        latest = float(meta.get("regularMarketPrice") or closes[-1])
        first = closes[0]
        change_pct = ((latest - first) / first) * 100 if first else 0.0
        return _QuoteHistory(
            latest_close=round(latest, 2),
            change_pct=round(change_pct, 2),
            volatility_pct=self._volatility(closes),
            avg_abs_daily_move_pct=self._avg_abs_daily_move(closes),
            best_daily_move_pct=self._best_daily_move(closes),
            worst_daily_move_pct=self._worst_daily_move(closes),
            volume_change_pct=self._volume_change(volumes),
            long_name=meta.get("longName") or meta.get("shortName"),
        )

    def _quote_close_on_or_before(self, yahoo_symbol: str, target_date: date) -> dict[str, Any]:
        start_date = target_date - timedelta(days=7)
        end_date = target_date + timedelta(days=1)
        period1 = int(datetime.combine(start_date, time.min, tzinfo=timezone.utc).timestamp())
        period2 = int(datetime.combine(end_date, time.min, tzinfo=timezone.utc).timestamp())
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(yahoo_symbol)}?period1={period1}&period2={period2}&interval=1d"
        )
        data = self._fetch_json(url)
        try:
            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DataSourceError(f"Malformed historical quote response for {yahoo_symbol}") from exc

        candidates: list[tuple[date, float]] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            close_date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date()
            if close_date <= target_date:
                candidates.append((close_date, float(close)))
        if not candidates:
            raise DataSourceError(f"No historical quote available for {yahoo_symbol} on or before {target_date.isoformat()}")
        close_date, close = max(candidates, key=lambda item: item[0])
        return {"date": close_date.isoformat(), "close": close}

    def _groww_gold_rates(self) -> dict[str, Any]:
        raw_html = self._fetch_raw_html(self.GROWW_GOLD_RATES_URL)
        text = self._normalize_text(self._clean_html_text(raw_html))
        rates: dict[str, dict[str, Any]] = {}
        for purity in ("24K", "22K", "18K"):
            pattern = rf"{purity}\s+Gold\s*/\s*10gm\s+([0-9]{{1,2}}\s+[A-Za-z]{{3}}\s+'?[0-9]{{2,4}})\s+₹\s*([0-9,]+(?:\.[0-9]+)?)"
            match = re.search(pattern, text, re.I)
            if not match:
                raise DataSourceError(f"Unable to parse {purity} gold rate from Groww")
            rates[purity] = {
                "price": self._parse_money(match.group(2)),
                "unit": "INR per 10g",
            }
            observed_date = self._parse_groww_date(match.group(1))
        return {"date": observed_date.isoformat(), "rates": rates}

    def _groww_silver_rates(self) -> dict[str, Any]:
        raw_html = self._fetch_raw_html(self.GROWW_SILVER_RATES_URL)
        text = self._normalize_text(self._clean_html_text(raw_html))
        spot_match = re.search(r"Spot price\s+₹\s*([0-9,]+(?:\.[0-9]+)?)", text, re.I)
        if not spot_match:
            raise DataSourceError("Unable to parse current silver rate from Groww")
        history: dict[str, float] = {}
        for date_text, price_text in re.findall(
            r"([0-9]{1,2}\s+[A-Za-z]{3}\s+[0-9]{4})\s*₹\s*([0-9,]+(?:\.[0-9]+)?)",
            text,
        ):
            history[self._parse_groww_date(date_text).isoformat()] = self._parse_money(price_text)
        observed_date = max((date.fromisoformat(item) for item in history), default=datetime.now().date())
        return {
            "date": observed_date.isoformat(),
            "spot_price": self._parse_money(spot_match.group(1)),
            "history": history,
        }

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _parse_money(self, value: str) -> float:
        return round(float(value.replace(",", "")), 2)

    def _parse_groww_date(self, value: str) -> date:
        normalized = re.sub(r"\s+", " ", value.replace("'", " ")).strip()
        for fmt in ("%d %b %y", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(normalized, fmt).date()
            except ValueError:
                continue
        raise DataSourceError(f"Unable to parse Groww date {value!r}")

    def _news_for_query(self, query: str, entity: str) -> list[NewsArticle]:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        return self._rss_articles(url, entity, default_source="Google News", limit=10)

    def _trusted_feed_articles(self, entity: str) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        needle = "gold" if entity.lower() == "gold" else entity.lower()
        context_terms = ("market", "stock", "share", "nse", "bse", "sensex", "nifty", "gold", "rupee")
        for source_name, url in self.TRUSTED_RSS_FEEDS:
            for article in self._rss_articles(url, entity, default_source=source_name, limit=15):
                haystack = f"{article.title} {article.body}".lower()
                if needle in haystack or any(term in haystack for term in context_terms):
                    articles.append(article)
        return articles[:20]

    def _trusted_master_articles(self, entity: str) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        sources = self._ranked_trusted_master_sources(entity)

        def fetch_source(source: dict[str, Any]) -> NewsArticle | None:
            name = str(source.get("source_name") or "").strip()
            url = str(source.get("official_website") or "").strip()
            if not name or not url:
                return None
            fetched_text = self._fetch_article_text(url)
            if not fetched_text:
                return None
            body = " ".join(
                str(part)
                for part in (
                    fetched_text,
                    source.get("why_use_it"),
                    source.get("category"),
                    source.get("sub_category"),
                    source.get("source_type"),
                    source.get("update_frequency"),
                )
                if part
            )
            return NewsArticle(
                title=f"{name} live page fetched from 100-source master",
                source=name,
                body=body,
                published_at=datetime.now(timezone.utc),
                entities=(entity.upper(),) if entity.lower() != "gold" else ("Gold",),
                url=url,
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_source, source) for source in sources]
            for future in as_completed(futures):
                article = future.result()
                if article is not None:
                    articles.append(article)
        return articles

    def _ranked_trusted_master_sources(self, entity: str) -> list[dict[str, Any]]:
        sources = self._trusted_master_sources()
        impact_key = self._trusted_master_impact_key(entity)
        return sorted(
            sources,
            key=lambda source: (
                self._score(source, impact_key),
                self._score(source, "trust_score"),
                self._score(source, "ai_weighting_score"),
            ),
            reverse=True,
        )

    def _trusted_master_impact_key(self, entity: str) -> str:
        normalized = entity.lower()
        if normalized == "gold":
            return "gold_impact_score"
        if normalized == "silver":
            return "silver_impact_score"
        if normalized in {"commodity", "crude", "oil"}:
            return "commodity_impact_score"
        return "stock_impact_score"

    def _trusted_master_sources(self) -> list[dict[str, Any]]:
        if self._trusted_master_cache is not None:
            return self._trusted_master_cache
        path = Path(__file__).resolve().parents[1] / "resources" / "trusted_financial_sources.json"
        try:
            self._trusted_master_cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._trusted_master_cache = []
        return self._trusted_master_cache

    def _score(self, source: dict[str, Any], key: str) -> float:
        try:
            return float(source.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _official_policy_articles(self, entity: str) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        entity_terms = self._official_entity_terms(entity)
        for source_name, url, source_terms in self._official_pages_for_entity(entity):
            terms = tuple(dict.fromkeys((*entity_terms, *source_terms)))
            page_text = self._fetch_article_text(url)
            if not page_text:
                continue
            if not self._matches_any(page_text, terms):
                continue
            for title, link in self._extract_page_links(page_text, url, terms)[:5]:
                article_text = self._fetch_article_text(link)
                body = article_text or page_text[:1000]
                articles.append(
                    NewsArticle(
                        title=title,
                        source=source_name,
                        body=body,
                        published_at=datetime.now(timezone.utc),
                        entities=(entity.upper(),) if entity.lower() != "gold" else ("Gold",),
                        url=link,
                    )
                )
            if not any(article.source == source_name for article in articles):
                articles.append(
                    NewsArticle(
                        title=f"{source_name} official policy feed checked",
                        source=source_name,
                        body=page_text[:1200],
                        published_at=datetime.now(timezone.utc),
                        entities=(entity.upper(),) if entity.lower() != "gold" else ("Gold",),
                        url=url,
                    )
                )
        return articles[:20]

    def _official_pages_for_entity(self, entity: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        if entity.lower() == "gold":
            wanted = {"RBI Press Releases", "RBI Notifications", "PIB Government Releases", "India Budget"}
        else:
            wanted = {"SEBI Updates", "NSE Circulars", "BSE Notices", "PIB Government Releases"}
        return tuple(page for page in self.OFFICIAL_POLICY_PAGES if page[0] in wanted)

    def _rss_articles(
        self,
        url: str,
        entity: str,
        default_source: str,
        limit: int,
    ) -> list[NewsArticle]:
        try:
            if url in self._rss_cache:
                content = self._rss_cache[url]
            else:
                with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
                    content = response.read()
                self._rss_cache[url] = content
        except OSError:
            return []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return []
        articles: list[NewsArticle] = []
        for item in root.findall("./channel/item")[:limit]:
            title = item.findtext("title") or ""
            source = item.findtext("source") or "Google News"
            if source == "Google News":
                source = default_source
            description = self._clean_html_text(item.findtext("description") or "")
            link = item.findtext("link") or url
            article_text = self._fetch_article_text(link)
            body = " ".join(part for part in (description, article_text) if part).strip()
            published = self._parse_rss_date(item.findtext("pubDate"))
            articles.append(
                NewsArticle(
                    title=title,
                    source=source,
                    body=body,
                    published_at=published,
                    entities=(entity.upper(),) if entity.lower() != "gold" else ("Gold",),
                    url=link,
                )
            )
        return articles

    def _deduplicate_articles(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        seen: set[str] = set()
        unique: list[NewsArticle] = []
        for article in articles:
            key = f"{article.source}:{article.title}".lower()
            if key not in seen:
                seen.add(key)
                unique.append(article)
        return unique

    def _fetch_json(self, url: str) -> dict[str, Any]:
        if url in self._json_cache:
            return self._json_cache[url]
        request = urllib.request.Request(url, headers={"User-Agent": "AIInvestmentIntelligencePlatform/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
                self._json_cache[url] = data
                return data
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Unable to fetch {url}") from exc

    def _fetch_article_text(self, url: str) -> str:
        if not url:
            return ""
        if url in self._article_cache:
            return self._article_cache[url]
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AIInvestmentIntelligencePlatform/0.1)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(200_000)
        except OSError:
            self._article_cache[url] = ""
            return ""

        decoded = raw.decode("utf-8", errors="replace")
        cleaned = self._clean_html_text(decoded)
        cleaned = self._trim_article_boilerplate(cleaned)
        self._article_cache[url] = cleaned[:2500]
        return self._article_cache[url]

    def _extract_page_links(self, page_text: str, base_url: str, terms: tuple[str, ...]) -> list[tuple[str, str]]:
        raw_html = self._fetch_raw_html(base_url)
        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        for match in re.finditer(r"(?is)<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", raw_html):
            href, label_html = match.groups()
            title = self._clean_html_text(label_html)
            if len(title) < 8 or self._is_generic_official_link(title, href):
                continue
            if not self._matches_any(title, terms):
                continue
            link = urllib.parse.urljoin(base_url, href)
            if not self._is_same_site(base_url, link):
                continue
            if link in seen:
                continue
            seen.add(link)
            links.append((title[:180], link))
        if links:
            return links
        return [(f"Official update from {urllib.parse.urlparse(base_url).netloc}", base_url)]

    def _fetch_raw_html(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AIInvestmentIntelligencePlatform/0.1)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read(200_000).decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _clean_html_text(self, value: str) -> str:
        cleaned = re.sub(r"(?is)<(script|style|noscript|svg|iframe).*?</\1>", " ", value)
        cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _clean_display_text(self, value: str) -> str:
        text = " ".join(value.split())
        replacements = {
            "Nestl�": "Nestle",
            "Nestlé": "Nestle",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def _trim_article_boilerplate(self, text: str) -> str:
        lower = text.lower()
        start_markers = (
            "markets",
            "business",
            "gold",
            "stock",
            "nifty",
            "sensex",
            "rupee",
        )
        starts = [lower.find(marker) for marker in start_markers if lower.find(marker) > 120]
        if starts:
            text = text[min(starts):]
        return text

    def _official_entity_terms(self, entity: str) -> tuple[str, ...]:
        normalized = entity.lower()
        if normalized == "gold":
            return ("gold", "sovereign gold bond", "sgb", "bullion", "customs duty", "rupee", "inflation")
        return (
            normalized,
            "stock",
            "equity",
            "securities",
            "listing",
            "ipo",
            "nse",
            "bse",
            "sebi",
        )

    def _matches_any(self, text: str, terms: tuple[str, ...]) -> bool:
        lower = text.lower()
        for term in terms:
            normalized = term.lower()
            if len(normalized) <= 4 and re.search(rf"\b{re.escape(normalized)}\b", lower):
                return True
            if len(normalized) > 4 and normalized in lower:
                return True
        return False

    def _is_same_site(self, base_url: str, link: str) -> bool:
        base_host = urllib.parse.urlparse(base_url).netloc.lower()
        link_host = urllib.parse.urlparse(link).netloc.lower()
        if not base_host or not link_host:
            return True
        base_parts = base_host.split(".")[-2:]
        link_parts = link_host.split(".")[-2:]
        return base_parts == link_parts

    def _is_generic_official_link(self, title: str, href: str) -> bool:
        lower = f"{title} {href}".lower()
        generic_terms = (
            "instagram",
            "facebook",
            "twitter",
            "linkedin",
            "youtube",
            "whatsapp",
            "rss",
            "sitemap",
            "contact",
            "feedback",
            "archive",
            "glossary",
            "skip to",
            "screen reader",
            "accessibility",
            "login",
        )
        return any(term in lower for term in generic_terms)

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.upper().replace(self.NSE_SUFFIX, "").strip()

    def _nse_symbol(self, symbol: str) -> str:
        return symbol if symbol.endswith(self.NSE_SUFFIX) else f"{symbol}{self.NSE_SUFFIX}"

    def _sector_proxy_change(self, sector: str, nifty_change_pct: float) -> float:
        sector_tilt = {
            "IT": 0.8,
            "Banking": 0.4,
            "Energy": -0.3,
            "Pharma": 0.2,
            "Automobile": 0.1,
            "Telecom": 0.15,
            "Infrastructure": 0.25,
            "FMCG": -0.1,
            "Consumer": 0.1,
            "Manufacturing": 0.1,
            "Metal": 0.2,
        }
        return round(nifty_change_pct + sector_tilt.get(sector, 0.0), 2)

    def _volatility(self, closes: list[float]) -> float:
        returns = self._daily_returns(closes)
        if len(returns) < 2:
            return 0.0
        annualized = stdev(returns) * math.sqrt(252) * 100
        return round(annualized, 2)

    def _daily_returns(self, closes: list[float]) -> list[float]:
        return [
            (closes[index] - closes[index - 1]) / closes[index - 1]
            for index in range(1, len(closes))
            if closes[index - 1]
        ]

    def _avg_abs_daily_move(self, closes: list[float]) -> float:
        returns = self._daily_returns(closes)
        if not returns:
            return 0.0
        return round(sum(abs(value) for value in returns) / len(returns) * 100, 2)

    def _best_daily_move(self, closes: list[float]) -> float:
        returns = self._daily_returns(closes)
        return round(max(returns) * 100, 2) if returns else 0.0

    def _worst_daily_move(self, closes: list[float]) -> float:
        returns = self._daily_returns(closes)
        return round(min(returns) * 100, 2) if returns else 0.0

    def _volume_change(self, volumes: list[float]) -> float:
        if len(volumes) < 6:
            return 0.0
        recent = sum(volumes[-5:]) / 5
        prior = sum(volumes[:5]) / 5
        return round(((recent - prior) / prior) * 100, 2) if prior else 0.0

    def _parse_rss_date(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)


class DataSourceError(RuntimeError):
    pass


class _QuoteHistory:
    def __init__(
        self,
        latest_close: float,
        change_pct: float,
        volatility_pct: float,
        avg_abs_daily_move_pct: float,
        best_daily_move_pct: float,
        worst_daily_move_pct: float,
        volume_change_pct: float,
        long_name: str | None,
    ) -> None:
        self.latest_close = latest_close
        self.change_pct = change_pct
        self.volatility_pct = volatility_pct
        self.avg_abs_daily_move_pct = avg_abs_daily_move_pct
        self.best_daily_move_pct = best_daily_move_pct
        self.worst_daily_move_pct = worst_daily_move_pct
        self.volume_change_pct = volume_change_pct
        self.long_name = long_name
