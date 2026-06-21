# AI Investment Intelligence Platform

AI Investment Intelligence Platform is a Python web and CLI application for Indian market research, realtime investment analysis, and risk-aware buy/hold/sell decision support. It analyzes gold, silver, NSE/BSE stocks, mutual funds, portfolio goals, macro risks, treaty/news impact, and sector trends using public realtime market data and trusted financial news feeds.

> This project is research software. It is not financial advice, and future market prices are estimates, not guarantees.

## Features

- Realtime prompt-driven investment analysis for gold, silver, stocks, mutual funds, SIPs, ETFs, IPOs, real estate, technology themes, forex, and macro/geopolitical risk.
- Direct actual-price handling for current and historical gold/silver prompts.
- Future-date forecasting with predicted range, buy/hold/sell probabilities, risk score, and confidence score.
- Intraday and top-stock screening across an NSE watchlist.
- Trusted-source news ingestion, SEO keyword sentiment analysis, and article evidence tables.
- Dependency-free local web app with live result rendering, probability bars, source links, and recent prompt menu.
- CLI for prompt search, prompt-dataset enrichment, regression validation, and workbook/report utilities.
- CI, Docker, Render, Railway, and Fly.io deployment configuration.

## Technology Stack

- Python 3.10+
- Standard-library HTTP server
- Public market/news data sources:
  - Groww gold and silver rate pages for current precious-metal rates
  - Yahoo Finance chart endpoints for stocks, indexes, forex, commodities, and historical fallback
  - Google News RSS, trusted financial RSS feeds, official policy pages, and curated source master data
- Vanilla HTML, CSS, and JavaScript frontend
- Python `unittest`
- GitHub Actions
- Docker

## Project Structure

```text
src/market_agent/core/          Core models and data-source contracts
src/market_agent/data/          Realtime market/news integrations
src/market_agent/intelligence/  NLP, SEO sentiment, and prediction engines
src/market_agent/interfaces/    Prompt parsing and query interpretation
src/market_agent/prompts/       Prompt library and JSONL prompt dataset tools
src/market_agent/resources/     Trusted source and SEO keyword resources
src/market_agent/services/      Analysis orchestration
src/market_agent/web.py         Web application server
src/market_agent/web_static/    Browser UI, robots.txt, sitemap.xml
tests/                          Unit, regression, and optional realtime user tests
tools/                          Workbook and validation report utilities
```

## Installation

```powershell
git clone <repository-url>
cd MakeMeRichApp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

On Linux/macOS:

```bash
git clone <repository-url>
cd MakeMeRichApp
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Local Development

Run the web app:

```powershell
python -m market_agent.web --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Run the CLI:

```powershell
python -m market_agent.cli --query "what will be gold price on 22 June 2026" --data-source realtime --format text
python -m market_agent.cli --query "Which intraday stock I can buy on 22 June" --data-source realtime --format text
python -m market_agent.cli --query "current silver price today" --data-source realtime --format text
```

## Build And Test

No frontend build step is required because the UI is vanilla HTML/CSS/JS.

Run tests:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests
```

Run optional realtime user tests:

```powershell
$env:RUN_USER_TESTS='1'
python -m unittest discover -s tests\user_test
```

Build Docker image:

```powershell
docker build -t ai-investment-intelligence-platform .
docker run --rm -p 8765:8765 -e HOST=0.0.0.0 -e PORT=8765 ai-investment-intelligence-platform
```

## Deployment

### GitHub Actions

The repository includes:

- `.github/workflows/ci.yml`: installs the package, runs Python tests, and checks JavaScript syntax.
- `.github/workflows/deployment-check.yml`: starts the web app and validates `/`, `/api/health`, `/robots.txt`, and `/sitemap.xml`.

These workflows run on pushes to `main`.

### GitHub Pages

GitHub Pages is not suitable for the live application because the app requires a Python backend for realtime market/news retrieval. A static landing page can be added later under a separate `docs/` folder if you want a GitHub Pages marketing site.

### Render

The repository includes `render.yaml`.

1. Push the repository to GitHub.
2. In Render, create a new Blueprint from the repository.
3. Render will build from `Dockerfile`.
4. Health check path: `/api/health`.

### Railway

The repository includes `railway.json`.

1. Create a Railway project from the GitHub repository.
2. Use Dockerfile deployment.
3. Set environment variables as needed.
4. Health check path: `/api/health`.

### Fly.io

The repository includes `fly.toml`.

```powershell
fly launch --no-deploy
fly deploy
```

### Generic Docker Hosting

```powershell
docker build -t ai-investment-intelligence-platform .
docker run -p 8765:8765 -e HOST=0.0.0.0 -e PORT=8765 ai-investment-intelligence-platform
```

## Environment Variables

```text
HOST=0.0.0.0
PORT=8765
CORS_ALLOW_ORIGIN=*
RUN_USER_TESTS=0
INDIAN_INVESTMENT_PROMPTS_JSONL=<optional path to prompt dataset>
```

No API keys are required for the current public-source prototype. For production, replace public endpoints with licensed market-data providers and store secrets using the deployment platform's secret manager.

## Post-Deployment Validation

After deployment, validate:

- Home page loads.
- `/api/health` returns `{"ok": true, ...}`.
- `/robots.txt` and `/sitemap.xml` are accessible.
- Prompt submission renders a live analysis result.
- Gold/silver current-day prompts return actual values, not predictions.
- Future-date prompts return predictive estimates with risk/confidence labels.
- Mobile layout is usable.
- Browser console has no JavaScript errors.
- GitHub Actions workflows are green.

## Production Notes

- Public endpoints can rate-limit or change markup. Use licensed feeds for production trading workflows.
- Keep generated files in `outputs/`; this directory is intentionally ignored by Git.
- Never commit `.env` files or large private prompt datasets.
- Review CORS before deploying a separate frontend domain.
- Add observability, request logging, persistence, authentication, and error monitoring before exposing this as a public product.

## License

MIT License. See [LICENSE](LICENSE).
