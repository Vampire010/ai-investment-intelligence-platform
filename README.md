# Make Me Rich Agent

Prototype AI/ML market analysis agent for India, based on the attached requirement PDF.

The agent analyzes:

- Indian economic indicators such as inflation, RBI rates, INR/USD, GDP, FII/DII flow, import duty, and crude oil.
- Gold factors including domestic demand, festival season, geopolitical tension, international gold movement, and INR impact.
- Indian stock factors including Nifty/Sensex trend, sector strength, earnings sentiment, volatility, and institutional activity.
- News intelligence using lightweight NLP sentiment, topic, entity, impact, and anomaly detection.

It currently runs offline with realistic sample data and exposes clean extension points for real NSE, BSE, RBI, SEBI, commodity, and news APIs.

## Run

```powershell
python -m market_agent.cli --stock RELIANCE --format text
```

JSON output:

```powershell
python -m market_agent.cli --stock RELIANCE --format json
```

## Test

```powershell
python -m unittest discover -s tests
```

## Project Structure

- `src/market_agent/models.py` - core data models.
- `src/market_agent/data_sources.py` - data-source contracts and sample Indian market data.
- `src/market_agent/nlp.py` - sentiment, topic, entity, and news impact analysis.
- `src/market_agent/predictors.py` - gold and stock prediction engines.
- `src/market_agent/agent.py` - orchestration layer.
- `src/market_agent/cli.py` - command-line interface.

## Next Production Steps

1. Add authenticated connectors for live market and macroeconomic data.
2. Persist raw and normalized data in a database or lakehouse.
3. Replace heuristic predictors with trained LSTM/GRU/XGBoost/Prophet ensemble models.
4. Add scheduled retraining and real-time alert delivery.
5. Add dashboards for trend visualizations and explainable AI output.
