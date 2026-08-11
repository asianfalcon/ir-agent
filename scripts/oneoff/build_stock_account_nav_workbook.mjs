import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("outputs/stock_account_nav_management");
const outputPath = path.join(outputDir, "stock_account_nav_management_20260707.xlsx");

const workbook = Workbook.create();
const cover = workbook.worksheets.add("Dashboard");
const accounts = workbook.worksheets.add("Accounts");
const scenarios = workbook.worksheets.add("Scenarios");
const ledger = workbook.worksheets.add("Ledger");
const sources = workbook.worksheets.add("Sources");

for (const ws of [cover, accounts, scenarios, ledger, sources]) {
  ws.showGridLines = false;
}

function setValues(ws, range, values) {
  ws.getRange(range).values = values;
}

function setFormulas(ws, range, formulas) {
  ws.getRange(range).formulas = formulas;
}

function fmt(range, options = {}) {
  const f = range.format;
  if (options.fill) f.fill.color = options.fill;
  if (options.fontColor) f.font.color = options.fontColor;
  if (options.bold !== undefined) f.font.bold = options.bold;
  if (options.size) f.font.size = options.size;
  if (options.wrap !== undefined) f.wrapText = options.wrap;
  if (options.hAlign) f.horizontalAlignment = options.hAlign;
  if (options.vAlign) f.verticalAlignment = options.vAlign;
  if (options.border) f.borders = options.border;
}

function money(range) {
  range.setNumberFormat('"¥"#,##0;[Red]("¥"#,##0);-');
}

function pct(range) {
  range.setNumberFormat('0.00%;[Red](0.00%);-');
}

function multiple(range) {
  range.setNumberFormat('0.00x;[Red](0.00x);-');
}

function integer(range) {
  range.setNumberFormat('#,##0;[Red](#,##0);-');
}

function section(ws, range, title) {
  const r = ws.getRange(range);
  r.merge();
  r.values = [[title]];
  fmt(r, { fill: "#1F4E78", fontColor: "#FFFFFF", bold: true, size: 12, hAlign: "left", border: { preset: "outside", style: "thin", color: "#1F4E78" } });
}

