const promptInput = document.querySelector("#prompt");
const analyzeBtn = document.querySelector("#analyzeBtn");
const cancelBtn = document.querySelector("#cancelBtn");
const clearBtn = document.querySelector("#clearBtn");
const clearRecentBtn = document.querySelector("#clearRecentBtn");
const recentToggleBtn = document.querySelector("#recentToggleBtn");
const recentMenu = document.querySelector("#recentMenu");
const statusEl = document.querySelector("#status");
const resultPanel = document.querySelector("#resultPanel");
const reportState = document.querySelector("#reportState");
const recentPromptsEl = document.querySelector("#recentPrompts");

const fields = {
  signal: document.querySelector("#signal"),
  direction: document.querySelector("#direction"),
  risk: document.querySelector("#risk"),
  range: document.querySelector("#range"),
  buyText: document.querySelector("#buyText"),
  holdText: document.querySelector("#holdText"),
  sellText: document.querySelector("#sellText"),
  buyBar: document.querySelector("#buyBar"),
  holdBar: document.querySelector("#holdBar"),
  sellBar: document.querySelector("#sellBar"),
};

let activeRequest = null;
const RECENT_PROMPTS_KEY = "ai-investment-recent-prompts";

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    promptInput.value = button.dataset.prompt;
    promptInput.focus();
  });
});

analyzeBtn.addEventListener("click", runAnalysis);
cancelBtn.addEventListener("click", cancelAnalysis);
clearBtn.addEventListener("click", clearPrompt);
clearRecentBtn.addEventListener("click", clearRecentPrompts);
recentToggleBtn.addEventListener("click", toggleRecentMenu);
promptInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    runAnalysis();
  }
});

async function runAnalysis() {
  const prompt = promptInput.value.trim();
  if (!prompt) {
    setStatus("Enter Prompt");
    return;
  }
  if (activeRequest) {
    activeRequest.abort();
  }
  const controller = new AbortController();
  activeRequest = controller;
  setLoading(true);
  setStatus("Analyzing");
  resetMetrics();
  showPanelMessage("Analyzing realtime feeds and building the result...");
  reportState.textContent = "Working";
  try {
    saveRecentPrompt(prompt);
    const payload = await requestAnalysis(prompt, controller.signal);
    renderResult(payload);
    setStatus("Complete");
    reportState.textContent = "Rendered";
  } catch (error) {
    if (error.name === "AbortError") {
      setStatus("Cancelled");
      showPanelMessage("Analysis cancelled.");
      reportState.textContent = "Cancelled";
    } else {
      const fallback = {
        ok: true,
        query: { text: prompt, perspective: "connection_status" },
        analysis: clientStatusAnalysis("The browser could not receive the live API result. Restart the web app server and run the prompt again."),
        summary: {
          signal: "Hold",
          direction: "Waiting For Server",
          risk_score: "100%",
          predicted_range: "Not calculated",
          buy_probability: "0%",
          hold_probability: "100%",
          sell_probability: "0%",
        },
        text: "",
      };
      renderResult(fallback);
      setStatus("Ready");
      reportState.textContent = "Rendered";
    }
  } finally {
    if (activeRequest === controller) {
      activeRequest = null;
      setLoading(false);
    }
  }
}

async function requestAnalysis(prompt, signal) {
  const requestBody = JSON.stringify({ prompt, no_prompt_training: true });
  try {
    return await postAnalysis(requestBody, signal);
  } catch (error) {
    if (error.name === "AbortError") {
      throw error;
    }
    await wait(900, signal);
    return postAnalysis(requestBody, signal);
  }
}

async function postAnalysis(requestBody, signal) {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: requestBody,
  });
  const payload = await safeJson(response);
  if ((!response.ok || payload.ok === false) && !payload.analysis) {
    throw new Error(payload.error || "Analysis failed");
  }
  return payload;
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {
      ok: true,
      query: { text: promptInput.value.trim(), perspective: "connection_status" },
      analysis: clientStatusAnalysis("The server response was not JSON. Restart the web app and run the prompt again."),
      summary: {
        signal: "Hold",
        direction: "Waiting For Server",
        risk_score: "100%",
        predicted_range: "Not calculated",
        buy_probability: "0%",
        hold_probability: "100%",
        sell_probability: "0%",
      },
      text: "",
    };
  }
}

