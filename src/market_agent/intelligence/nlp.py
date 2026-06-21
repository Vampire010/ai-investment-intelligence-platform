from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from market_agent.core.models import NewsAnalysis, NewsArticle, Sentiment


POSITIVE_WORDS = {
    "better",
    "buying",
    "demand",
    "gain",
    "improves",
    "positive",
    "strong",
    "strengthens",
    "supporting",
    "upward",
}

NEGATIVE_WORDS = {
    "crisis",
    "downward",
    "elevated",
    "negative",
    "pressure",
    "risk",
    "selling",
    "tension",
    "volatility",
    "weakens",
    "weaker",
}

TOPIC_KEYWORDS = {
    "inflation": "Inflation",
    "festival": "Festival demand",
    "wedding": "Wedding demand",
    "rupee": "INR/USD",
    "dollar": "INR/USD",
    "fii": "FII flow",
    "earnings": "Earnings",
    "oil": "Crude oil",
    "geopolitical": "Geopolitics",
    "sector": "Sector performance",
}

CATEGORY_LABELS = {
    "gold_seo": "Gold",
    "silver_seo": "Silver",
    "stock_market_seo": "Stock market",
    "intraday_trading": "Intraday trading",
    "inflation": "Inflation",
    "recession": "Recession",
    "war_geopolitical": "Geopolitics",
    "financial_crisis": "Financial crisis",
    "commodity": "Commodity",
    "shortage": "Shortage",
    "ai_financial_intelligence": "AI financial intelligence",
    "high_value_buyer_intent": "Buyer intent",
    "institutional_intelligence": "Institutional intelligence",
}

BULLISH_SEO_TERMS = {
    "buy",
    "buying",
    "bull",
    "bullish",
    "demand",
    "growth",
    "hedge",
    "momentum",
    "opportunities",
    "positive",
    "rising",
    "safe haven",
    "strong",
    "support",
    "value investing",
}

BEARISH_SEO_TERMS = {
    "bear",
    "collapse",
    "crash",
    "crisis",
    "down",
    "falling",
    "panic",
    "recession",
    "risk",
    "selling",
    "shortage",
    "slowdown",
    "war",
    "weak",
}

SEO_KEYWORDS = {}


def _load_seo_keywords() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[1] / "resources" / "seo_financial_keywords.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(category): tuple(dict.fromkeys(str(term).strip() for term in terms if str(term).strip()))
        for category, terms in data.items()
    }


SEO_KEYWORDS = _load_seo_keywords()


class NewsIntelligenceEngine:
    def analyze(self, articles: list[NewsArticle]) -> NewsAnalysis:
        text = " ".join([article.title + " " + article.body for article in articles])
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        counts = Counter(tokens)
        positive = sum(counts[word] for word in POSITIVE_WORDS)
        negative = sum(counts[word] for word in NEGATIVE_WORDS)
        keyword_hits, keyword_categories, seo_score = self._seo_keyword_analysis(text)
        raw_score = positive - negative + seo_score * 4.0

        if raw_score > 1:
            sentiment = Sentiment.POSITIVE
        elif raw_score < -1:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL

        sentiment_score = max(-1.0, min(1.0, raw_score / 8.0))
        impact_score = self._impact_score(tokens, articles, keyword_hits)
        topic_labels = {label for key, label in TOPIC_KEYWORDS.items() if key in counts}
        topic_labels.update(keyword_categories)
        topics = tuple(sorted(topic_labels))
        entities = tuple(sorted({entity for article in articles for entity in article.entities}))
        anomaly_flags = self._anomalies(tokens, impact_score)

        return NewsAnalysis(
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            impact_score=impact_score,
            topics=topics,
            entities=entities,
            anomaly_flags=anomaly_flags,
            keyword_hits=tuple(keyword_hits[:24]),
            keyword_categories=tuple(keyword_categories),
            seo_sentiment_score=round(seo_score, 2),
            article_count=len(articles),
            source_count=len({article.source for article in articles}),
        )

    def _impact_score(
        self,
        tokens: list[str],
        articles: list[NewsArticle],
        keyword_hits: list[str],
    ) -> float:
        high_impact_terms = {
            "budget",
            "conflict",
            "crisis",
            "duty",
            "election",
            "fii",
            "inflation",
            "policy",
            "rbi",
            "selling",
            "volatility",
        }
        hits = sum(1 for token in tokens if token in high_impact_terms)
        source_factor = min(1.0, len({article.source for article in articles}) / 5.0)
        keyword_factor = min(0.25, len(keyword_hits) / 40.0)
        return round(min(1.0, hits / 12.0 + source_factor * 0.25 + keyword_factor), 2)

    def _anomalies(self, tokens: list[str], impact_score: float) -> tuple[str, ...]:
        flags: list[str] = []
        token_set = set(tokens)
        if {"volatility", "selling"}.issubset(token_set):
            flags.append("Unusual selling with elevated volatility")
        if {"geopolitical", "tension", "weakens"}.issubset(token_set):
            flags.append("Macro shock cluster affecting gold")
        if impact_score >= 0.75:
            flags.append("High news impact concentration")
        return tuple(flags)

    def _seo_keyword_analysis(self, text: str) -> tuple[list[str], list[str], float]:
        normalized = " ".join(text.lower().split())
        hits: list[str] = []
        category_hits: list[str] = []
        bullish = 0
        bearish = 0
        for category, keywords in SEO_KEYWORDS.items():
            matched = False
            for keyword in keywords:
                if self._phrase_in_text(normalized, keyword.lower()):
                    hits.append(keyword)
                    matched = True
                    keyword_lower = keyword.lower()
                    if any(term in keyword_lower for term in BULLISH_SEO_TERMS):
                        bullish += 1
                    if any(term in keyword_lower for term in BEARISH_SEO_TERMS):
                        bearish += 1
            if matched:
                category_hits.append(CATEGORY_LABELS.get(category, category.replace("_", " ").title()))
        score = 0.0
        if bullish or bearish:
            score = max(-1.0, min(1.0, (bullish - bearish) / max(4.0, bullish + bearish)))
        return list(dict.fromkeys(hits)), list(dict.fromkeys(category_hits)), score

    def _phrase_in_text(self, text: str, phrase: str) -> bool:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        return re.search(pattern, text) is not None
