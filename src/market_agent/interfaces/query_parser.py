from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketQuery:
    raw_text: str
    instrument_type: str
    stock_symbol: str | None
    requested_datetime_text: str | None
    is_prediction: bool
    perspective: str
    horizons: tuple[str, ...]
    output_json_requested: bool
    investment_amount: float | None
    risk_profile: str | None
    top_n: int

    @property
    def certainty_label(self) -> str:
        return "Predictive estimate" if self.is_prediction else "Actual/current or historical"


KNOWN_SYMBOL_WORDS = {
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "SUNPHARMA",
    "MARUTI",
    "BHARTIARTL",
    "LT",
    "ITC",
}
COMPANY_SYMBOL_ALIASES = {
    "infosys": "INFY",
    "tata consultancy services": "TCS",
    "tcs": "TCS",
    "reliance": "RELIANCE",
    "hdfc bank": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "state bank of india": "SBIN",
    "sbi": "SBIN",
}


def parse_market_query(text: str, fallback_stock: str | None = None) -> MarketQuery:
    normalized = text.strip()
    lower = normalized.lower()
    instrument_type = _instrument_type(lower)
    perspective = _perspective(lower)
    stock_symbol = (
        _extract_symbol(normalized, fallback_stock)
        if instrument_type == "stock"
        and perspective
        not in {
            "sector_analysis",
            "top_stocks",
            "multi_news_intelligence",
            "news_impact",
            "master_platform",
        }
        else None
    )
    is_prediction = any(
        phrase in lower
        for phrase in (
            "expected",
            "predict",
            "prediction",
            "will be",
            "what will",
            "future",
            "estimate",
            "forecast",
            "target",
            "outlook",
        )
    ) or perspective in {
        "gold_forecast",
        "equity_research",
        "intraday_trading",
        "swing_trading",
        "portfolio_advisor",
        "master_platform",
    }
    requested_datetime_text = _extract_datetime_text(normalized)
    if requested_datetime_text:
        is_prediction = is_prediction or _looks_future_or_exact_time(requested_datetime_text)
    return MarketQuery(
        raw_text=normalized,
        instrument_type=instrument_type,
        stock_symbol=stock_symbol,
        requested_datetime_text=requested_datetime_text,
        is_prediction=is_prediction,
        perspective=perspective,
        horizons=_horizons(lower),
        output_json_requested="json" in lower,
        investment_amount=_investment_amount(normalized),
        risk_profile=_risk_profile(lower),
        top_n=_top_n(lower),
    )


def _instrument_type(lower: str) -> str:
    library_category = _prompt_library_category(lower)
    if library_category == "gold":
        return "gold"
    if library_category == "silver":
        return "silver"
    if library_category == "stock":
        return "stock"
    if library_category == "macro":
        return "news"
    if library_category == "portfolio":
        return "portfolio"
    if _looks_like_policy_or_treaty_question(lower):
        return "news"
    if _looks_like_return_multiple_goal(lower):
        return "wealth"
    if _looks_like_market_summary(lower) or _looks_like_sector_outlook(lower) or _looks_like_macro_event_brief(lower):
        return "news"
    if _looks_like_macro_geopolitics(lower):
        return "news"
    if (
        "business ideas" in lower
        or "passive income" in lower
        or "monthly income" in lower
        or "wealth plan" in lower
        or "wealth dashboard" in lower
        or "net worth" in lower
        or "income, expenses" in lower
    ):
        return "wealth"
    if "mutual fund" in lower or "sip" in lower or "index fund" in lower:
        return "mutual_fund"
    if "real estate" in lower or "property" in lower or "rera" in lower or "reit" in lower:
        return "real_estate"
    if "ipo" in lower or "initial public offer" in lower:
        return "ipo"
    if (
        "new technology" in lower
        or "technology investment" in lower
        or "ai investment" in lower
        or "semiconductor" in lower
        or "startup investment" in lower
    ):
        return "technology"
    if "silver" in lower:
        return "silver"
    if "crypto" in lower or "bitcoin" in lower or "ethereum" in lower:
        return "crypto"
    if "usd/inr" in lower or "forex" in lower or "currency" in lower:
        return "forex"
    if "portfolio" in lower or "investment amount" in lower or "diversified" in lower:
        return "portfolio"
    if "news" in lower and "stock" not in lower and "gold" not in lower:
        return "news"
    if "gold" in lower:
        return "gold"
    return "stock"


def _extract_symbol(text: str, fallback_stock: str | None) -> str | None:
    upper_tokens = re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", text)
    ignored = {"PM", "AM", "NSE", "BSE", "SEBI", "USD", "INR", "UK", "US", "USA", "INDIA"}
    for token in upper_tokens:
        if token not in ignored:
            return token.replace("&", "")
    for symbol in KNOWN_SYMBOL_WORDS:
        if symbol.lower() in text.lower():
            return symbol
    lower = text.lower()
    for name, symbol in COMPANY_SYMBOL_ALIASES.items():
        if name in lower:
            return symbol
    return fallback_stock


