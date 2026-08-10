import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..", "..");
const src = resolve(root, "output/reports/joulwatt_research_report_pdf_20260708.md");
const htmlOut = resolve(root, "output/reports/joulwatt_research_report_pdf_20260708.html");
const pdfOut = resolve(root, "output/pdf/joulwatt_research_report_pdf_20260708.pdf");

marked.setOptions({ gfm: true, breaks: false });

const md = await readFile(src, "utf8");
const body = marked.parse(md);

const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>杰华特业绩预测研报</title>
<style>
@page { size: Letter landscape; margin: 12mm 13mm 13mm; }
* { box-sizing: border-box; }
body {
  margin: 0;
  color: #111827;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI Emoji", sans-serif;
  font-size: 13px;
  line-height: 1.48;
}
h1 {
  margin: 0 0 8px;
  color: #0b2545;
  font-size: 26px;
  line-height: 1.18;
  letter-spacing: 0;
}
h2 {
  margin: 18px 0 8px;
  color: #183b59;
  font-size: 18px;
  line-height: 1.25;
  break-after: avoid;
}
p { margin: 6px 0 8px; }
strong { font-weight: 800; color: #0f172a; }
code {
  font-family: "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 0.92em;
  background: #f3f4f6;
  border-radius: 3px;
  padding: 1px 4px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 14px;
  table-layout: fixed;
  break-inside: avoid;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #b8c2cc;
  padding: 7px 8px;
  vertical-align: middle;
  word-break: break-word;
}
th {
  background: #eaf2f8;
  color: #0f172a;
  text-align: center;
  font-weight: 800;
}
tbody tr:nth-child(even) td { background: #f8fafc; }
td:nth-child(1), td:nth-child(2), td:nth-child(3), td:nth-child(4) { text-align: center; }
td:last-child { text-align: left; }
td.delta {
  background: #fff7ed !important;
  font-weight: 800;
}
.up { color: #15803d; font-weight: 800; }
.down { color: #b91c1c; font-weight: 800; }
ul { margin: 5px 0 8px 18px; padding: 0; }
li { margin: 3px 0; }
.footer {
  position: fixed;
  right: 13mm;
  bottom: 5mm;
  color: #6b7280;
  font-size: 10px;
}
.page-break { break-before: page; }
</style>
</head>
<body>
<div class="footer">杰华特业绩预测研报 | 2026-07-08</div>
${body}
<script>
for (const td of document.querySelectorAll("td")) {
  if (td.textContent.includes("🔼") || td.textContent.includes("🔽")) {
    td.classList.add("delta");
    td.innerHTML = td.innerHTML
      .replace(/([^<\\s]+\\s*🔼\\s*[^<\\s]+)/g, '<span class="up">$1</span>')
      .replace(/([^<\\s]+\\s*🔽\\s*[^<\\s]+)/g, '<span class="down">$1</span>');
  }
}
</script>
</body>
</html>`;

await mkdir(dirname(htmlOut), { recursive: true });
await mkdir(dirname(pdfOut), { recursive: true });
await writeFile(htmlOut, html, "utf8");

const browser = await chromium.launch({
  headless: true,
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
});
const page = await browser.newPage();
await page.goto(`file://${htmlOut}`, { waitUntil: "networkidle" });
await page.pdf({
  path: pdfOut,
  format: "Letter",
  landscape: true,
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();

console.log(htmlOut);
console.log(pdfOut);