// Dashboard
section(cover, "A1:H1", "股票账户净值与市值管理看板");
setValues(cover, "A3:H3", [["指标", "当前值", "说明", "", "指标", "当前值", "说明", ""]]);
fmt(cover.getRange("A3:H3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
setValues(cover, "A4:C12", [
  ["账户初始总值", null, "用户输入"],
  ["当前总净值", null, "用户输入"],
  ["累计盈亏", null, "当前净值 - 初始总值"],
  ["累计收益率", null, "累计盈亏 / 初始总值"],
  ["A追加转入", null, "用户输入"],
  ["转入后总资产", null, "当前净值 + A追加转入"],
  ["转入后净投入", null, "初始总值 + A追加转入"],
  ["转入后盈亏", null, "转入后总资产 - 转入后净投入"],
  ["转入后收益率", null, "转入后盈亏 / 转入后净投入"],
]);
setFormulas(cover, "B4:B12", [
  ["='Accounts'!B4"],
  ["='Accounts'!B7"],
  ["=B5-B4"],
  ["=IFERROR(B6/B4,0)"],
  ["='Accounts'!B13"],
  ["=B5+B8"],
  ["=B4+B8"],
  ["=B9-B10"],
  ["=IFERROR(B11/B10,0)"],
]);
setValues(cover, "E4:G12", [
  ["A当前估算净值", null, "按初始占比分摊，可在 Accounts 改为手工值"],
  ["B当前估算净值", null, "按初始占比分摊，可在 Accounts 改为手工值"],
  ["A转入后资产", null, "A当前 + 转入"],
  ["B转入后资产", null, "B不变"],
  ["A转入后占比", null, "A转入后资产 / 总资产"],
  ["B转入后占比", null, "B转入后资产 / 总资产"],
  ["回本所需收益率", null, "从转入后总资产回到转入后净投入"],
  ["目标 10% 收益市值", null, "转入后净投入 * 110%"],
  ["目标 20% 收益市值", null, "转入后净投入 * 120%"],
]);
setFormulas(cover, "F4:F12", [
  ["='Accounts'!B9"],
  ["='Accounts'!B10"],
  ["='Accounts'!B16"],
  ["='Accounts'!B17"],
  ["='Accounts'!B18"],
  ["='Accounts'!B19"],
  ["=IFERROR(B10/B9-1,0)"],
  ["=B10*(1+10%)"],
  ["=B10*(1+20%)"],
]);
money(cover.getRange("B4:B6"));
pct(cover.getRange("B7:B7"));
money(cover.getRange("B8:B11"));
pct(cover.getRange("B12:B12"));
money(cover.getRange("F4:F7"));
pct(cover.getRange("F8:F10"));
money(cover.getRange("F11:F12"));
fmt(cover.getRange("A4:C12"), { border: { preset: "all", style: "thin", color: "#D9E2F3" } });
fmt(cover.getRange("E4:G12"), { border: { preset: "all", style: "thin", color: "#D9E2F3" } });
fmt(cover.getRange("B4:B5"), { fontColor: "#000000", bold: true });
fmt(cover.getRange("B8:B8"), { fontColor: "#0000FF", bold: true, fill: "#FFF2CC" });
fmt(cover.getRange("B6:B7"), { bold: true });

section(cover, "A15:H15", "后续收益敏感性");
setValues(cover, "A16:H16", [["后续收益率", "组合市值", "组合盈亏", "总收益率", "A资产", "B资产", "备注", ""]]);
fmt(cover.getRange("A16:H16"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
const dashRates = [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.5, 1.0];
setValues(cover, "A17:A25", dashRates.map((v) => [v]));
setFormulas(cover, "B17:G25", dashRates.map((_, idx) => {
  const row = 17 + idx;
  return [
    `=$B$9*(1+A${row})`,
    `=B${row}-$B$10`,
    `=IFERROR(C${row}/$B$10,0)`,
    `=$F$6*(1+A${row})`,
    `=$F$7*(1+A${row})`,
    `=IF(A${row}<0,"回撤情景",IF(A${row}=0,"转入后基准","盈利情景"))`,
  ];
}));
pct(cover.getRange("A17:A25"));
money(cover.getRange("B17:C25"));
pct(cover.getRange("D17:D25"));
money(cover.getRange("E17:F25"));
fmt(cover.getRange("A17:G25"), { border: { preset: "all", style: "thin", color: "#E2E8F0" } });

// Accounts sheet
section(accounts, "A1:F1", "账户输入与拆分");
setValues(accounts, "A3:D3", [["项目", "金额/比例", "说明", "输入类型"]]);
fmt(accounts.getRange("A3:D3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
setValues(accounts, "A4:D18", [
  ["初始总值", 27500000, "账户初始值", "输入"],
  ["A初始值", 25000000, "A账户初始资金", "输入"],
  ["B初始值", 2500000, "B账户初始资金", "输入"],
  ["当前总净值", 20683829, "当前账户总净值", "输入"],
  ["A初始占比", null, "A初始值 / 初始总值", "公式"],
  ["A当前估算净值", null, "当前总净值 * A初始占比", "公式"],
  ["B当前估算净值", null, "当前总净值 - A当前估算", "公式"],
  ["当前累计盈亏", null, "当前总净值 - 初始总值", "公式"],
  ["当前收益率", null, "当前累计盈亏 / 初始总值", "公式"],
  ["A追加转入", 50000000, "A当前追加转入金额", "输入"],
  ["转入后总资产", null, "当前总净值 + A追加转入", "公式"],
  ["转入后净投入", null, "初始总值 + A追加转入", "公式"],
  ["A转入后资产", null, "A当前估算净值 + A追加转入", "公式"],
  ["B转入后资产", null, "B当前估算净值", "公式"],
  ["A转入后占比", null, "A转入后资产 / 转入后总资产", "公式"],
]);
setValues(accounts, "A19:D19", [["B转入后占比", null, "B转入后资产 / 转入后总资产", "公式"]]);
setFormulas(accounts, "B8:B12", [
  ["=IFERROR(B5/B4,0)"],
  ["=B7*B8"],
  ["=B7-B9"],
  ["=B7-B4"],
  ["=IFERROR(B11/B4,0)"],
]);
setFormulas(accounts, "B14:B19", [
  ["=B7+B13"],
  ["=B4+B13"],
  ["=B9+B13"],
  ["=B10"],
  ["=IFERROR(B16/B14,0)"],
  ["=IFERROR(B17/B14,0)"],
]);
money(accounts.getRange("B4:B7"));
pct(accounts.getRange("B8:B8"));
money(accounts.getRange("B9:B11"));
pct(accounts.getRange("B12:B12"));
money(accounts.getRange("B13:B17"));
pct(accounts.getRange("B18:B19"));
fmt(accounts.getRange("A4:D19"), { border: { preset: "all", style: "thin", color: "#D9E2F3" } });
fmt(accounts.getRange("B4:B7"), { fontColor: "#0000FF" });
fmt(accounts.getRange("B13:B13"), { fontColor: "#0000FF", fill: "#FFF2CC" });
fmt(accounts.getRange("B8:B12"), { fontColor: "#000000" });
fmt(accounts.getRange("B14:B19"), { fontColor: "#000000" });

// Scenarios sheet
section(scenarios, "A1:H1", "后续收益与市值情景分析");
setValues(scenarios, "A3:H3", [["后续收益率", "组合市值", "总盈亏", "总收益率", "A资产", "B资产", "A占比", "B占比"]]);
fmt(scenarios.getRange("A3:H3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
const rates = [-0.5, -0.4, -0.3, -0.2, -0.1, 0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0];
setValues(scenarios, "A4:A18", rates.map((v) => [v]));
setFormulas(scenarios, "B4:H18", rates.map((_, i) => {
  const row = 4 + i;
  return [
    `='Accounts'!$B$14*(1+A${row})`,
    `=B${row}-'Accounts'!$B$15`,
    `=IFERROR(C${row}/'Accounts'!$B$15,0)`,
    `='Accounts'!$B$16*(1+A${row})`,
    `='Accounts'!$B$17*(1+A${row})`,
    `=IFERROR(E${row}/B${row},0)`,
    `=IFERROR(F${row}/B${row},0)`,
  ];
}));
pct(scenarios.getRange("A4:A18"));
money(scenarios.getRange("B4:C18"));
pct(scenarios.getRange("D4:D18"));
money(scenarios.getRange("E4:F18"));
pct(scenarios.getRange("G4:H18"));
fmt(scenarios.getRange("A4:H18"), { border: { preset: "all", style: "thin", color: "#E2E8F0" } });

section(scenarios, "J1:N1", "目标收益倒推");
setValues(scenarios, "J3:N3", [["目标总收益率", "目标市值", "所需增量市值", "A目标资产", "B目标资产"]]);
fmt(scenarios.getRange("J3:N3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
const targetRates = [0, 0.05, 0.1, 0.2, 0.3, 0.5];
setValues(scenarios, "J4:J9", targetRates.map((v) => [v]));
setFormulas(scenarios, "K4:N9", targetRates.map((_, i) => {
  const row = 4 + i;
  return [
    `='Accounts'!$B$15*(1+J${row})`,
    `=K${row}-'Accounts'!$B$14`,
    `=K${row}*'Accounts'!$B$18`,
    `=K${row}*'Accounts'!$B$19`,
  ];
}));
pct(scenarios.getRange("J4:J9"));
money(scenarios.getRange("K4:N9"));
fmt(scenarios.getRange("J4:N9"), { border: { preset: "all", style: "thin", color: "#E2E8F0" } });

// Ledger sheet
section(ledger, "A1:H1", "资金流水和净值跟踪");
setValues(ledger, "A3:H3", [["日期", "账户", "动作", "现金流", "期末市值", "净投入累计", "累计盈亏", "累计收益率"]]);
fmt(ledger.getRange("A3:H3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
setValues(ledger, "A4:E6", [
  [new Date("2026-07-07"), "组合", "初始投入", 27500000, 27500000],
  [new Date("2026-07-07"), "组合", "当前净值记录", 0, 20683829],
  [new Date("2026-07-07"), "A", "追加转入", 50000000, 70683829],
]);
setFormulas(ledger, "F4:H30", Array.from({ length: 27 }, (_, i) => {
  const row = 4 + i;
  return [
    `=SUM($D$4:D${row})`,
    `=IF(E${row}="","",E${row}-F${row})`,
    `=IFERROR(G${row}/F${row},0)`,
  ];
}));
ledger.getRange("A4:A30").setNumberFormat("yyyy-mm-dd");
money(ledger.getRange("D4:G30"));
pct(ledger.getRange("H4:H30"));
fmt(ledger.getRange("A4:H30"), { border: { preset: "all", style: "thin", color: "#E2E8F0" } });
fmt(ledger.getRange("D4:E30"), { fontColor: "#0000FF" });

// Sources sheet
section(sources, "A1:D1", "来源、假设与使用说明");
setValues(sources, "A3:D11", [
  ["项目", "值", "来源/说明", "可编辑"],
  ["账户初始值", 27500000, "用户提供：账户初始值", "是"],
  ["A初始值", 25000000, "用户提供：A占25000000", "是"],
  ["B初始值", 2500000, "用户提供：B占2500000", "是"],
  ["当前总净值", 20683829, "用户提供：目前净值20683829", "是"],
  ["A追加转入", 50000000, "用户提供：A当前再转入50000000", "是"],
  ["当前A/B拆分", "按初始占比分摊", "如果有真实A/B当前值，可在 Accounts 直接替换 A当前估算/B当前估算的逻辑", "可改"],
  ["模型单位", "人民币元", "所有金额为元，显示为人民币", "否"],
  ["后续收益率", "情景变量", "Scenarios 中可修改收益率行", "是"],
]);
fmt(sources.getRange("A3:D3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
fmt(sources.getRange("A4:D11"), { border: { preset: "all", style: "thin", color: "#E2E8F0" }, wrap: true, vAlign: "top" });
money(sources.getRange("B4:B7"));

// Column sizing
const sizing = [
  [cover, ["A", "B", "C", "E", "F", "G"], [18, 18, 34, 18, 18, 34]],
  [accounts, ["A", "B", "C", "D"], [20, 18, 42, 14]],
  [scenarios, ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N"], [14, 18, 18, 14, 18, 18, 12, 12, 16, 18, 18, 18, 18]],
  [ledger, ["A", "B", "C", "D", "E", "F", "G", "H"], [14, 12, 18, 16, 16, 16, 16, 14]],
  [sources, ["A", "B", "C", "D"], [18, 18, 70, 12]],
];
for (const [ws, cols, widths] of sizing) {
  cols.forEach((col, idx) => {
    ws.getRange(`${col}:${col}`).format.columnWidth = widths[idx];
  });
}
for (const ws of [cover, accounts, scenarios, ledger, sources]) {
  ws.freezePanes.freezeRows(3);
}

// Checks
section(sources, "F1:J1", "模型检查");
setValues(sources, "F3:J3", [["检查项", "实际", "预期", "差异", "状态"]]);
fmt(sources.getRange("F3:J3"), { fill: "#D9EAF7", bold: true, hAlign: "center", border: { preset: "all", style: "thin", color: "#B7C9D6" } });
setValues(sources, "F4:F7", [
  ["A+B初始值=初始总值"],
  ["A+B转入后资产=转入后总资产"],
  ["A+B转入后占比=100%"],
  ["Dashboard总资产=Accounts总资产"],
]);
setFormulas(sources, "G4:J7", [
  ["='Accounts'!B5+'Accounts'!B6", "='Accounts'!B4", "=G4-H4", '=IF(ABS(I4)<1,"OK","CHECK")'],
  ["='Accounts'!B16+'Accounts'!B17", "='Accounts'!B14", "=G5-H5", '=IF(ABS(I5)<1,"OK","CHECK")'],
  ["='Accounts'!B18+'Accounts'!B19", "1", "=G6-H6", '=IF(ABS(I6)<0.0001,"OK","CHECK")'],
  ["='Dashboard'!B9", "='Accounts'!B14", "=G7-H7", '=IF(ABS(I7)<1,"OK","CHECK")'],
]);
money(sources.getRange("G4:I5"));
pct(sources.getRange("G6:I6"));
money(sources.getRange("G7:I7"));
fmt(sources.getRange("F4:J7"), { border: { preset: "all", style: "thin", color: "#E2E8F0" } });

await fs.mkdir(outputDir, { recursive: true });

// Compact verification before export.
const dashboardCheck = await workbook.inspect({
  kind: "table",
  sheetId: "Dashboard",
  range: "A1:H25",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 8,
  maxChars: 6000,
});
console.log(dashboardCheck.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 4000,
});
console.log(errors.ndjson);

for (const sheetName of ["Dashboard", "Accounts", "Scenarios", "Ledger", "Sources"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const bytes = new Uint8Array(await preview.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName}.png`), bytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
