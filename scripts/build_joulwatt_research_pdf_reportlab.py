from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf/joulwatt_research_report_pdf_20260708.pdf"


def register_fonts():
    pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="CN", fontSize=22, leading=28, textColor=colors.HexColor("#0B2545"), alignment=TA_LEFT, spaceAfter=5),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName="CN", fontSize=10, leading=14, textColor=colors.HexColor("#4B5563"), spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="CN", fontSize=14.5, leading=18, textColor=colors.HexColor("#183B59"), spaceBefore=9, spaceAfter=5),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="CN", fontSize=9.3, leading=13.5, textColor=colors.HexColor("#111827"), alignment=TA_LEFT, spaceAfter=5),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName="CN", fontSize=7.6, leading=10.5, textColor=colors.HexColor("#4B5563"), spaceAfter=3),
        "table": ParagraphStyle("table", parent=base["BodyText"], fontName="CN", fontSize=7.3, leading=10.2, textColor=colors.HexColor("#111827"), alignment=TA_CENTER),
        "table_left": ParagraphStyle("table_left", parent=base["BodyText"], fontName="CN", fontSize=7.2, leading=10, textColor=colors.HexColor("#111827"), alignment=TA_LEFT),
        "header": ParagraphStyle("header", parent=base["BodyText"], fontName="CN", fontSize=7.5, leading=10, textColor=colors.white, alignment=TA_CENTER),
    }


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def p(text, style):
    return Paragraph(text, style)


def fmt_cell(value, style):
    if hasattr(value, "wrap"):
        return value
    return Paragraph(str(value), style)


def make_table(data, widths, s, left_cols=()):
    wrapped = []
    for r, row in enumerate(data):
        out = []
        for c, value in enumerate(row):
            style = s["header"] if r == 0 else (s["table_left"] if c in left_cols else s["table"])
            out.append(fmt_cell(value, style))
        wrapped.append(out)
    t = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "CN"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C2CC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(14 * mm, 8 * mm, "杰华特业绩预测研报 | 2026-07-08")
    canvas.drawRightString(264 * mm, 8 * mm, str(doc.page))
    canvas.restoreState()