def _perspective(lower: str) -> str:
    library_category = _prompt_library_category(lower)
    if library_category == "gold":
        return "gold_intelligence"
    if library_category == "silver":
        return "silver_intelligence"
    if library_category == "stock":
        return "equity_research"
    if library_category == "macro":
        return "macro_geopolitics"
    if library_category == "portfolio":
        return "portfolio_strategy"
    if _looks_like_policy_or_treaty_question(lower):
        return "news_impact"
    if _looks_like_return_multiple_goal(lower):
        return "multibagger_goal"
    if _looks_like_market_summary(lower):
        return "market_summary"
    if _looks_like_sector_outlook(lower):
        return "sector_outlook"
    if _looks_like_macro_event_brief(lower):
        return "macro_events"
    if _looks_like_macro_geopolitics(lower):
        return "macro_geopolitics"
    if (
        "business ideas" in lower
        or "passive income" in lower
        or "wealth plan" in lower
        or "wealth dashboard" in lower
        or "net worth" in lower
        or "income, expenses" in lower
    ):
        return "wealth_plan"
    if "usd/inr" in lower or "forex" in lower or "currency weakness" in lower:
        return "forex_analysis"
    if "mutual fund" in lower or "sip" in lower or "index fund" in lower:
        return "mutual_funds"
    if "real estate" in lower or "property" in lower or "rera" in lower or "reit" in lower:
        return "real_estate"
    if "ipo" in lower or "initial public offer" in lower:
        return "ipo_analysis"
    if (
        "new technology" in lower
        or "technology investment" in lower
        or "ai investment" in lower
        or "semiconductor" in lower
        or "startup investment" in lower
    ):
        return "technology_investment"
    if "it sector" in lower or "it stocks" in lower:
        return "sector_analysis"
    if "silver" in lower and (
        "last 7" in lower
        or "technical" in lower
        or "support/resistance" in lower
        or "support" in lower and "resistance" in lower
    ):
        return "precious_metals_technical"
    if "silver" in lower:
        return "gold_silver_compare"
    if "crypto" in lower or "bitcoin" in lower or "ethereum" in lower:
        return "crypto_analysis"
    if (
        "top stocks" in lower
        or "best stocks" in lower
        or "stocks to buy" in lower
        or "stock i can buy" in lower
        or "stock can i buy" in lower
        or "stock to buy" in lower and "intraday" in lower
        or "intraday stock" in lower and "buy" in lower
        or "risky" in lower and "stocks" in lower
        or "undervalued" in lower and "stocks" in lower
        or "intraday stocks" in lower
        or "breakout" in lower and "stocks" in lower
        or "overbought" in lower and "stocks" in lower
        or "oversold" in lower and "stocks" in lower
        or "bullish nse stocks" in lower
        or "suggest me" in lower and "stock" in lower and "buy" in lower
    ):
        return "top_stocks"
    if "intraday" in lower or "day trading" in lower or "opening range" in lower:
        return "intraday_trading"
    if "warren buffett" in lower or "buffett" in lower or "business quality" in lower:
        return "buffett"
    if "swing trader" in lower or "swing trading" in lower or "stop loss" in lower or "rsi" in lower:
        return "swing_trading"
    if "portfolio manager" in lower or "portfolio" in lower or "investment amount" in lower:
        return "portfolio_advisor"
    if "news article" in lower or "news impact" in lower:
        return "news_impact"
    if "all provided news" in lower or "market themes" in lower or "top 10 bullish" in lower:
        return "multi_news_intelligence"
    if "rank all assets" in lower or "investment intelligence platform" in lower:
        return "master_platform"
    if "gold" in lower and (
        "last 7" in lower
        or "technical" in lower
        or "support/resistance" in lower
        or "support" in lower and "resistance" in lower
    ):
        return "precious_metals_technical"
    if "gold market analyst" in lower or ("gold" in lower and ("next 7" in lower or "next 30" in lower or "next 90" in lower)):
        return "gold_forecast"
    if (
        "stock analysis" in lower
        or "equity research analyst" in lower
        or "fundamental score" in lower
        or "technical score" in lower
        or "fundamentals" in lower
        or "intrinsic value" in lower
        or "earnings quality" in lower
        or "growth sustainability" in lower
        or "industry peers" in lower
        or "expected return" in lower
    ):
        return "equity_research"
    return "standard"


