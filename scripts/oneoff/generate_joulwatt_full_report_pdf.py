from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "joulwatt_full_report_20260703.pdf"


def register_font():
    pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="CN", fontSize=22, leading=28, textColor=colors.HexColor("#17324D"), alignment=TA_LEFT, spaceAfter=5),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName="CN", fontSize=9, leading=13, textColor=colors.HexColor("#5E6A72"), spaceAfter=11),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="CN", fontSize=14, leading=18, textColor=colors.HexColor("#17324D"), spaceBefore=11, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="CN", fontSize=11.3, leading=15, textColor=colors.HexColor("#17324D"), spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="CN", fontSize=9.0, leading=13.4, textColor=colors.HexColor("#263238"), spaceAfter=5),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName="CN", fontSize=7.4, leading=10, textColor=colors.HexColor("#65737B"), spaceAfter=3),
        "tag": ParagraphStyle("tag", parent=base["BodyText"], fontName="CN", fontSize=8.2, leading=10.5, textColor=colors.white, alignment=TA_CENTER),
        "callout": ParagraphStyle("callout", parent=base["BodyText"], fontName="CN", fontSize=9.2, leading=13.5, textColor=colors.HexColor("#17324D"), spaceAfter=4),
    }


def p(text, style):
    return Paragraph(text, style)


def wrap(data, font_size=8.0):
    th = ParagraphStyle("th", fontName="CN", fontSize=font_size, leading=font_size + 3, textColor=colors.white, alignment=TA_CENTER)
    td = ParagraphStyle("td", fontName="CN", fontSize=font_size, leading=font_size + 3, textColor=colors.black, alignment=TA_CENTER)
    rows = []
    for i, row in enumerate(data):
        st = th if i == 0 else td
        rows.append([cell if hasattr(cell, "wrap") else Paragraph(str(cell), st) for cell in row])
    return rows


