const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const {
  FaSearch, FaShieldAlt, FaBolt, FaBrain, FaDatabase, FaCloud,
  FaCheckCircle, FaFileAlt, FaChartLine, FaLock, FaRocket, FaRobot,
} = require("react-icons/fa");

// Midnight Executive palette + a cyan accent
const NAVY = "1E2761";
const ICE = "CADCFC";
const WHITE = "FFFFFF";
const CYAN = "00C2D1";
const SLATE = "475569";
const LIGHT = "F4F6FB";
const DARKTEXT = "1B1F2A";

function renderIconSvg(IconComponent, color, size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}
async function iconPng(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

const shadowCard = () => ({ type: "outer", color: "000000", blur: 8, offset: 3, angle: 45, opacity: 0.12 });

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
  pres.author = "FilingsIQ";
  pres.title = "FilingsIQ — Chat with SEC Filings on Azure";

  const W = 13.3, H = 7.5;

  // Pre-render icons
  const icons = {
    search: await iconPng(FaSearch, NAVY, 256),
    searchWhite: await iconPng(FaSearch, WHITE, 256),
    shield: await iconPng(FaShieldAlt, NAVY, 256),
    shieldWhite: await iconPng(FaShieldAlt, WHITE, 256),
    bolt: await iconPng(FaBolt, NAVY, 256),
    brain: await iconPng(FaBrain, NAVY, 256),
    brainWhite: await iconPng(FaBrain, WHITE, 256),
    db: await iconPng(FaDatabase, NAVY, 256),
    dbWhite: await iconPng(FaDatabase, WHITE, 256),
    cloud: await iconPng(FaCloud, NAVY, 256),
    cloudWhite: await iconPng(FaCloud, WHITE, 256),
    check: await iconPng(FaCheckCircle, CYAN, 256),
    file: await iconPng(FaFileAlt, NAVY, 256),
    fileWhite: await iconPng(FaFileAlt, WHITE, 256),
    chart: await iconPng(FaChartLine, NAVY, 256),
    chartWhite: await iconPng(FaChartLine, WHITE, 256),
    lock: await iconPng(FaLock, NAVY, 256),
    lockWhite: await iconPng(FaLock, WHITE, 256),
    rocket: await iconPng(FaRocket, WHITE, 256),
    robot: await iconPng(FaRobot, NAVY, 256),
    robotWhite: await iconPng(FaRobot, WHITE, 256),
  };

  function iconCircle(slide, icon, x, y, d, bg) {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg } });
    const pad = d * 0.24;
    slide.addImage({ data: icon, x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
  }

  // ---------- Slide 1 — Title ----------
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    iconCircle(s, icons.brainWhite, W - 2.6, 0.6, 1.1, "2B3580");
    s.addText("FilingsIQ", {
      x: 0.8, y: 2.5, w: 10, h: 1.3, fontSize: 54, bold: true, color: WHITE,
      fontFace: "Cambria", margin: 0,
    });
    s.addText("Chat with SEC filings. Grounded answers, real citations — built and deployed end-to-end on Azure.", {
      x: 0.8, y: 3.75, w: 10.5, h: 0.8, fontSize: 18, color: ICE, fontFace: "Calibri", margin: 0,
    });
    s.addText([
      { text: "Live app:  ", options: { bold: true, color: CYAN } },
      { text: "filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io", options: { color: ICE } },
    ], { x: 0.8, y: 5.3, w: 11.5, h: 0.4, fontSize: 13, fontFace: "Calibri", margin: 0 });
    s.addText([
      { text: "Repo:  ", options: { bold: true, color: CYAN } },
      { text: "github.com/leopbar/FilingsIQ", options: { color: ICE } },
    ], { x: 0.8, y: 5.7, w: 11.5, h: 0.4, fontSize: 13, fontFace: "Calibri", margin: 0 });
    s.addText("Azure AI Engineer Portfolio Project", {
      x: 0.8, y: 6.7, w: 8, h: 0.4, fontSize: 12, color: "8A93C8", fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 2 — Problem ----------
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    s.addText("SEC filings are long, dense, and easy to misread", {
      x: 0.7, y: 0.5, w: 11.8, h: 0.9, fontSize: 30, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });

    const leftItems = [
      ["A 10-K can run 100+ pages of legal and financial language", icons.file],
      ["Generic chatbots answer from memory — they hallucinate numbers", icons.brain],
      ["A wrong figure in a financial answer is a real liability, not a typo", icons.shield],
    ];
    let y = 1.9;
    leftItems.forEach(([text, icon]) => {
      iconCircle(s, icon, 0.8, y, 0.65, LIGHT);
      s.addText(text, { x: 1.7, y: y + 0.02, w: 5.6, h: 0.65, fontSize: 15, color: SLATE, fontFace: "Calibri", valign: "middle", margin: 0 });
      y += 1.0;
    });

    // Right: highlighted answer card mock
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 7.3, y: 1.7, w: 5.3, h: 4.6, rectRadius: 0.08, fill: { color: LIGHT }, shadow: shadowCard(),
    });
    s.addText("FilingsIQ", { x: 7.7, y: 1.95, w: 4.5, h: 0.4, fontSize: 14, bold: true, color: NAVY, fontFace: "Calibri", margin: 0 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 7.7, y: 2.5, w: 4.5, h: 0.7, rectRadius: 0.06, fill: { color: WHITE }, line: { color: "D7DCEC", width: 1 },
    });
    s.addText("What were Apple's total net sales in FY2025?", {
      x: 7.9, y: 2.5, w: 4.1, h: 0.7, fontSize: 11.5, color: SLATE, fontFace: "Calibri", valign: "middle", margin: 0,
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 7.7, y: 3.4, w: 4.5, h: 1.7, rectRadius: 0.06, fill: { color: WHITE },
    });
    s.addText([
      { text: "Total net sales were ", options: {} },
      { text: "$416,161M", options: { bold: true, color: NAVY } },
      { text: " for fiscal year 2025. ", options: {} },
      { text: "[1]", options: { color: CYAN, bold: true } },
    ], { x: 7.9, y: 3.55, w: 4.1, h: 1.0, fontSize: 12, color: DARKTEXT, fontFace: "Calibri", margin: 0 });
    s.addText("[1] “Total net sales … $416,161 million …” — 10-K, FY2025", {
      x: 7.9, y: 4.55, w: 4.1, h: 0.4, fontSize: 9.5, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
    });
    s.addText("Grounded. Cited. Never guessed.", {
      x: 7.7, y: 5.55, w: 4.6, h: 0.5, fontSize: 13, bold: true, color: CYAN, fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 3 — Architecture ----------
  {
    const s = pres.addSlide();
    s.background = { color: LIGHT };
    s.addText("Architecture: a grounded RAG pipeline, not a wrapper around GPT", {
      x: 0.6, y: 0.45, w: 12.2, h: 0.8, fontSize: 26, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });

    const steps = [
      ["Content Safety", "screen the question", icons.shield],
      ["Embed", "text-embedding-3-small", icons.bolt],
      ["Hybrid search", "BM25 + vector + re-ranker", icons.search],
      ["GPT-4o", "answer only from retrieved chunks", icons.brain],
      ["Trace", "Application Insights spans", icons.chart],
    ];
    const boxW = 2.15, gap = 0.32, startX = 0.6, by = 2.0, boxH = 1.7;
    steps.forEach(([title, sub, icon], i) => {
      const x = startX + i * (boxW + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: by, w: boxW, h: boxH, rectRadius: 0.08, fill: { color: WHITE }, shadow: shadowCard() });
      iconCircle(s, icon, x + boxW / 2 - 0.32, by + 0.22, 0.64, LIGHT);
      s.addText(title, { x: x + 0.08, y: by + 0.98, w: boxW - 0.16, h: 0.35, fontSize: 12.5, bold: true, color: NAVY, align: "center", fontFace: "Calibri", margin: 0 });
      s.addText(sub, { x: x + 0.08, y: by + 1.3, w: boxW - 0.16, h: 0.35, fontSize: 9.5, color: SLATE, align: "center", fontFace: "Calibri", margin: 0 });
      if (i < steps.length - 1) {
        s.addShape(pres.shapes.LINE, { x: x + boxW + 0.03, y: by + boxH / 2, w: gap - 0.06, h: 0, line: { color: CYAN, width: 2.5 } });
      }
    });
    s.addText("Browser (Next.js)  →  FastAPI backend  →  Azure OpenAI + Azure AI Search  →  { answer, sources }", {
      x: 0.6, y: by + boxH + 0.35, w: 12.2, h: 0.4, fontSize: 12, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
    });

    // Ingestion strip
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 4.85, w: 12.1, h: 1.9, rectRadius: 0.08, fill: { color: NAVY }, shadow: shadowCard() });
    s.addText("Offline ingestion", { x: 0.9, y: 5.0, w: 4, h: 0.35, fontSize: 13, bold: true, color: WHITE, fontFace: "Calibri", margin: 0 });
    s.addText("PDF  →  Document Intelligence (layout + tables)  →  Azure AI Language (PII redaction)  →  chunk + embed  →  Azure AI Search index", {
      x: 0.9, y: 5.4, w: 11.5, h: 0.5, fontSize: 12.5, color: ICE, fontFace: "Calibri", margin: 0,
    });
    s.addText("5 years of Apple 10-Ks processed in parallel via a PySpark + MLflow batch pipeline (640 chunks, 0 errors)", {
      x: 0.9, y: 5.95, w: 11.5, h: 0.5, fontSize: 12, italic: true, color: ICE, fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 4 — Key results (stat callouts) ----------
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    s.addText("Results, not promises", {
      x: 0.7, y: 0.5, w: 10, h: 0.8, fontSize: 30, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });

    const stats = [
      ["77.5%", "fine-tuned clause-\nclassification accuracy\n(up from 17.7% zero-shot)"],
      ["+59.8pp", "accuracy gain from\nfine-tuning gpt-4o on\n671 held-out test clauses"],
      ["640", "filing chunks processed by\na parallel PySpark + MLflow\npipeline — 0 errors"],
      ["0.89", "RAGAS context recall across\na 24-question golden\nevaluation set"],
    ];
    const cw = 2.85, ch = 2.7, gap = 0.25, sx = 0.7, sy = 1.7;
    stats.forEach(([big, label], i) => {
      const x = sx + i * (cw + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: sy, w: cw, h: ch, rectRadius: 0.1, fill: { color: i === 0 || i === 1 ? NAVY : LIGHT }, shadow: shadowCard() });
      s.addText(big, { x: x + 0.15, y: sy + 0.35, w: cw - 0.3, h: 0.9, fontSize: 40, bold: true, color: i === 0 || i === 1 ? CYAN : NAVY, align: "center", fontFace: "Calibri", margin: 0 });
      s.addText(label, { x: x + 0.2, y: sy + 1.35, w: cw - 0.4, h: 1.2, fontSize: 11.5, color: i === 0 || i === 1 ? ICE : SLATE, align: "center", fontFace: "Calibri", margin: 0 });
    });

    s.addText("Every number above comes from an actual eval run, saved to the repo — not an estimate.", {
      x: 0.7, y: sy + ch + 0.4, w: 11.5, h: 0.5, fontSize: 13, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 5 — Fine-tuning ----------
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    s.addText("Fine-tuning: gpt-4o on legal clause classification", {
      x: 0.6, y: 0.45, w: 12.2, h: 0.8, fontSize: 26, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });
    s.addText("CUAD dataset · 41 standard contract-clause categories · 671 held-out test clauses", {
      x: 0.6, y: 1.2, w: 12, h: 0.4, fontSize: 13, color: SLATE, fontFace: "Calibri", margin: 0,
    });

    s.addChart(pres.charts.BAR, [
      { name: "Accuracy %", labels: ["Zero-shot baseline", "Fine-tuned gpt-4o"], values: [17.7, 77.5] },
    ], {
      x: 0.6, y: 1.8, w: 6.0, h: 4.6, barDir: "col",
      chartColors: [NAVY],
      chartArea: { fill: { color: "FFFFFF" } },
      catAxisLabelColor: SLATE, valAxisLabelColor: SLATE,
      valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" },
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: DARKTEXT, dataLabelFontSize: 14,
      dataLabelFormatCode: "0.0",
      showLegend: false, showTitle: true, title: "Test-set accuracy", titleColor: DARKTEXT, titleFontSize: 14,
      valAxisMaxVal: 100,
    });

    const rightItems = [
      "Why fine-tune at all? Dense, overlapping legal categories are genuinely hard to separate zero-shot — the low baseline proves the task, not the model.",
      "Training: 5,361 examples, 3 epochs, ~5h35m, ~$43 — a real cost/time tradeoff documented in ADR-003.",
      "Macro F1 moved 0.15 → 0.69, with several categories going from 0% to near-perfect F1.",
    ];
    let ry = 1.9;
    rightItems.forEach((t) => {
      iconCircle(s, icons.check, 7.0, ry, 0.45, LIGHT);
      s.addText(t, { x: 7.6, y: ry - 0.05, w: 5.0, h: 1.3, fontSize: 12.5, color: SLATE, fontFace: "Calibri", margin: 0 });
      ry += 1.55;
    });
  }

  // ---------- Slide 6 — PySpark pipeline ----------
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    s.addText("Scalable ingestion: PySpark + MLflow batch pipeline", {
      x: 0.6, y: 0.45, w: 12.2, h: 0.8, fontSize: 26, bold: true, color: WHITE, fontFace: "Cambria", margin: 0,
    });
    s.addText("5 years of Apple 10-K filings, processed and tracked as a real batch job", {
      x: 0.6, y: 1.2, w: 12, h: 0.4, fontSize: 13, color: ICE, fontFace: "Calibri", margin: 0,
    });

    const flow = ["Manifest\n(Spark DF)", "Parallel\nworkers (5)", "Chunk +\nembed", "Upload to\nAI Search", "MLflow\ntracking"];
    const fw = 2.15, fgap = 0.25, fx = 0.6, fy = 2.2, fh = 1.4;
    flow.forEach((label, i) => {
      const x = fx + i * (fw + fgap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: fy, w: fw, h: fh, rectRadius: 0.08, fill: { color: "2B3580" } });
      s.addText(label, { x: x + 0.1, y: fy, w: fw - 0.2, h: fh, fontSize: 12.5, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: "Calibri", margin: 0 });
      if (i < flow.length - 1) {
        s.addShape(pres.shapes.LINE, { x: x + fw + 0.03, y: fy + fh / 2, w: fgap - 0.06, h: 0, line: { color: CYAN, width: 2.5 } });
      }
    });

    s.addChart(pres.charts.BAR, [
      { name: "Chunks", labels: ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"], values: [136, 132, 123, 124, 125] },
    ], {
      x: 0.6, y: 4.0, w: 7.4, h: 3.0, barDir: "col",
      chartColors: [CYAN],
      chartArea: { fill: { color: "1E2761" } },
      catAxisLabelColor: ICE, valAxisLabelColor: ICE,
      valGridLine: { color: "3A458F", size: 0.5 }, catGridLine: { style: "none" },
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: WHITE,
      showLegend: false, showTitle: true, title: "Chunks per fiscal year (640 total)", titleColor: WHITE, titleFontSize: 13,
    });

    const stats6 = [["0", "errors across\nall 5 filings"], ["132.5s", "total pipeline\nduration"], ["7 / 19", "params / metrics\nlogged per run"]];
    let s6y = 4.0;
    stats6.forEach(([big, label]) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.3, y: s6y, w: 4.4, h: 0.92, rectRadius: 0.08, fill: { color: "2B3580" } });
      s.addText(big, { x: 8.5, y: s6y, w: 1.6, h: 0.92, fontSize: 24, bold: true, color: CYAN, valign: "middle", fontFace: "Calibri", margin: 0 });
      s.addText(label, { x: 10.15, y: s6y, w: 2.45, h: 0.92, fontSize: 11, color: ICE, valign: "middle", fontFace: "Calibri", margin: 0 });
      s6y += 1.08;
    });
  }

  // ---------- Slide 7 — MLOps / LLMOps ----------
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    s.addText("MLOps/LLMOps: the layer you don't see in the UI", {
      x: 0.6, y: 0.45, w: 12.2, h: 0.8, fontSize: 26, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });

    const cards = [
      [icons.chart, "RAGAS eval gate", "24-question golden set scores faithfulness, relevancy, and retrieval quality — category-aware thresholds, not one flat bar."],
      [icons.bolt, "Application Insights", "Every request traced end-to-end — embed, search, generate as separate spans — visible in production, not just locally."],
      [icons.shield, "Content Safety", "Every question screened before it reaches GPT-4o. Fails open, so a non-critical gate's outage never takes down chat."],
    ];
    const cw7 = 3.85, ch7 = 4.4, gap7 = 0.3, sx7 = 0.6, sy7 = 1.7;
    cards.forEach(([icon, title, desc], i) => {
      const x = sx7 + i * (cw7 + gap7);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: sy7, w: cw7, h: ch7, rectRadius: 0.1, fill: { color: LIGHT }, shadow: shadowCard() });
      iconCircle(s, icon, x + cw7 / 2 - 0.45, sy7 + 0.4, 0.9, WHITE);
      s.addText(title, { x: x + 0.25, y: sy7 + 1.55, w: cw7 - 0.5, h: 0.5, fontSize: 16, bold: true, color: NAVY, align: "center", fontFace: "Calibri", margin: 0 });
      s.addText(desc, { x: x + 0.35, y: sy7 + 2.15, w: cw7 - 0.7, h: 2.0, fontSize: 12.5, color: SLATE, align: "center", fontFace: "Calibri", margin: 0 });
    });

    s.addText("Found and documented honestly: a DI table-flattening artifact that tanked one metric on correct answers, and a real cross-document retrieval gap — treated differently, not averaged away.", {
      x: 0.6, y: sy7 + ch7 + 0.25, w: 12.1, h: 0.5, fontSize: 11.5, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 8 — Security & Governance ----------
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    s.addText("Governance: no plaintext secret, anywhere", {
      x: 0.6, y: 0.45, w: 12.2, h: 0.8, fontSize: 26, bold: true, color: WHITE, fontFace: "Cambria", margin: 0,
    });

    const items8 = [
      [icons.lockWhite, "8 credentials", "live only in Azure Key Vault — never a CLI argument, file, or chat message"],
      [icons.cloudWhite, "Managed Identity", "both Container Apps and the ACR pull use system-assigned identities, no admin passwords"],
      [icons.shieldWhite, "Scale to zero", "both apps cost nothing while idle — enterprise pattern, portfolio budget"],
      [icons.fileWhite, "6 ADRs", "every major decision documented — including the ones that needed a second attempt"],
    ];
    const cw8 = 2.85, gap8 = 0.25, sx8 = 0.6, sy8 = 1.9, ch8 = 3.6;
    items8.forEach(([icon, title, desc], i) => {
      const x = sx8 + i * (cw8 + gap8);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: sy8, w: cw8, h: ch8, rectRadius: 0.1, fill: { color: "2B3580" } });
      iconCircle(s, icon, x + cw8 / 2 - 0.4, sy8 + 0.35, 0.8, "3A458F");
      s.addText(title, { x: x + 0.15, y: sy8 + 1.4, w: cw8 - 0.3, h: 0.6, fontSize: 15, bold: true, color: CYAN, align: "center", fontFace: "Calibri", margin: 0 });
      s.addText(desc, { x: x + 0.2, y: sy8 + 2.05, w: cw8 - 0.4, h: 1.45, fontSize: 11.5, color: ICE, align: "center", fontFace: "Calibri", margin: 0 });
    });

    s.addText("A real incident, handled honestly: a debug command briefly printed one API key into a chat transcript — caught, rotated, and documented in ADR-006 rather than hidden.", {
      x: 0.6, y: sy8 + ch8 + 0.3, w: 12.1, h: 0.5, fontSize: 11.5, italic: true, color: "AAB4E8", fontFace: "Calibri", margin: 0,
    });
  }

  // ---------- Slide 9 — Job requirement coverage ----------
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    s.addText("10 of 10 job requirements covered", {
      x: 0.6, y: 0.4, w: 12, h: 0.7, fontSize: 26, bold: true, color: DARKTEXT, fontFace: "Cambria", margin: 0,
    });

    const rows = [
      ["Azure OpenAI + related AI services", "gpt-4o + text-embedding-3-small"],
      ["Prompt engineering + RAG + vector search", "Grounded RAG, hybrid + semantic search"],
      ["Vector database + Cognitive Search", "Azure AI Search (BM25 + HNSW + re-ranker)"],
      ["Document processing (DI + Cognitive Services)", "Layout extraction + PII redaction"],
      ["Governance & best practices", "Key Vault + Managed Identity, ADR trail"],
      ["Design & architect AI solutions on Azure", "Multi-service, live on Container Apps"],
      ["Fine-tuning & model optimization", "+59.8pp accuracy on CUAD clauses"],
      ["PySpark + scalable data pipelines", "Hybrid Spark + MLflow batch pipeline"],
      ["MLOps / LLMOps", "RAGAS gate, tracing, Content Safety"],
      ["Customer enablement / presentations", "README, ADRs, this deck"],
    ];

    const tableRows = [
      [
        { text: "Requirement", options: { bold: true, color: WHITE, fill: { color: NAVY } } },
        { text: "Covered by", options: { bold: true, color: WHITE, fill: { color: NAVY } } },
        { text: "", options: { bold: true, color: WHITE, fill: { color: NAVY } } },
      ],
      ...rows.map(([req, by]) => [
        { text: req, options: { color: DARKTEXT } },
        { text: by, options: { color: SLATE } },
        { text: "✓", options: { color: CYAN, bold: true, align: "center" } },
      ]),
    ];

    s.addTable(tableRows, {
      x: 0.6, y: 1.25, w: 12.1, h: 6.0,
      colW: [5.6, 6.0, 0.5],
      fontSize: 11.5, fontFace: "Calibri",
      border: { pt: 0.5, color: "E2E8F0" },
      autoPage: false,
      rowH: 0.56,
      valign: "middle",
    });
  }

  // ---------- Slide 10 — Close ----------
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    iconCircle(s, icons.rocket, W / 2 - 0.55, 1.0, 1.1, "2B3580");
    s.addText("Built to be defensible end-to-end", {
      x: 0.8, y: 2.4, w: 11.7, h: 0.9, fontSize: 32, bold: true, color: WHITE, align: "center", fontFace: "Cambria", margin: 0,
    });
    s.addText("Not a demo that works once — a deployed app with a real decision trail.", {
      x: 0.8, y: 3.3, w: 11.7, h: 0.5, fontSize: 15, color: ICE, align: "center", fontFace: "Calibri", margin: 0,
    });

    const links = [
      ["Live app", "filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io"],
      ["Source + 6 ADRs", "github.com/leopbar/FilingsIQ"],
    ];
    let ly = 4.4;
    links.forEach(([label, url]) => {
      s.addText([
        { text: label + ":  ", options: { bold: true, color: CYAN } },
        { text: url, options: { color: WHITE } },
      ], { x: 0.8, y: ly, w: 11.7, h: 0.45, fontSize: 15, align: "center", fontFace: "Calibri", margin: 0 });
      ly += 0.6;
    });

    s.addText("FilingsIQ — Azure AI Engineer Portfolio Project", {
      x: 0.8, y: 6.7, w: 11.7, h: 0.4, fontSize: 11, color: "8A93C8", align: "center", fontFace: "Calibri", margin: 0,
    });
  }

  await pres.writeFile({ fileName: "FilingsIQ-Deck.pptx" });
  console.log("done");
}

main().catch((e) => { console.error(e); process.exit(1); });
