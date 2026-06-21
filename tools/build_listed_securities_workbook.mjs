import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("outputs", "listed_securities");
const outputPath = path.join(outputDir, "india_listed_securities_nse_bse_sebi.xlsx");

const nseUrl = "https://archives.nseindia.com/content/equities/EQUITY_L.csv";
const bseUrl =
  "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active";

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const [nseText, bseRows] = await Promise.all([fetchText(nseUrl), fetchBseJson()]);

  const nseRows = parseCsv(nseText).map((row) => ({
    exchange: "NSE",
    companyName: clean(row["NAME OF COMPANY"]),
    stockSymbol: clean(row.SYMBOL),
    nseCode: clean(row.SYMBOL),
    bseCode: "",
    industrySector: "",
    marketCapInrCrore: "",
    sebiRegistrationDetails:
      "Not applicable for ordinary listed equity issuer; issuer/listing governed by SEBI regulations",
    isin: clean(row["ISIN NUMBER"]),
    listingDate: clean(row["DATE OF LISTING"]),
    faceValue: numberOrText(row["FACE VALUE"]),
    status: "Listed",
    bseGroup: "",
    sourceUrl: nseUrl,
  }));

  const bseNormalized = bseRows.map((row) => ({
    exchange: "BSE",
    companyName: clean(row.Issuer_Name || row.Scrip_Name),
    stockSymbol: clean(row.scrip_id),
    nseCode: "",
    bseCode: clean(row.SCRIP_CD),
    industrySector: clean(row.INDUSTRY),
    marketCapInrCrore: numberOrText(row.Mktcap),
    sebiRegistrationDetails:
      "Not applicable for ordinary listed equity issuer; issuer/listing governed by SEBI regulations",
    isin: clean(row.ISIN_NUMBER),
    listingDate: "",
    faceValue: numberOrText(row.FACE_VALUE),
    status: clean(row.Status),
    bseGroup: clean(row.GROUP),
    sourceUrl: bseUrl,
  }));

  const masterRows = mergeByIsin(nseRows, bseNormalized);
  const generatedAt = new Date();

  const workbook = Workbook.create();
  addSummarySheet(workbook, masterRows, nseRows, bseNormalized, generatedAt);
  addRowsSheet(workbook, "Master Listed Securities", masterRows, "master");
  addRowsSheet(workbook, "NSE Source", nseRows, "source");
  addRowsSheet(workbook, "BSE Source", bseNormalized, "source");
  addGuidanceSheet(workbook);

  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
  });
  console.log(errors.ndjson);

  const preview = await workbook.render({
    sheetName: "Summary",
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(outputDir, "summary_preview.png"),
    new Uint8Array(await preview.arrayBuffer()),
  );

  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(outputPath);
  console.log(JSON.stringify({ outputPath, masterRows: masterRows.length, nseRows: nseRows.length, bseRows: bseNormalized.length }));
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0",
      Accept: "text/csv,*/*",
    },
  });
  if (!response.ok) {
    throw new Error(`Fetch failed ${response.status} ${url}`);
  }
  return response.text();
}

async function fetchBseJson() {
  const response = await fetch(bseUrl, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      Accept: "application/json, text/plain, */*",
      Referer: "https://www.bseindia.com/corporates/List_Scrips.html",
      Origin: "https://www.bseindia.com",
    },
  });
  if (!response.ok) {
    throw new Error(`Fetch failed ${response.status} ${bseUrl}`);
  }
  const text = await response.text();
  return JSON.parse(text);
}

