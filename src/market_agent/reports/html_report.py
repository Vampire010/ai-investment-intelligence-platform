from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path("outputs/html_reports")


def save_html_report(result: dict[str, Any], report_kind: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    question = _question(result)
    filename = _slug(question or report_kind)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{timestamp}_{filename}.html"
    path.write_text(_render_html(result, report_kind), encoding="utf-8")
    return path.resolve()


def _render_html(result: dict[str, Any], report_kind: str) -> str:
    question = _question(result)
    body = _render_top_stocks(result) if report_kind == "top_stocks" else _render_category_or_single(result)
    evidence = _render_evidence(result, report_kind)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Investment Intelligence Platform</title>
  <style>
    :root {{
      --ink:#17202a; --muted:#5b6673; --line:#d8e0e8; --panel:#f7fafc;
      --green:#0f8b5f; --red:#c2413a; --amber:#b7791f; --blue:#2563eb;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; color:var(--ink); background:#eef3f7; }}
    .page {{ max-width:1180px; margin:0 auto; padding:28px; }}
    .hero {{ background:#0f766e; color:white; padding:24px 28px; border-radius:8px; }}
    .hero h1 {{ margin:0 0 8px; font-size:28px; }}
    .hero p {{ margin:0; font-size:15px; opacity:.95; }}
    .meta {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin:18px 0; }}
    .card {{ background:white; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .card h2 {{ margin:0 0 12px; font-size:18px; }}
    .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    .value {{ font-size:20px; font-weight:700; margin-top:4px; }}
    .grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:14px; }}
    .stock-grid {{ display:grid; grid-template-columns:1fr; gap:14px; }}
    .bar {{ height:10px; background:#e5eaf0; border-radius:999px; overflow:hidden; margin-top:8px; }}
    .fill {{ height:100%; background:var(--green); }}
    .fill.hold {{ background:var(--amber); }}
    .fill.sell {{ background:var(--red); }}
    .fill.risk {{ background:var(--blue); }}
    .metrics {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin-top:12px; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); padding:10px; border-radius:6px; }}
    ul {{ margin:8px 0 0 18px; padding:0; }}
    li {{ margin:4px 0; }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); }}
    th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:10px; vertical-align:top; }}
    th {{ background:#e0f2f1; }}
    a {{ color:#0f5eb8; }}
    .small {{ color:var(--muted); font-size:12px; }}
    @media (max-width:800px) {{ .meta,.grid,.metrics {{ grid-template-columns:1fr; }} .page {{ padding:14px; }} }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>AI Investment Intelligence Platform</h1>
      <p>{_esc(question)}</p>
    </section>
    <section class="meta">
      <div class="card"><div class="label">Generated</div><div class="value">{_esc(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div></div>
      <div class="card"><div class="label">Report Type</div><div class="value">{_esc(report_kind.replace("_", " ").title())}</div></div>
      <div class="card"><div class="label">Data Mode</div><div class="value">{_esc(_data_mode(result))}</div></div>
    </section>
    {body}
    {evidence}
  </div>
</body>
</html>"""


def _render_top_stocks(result: dict[str, Any]) -> str:
    rows = []
    cards = []
    for index, item in enumerate(result.get("top_buy_stocks", []), start=1):
        prediction = item["prediction"]
        signal = "Buy" if prediction["signal"] == "Buy" or prediction["buy_probability"] >= 50 else prediction["signal"]
        source_links = item.get("research_source_links") or _source_links_from_names(item.get("research_sources", []))
        rows.append(
            f"<tr><td>{index}</td><td>{_esc(prediction['instrument'])}</td><td>{_esc(signal)}</td>"
            f"<td>{prediction['buy_probability']}%</td><td>{prediction['confidence_score']}%</td>"
            f"<td>{prediction['risk_score']}%</td><td>{_source_links_html(source_links[:3])}</td></tr>"
        )
        cards.append(_prediction_card(prediction, f"{index}. {prediction['instrument']}", source_links, signal))
    return f"""
    <section class="card">
      <h2>Ranked Buy Candidates</h2>
      <table><thead><tr><th>Rank</th><th>Stock</th><th>Recommendation</th><th>Buy</th><th>Confidence</th><th>Risk</th><th>Sources</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>
    <section class="stock-grid" style="margin-top:14px;">{''.join(cards)}</section>
    """


def _render_category_or_single(result: dict[str, Any]) -> str:
    if "category_analysis" in result:
        profile = result["category_analysis"]
        return _category_card(profile)
    prediction = result.get("gold_prediction") or result.get("stock_prediction")
    if result.get("user_query", {}).get("instrument_type") == "stock":
        prediction = result["stock_prediction"]
    elif result.get("user_query", {}).get("instrument_type") == "gold":
        prediction = result["gold_prediction"]
    source_key = result.get("user_query", {}).get("instrument_type")
    sources = result.get("research_source_links_by_instrument", {}).get(
        source_key,
        result.get("research_source_links", _source_links_from_names(result.get("research_sources", []))),
    )
    return _prediction_card(prediction, prediction["instrument"], sources, prediction["signal"])


def _render_evidence(result: dict[str, Any], report_kind: str) -> str:
    if report_kind == "top_stocks" or "category_analysis" in result:
        return ""
    source_key = result.get("user_query", {}).get("instrument_type")
    evidence = result.get("news_evidence_by_instrument", {}).get(source_key, [])
    if not evidence:
        return ""
    rows = []
    for item in evidence[:6]:
        title = _esc(item.get("title", ""))
        source = _esc(item.get("source", ""))
        url = item.get("url", "")
        linked_title = (
            f"<a href='{_esc(url)}' target='_blank' rel='noopener noreferrer'>{title}</a>"
            if url
            else title
        )
        rows.append(
            "<tr>"
            f"<td>{source}<div class='small'>{_esc(item.get('published_at', ''))}</div></td>"
            f"<td>{linked_title}</td>"
            f"<td>{_esc(item.get('snippet', ''))}</td>"
            "</tr>"
        )
    return f"""
    <section class="card" style="margin-top:14px;">
      <h2>Realtime Article Evidence</h2>
      <table><thead><tr><th>Source</th><th>Article URL</th><th>Fetched Text Used</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>
    """


def _prediction_card(prediction: dict[str, Any], title: str, sources: list[Any] | tuple[Any, ...], signal: str) -> str:
    reasons = "".join(f"<li>{_esc(reason)}</li>" for reason in prediction.get("reasons", [])[:10])
    source_items = _source_items_html(sources[:8])
    history = _history_metrics_html(prediction.get("metadata", {}))
    institutional = _institutional_metrics_html(prediction.get("metadata", {}))
    return f"""
    <article class="card">
      <h2>{_esc(title)}</h2>
      <div class="grid">
        {_score_box("Buy Probability", prediction.get("buy_probability", 0), "fill")}
        {_score_box("Hold Probability", prediction.get("hold_probability", 0), "fill hold")}
        {_score_box("Sell Probability", prediction.get("sell_probability", 0), "fill sell")}
      </div>
      <div class="metrics">
        <div class="metric"><div class="label">Recommendation</div><b>{_esc(signal)}</b></div>
        <div class="metric"><div class="label">Confidence</div><b>{prediction.get('confidence_score', 0)}%</b></div>
        <div class="metric"><div class="label">Risk</div><b>{prediction.get('risk_score', 0)}%</b></div>
        <div class="metric"><div class="label">Range</div><b>{prediction.get('predicted_low', '')} - {prediction.get('predicted_high', '')} {_esc(prediction.get('metadata', {}).get('unit', ''))}</b></div>
      </div>
      <h2 style="margin-top:16px;">Reasons</h2>
      <ul>{reasons}</ul>
      {institutional}
      {history}
      <h2 style="margin-top:16px;">Research Sources</h2>
      <ul>{source_items}</ul>
    </article>"""


def _institutional_metrics_html(metadata: dict[str, Any]) -> str:
    report = metadata.get("institutional_report") or {}
    intraday = metadata.get("intraday_plan") or {}
    if not report and not intraday:
        return ""
    report_rows = []
    if report:
        rows = (
            ("Institutional View", report.get("view", "")),
            ("Source Coverage", report.get("coverage", "")),
            ("News Sentiment", report.get("news_sentiment", "")),
            ("News Impact", f"{report.get('news_impact_pct', 0)}%"),
            ("SEO Sentiment Score", report.get("seo_sentiment_score", "")),
            ("Keyword Categories", ", ".join(report.get("keyword_categories", []))),
            ("Top SEO Keywords", ", ".join(report.get("top_keywords", []))),
            ("Research Thesis", report.get("thesis", "")),
        )
        report_rows = [f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in rows if value != ""]
    intraday_rows = []
    if intraday:
        rows = (
            ("Bias", intraday.get("bias", "")),
            ("Entry Zone", intraday.get("entry_zone", "")),
            ("Target 1", intraday.get("target_1", "")),
            ("Target 2", intraday.get("target_2", "")),
            ("Stop Loss", intraday.get("stop_loss", "")),
            ("Invalidation", intraday.get("invalidation", "")),
            ("Risk Control", intraday.get("risk_note", "")),
        )
        intraday_rows = [f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in rows if value]
    report_table = (
        "<h2 style='margin-top:16px;'>Institutional Research Summary</h2>"
        f"<table><tbody>{''.join(report_rows)}</tbody></table>"
        if report_rows
        else ""
    )
    intraday_table = (
        "<h2 style='margin-top:16px;'>Intraday Trading Plan</h2>"
        f"<table><tbody>{''.join(intraday_rows)}</tbody></table>"
        if intraday_rows
        else ""
    )
    return f"{report_table}{intraday_table}"


def _history_metrics_html(metadata: dict[str, Any]) -> str:
    observed = (
        ("Current Observed Price", "current_observed_price", f" {_esc(metadata.get('profit_loss_unit', metadata.get('unit', '')))}"),
        ("Historical 30D Move", "historical_30d_change_pct", "%"),
        ("Historical Volatility", "historical_volatility_pct", "%"),
        ("Avg Daily Move", "avg_daily_move_pct", "%"),
        ("Best Daily Move", "best_daily_move_pct", "%"),
        ("Worst Daily Move", "worst_daily_move_pct", "%"),
    )
    forecast = (
        ("Forecast Entry Reference", "forecast_entry_reference", f" {_esc(metadata.get('profit_loss_unit', ''))}"),
        ("Forecast Upside Target", "forecast_target_price", f" {_esc(metadata.get('profit_loss_unit', ''))}"),
        ("Forecast Downside Guard", "forecast_downside_guard", f" {_esc(metadata.get('profit_loss_unit', ''))}"),
        ("Estimated Profit", "estimated_profit_pct", "%"),
        ("Estimated Loss", "estimated_loss_pct", "%"),
        ("Reward/Risk", "reward_risk_ratio", "x"),
    )
    observed_rows = []
    for label, key, suffix in observed:
        if key in metadata:
            observed_rows.append(f"<tr><td>{_esc(label)}</td><td>{_esc(metadata[key])}{suffix}</td></tr>")
    forecast_rows = []
    for label, key, suffix in forecast:
        if key in metadata:
            forecast_rows.append(f"<tr><td>{_esc(label)}</td><td>{_esc(metadata[key])}{suffix}</td></tr>")
    if not observed_rows and not forecast_rows:
        return ""
    basis = metadata.get("range_basis", "Future forecast only; current and historical prices are observed context.")
    observed_table = (
        f"<h2 style='margin-top:16px;'>Observed Current And Historical Context</h2>"
        f"<p class='small'>{_esc(basis)}</p>"
        f"<table><tbody>{''.join(observed_rows)}</tbody></table>"
        if observed_rows
        else ""
    )
    forecast_table = (
        f"<h2 style='margin-top:16px;'>Future Forecast Profit/Loss</h2>"
        f"<table><tbody>{''.join(forecast_rows)}</tbody></table>"
        if forecast_rows
        else ""
    )
    return f"""
      {observed_table}
      {forecast_table}
    """


def _category_card(profile: dict[str, Any]) -> str:
    reasons = "".join(f"<li>{_esc(reason)}</li>" for reason in profile.get("reasons", []))
    source_links = profile.get("research_source_links") or _source_links_from_names(profile.get("research_sources", []))
    sources = _source_items_html(source_links)
    allocation_rows = ""
    allocations = profile.get("allocations", ())
    if allocations:
        for row in allocations:
            name = row.get("category") or row.get("asset")
            allocation_rows += f"<tr><td>{_esc(name)}</td><td>{row.get('allocation_pct', '')}%</td><td>{_esc(row.get('purpose', ''))}</td></tr>"
    allocation_table = (
        f"<h2 style='margin-top:16px;'>Allocation</h2><table><thead><tr><th>Area</th><th>Allocation</th><th>Purpose</th></tr></thead><tbody>{allocation_rows}</tbody></table>"
        if allocation_rows
        else ""
    )
    agreement_rows = ""
    for row in profile.get("agreements", ()):
        agreement_rows += (
            "<tr>"
            f"<td>{_esc(row.get('name', ''))}</td>"
            f"<td>{_esc(row.get('status', ''))}<div class='small'>{_esc(row.get('date', ''))}</div></td>"
            f"<td>{_esc(row.get('coverage', ''))}</td>"
            f"<td>{_esc(row.get('impact', ''))}</td>"
            "</tr>"
        )
    agreement_table = (
        "<h2 style='margin-top:16px;'>Signed / Announced Agreements</h2>"
        "<table><thead><tr><th>Agreement</th><th>Status</th><th>Coverage</th><th>Why It Matters</th></tr></thead>"
        f"<tbody>{agreement_rows}</tbody></table>"
        if agreement_rows
        else ""
    )
    summary = (
        f"<p>{_esc(profile.get('summary', ''))}</p>"
        if profile.get("summary")
        else ""
    )
    analysis_tables = ""
    for section in profile.get("analysis_sections", ()):
        rows = ""
        for row in section.get("rows", ()):
            rows += (
                "<tr>"
                f"<td>{_esc(row.get('metric', ''))}</td>"
                f"<td>{_esc(row.get('value', ''))}</td>"
                f"<td>{_esc(row.get('interpretation', ''))}</td>"
                "</tr>"
            )
        if rows:
            analysis_tables += (
                f"<h2 style='margin-top:16px;'>{_esc(section.get('title', 'Analysis'))}</h2>"
                "<table><thead><tr><th>Metric</th><th>Value / Dataset</th><th>Interpretation</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )
    news_context = profile.get("news_context") or {}
    news_table = ""
    if news_context:
        news_rows = (
            ("Articles Checked", news_context.get("article_count", 0)),
            ("Sentiment", f"{news_context.get('sentiment', '')} ({news_context.get('sentiment_score', 0)})"),
            ("Impact Score", f"{news_context.get('impact_score_pct', 0)}%"),
            ("Topics", ", ".join(news_context.get("topics", []))),
            ("SEO Keyword Categories", ", ".join(news_context.get("keyword_categories", []))),
            ("Keyword Hits", ", ".join(news_context.get("keyword_hits", [])[:10])),
            ("Anomaly Flags", ", ".join(news_context.get("anomaly_flags", []))),
        )
        rows = "".join(f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td></tr>" for label, value in news_rows if value != "")
        news_table = f"<h2 style='margin-top:16px;'>Realtime News Feed Analysis</h2><table><tbody>{rows}</tbody></table>"
    evidence_rows = ""
    for item in profile.get("news_evidence", ()):
        title = _esc(item.get("title", ""))
        url = item.get("url", "")
        linked_title = f"<a href='{_esc(url)}' target='_blank' rel='noopener noreferrer'>{title}</a>" if url else title
        evidence_rows += (
            "<tr>"
            f"<td>{_esc(item.get('source', ''))}<div class='small'>{_esc(item.get('published_at', ''))}</div></td>"
            f"<td>{linked_title}</td>"
            f"<td>{_esc(item.get('snippet', ''))}</td>"
            "</tr>"
        )
    evidence_table = (
        "<h2 style='margin-top:16px;'>News Feed Evidence</h2>"
        "<table><thead><tr><th>Source</th><th>Article URL</th><th>Fetched Text Used</th></tr></thead>"
        f"<tbody>{evidence_rows}</tbody></table>"
        if evidence_rows
        else ""
    )
    return f"""
    <section class="card">
      <h2>{_esc(profile.get('title', 'Financial Report'))}</h2>
      {summary}
      <div class="grid">
        {_score_box("Buy", profile.get("buy_probability", 0), "fill")}
        {_score_box("Hold", profile.get("hold_probability", 0), "fill hold")}
        {_score_box("Sell", profile.get("sell_probability", 0), "fill sell")}
      </div>
      <div class="metrics">
        <div class="metric"><div class="label">Signal</div><b>{_esc(profile.get('signal', ''))}</b></div>
        <div class="metric"><div class="label">Confidence</div><b>{profile.get('confidence_score', 0)}%</b></div>
        <div class="metric"><div class="label">Risk</div><b>{profile.get('risk_score', 0)}%</b></div>
        <div class="metric"><div class="label">Range</div><b>{_esc(profile.get('predicted_range', 'Not applicable'))}</b></div>
      </div>
      {allocation_table}
      {agreement_table}
      {analysis_tables}
      {news_table}
      {evidence_table}
      <h2 style="margin-top:16px;">Reasons</h2><ul>{reasons}</ul>
      <h2 style="margin-top:16px;">Research Sources</h2><ul>{sources}</ul>
    </section>"""


def _score_box(label: str, value: int | float, fill_class: str) -> str:
    value = max(0, min(100, int(value or 0)))
    return f"<div><div class='label'>{_esc(label)}</div><div class='value'>{value}%</div><div class='bar'><div class='{fill_class}' style='width:{value}%'></div></div></div>"


def _source_links_from_names(sources: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    return [{"source": source, "url": ""} for source in sources]


def _source_items_html(sources: list[Any] | tuple[Any, ...]) -> str:
    return "".join(f"<li>{_source_link_html(source)}</li>" for source in sources)


def _source_links_html(sources: list[Any] | tuple[Any, ...]) -> str:
    return "<br>".join(_source_link_html(source) for source in sources)


def _source_link_html(source: Any) -> str:
    if isinstance(source, dict):
        name = source.get("source", "")
        url = source.get("url", "")
    else:
        name = str(source)
        url = ""
    if url:
        return f"<a href='{_esc(url)}' target='_blank' rel='noopener noreferrer'>{_esc(name)}</a>"
    return _esc(name)


def _question(result: dict[str, Any]) -> str:
    return result.get("user_query", {}).get("text") or result.get("user_query", {}).get("text", "Market report")


def _data_mode(result: dict[str, Any]) -> str:
    mode = result.get("user_query", {}).get("data_source")
    if mode == "realtime":
        return "Realtime market/news feeds"
    return "Realtime market/news feeds"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:80] or "market_report"


def _esc(value: Any) -> str:
    return html.escape(str(value))
