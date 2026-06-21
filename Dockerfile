FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8765

WORKDIR /app

COPY pyproject.toml README.md ./
COPY market_agent ./market_agent
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 8765

CMD ["python", "-m", "market_agent.web"]