def build():
    register_fonts()
    s = make_styles()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(OUT),
        pagesize=landscape(letter),
        leftMargin=13 * mm,
        rightMargin=13 * mm,
        topMargin=11 * mm,
        bottomMargin=13 * mm,
        title="杰华特业绩预测研报",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    story = []
    story.append(p("杰华特（688141.SH）业绩预测研报", s["title"]))
    story.append(p("日期：2026-07-08　评级结论：<b>买入，定义为“潜力股”，不是短期利润兑现型标的。</b>", s["subtitle"]))

    story.append(p("1. 核心判断", s["h1"]))
    story.append(p("<b>杰华特当前的核心机会不在 2026 年利润，而在 2027 年扭亏与 2028 年 AI 服务器电源产品的利润弹性。</b> 2025 年和 2026Q1 收入增长已经验证需求，但 2026Q1 毛利率仍低、净利润仍亏，说明利润兑现尚未被财务报表验证。", s["body"]))
    story.append(p("本文采用稳健口径：以国信证券和东吴证券的一致预期为锚，再用 AceCamp 专家纪要修正。2026-07-06 版本中 2026E 收入 58-70 亿元的激进外推，不作为本报告基准，只作为超乐观情形参考。", s["body"]))

    story.append(p("2. 口径校验", s["h1"]))
    story.append(p("financial_reports 中 2025Q4 更接近全年/年报累计口径，而不是单四季度口径。2025Q4 收入 26.55 亿元、SQLite 净利润 -7.52 亿元；国信证券披露 2025 年收入 26.55 亿元、归母净利润 -7.17 亿元，收入一致，利润存在“净利润 vs 归母净利润”口径差异 [来源: SQLite financial_reports；broker_report/464a34af07da · 2026-04-02]。", s["body"]))
    story.append(p("2026Q1 财务看板显示收入 7.65 亿元，同比增长 44.8%；净利润 -2.93 亿元；毛利率 25.32%，同比下降 14.7pct [来源: mcp__ira.financial_dashboard · 2026Q1]。<b>口径结论：历史锚点使用 SQLite 财务库；未来预测统一采用券商归母净利润口径。</b>", s["body"]))

    story.append(p("3. 业绩总表", s["h1"]))
    red = '<font color="#B91C1C"><b>{}</b></font>'
    green = '<font color="#15803D"><b>{}</b></font>'
    perf = [
        ["期间", "一致预期或实际锚点（营收/净利润）", "纪要修正后预测（营收/净利润）", "修正值（Δ营收/Δ净利润）", "判断"],
        ["2025A 实际", "26.55 亿 / -7.52 亿", "实际锚点，不修正", "-", "收入高增但亏损扩大，利润未兑现 [来源: SQLite financial_reports]"],
        ["2026Q1 实际", "7.65 亿 / -2.93 亿", "实际锚点，不修正", "-", "收入同比 +44.8%，毛利率 25.32%，仍是验证期 [来源: mcp__ira.financial_dashboard]"],
        ["2026E 短期", "40.56 亿 / -3.82 亿", "43.00 亿 / -3.90 亿", green.format("+2.44 亿 ▲6.0%") + " / " + red.format("-0.08 亿 ▼2.1%"), "收入小幅上修，利润略谨慎"],
        ["2027E 中期", "62.26 亿 / 3.41 亿", "71.50 亿 / 6.00 亿", green.format("+9.24 亿 ▲14.8%") + " / " + green.format("+2.59 亿 ▲76.0%"), "非华为客户和产能释放带来上修"],
        ["2028E 长期", "92.47 亿 / 11.94 亿", "100.00 亿 / 12.50 亿", green.format("+7.53 亿 ▲8.1%") + " / " + green.format("+0.56 亿 ▲4.7%"), "维持中间偏乐观，但不直接采用东吴上沿"],
    ]
    story.append(make_table(perf, [25 * mm, 46 * mm, 46 * mm, 48 * mm, 88 * mm], s, left_cols=(4,)))
    story.append(p("注：2026-2028E 一致预期为国信证券与东吴证券预测均值；纪要修正后预测采用基准区间中点。PDF 内使用 ▲/▼ 渲染以保证兼容，Markdown 原文保留 🔼/🔽。", s["small"]))

    story.append(PageBreak())
    story.append(p("4. 券商观点来源表", s["h1"]))
    brokers = [
        ["研报", "日期", "核心预测与评级", "作为一致预期的角色"],
        ["国信证券《2025年收入增长58%，高研发投入拖累利润》", "2026-04-02", "2026-2028E 收入 36.60/48.75/63.27 亿，归母净利 -2.75/0.60/2.48 亿，维持“优于大市” [来源: broker_report/c295f1fe05c9]", "保守下沿"],
        ["东吴证券《乘国产算力芯片之风，平台型模拟龙头展DrMOS宏图》", "2026-06-14", "2026-2028E 收入 44.51/75.77/121.66 亿，归母净利 -4.88/6.22/21.40 亿，首次覆盖“买入” [来源: 东吴证券PDF/pdftotext]", "乐观上沿"],
    ]
    story.append(make_table(brokers, [62 * mm, 28 * mm, 105 * mm, 58 * mm], s, left_cols=(0, 2)))
    story.append(p("样本说明：本地可验证、直接覆盖杰华特且包含 2026-2028E 预测的核心研报为 2 篇。行业报告可提供产业趋势证据，但不纳入公司三年业绩一致预期均值。", s["body"]))

    story.append(p("5. 纪要证据与修正逻辑", s["h1"]))
    minutes = [
        ["纪要变量", "纪要证据", "对业绩预测的修正"],
        ["华为占比提升", "2026 年华为收入占比预计从历史约 1/4 提升至约 1/3 [来源: acecamp_expert_column/f15f36da8b0e · 2026-07-06]", "2026E 收入向卖方上沿靠近，营收 " + green.format("+2.44 亿 ▲6.0%")],
        ["非华为客户滞后", "非华为客户多数仍在评估，预计 2026Q4 才开始规模化放量 [来源: acecamp_expert_column/f15f36da8b0e · 2026-07-06]", "2026E 利润不激进上修，净利 " + red.format("-0.08 亿 ▼2.1%")],
        ["华为低价", "华为专用料号价格显著低于同规格通用型号 [来源: acecamp_expert_column/f15f36da8b0e · 2026-07-06]", "压制 2026 毛利率和净利率"],
        ["产能扩张", "当前 DrMOS 月投入约 6000 片晶圆、月产能约 1800 万颗；2026Q3/Q4 新增数千片，2027Q1/Q2 进一步增长 [来源: acecamp_expert_column/279aee744bbf · 2026-06-23，hot，source_weight=1.2]", "2027E 收入和净利上修，净利 " + green.format("+2.59 亿 ▲76.0%")],
        ["新客户导入", "新客户最快 2026 年 10-11 月小批量供货，显著增长主要体现在 2027 年 [来源: acecamp_expert_column/be1d1ebe905d · 2026-05-15，hot，source_weight=1.2]", "2027 年是关键兑现窗口"],
    ]
    story.append(make_table(minutes, [35 * mm, 126 * mm, 92 * mm], s, left_cols=(1, 2)))
    story.append(p("<b>核心修正句：2026 年只上修收入、不上修利润；2027-2028 年在产能释放和非华为客户导入支撑下，上修收入和利润，但 2028 年不直接采用东吴极乐观上沿。</b>", s["body"]))

    story.append(PageBreak())
    story.append(p("6. 推理链", s["h1"]))
    story.append(p("已验证事实：2025 年收入 26.55 亿元，2026Q1 收入 7.65 亿元且同比 +44.8%，说明需求和客户导入不是空转 [来源: SQLite financial_reports；mcp__ira.financial_dashboard]。", s["body"]))
    story.append(p("直接推论：收入端具备继续接近卖方上沿的条件，但 2026Q1 毛利率仅 25.32%、净利润仍亏 2.93 亿元，说明利润释放还没有被财报验证 [来源: mcp__ira.financial_dashboard]。", s["body"]))
    story.append(p("纪要修正：华为放量支撑 2026 收入；华为低价和非华为客户滞后压制 2026 利润；产能扩张和新客户 2026Q4 起放量支撑 2027-2028 弹性 [来源: acecamp_expert_column/f15f36da8b0e；279aee744bbf；be1d1ebe905d]。", s["body"]))
    story.append(p("<b>更高层结论：杰华特不是 2026 年利润股，而是 2027 年扭亏、2028 年利润弹性的潜力股。</b>", s["body"]))

    story.append(p("7. 一致预期对比与评级", s["h1"]))
    story.append(p("短期 0-6 个月：低于利润想象。2026Q1 仍亏，毛利率低，非华为客户尚未规模化，因此短期不定义为利润兑现。", s["body"]))
    story.append(p("中期 6-12 个月：收入接近上沿，利润仍需验证。若 2026H2 毛利率回到 28%-30%，且非华为客户开始小批量转批量，利润预测可继续上修。", s["body"]))
    story.append(p("长期 1-2 年：高于一致预期。2027-2028 年产能释放、客户扩散、产品结构改善三者共振，修正后预测高于卖方均值。", s["body"]))
    story.append(p("<b>评级结论：买入，潜力股。</b> 理由：长期修正后预测高于一致预期，但短期和中期没有全面超预期，因此不定义为“大牛股”。", s["body"]))

    story.append(p("8. 风险与机会", s["h1"]))
    story.append(p("机会：华为 DrMOS 放量；非华为算力客户 2026Q4 起放量；2026H2-2027H1 产能新增；研发费率随收入放大摊薄。", s["body"]))
    story.append(p("风险：华为专用料号低价压制毛利率；非华为客户导入延期；国产竞争者跟进引发价格战；研发费用率下降慢于预期；产能、封测、可靠性验证不及预期。", s["body"]))

    story.append(p("9. 核心跟踪指标", s["h1"]))
    tracking = [
        ["指标", "看多信号", "看空信号"],
        ["2026H2 毛利率", "回到 28%-30%", "继续低于 27%"],
        ["非华为客户", "2026Q4 小批量转批量", "仍停留评估"],
        ["DrMOS 价格", "非华为高价订单占比提升", "华为低价订单占比继续上升"],
        ["研发费率", "随收入放大明显下降", "继续高位吞噬毛利"],
        ["现金流", "经营现金流亏损收窄", "高库存、高应收、高投入同时扩张"],
    ]
    story.append(make_table(tracking, [50 * mm, 102 * mm, 101 * mm], s, left_cols=()))

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