function clientStatusAnalysis(reason) {
  return {
    category_analysis: {
      title: "Live API Connection Status",
      direction: "Waiting For Server",
      signal: "Hold",
      buy_probability: 0,
      hold_probability: 100,
      sell_probability: 0,
      confidence_score: 0,
      predicted_range: "Not calculated",
      risk_score: 100,
      reasons: [
        reason,
        "This panel renders the structured API data directly in the UI.",
        "Use Ctrl+C in the PowerShell server window, then start again with: python -m market_agent.web --host 127.0.0.1 --port 8765",
      ],
      research_source_links: [],
    },
  };
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

function cancelAnalysis() {
  if (!activeRequest) return;
  activeRequest.abort();
}

function clearPrompt() {
  if (activeRequest) {
    activeRequest.abort();
  }
  promptInput.value = "";
  promptInput.focus();
  resetResults();
  setStatus("Ready");
}

function toggleRecentMenu() {
  const isOpen = recentMenu.classList.toggle("open");
  recentToggleBtn.setAttribute("aria-expanded", String(isOpen));
}

function saveRecentPrompt(prompt) {
  const items = loadRecentPrompts().filter((item) => item.toLowerCase() !== prompt.toLowerCase());
  items.unshift(prompt);
  localStorage.setItem(RECENT_PROMPTS_KEY, JSON.stringify(items.slice(0, 12)));
  renderRecentPrompts();
}

function loadRecentPrompts() {
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_PROMPTS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string" && item.trim()) : [];
  } catch {
    return [];
  }
}

function clearRecentPrompts() {
  localStorage.removeItem(RECENT_PROMPTS_KEY);
  renderRecentPrompts();
}

function renderRecentPrompts() {
  const prompts = loadRecentPrompts();
  if (!prompts.length) {
    recentPromptsEl.innerHTML = `<p class="recent-empty">No recent prompts yet.</p>`;
    return;
  }
  recentPromptsEl.innerHTML = prompts
    .map((prompt) => `<button type="button" class="recent-item" data-recent-prompt="${escapeAttr(prompt)}">${escapeHtml(prompt)}</button>`)
    .join("");
  recentPromptsEl.querySelectorAll("[data-recent-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      promptInput.value = button.dataset.recentPrompt;
      promptInput.focus();
      recentMenu.classList.remove("open");
      recentToggleBtn.setAttribute("aria-expanded", "false");
    });
  });
}

function renderResult(payload) {
  const summary = payload.summary || {};
  const analysis = payload.analysis || {};
  fields.signal.textContent = summary.signal || "-";
  fields.direction.textContent = summary.direction || "-";
  fields.risk.textContent = summary.risk_score || "-";
  fields.range.textContent = summary.predicted_range || "-";
  setPercent("buy", summary.buy_probability);
  setPercent("hold", summary.hold_probability);
  setPercent("sell", summary.sell_probability);

  const question = payload.query?.text || promptInput.value.trim();
  resultPanel.innerHTML = [
    heroHtml(question, payload.query),
    resultBodyHtml(analysis, payload.text),
  ].join("");
}

function resultBodyHtml(analysis, text) {
  if (analysis.top_buy_stocks) {
    return topStocksHtml(analysis);
  }
  if (analysis.category_analysis) {
    return categoryHtml(analysis.category_analysis);
  }
  const query = analysis.user_query || {};
  const prediction =
    query.instrument_type === "stock"
      ? analysis.stock_prediction
      : query.instrument_type === "gold"
        ? analysis.gold_prediction
        : analysis.gold_prediction || analysis.stock_prediction;
  if (prediction) {
    const sourceKey = query.instrument_type || "gold";
    const sources =
      analysis.research_source_links_by_instrument?.[sourceKey] ||
      analysis.research_source_links ||
      sourceLinksFromNames(analysis.research_sources || []);
    const evidence = analysis.news_evidence_by_instrument?.[sourceKey] || [];
    return predictionHtml(prediction, prediction.instrument, sources, evidence);
  }
  return textFallbackHtml(text);
}

function heroHtml(question, query) {
  const type = query?.perspective || query?.instrument_type || "investment";
  return `
    <section class="result-hero">
      <p class="eyebrow">Direct UI result</p>
      <h3>${escapeHtml(question || "Investment research request")}</h3>
      <div class="result-meta">
        <span>${escapeHtml(String(type).replaceAll("_", " "))}</span>
        <span>Realtime data workflow</span>
      </div>
    </section>`;
}