function mergeByIsin(nseRows, bseRows) {
  const byIsin = new Map();
  for (const row of [...nseRows, ...bseRows]) {
    const key = row.isin || `${row.exchange}:${row.stockSymbol || row.bseCode}:${row.companyName}`;
    const existing = byIsin.get(key);
    if (!existing) {
      byIsin.set(key, {
        companyName: row.companyName,
        stockSymbol: row.stockSymbol,
        nseCode: row.nseCode,
        bseCode: row.bseCode,
        industrySector: row.industrySector,
        marketCapInrCrore: row.marketCapInrCrore,
        sebiRegistrationDetails: row.sebiRegistrationDetails,
        isin: row.isin,
        exchangesListed: row.exchange,
        listingDate: row.listingDate,
        faceValue: row.faceValue,
        status: row.status,
        bseGroup: row.bseGroup,
        sourceUrl: row.sourceUrl,
      });
      continue;
    }
    existing.companyName = existing.companyName || row.companyName;
    existing.stockSymbol = existing.nseCode || existing.stockSymbol || row.stockSymbol;
    existing.nseCode = existing.nseCode || row.nseCode;
    existing.bseCode = existing.bseCode || row.bseCode;
    existing.industrySector = existing.industrySector || row.industrySector;
    existing.marketCapInrCrore = existing.marketCapInrCrore || row.marketCapInrCrore;
    existing.listingDate = existing.listingDate || row.listingDate;
    existing.faceValue = existing.faceValue || row.faceValue;
    existing.status = [existing.status, row.status].filter(Boolean).join(" / ");
    existing.bseGroup = existing.bseGroup || row.bseGroup;
    existing.exchangesListed = Array.from(new Set(`${existing.exchangesListed}, ${row.exchange}`.split(/,\s*/))).join(", ");
    existing.sourceUrl = Array.from(new Set(`${existing.sourceUrl}\n${row.sourceUrl}`.split("\n"))).join("\n");
  }
  return [...byIsin.values()].sort((a, b) => a.companyName.localeCompare(b.companyName));
}

function addSummarySheet(workbook, masterRows, nseRows, bseRows, generatedAt) {
  const sheet = workbook.worksheets.add("Summary");
  sheet.showGridLines = false;
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [["India Listed Securities - NSE, BSE, SEBI Notes"]];
  sheet.getRange("A1").format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF", size: 16 },
  };
  sheet.getRange("A3:B10").values = [
    ["Generated at", generatedAt],
    ["Master securities rows", masterRows.length],
    ["NSE source rows", nseRows.length],
    ["BSE active equity source rows", bseRows.length],
    ["Rows listed on both NSE and BSE", masterRows.filter((row) => row.exchangesListed.includes("NSE") && row.exchangesListed.includes("BSE")).length],
    ["Rows listed only on NSE", masterRows.filter((row) => row.exchangesListed === "NSE").length],
    ["Rows listed only on BSE", masterRows.filter((row) => row.exchangesListed === "BSE").length],
    ["Market cap unit", "INR crore where supplied by BSE"],
  ];
  sheet.getRange("A3:A10").format = { fill: "#E0F2F1", font: { bold: true } };
  sheet.getRange("B3:B10").format = { fill: "#F8FAFC" };
  sheet.getRange("B3").setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("B4:B9").setNumberFormat("#,##0");
  sheet.getRange("A12:H16").values = [
    ["Important Notes", "", "", "", "", "", "", ""],
    ["NSE data comes from the NSE equity master CSV.", "", "", "", "", "", "", ""],
    ["BSE data comes from the BSE public active equity scrip endpoint.", "", "", "", "", "", "", ""],
    ["SEBI registration is not generally applicable to ordinary listed equity issuers; the workbook flags this explicitly.", "", "", "", "", "", "", ""],
    ["Industry/Sector is populated only where supplied by source data; blank cells mean the source feed did not provide it.", "", "", "", "", "", "", ""],
  ];
  sheet.getRange("A12:H12").merge();
  sheet.getRange("A13:H13").merge();
  sheet.getRange("A14:H14").merge();
  sheet.getRange("A15:H15").merge();
  sheet.getRange("A16:H16").merge();
  sheet.getRange("A12").format = { fill: "#1E293B", font: { bold: true, color: "#FFFFFF" } };
  sheet.getRange("A13:H16").format = { fill: "#F8FAFC", wrapText: true };
  sheet.getRange("A18:B20").values = [
    ["Source", "URL"],
    ["NSE equity master", nseUrl],
    ["BSE active equity endpoint", bseUrl],
  ];
  sheet.getRange("A18:B18").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF" } };
  sheet.getRange("A1:H20").format.autofitColumns();
  sheet.getRange("B18:B20").format.columnWidth = 70;
}