def table(data, widths, font_size=8.0, repeat=1):
    t = Table(wrap(data, font_size), colWidths=widths, repeatRows=repeat, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "CN"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DEE3")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7F9")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#6B7780"))
    canvas.drawString(16 * mm, 10 * mm, "杰华特完整研报 | 仅供研究讨论，不构成投资建议")
    canvas.drawRightString(194 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def add_summary(story, s):
    story += [
        p("杰华特（688141.SH）完整预测研报", s["title"]),
        p("日期：2026-07-03 | 数据底座：AlphaSonar MCP / SQLite financial_reports / 本地研报切片", s["subtitle"]),
    ]
    rows = [
        [p("评级", s["tag"]), p("中性偏多。2026 年仍处亏损修复期，2027 年看扭亏，2028 年看 AI 服务器电源利润弹性。", s["callout"])],
        [p("核心预测", s["tag"]), p("基准情景：2026E 营收 42-45 亿、净利 -5 至 -3 亿；2027E 营收 58-65 亿、净利 1-5 亿；2028E 营收 80-95 亿、净利 7-13 亿。", s["callout"])],
        [p("主要矛盾", s["tag"]), p("收入增长已被财务数据验证，但利润释放仍取决于毛利率修复和研发费率摊薄。订单放量不等于利润释放。", s["callout"])],
    ]
    t = Table(rows, colWidths=[24 * mm, 150 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "CN"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2E5E7E")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#EEF4F7")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DEE3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [t, Spacer(1, 7)]


def build():
    register_font()
    s = styles()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm, title="杰华特完整预测研报", author="Codex")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])
    story = []

    add_summary(story, s)

    story.append(p("1. 投资结论：看 2027 年扭亏，看 2028 年弹性", s["h1"]))
    story.append(p("杰华特当前的核心定价变量不是 2026 年当期利润，而是 2027 年是否完成扭亏，以及 2028 年 AI 服务器电源产品能否带来利润弹性。公司已经通过收入增长证明客户导入和需求并非空转，但 2025 年和 2026Q1 仍显示利润端承压。", s["body"]))
    story.append(p("投资判断上，应把它视为“订单质量验证型”公司：若 DrMOS、多相控制器、大电流 DC-DC 在 AI 服务器客户侧持续放量，并且毛利率进入 30%以上区间，则 2027 年扭亏概率上升；若毛利率停留在 26%-28%，高收入增长也可能继续被研发投入和价格竞争吞噬。", s["body"]))

    story.append(p("2. MCP 财务数据：收入兑现，利润仍承压", s["h1"]))
    fin = [
        ["期间", "营收", "净利润", "收入趋势", "利润趋势"],
        ["2024Q4", "16.79亿", "-6.11亿", "年度收入基数形成", "亏损高位"],
        ["2025Q1", "5.28亿", "-1.15亿", "季度低点", "亏损较小"],
        ["2025Q2", "11.87亿", "-3.01亿", "环比恢复", "亏损扩大"],
        ["2025Q3", "19.42亿", "-4.67亿", "增长延续", "费用/毛利压力仍在"],
        ["2025Q4", "26.55亿", "-7.52亿", "全年高增兑现", "亏损扩大"],
        ["2026Q1", "7.65亿", "-2.93亿", "同比 +44.8%", "环比亏损收窄 61.0%"],
    ]
    story.append(table(fin, [22 * mm, 28 * mm, 28 * mm, 50 * mm, 46 * mm], font_size=7.8))
    story.append(p("数据含义：收入端已经从 2025 年开始持续放大，说明订单和客户导入正在兑现；但净利润持续为负，说明公司仍处高研发、高竞争、产品结构爬坡阶段。", s["body"]))

    story.append(p("3. 业务结构：AI 服务器电源是核心上修方向", s["h1"]))
    biz = [
        ["业务方向", "当前状态", "订单含义", "对利润的影响"],
        ["AI 服务器电源", "DrMOS、多相控制器、大电流 DC-DC 是关键主线", "决定未来 2-3 年上修空间", "若产品占比提升，毛利率有修复空间"],
        ["H 客户", "调研线索显示为 2025 放量主线", "短期最重要需求来源", "持续放量利好，但需防单一客户依赖"],
        ["车规产品", "车规 DrMOS、eFuse、PMIC 量产/送样推进", "中期订单储备", "兑现节奏慢，但生命周期更优"],
        ["信号链", "2025 年收入快速增长", "第二增长曲线", "改善产品平台完整度"],
        ["传统电源管理", "收入基盘", "提供规模支撑", "价格竞争可能压制毛利"],
    ]
    story.append(table(biz, [32 * mm, 49 * mm, 46 * mm, 47 * mm], font_size=7.5))

    story.append(PageBreak())
    story.append(p("4. 三情景业绩预测", s["h1"]))
    forecasts = [
        ["情景", "2026E", "2027E", "2028E", "触发条件"],
        ["保守", "营收 36-38亿 / 净利 -6.5至-5亿", "营收 48-52亿 / 净利 -2至0亿", "营收 63-70亿 / 净利 2-4亿", "毛利率修复慢，AI 服务器订单不及预期，研发费率高位"],
        ["基准", "营收 42-45亿 / 净利 -5至-3亿", "营收 58-65亿 / 净利 1-5亿", "营收 80-95亿 / 净利 7-13亿", "H 客户延续放量，毛利率上 30%，研发费率下降"],
        ["乐观", "营收 48-52亿 / 净利 -2至0亿", "营收 75-85亿 / 净利 8-12亿", "营收 110-125亿 / 净利 18-24亿", "DrMOS/多相控制器进入 AI 服务器大客户，车规与信号链同步放量"],
    ]
    story.append(table(forecasts, [16 * mm, 38 * mm, 38 * mm, 38 * mm, 44 * mm], font_size=7.0))
    story.append(p("本文采用基准情景作为主判断：2026 年亏损收窄，2027 年进入扭亏窗口，2028 年利润开始释放。乐观情景需要更多客户扩散和更快毛利率修复，目前尚不能作为主情景。", s["body"]))

    story.append(p("5. 盈利弹性拆解：毛利率比收入更关键", s["h1"]))
    sensitivity = [
        ["变量", "低情景", "基准情景", "高情景", "判断"],
        ["2026 收入", "36-38亿", "42-45亿", "48-52亿", "收入上修来自 AI 服务器订单"],
        ["2026 毛利率", "26%-28%", "30%-32%", "33%以上", "毛利率决定亏损收窄速度"],
        ["2026 研发费率", "33%以上", "26%-29%", "25%以下", "费用率摊薄决定经营杠杆"],
        ["2027 净利率", "0%以下", "2%-8%", "10%以上", "产品结构决定扭亏质量"],
    ]
    story.append(table(sensitivity, [34 * mm, 34 * mm, 34 * mm, 34 * mm, 38 * mm], font_size=7.5))
    story.append(p("敏感性结论：收入增速只是必要条件，毛利率和研发费率才是充分条件。若 2026H2 毛利率不能站上 30%，则 2027 年扭亏需要明显下修。", s["body"]))

    story.append(p("6. 订单判断：已有收入兑现，但大单金额未公告", s["h1"]))
    story.append(p("公司没有公开披露明确在手订单金额，因此不能把调研线索直接当作公告订单。当前能确认的是：2025 年收入高增，2026Q1 营收同比继续增长，说明订单已部分体现在收入中；但 AI 服务器订单的客户份额、持续性和毛利率仍需后续财报验证。", s["body"]))
    order_check = [
        ["订单层级", "可确认程度", "当前判断", "需要验证"],
        ["已确认收入", "高", "2025 年至 2026Q1 收入放量", "收入是否持续环比改善"],
        ["H 客户放量", "中", "调研线索显示为主线", "客户收入占比与毛利率"],
        ["其他国产服务器客户", "中低", "处于导入/验证逻辑", "是否进入批量出货"],
        ["海外客户", "低", "小批量或资格阶段", "是否形成持续订单"],
    ]
    story.append(table(order_check, [32 * mm, 28 * mm, 57 * mm, 57 * mm], font_size=7.5))

    story.append(PageBreak())
    story.append(p("7. 估值框架：亏损期更适合 PS 与情景估值", s["h1"]))
    story.append(p("由于 2026 年仍可能亏损，PE 估值参考意义有限。更合理的方法是用 PS 或 2028 年利润情景折现。若采用收入框架，关键是判断 2027-2028 年收入能否站上 60 亿、80 亿两个台阶；若采用利润框架，核心是 2028 年净利率能否达到 8%-14%。", s["body"]))
    val = [
        ["框架", "适用阶段", "核心变量", "解释"],
        ["PS", "2026-2027 亏损/扭亏期", "收入增速与订单确定性", "适合收入高增但利润未释放阶段"],
        ["PE", "2028 后利润释放期", "净利润与净利率", "需等利润稳定转正后更有效"],
        ["情景估值", "当前", "AI 服务器订单 + 毛利率", "适合不确定性较高的弹性资产"],
    ]
    story.append(table(val, [30 * mm, 42 * mm, 46 * mm, 56 * mm], font_size=7.8))

    story.append(p("8. 催化剂与证伪条件", s["h1"]))
    cats = [
        ["类型", "事件", "影响"],
        ["催化", "披露 AI 服务器电源批量客户或订单进展", "上修 2027-2028 收入与利润"],
        ["催化", "2026H2 毛利率站上 30%", "扭亏时间表前移"],
        ["催化", "车规产品从送样进入量产", "增强第二增长曲线"],
        ["证伪", "毛利率停留在 26%-28%", "收入增长难以转化为利润"],
        ["证伪", "研发费率仍高于 33%", "经营杠杆不足"],
        ["证伪", "经营现金流未随收入改善", "订单质量存疑"],
    ]
    story.append(table(cats, [28 * mm, 90 * mm, 56 * mm], font_size=7.6))

    story.append(p("9. 风险提示", s["h1"]))
    risks = [
        ["风险", "说明", "跟踪指标"],
        ["客户集中", "若 H 客户贡献过高，订单波动会放大利润波动", "前五大客户占比、单季收入波动"],
        ["价格竞争", "通用电源管理芯片竞争激烈，可能压制毛利率", "季度毛利率、存货跌价"],
        ["研发投入刚性", "高研发强度短期压制净利", "研发费用率"],
        ["产品导入不及预期", "服务器和车规客户验证周期可能拉长", "新客户量产公告、收入结构"],
        ["现金流压力", "收入增长若伴随应收和库存扩张，质量下降", "经营现金流、存货周转"],
    ]
    story.append(table(risks, [34 * mm, 88 * mm, 52 * mm], font_size=7.4))

    story.append(p("10. 跟踪清单", s["h1"]))
    checks = [
        ["优先级", "指标", "判断标准"],
        ["高", "毛利率", "2026H2 是否站上 30%；低于 28% 则下修"],
        ["高", "研发费率", "是否降至 30%以下；高于 33% 则扭亏后移"],
        ["高", "AI 服务器订单", "是否披露批量客户或收入结构"],
        ["中", "经营现金流", "是否随收入改善"],
        ["中", "存货减值", "是否继续扩大"],
        ["中", "车规进展", "送样是否进入量产收入"],
    ]
    story.append(table(checks, [22 * mm, 48 * mm, 104 * mm], font_size=7.8))

    story.append(PageBreak())
    story.append(p("11. 证据链与口径说明", s["h1"]))
    story.append(p("MCP text2sql：2024Q4-2026Q1 营收与净利润来自 SQLite financial_reports。", s["body"]))
    story.append(p("MCP financial_dashboard：2026Q1 营收 7.65 亿元，同比 +44.8%；净利润 -2.93 亿元，环比亏损收窄 61.0%。", s["body"]))
    story.append(p("MCP graph_propagation：DrMOS 对应公司为杰华特，产品归类为模拟芯片。", s["body"]))
    story.append(p("本地研报切片：国信证券预测偏保守，东吴证券预测偏乐观；本文采用中间基准情景，原因是收入弹性已有线索，但利润释放仍受毛利率、研发费率和客户结构制约。", s["body"]))
    story.append(p("口径提醒：SQLite financial_reports 的 net_profit 为净利润口径；部分券商报告使用归母净利润口径，两者不完全等同。本文预测表以归母净利润/净利润近似区间表达，实际跟踪应以公司正式财报口径为准。", s["small"]))

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