function topStocksHtml(analysis) {
  const stocks = analysis.top_buy_stocks || [];
  const rows = stocks
    .map((item, index) => {
      const prediction = item.prediction || {};
      return `
        <tr>
          <td>${index + 1}</td>
          <td>${escapeHtml(prediction.instrument || "-")}</td>
          <td>${escapeHtml(prediction.signal || "Buy")}</td>
          <td>${percentText(prediction.buy_probability)}</td>
          <td>${percentText(prediction.confidence_score)}</td>
          <td>${percentText(prediction.risk_score)}</td>
          <td>${sourceLinksHtml((item.research_source_links || []).slice(0, 3))}</td>
        </tr>`;
    })
    .join("");
  const cards = stocks
    .map((item, index) =>
      predictionHtml(
        item.prediction || {},
        `${index + 1}. ${(item.prediction || {}).instrument || "Stock"}`,
        item.research_source_links || [],
        []
      )
    )
    .join("");
  return `
    <section class="result-card">
      <h3>Ranked Buy Candidates</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Rank</th><th>Stock</th><th>Signal</th><th>Buy</th><th>Confidence</th><th>Risk</th><th>Sources</th></tr></thead>
          <tbody>${rows || emptyRow(7)}</tbody>
        </table>
      </div>
    </section>
    <div class="stack">${cards}</div>`;
}

function categoryHtml(profile) {
  const valueLabel = profile.actual_value ? "Actual Value" : "Range";
  const allocations = tableFromRows(
    ["Area", "Allocation", "Purpose"],
    (profile.allocations || []).map((row) => [
      row.category || row.asset || "",
      row.allocation_pct ? `${row.allocation_pct}%` : "",
      row.purpose || "",
    ])
  );
  const agreements = tableFromRows(
    ["Agreement", "Status", "Coverage", "Why It Matters"],
    (profile.agreements || []).map((row) => [
      row.name || "",
      [row.status, row.date].filter(Boolean).join(" | "),
      row.coverage || "",
      row.impact || "",
    ])
  );
  const analysisSections = (profile.analysis_sections || [])
    .map((section) =>
      sectionHtml(
        section.title || "Analysis",
        tableFromRows(
          ["Metric", "Value / Dataset", "Interpretation"],
          (section.rows || []).map((row) => [row.metric || "", row.value || "", row.interpretation || ""])
        )
      )
    )
    .join("");
  return `
    <section class="result-card">
      <h3>${escapeHtml(profile.title || "Financial Report")}</h3>
      ${profile.summary ? `<p>${escapeHtml(profile.summary)}</p>` : ""}
      ${scoreGridHtml(profile)}
      ${metricGridHtml([
        ["Signal", profile.signal || "-"],
        ["Confidence", percentText(profile.confidence_score)],
        ["Risk", percentText(profile.risk_score)],
        [valueLabel, profile.actual_value || profile.predicted_range || "Not applicable"],
      ])}
      ${allocations ? sectionHtml("Allocation", allocations) : ""}
      ${agreements ? sectionHtml("Signed / Announced Agreements", agreements) : ""}
      ${analysisSections}
      ${newsContextHtml(profile.news_context)}
      ${evidenceHtml(profile.news_evidence || [])}
      ${listSectionHtml("Reasons", profile.reasons || [])}
      ${sourceSectionHtml(profile.research_source_links || sourceLinksFromNames(profile.research_sources || []))}
    </section>`;
}

function predictionHtml(prediction, title, sources, evidence) {
  const metadata = prediction.metadata || {};
  return `
    <section class="result-card">
      <h3>${escapeHtml(title || prediction.instrument || "Prediction")}</h3>
      ${scoreGridHtml(prediction)}
      ${metricGridHtml([
        ["Signal", prediction.signal || "-"],
        ["Confidence", percentText(prediction.confidence_score)],
        ["Risk", percentText(prediction.risk_score)],
        ["Range", predictionRange(prediction)],
      ])}
      ${institutionalHtml(metadata)}
      ${historyHtml(metadata)}
      ${listSectionHtml("Reasons", prediction.reasons || [])}
      ${sourceSectionHtml(sources)}
      ${evidenceHtml(evidence)}
    </section>`;
}

function scoreGridHtml(source) {
  return `
    <div class="score-grid">
      ${scoreBoxHtml("Buy", source.buy_probability, "buy")}
      ${scoreBoxHtml("Hold", source.hold_probability, "hold")}
      ${scoreBoxHtml("Sell", source.sell_probability, "sell")}
    </div>`;
}