function addRowsSheet(workbook, name, rows, mode) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const headers = [
    "Company Name",
    "Stock Symbol / Ticker",
    "NSE Code",
    "BSE Code",
    "Industry / Sector",
    "Market Capitalization",
    "SEBI Registration Details",
    "ISIN",
    "Exchanges Listed",
    "Listing Date",
    "Face Value",
    "Status",
    "BSE Group",
    "Source URL",
  ];
  const values = [
    headers,
    ...rows.map((row) => [
      row.companyName,
      row.stockSymbol,
      row.nseCode,
      row.bseCode,
      row.industrySector,
      row.marketCapInrCrore,
      row.sebiRegistrationDetails,
      row.isin,
      mode === "master" ? row.exchangesListed : row.exchange,
      row.listingDate,
      row.faceValue,
      row.status,
      row.bseGroup,
      row.sourceUrl,
    ]),
  ];
  const range = sheet.getRangeByIndexes(0, 0, values.length, headers.length);
  range.values = values;
  const table = sheet.tables.add(`A1:N${values.length}`, true, tableName(name));
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A1:N1").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF" } };
  sheet.getRange(`F2:F${values.length}`).setNumberFormat("#,##0.00");
  sheet.getRange(`K2:K${values.length}`).setNumberFormat("0.00");
  sheet.getRange(`A1:N${Math.min(values.length, 200)}`).format.autofitColumns();
  const widths = [34, 18, 14, 12, 22, 18, 48, 18, 18, 14, 12, 14, 12, 60];
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = width;
  });
  sheet.getRange(`G2:G${values.length}`).format.wrapText = true;
  sheet.getRange(`N2:N${values.length}`).format.wrapText = true;
}

function addGuidanceSheet(workbook) {
  const sheet = workbook.worksheets.add("Query Guidance");
  sheet.showGridLines = false;
  sheet.getRange("A1:E1").merge();
  sheet.getRange("A1").values = [["Market Query Response Guidance"]];
  sheet.getRange("A1").format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF", size: 15 },
  };
  sheet.getRange("A3:E7").values = [
    ["User Query Type", "Example", "Data Handling", "Response Principle", "Certainty Label"],
    [
      "Current or historical commodity price",
      "What is the actual Gold price on 21 June 2026?",
      "Retrieve observed market data if the date/time is available from source feeds.",
      "Report source, timestamp, and market/contract basis.",
      "Actual/current or historical",
    ],
    [
      "Future commodity price",
      "What is the expected Gold price on 21 June 2026?",
      "Use forecasting model, current trend, macro factors, and confidence interval.",
      "Do not state as certain; clearly label as prediction.",
      "Predictive estimate",
    ],
    [
      "Future stock price by date",
      "What will be the stock price on 22 June 2026?",
      "Use stock snapshot, index trend, volatility, sector trend, news, and model forecast.",
      "Provide range, confidence score, and key drivers.",
      "Predictive estimate",
    ],
    [
      "Future stock price by exact time",
      "What will be the stock price on 25 June 2026 at 12:03 PM?",
      "Intraday forecast requires live/intraday model and liquidity/volatility data.",
      "Provide estimated range and state that exact future price is unknowable.",
      "Predictive estimate",
    ],
  ];
  sheet.getRange("A3:E3").format = { fill: "#1E293B", font: { bold: true, color: "#FFFFFF" } };
  sheet.getRange("A3:E7").format.wrapText = true;
  sheet.getRange("A3:E7").format.autofitRows();
  sheet.getRange("A:E").format.columnWidth = 28;
}

function parseCsv(text) {
  const rows = [];
  const records = [];
  let cell = "";
  let row = [];
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(cell);
      cell = "";
      if (row.some((value) => value.trim() !== "")) rows.push(row);
      row = [];
    } else {
      cell += char;
    }
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  const headers = rows.shift().map((header) => header.trim());
  for (const values of rows) {
    records.push(Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
  }
  return records;
}

function clean(value) {
  return value == null ? "" : String(value).trim();
}

function numberOrText(value) {
  const cleaned = clean(value).replace(/,/g, "");
  if (!cleaned) return "";
  const number = Number(cleaned);
  return Number.isFinite(number) ? number : clean(value);
}

function tableName(name) {
  return name.replace(/[^A-Za-z0-9]/g, "") + "Table";
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
