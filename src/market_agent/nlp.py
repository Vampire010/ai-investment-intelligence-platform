from __future__ import annotations

import re
from collections import Counter

from market_agent.models import NewsAnalysis, NewsArticle, Sentiment


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


class NewsIntelligenceEngine:
    def analyze(self, articles: list[NewsArticle]) -> NewsAnalysis:
        text = " ".join([article.title + " " + article.body for article in articles])
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        counts = Counter(tokens)
        positive = sum(counts[word] for word in POSITIVE_WORDS)
        negative = sum(counts[word] for word in NEGATIVE_WORDS)
        raw_score = positive - negative

        if raw_score > 1:
            sentiment = Sentiment.POSITIVE
        elif raw_score < -1:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL

        sentiment_score = max(-1.0, min(1.0, raw_score / 8.0))
        impact_score = self._impact_score(tokens, articles)
        topics = tuple(sorted({label for key, label in TOPIC_KEYWORDS.items() if key in counts}))
        entities = tuple(sorted({entity for article in articles for entity in article.entities}))
        anomaly_flags = self._anomalies(tokens, impact_score)

        return NewsAnalysis(
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            impact_score=impact_score,
            topics=topics,
            entities=entities,
            anomaly_flags=anomaly_flags,
        )

    def _impact_score(self, tokens: list[str], articles: list[NewsArticle]) -> float:
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
        return round(min(1.0, hits / 12.0 + source_factor * 0.25), 2)

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