function scoreBoxHtml(label, value, kind) {
  const percent = parsePercent(value);
  return `
    <div class="score-box">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${percent}%</div>
      <div class="bar"><div class="fill ${kind}" style="width:${percent}%"></div></div>
    </div>`;
}

function metricGridHtml(rows) {
  return `
    <div class="metric-grid">
      ${rows
        .map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
        .join("")}
    </div>`;
}

function institutionalHtml(metadata) {
  const report = metadata.institutional_report || {};
  const intraday = metadata.intraday_plan || {};
  const reportTable = tableFromPairs([
    ["Institutional View", report.view],
    ["Source Coverage", report.coverage],
    ["News Sentiment", report.news_sentiment],
    ["News Impact", report.news_impact_pct ? `${report.news_impact_pct}%` : ""],
    ["SEO Sentiment Score", report.seo_sentiment_score],
    ["Keyword Categories", (report.keyword_categories || []).join(", ")],
    ["Top SEO Keywords", (report.top_keywords || []).join(", ")],
    ["Research Thesis", report.thesis],
  ]);
  const intradayTable = tableFromPairs([
    ["Bias", intraday.bias],
    ["Entry Zone", intraday.entry_zone],
    ["Target 1", intraday.target_1],
    ["Target 2", intraday.target_2],
    ["Stop Loss", intraday.stop_loss],
    ["Invalidation", intraday.invalidation],
    ["Risk Control", intraday.risk_note],
  ]);
  return [
    reportTable ? sectionHtml("Institutional Research Summary", reportTable) : "",
    intradayTable ? sectionHtml("Intraday Trading Plan", intradayTable) : "",
  ].join("");
}

function historyHtml(metadata) {
  const observed = tableFromPairs([
    ["Current Observed Price", appendUnit(metadata.current_observed_price, metadata.profit_loss_unit || metadata.unit)],
    ["Historical 30D Move", appendUnit(metadata.historical_30d_change_pct, "%")],
    ["Historical Volatility", appendUnit(metadata.historical_volatility_pct, "%")],
    ["Avg Daily Move", appendUnit(metadata.avg_daily_move_pct, "%")],
    ["Best Daily Move", appendUnit(metadata.best_daily_move_pct, "%")],
    ["Worst Daily Move", appendUnit(metadata.worst_daily_move_pct, "%")],
  ]);
  const forecast = tableFromPairs([
    ["Forecast Entry Reference", appendUnit(metadata.forecast_entry_reference, metadata.profit_loss_unit)],
    ["Forecast Upside Target", appendUnit(metadata.forecast_target_price, metadata.profit_loss_unit)],
    ["Forecast Downside Guard", appendUnit(metadata.forecast_downside_guard, metadata.profit_loss_unit)],
    ["Estimated Profit", appendUnit(metadata.estimated_profit_pct, "%")],
    ["Estimated Loss", appendUnit(metadata.estimated_loss_pct, "%")],
    ["Reward/Risk", appendUnit(metadata.reward_risk_ratio, "x")],
  ]);
  const basis = metadata.range_basis || "Future forecast only; current and historical prices are observed context.";
  return [
    observed ? sectionHtml("Observed Current And Historical Context", `<p class="small">${escapeHtml(basis)}</p>${observed}`) : "",
    forecast ? sectionHtml("Future Forecast Profit/Loss", forecast) : "",
  ].join("");
}

function newsContextHtml(context) {
  if (!context) return "";
  const table = tableFromPairs([
    ["Articles Checked", context.article_count],
    ["Sentiment", [context.sentiment, context.sentiment_score].filter((value) => value !== undefined && value !== "").join(" ")],
    ["Impact Score", appendUnit(context.impact_score_pct, "%")],
    ["Topics", (context.topics || []).join(", ")],
    ["SEO Keyword Categories", (context.keyword_categories || []).join(", ")],
    ["Keyword Hits", (context.keyword_hits || []).slice(0, 10).join(", ")],
    ["Anomaly Flags", (context.anomaly_flags || []).join(", ")],
  ]);
  return table ? sectionHtml("Realtime News Feed Analysis", table) : "";
}

