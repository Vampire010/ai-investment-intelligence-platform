from __future__ import annotations


PROMPT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "gold_silver": (
        "What will be the gold price on 22 June 2026?",
        "Analyze gold for the next 7 days, 30 days, and 90 days. Give Buy, Hold, Sell probability, confidence score, risk score, predicted range, reasons, and research sources.",
        "Compare gold and silver investment opportunity for this month. Which has better upside potential and lower risk?",
        "Will silver outperform gold in the next 3 months? Analyze industrial demand, global rates, USD/INR, inflation, and commodity trends.",
        "Should I buy physical gold, gold ETF, sovereign gold bond, or digital gold right now?",
    ),
    "stocks": (
        "Suggest me top stocks to buy on 22 June 2026.",
        "Analyze RELIANCE stock for Buy, Hold, or Sell with probability, confidence score, risk score, target range, and research sources.",
        "Give me top 10 bullish NSE stocks for next week based on price trend, volume, sector strength, FII/DII activity, and news sentiment.",
        "Which stocks are risky to buy today and why?",
        "Find undervalued Indian stocks with strong fundamentals, low debt, high ROE, and positive earnings growth.",
    ),
    "it_sector": (
        "Analyze the Indian IT sector ups and downs for the next 30 days.",
        "Compare TCS, INFY, WIPRO, HCLTECH, and TECHM. Which IT stock is best to buy now?",
        "Why are IT stocks rising or falling today? Analyze global tech demand, USD/INR, US recession risk, deal wins, and earnings.",
        "Suggest top IT sector stocks for short-term trading and long-term investment.",
    ),
    "mutual_funds": (
        "Suggest best mutual funds for SIP for a medium-risk investor with 5-year horizon.",
        "Compare large-cap, mid-cap, small-cap, flexi-cap, and index mutual funds for wealth creation.",
        "Build a mutual fund portfolio for INR 10,000 monthly SIP with low, medium, and high-risk options.",
        "Should I invest in index funds or actively managed mutual funds right now?",
        "Analyze my mutual fund portfolio and suggest rebalancing.",
    ),
    "portfolio_wealth": (
        "Create a diversified portfolio for INR 5 lakh with gold, stocks, mutual funds, ETFs, and debt funds.",
        "I have INR 1 lakh to invest. Suggest allocation for short-term, medium-term, and long-term wealth creation.",
        "Create a wealth plan to reach INR 1 crore in 10 years using SIP, stocks, gold, and ETFs.",
        "Suggest an investment strategy for low-risk monthly income.",
        "How should I rebalance my portfolio if stock market falls 10%?",
    ),
    "trading": (
        "Suggest intraday stocks to watch today with entry, stop loss, target 1, target 2, and risk-reward ratio.",
        "Analyze RELIANCE for swing trading using RSI, MACD, moving averages, volume, support, and resistance.",
        "Find stocks with breakout patterns and strong volume confirmation.",
        "Which NSE stocks are overbought or oversold today?",
    ),
    "news_market_intelligence": (
        "Analyze today's financial news and identify top bullish and bearish sectors.",
        "Analyze this news article and tell me its impact on gold, silver, crude oil, banking, IT, pharma, and auto stocks.",
        "Find hidden risks in today's market based on news, FII/DII activity, crude oil, USD/INR, and global markets.",
        "Give me top 10 market opportunities and top 10 market risks for this week.",
    ),
    "commodities_forex_crypto": (
        "Analyze USD/INR movement and its impact on gold, IT stocks, importers, and exporters.",
        "Compare crude oil, gold, silver, and equity markets. Which asset has better risk-reward now?",
        "Analyze Bitcoin and Ethereum trend with risk score and investment suitability.",
    ),
    "business_income": (
        "Suggest business ideas in India with low investment and high profit potential.",
        "Suggest passive income ideas based on INR 1 lakh, INR 5 lakh, and INR 10 lakh capital.",
        "How can I increase monthly income using investments, side business, and digital assets?",
        "Create a personal wealth dashboard prompt covering income, expenses, savings, debt, investments, and net worth.",
    ),
    "master": (
        "Act as an AI Investment Intelligence Platform for India. Analyze gold, silver, NSE stocks, BSE stocks, mutual funds, ETFs, commodities, IT sector, banking sector, pharma sector, auto sector, and macroeconomic indicators. Use realtime market data, financial news, sector trends, FII/DII activity, inflation, interest rates, USD/INR, crude oil, earnings, technical indicators, and risk analysis. Return asset name, predicted direction, buy probability, hold probability, sell probability, confidence score, predicted range, risk score, key reasons, research sources, and final recommendation.",
    ),
}


def prompt_categories() -> tuple[str, ...]:
    return tuple(PROMPT_CATEGORIES)


def prompts_for_category(category: str | None = None) -> dict[str, tuple[str, ...]]:
    if category is None:
        return PROMPT_CATEGORIES
    normalized = category.lower().strip()
    if normalized not in PROMPT_CATEGORIES:
        raise KeyError(normalized)
    return {normalized: PROMPT_CATEGORIES[normalized]}


def format_prompt_library(category: str | None = None) -> str:
    groups = prompts_for_category(category)
    lines: list[str] = ["Prompt Library:"]
    for group_name, prompts in groups.items():
        lines.extend(["", group_name.replace("_", " ").title() + ":"])
        lines.extend(f"{index}. {prompt}" for index, prompt in enumerate(prompts, start=1))
    return "\n".join(lines)