def _prompt_library_category(lower: str) -> str | None:
    match = re.search(r"\[(gold intelligence|silver intelligence|stock analysis|macro & geopolitics|portfolio & risk)\]", lower)
    if not match:
        return None
    label = match.group(1)
    return {
        "gold intelligence": "gold",
        "silver intelligence": "silver",
        "stock analysis": "stock",
        "macro & geopolitics": "macro",
        "portfolio & risk": "portfolio",
    }[label]


def _looks_like_return_multiple_goal(lower: str) -> bool:
    return bool(
        re.search(r"\b[2-9]\s*x\b", lower)
        or re.search(r"\b[2-9]x\b", lower)
        or any(
            phrase in lower
            for phrase in (
                "double my money",
                "triple my money",
                "multibagger",
                "multi bagger",
                "wealth multiplier",
                "multiply my investment",
            )
        )
    )


def _looks_like_macro_geopolitics(lower: str) -> bool:
    macro_terms = (
        "macro & geopolitics",
        "geopolitical",
        "middle east conflict",
        "trade war",
        "recession fears",
        "interest-rate hike",
        "interest rate hike",
        "inflation effects",
        "supply shortage",
        "commodity reactions",
        "indian markets",
    )
    return any(term in lower for term in macro_terms)


def _looks_like_market_summary(lower: str) -> bool:
    return (
        "market summary" in lower
        or "sensex" in lower and "nifty" in lower and ("movers" in lower or "sector" in lower)
        or "fii" in lower and "dii" in lower and "market" in lower
    )


def _looks_like_sector_outlook(lower: str) -> bool:
    return (
        "top 5 sectors" in lower
        or "top sectors" in lower
        or "sector outlook" in lower
        or ("sectors in india" in lower and ("6" in lower or "12" in lower or "months" in lower))
    )


def _looks_like_macro_event_brief(lower: str) -> bool:
    return (
        "macro or policy events" in lower
        or "policy events" in lower
        or ("rbi" in lower and "cpi" in lower and "gdp" in lower)
        or ("equities" in lower and "bonds" in lower and "inr" in lower)
    )


def _looks_like_policy_or_treaty_question(lower: str) -> bool:
    policy_patterns = (
        r"\btreaty\b",
        r"\bagreement\b",
        r"\bsigned\s+between\b",
        r"\bfree\s+trade\s+agreement\b",
        r"\bfta\b",
        r"\bmou\b",
        r"\bmemorandum\s+of\s+understanding\b",
        r"\bbilateral\b",
        r"\btrade\s+deal\b",
        r"\bindia\s+and\s+uk\b",
        r"\bindia\s+uk\b",
        r"\bindia-uk\b",
        r"\bindia\s+and\s+us\b",
        r"\bindia\s+us\b",
        r"\bindia-us\b",
        r"\bindia\s+and\s+usa\b",
        r"\bindia\s+usa\b",
        r"\bindia\s+united\s+states\b",
    )
    return any(re.search(pattern, lower) for pattern in policy_patterns)


def _horizons(lower: str) -> tuple[str, ...]:
    horizons: list[str] = []
    if "today" in lower:
        horizons.append("Today")
    horizon_patterns = (
        ("next 7", "Next 7 Days"),
        ("1 week", "1 Week"),
        ("next 30", "Next 30 Days"),
        ("1 month", "1 Month"),
        ("3 months", "3 Months"),
        ("next 90", "Next 90 Days"),
        ("6 months", "6 Months"),
        ("1 year", "1 Year"),
    )
    for needle, label in horizon_patterns:
        if needle in lower:
            horizons.append(label)
    return tuple(dict.fromkeys(horizons))


def _investment_amount(text: str) -> float | None:
    if not re.search(r"(investment amount|portfolio|₹|rs\.?|inr)", text, re.I):
        return None
    match = re.search(r"(?:investment amount\s*:?\s*)?(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(lakh|lac|crore|cr)?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    if unit in {"lakh", "lac"}:
        amount *= 100000
    elif unit in {"crore", "cr"}:
        amount *= 10000000
    return amount


def _risk_profile(lower: str) -> str | None:
    for profile in ("low", "medium", "high"):
        if re.search(rf"\b{profile}\b", lower):
            return profile.title()
    return None


def _top_n(lower: str) -> int:
    match = re.search(r"\btop\s+(\d{1,2})\b", lower)
    if not match:
        return 5
    return max(1, min(20, int(match.group(1))))


def _extract_datetime_text(text: str) -> str | None:
    date_match = re.search(
        r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})(?:\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?))?",
        text,
    )
    if date_match:
        return " ".join(part for part in date_match.groups() if part)
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?\b", text)
    return iso_match.group(0) if iso_match else None


def _looks_future_or_exact_time(value: str) -> bool:
    if re.search(r"\d{1,2}:\d{2}", value):
        return True
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.split(" at ")[0], fmt).date() >= datetime.now().date()
        except ValueError:
            continue
    return False