function evidenceHtml(items) {
  const rows = (items || []).map((item) => [
    [item.source, item.published_at].filter(Boolean).join(" | "),
    item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title || item.url)}</a>` : escapeHtml(item.title || ""),
    escapeHtml(item.snippet || ""),
  ]);
  const table = tableFromRows(["Source", "Article URL", "Fetched Text Used"], rows, true);
  return table ? sectionHtml("News Feed Evidence", table) : "";
}

function listSectionHtml(title, items) {
  if (!items || !items.length) return "";
  return sectionHtml(title, `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
}

function sourceSectionHtml(sources) {
  if (!sources || !sources.length) return "";
  return sectionHtml("Research Sources", `<ul>${sources.map((source) => `<li>${sourceLinkHtml(source)}</li>`).join("")}</ul>`);
}

function sectionHtml(title, content) {
  if (!content) return "";
  return `<section class="result-section"><h4>${escapeHtml(title)}</h4>${content}</section>`;
}

function tableFromPairs(pairs) {
  const rows = pairs
    .filter(([, value]) => value !== undefined && value !== null && String(value) !== "")
    .map(([label, value]) => [label, value]);
  return tableFromRows(["Metric", "Value"], rows);
}

function tableFromRows(headers, rows, rowsAreHtml = false) {
  const filtered = rows.filter((row) => row.some((value) => value !== undefined && value !== null && String(value) !== ""));
  if (!filtered.length) return "";
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${filtered
            .map(
              (row) =>
                `<tr>${row
                  .map((value) => `<td>${rowsAreHtml ? String(value) : escapeHtml(value)}</td>`)
                  .join("")}</tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function textFallbackHtml(text) {
  return `
    <section class="result-card">
      <h3>Analysis Result</h3>
      <pre>${escapeHtml(text || "No structured result returned.")}</pre>
    </section>`;
}

function emptyRow(columns) {
  return `<tr><td colspan="${columns}">No records returned.</td></tr>`;
}

function predictionRange(prediction) {
  if (prediction.predicted_low !== undefined && prediction.predicted_high !== undefined) {
    return `${prediction.predicted_low} - ${prediction.predicted_high} ${prediction.metadata?.unit || ""}`.trim();
  }
  return prediction.predicted_range || "-";
}

function appendUnit(value, unit) {
  if (value === undefined || value === null || String(value) === "") return "";
  return `${value}${unit ? ` ${unit}` : ""}`;
}

function sourceLinksFromNames(sources) {
  return sources.map((source) => ({ source, url: "" }));
}

function sourceLinksHtml(sources) {
  if (!sources || !sources.length) return "-";
  return sources.map(sourceLinkHtml).join("<br>");
}

function sourceLinkHtml(source) {
  const name = typeof source === "object" && source !== null ? source.source || source.url || "" : String(source || "");
  const url = typeof source === "object" && source !== null ? source.url || "" : "";
  if (url) {
    return `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(name)}</a>`;
  }
  return escapeHtml(name);
}

function setPercent(kind, rawValue) {
  const value = parsePercent(rawValue);
  fields[`${kind}Text`].textContent = `${value}%`;
  fields[`${kind}Bar`].style.width = `${value}%`;
}

function percentText(rawValue) {
  if (rawValue === undefined || rawValue === null || rawValue === "") return "-";
  return `${parsePercent(rawValue)}%`;
}

function parsePercent(rawValue) {
  if (rawValue === undefined || rawValue === null || rawValue === "") return 0;
  const match = String(rawValue).match(/-?\d+(\.\d+)?/);
  if (!match) return 0;
  return Math.max(0, Math.min(100, Math.round(Number(match[0]))));
}

function setLoading(isLoading) {
  analyzeBtn.disabled = isLoading;
  cancelBtn.disabled = !isLoading;
  clearBtn.disabled = false;
  analyzeBtn.textContent = isLoading ? "Analyzing..." : "Analyze";
}

function resetResults() {
  resetMetrics();
  showPanelMessage("Run a prompt to render the analysis directly in this panel.");
  reportState.textContent = "No result yet";
}

function resetMetrics() {
  fields.signal.textContent = "-";
  fields.direction.textContent = "-";
  fields.risk.textContent = "-";
  fields.range.textContent = "-";
  setPercent("buy", 0);
  setPercent("hold", 0);
  setPercent("sell", 0);
}

function setStatus(text) {
  statusEl.textContent = text;
  statusEl.style.background = "#d8f5ef";
  statusEl.style.color = "#063b35";
}

function showPanelMessage(message) {
  resultPanel.innerHTML = `<div class="panel-message">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

resetResults();
renderRecentPrompts();
