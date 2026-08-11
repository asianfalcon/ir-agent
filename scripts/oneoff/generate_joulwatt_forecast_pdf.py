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
OUT = ROOT / "output" / "pdf" / "joulwatt_forecast_report_20260703.pdf"


def register_fonts():
    pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="CN",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#17324D"),
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="CN",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#52616B"),
            spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="CN",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="CN",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=9.5,
            leading=14.5,
            textColor=colors.HexColor("#263238"),
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#5F6C72"),
            spaceAfter=3,
        ),
        "tag": ParagraphStyle(
            "tag",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def p(text, style):
    return Paragraph(text, style)


def wrap_cells(data, font_size):
    header_style = ParagraphStyle(
        "table_header",
        fontName="CN",
        fontSize=font_size,
        leading=font_size + 3,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    body_style = ParagraphStyle(
        "table_body",
        fontName="CN",
        fontSize=font_size,
        leading=font_size + 3,
        textColor=colors.black,
        alignment=TA_CENTER,
    )
    wrapped = []
    for r, row in enumerate(data):
        style = header_style if r == 0 else body_style
        wrapped.append([cell if hasattr(cell, "wrap") else Paragraph(str(cell), style) for cell in row])
    return wrapped


def make_table(data, col_widths, header_rows=1, font_size=8.6, align="CENTER"):
    table = Table(wrap_cells(data, font_size), colWidths=col_widths, repeatRows=header_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "CN"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 3),
                ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), align),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DEE3")),
                ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#6B7780"))
    canvas.drawString(18 * mm, 10 * mm, "杰华特预测型研报 | 仅供研究讨论，不构成投资建议")
    canvas.drawRightString(192 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def build():
    register_fonts()
    s = styles()

    doc = BaseDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="杰华特预测型研报",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])

    story = []
    story += [
        p("杰华特（688141.SH）预测型研报", s["title"]),
        p("日期：2026-07-03 | 主题：未来三年业绩预测、关键假设与验证指标", s["subtitle"]),
    ]

    summary = [
        [p("核心评级", s["tag"]), p("中性偏多：2026 仍承压，2027 扭亏，2028 利润弹性释放", s["body"])],
        [p("预测主线", s["tag"]), p("AI 服务器电源产品放量 + 毛利率修复 + 研发费率摊薄，是未来三年业绩上修的核心。", s["body"])],
        [p("最大分歧", s["tag"]), p("收入增长确定性强于利润确定性。若 2026H2 毛利率不能站上 30%，扭亏将后移。", s["body"])],
    ]
    t = Table(summary, colWidths=[28 * mm, 146 * mm], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "CN"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2E5E7E")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#EEF4F7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7DEE3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 8))

    story.append(p("1. 业绩预测：三情景模型", s["h1"]))
    forecast = [
        ["情景", "2026E 营收/归母净利", "2027E 营收/归母净利", "2028E 营收/归母净利", "核心触发条件"],
        ["保守", "36-38亿 / -6.5至-5亿", "48-52亿 / -2至0亿", "63-70亿 / 2-4亿", "毛利率低于30%，AI服务器产品放量慢，费用率下降不及预期"],
        ["基准", "42-45亿 / -5至-3亿", "58-65亿 / 1-5亿", "80-95亿 / 7-13亿", "毛利率逐步修复，研发费率降至约27%/21%/19%"],
        ["乐观", "48-52亿 / -2至0亿", "75-85亿 / 8-12亿", "110-125亿 / 18-24亿", "DrMOS/多相控制器进入AI服务器大客户，车规与信号链同步放量"],
    ]
    story.append(make_table(forecast, [18 * mm, 34 * mm, 34 * mm, 34 * mm, 54 * mm], font_size=7.6))
    story.append(Spacer(1, 4))
    story.append(
        p(
            "预测结论：杰华特 2026 年仍处于投入兑现前夜，2027 年是盈亏平衡窗口，2028 年利润弹性取决于高端电源产品和车规产品占比。基准情景下，2028 年净利率约 8%-14%。",
            s["body"],
        )
    )

    story.append(p("2. 基准预测拆解", s["h1"]))
    model = [
        ["指标", "2025A", "2026E", "2027E", "2028E", "预测含义"],
        ["营业收入", "26.55亿", "42-45亿", "58-65亿", "80-95亿", "AI服务器电源、车规、信号链驱动"],
        ["收入增速", "+58.15%", "+58%-70%", "+35%-50%", "+30%-45%", "高基数后增速回落但仍高于行业均值"],
        ["毛利率", "26.37%", "30%-32%", "34%-36%", "36%-38%", "产品结构改善是扭亏关键"],
        ["研发费率", "36.06%", "26%-29%", "20%-23%", "18%-20%", "不靠砍研发，靠收入摊薄"],
        ["归母净利", "-7.17亿", "-5至-3亿", "1-5亿", "7-13亿", "2027 年进入扭亏观察期"],
    ]
    story.append(make_table(model, [24 * mm, 25 * mm, 27 * mm, 27 * mm, 27 * mm, 44 * mm], font_size=7.8))

    story.append(p("3. 为什么 2027 年是拐点", s["h1"]))
    story.append(
        p(
            "收入端：2026Q1 已实现收入 7.65 亿元，同比增长 44.8%，说明公司需求和客户导入仍在扩张。若季度收入维持环比改善，全年收入达到 42-45 亿元具备可解释性。",
            s["body"],
        )
    )
    story.append(
        p(
            "毛利端：2025 年毛利率仅 26.37%，主要受价格竞争和产品结构影响。扭亏不要求毛利率回到海外龙头水平，但至少需要 2026H2 站上 30%，2027 年接近 35%。",
            s["body"],
        )
    )
    story.append(
        p(
            "费用端：2025 年研发费用 9.57 亿元，研发费率 36.06%。若研发费用保持投入、但收入扩大到 60 亿元附近，研发费率自然下行，利润表会出现明显经营杠杆。",
            s["body"],
        )
    )

    story.append(PageBreak())
    story.append(p("4. 上修与下修变量", s["h1"]))
    updown = [
        ["方向", "变量", "对业绩的影响", "观察方式"],
        ["上修", "AI服务器 DrMOS/多相控制器放量", "提高收入天花板，并改善毛利率", "服务器客户批量出货、单季收入加速"],
        ["上修", "车规 DrMOS、eFuse、PMIC 量产", "增强收入稳定性，提高产品生命周期质量", "车规认证与量产客户数量"],
        ["上修", "信号链芯片持续扩张", "降低单一电源管理依赖，改善综合毛利", "信号链收入占比与毛利率"],
        ["下修", "价格竞争持续", "毛利率停留在 26%-28%，扭亏延后", "季度毛利率、存货跌价准备"],
        ["下修", "研发费用继续高增", "收入增长无法传导为利润", "研发费率是否低于 30%"],
        ["下修", "客户导入慢于预期", "东吴乐观情景难以兑现", "送样到量产节奏、订单披露"],
    ]
    story.append(make_table(updown, [18 * mm, 45 * mm, 61 * mm, 50 * mm], font_size=7.8))

    story.append(p("5. 和卖方预测的差异", s["h1"]))
    compare = [
        ["机构/模型", "2026E营收", "2027E营收", "2028E营收", "2026E净利", "2027E净利", "2028E净利"],
        ["国信证券", "36.6亿", "48.8亿", "63.3亿", "-2.75亿", "0.60亿", "2.48亿"],
        ["东吴证券", "44.5亿", "75.8亿", "121.7亿", "-4.88亿", "6.22亿", "21.40亿"],
        ["本文基准", "42-45亿", "58-65亿", "80-95亿", "-5至-3亿", "1-5亿", "7-13亿"],
    ]
    story.append(make_table(compare, [25 * mm, 25 * mm, 25 * mm, 25 * mm, 25 * mm, 25 * mm, 24 * mm], font_size=7.8))
    story.append(
        p(
            "解释：本文采用中间情景。收入端认可东吴对 AI 服务器电源的弹性判断，但利润端保留国信对高研发投入和价格竞争的谨慎假设。",
            s["body"],
        )
    )

    story.append(p("6. 投资结论", s["h1"]))
    story.append(
        p(
            "短期看，杰华特不是 2026 年利润型资产，而是 2027 年扭亏期权。中期看，若 AI 服务器电源链验证成功，2028 年利润弹性可能显著高于当前线性外推。最关键的交易验证点是：2026H2 毛利率能否站上 30%，研发费率能否进入 30%以下区间。",
            s["body"],
        )
    )

    story.append(p("7. 关键跟踪清单", s["h1"]))
    checklist = [
        ["优先级", "指标", "判断标准"],
        ["高", "季度毛利率", "2026H2 是否站上 30%；若低于 28%，下修利润"],
        ["高", "研发费率", "2026 是否降至 30%以内；若仍高于 33%，扭亏后移"],
        ["高", "AI服务器产品", "DrMOS/多相控制器是否出现明确批量客户"],
        ["中", "经营现金流", "收入增长是否伴随回款改善"],
        ["中", "存货减值", "若继续扩大，说明价格和产品迭代压力仍大"],
    ]
    story.append(make_table(checklist, [20 * mm, 54 * mm, 100 * mm], font_size=8))

    story.append(p("8. 证据来源", s["h1"]))
    story.append(
        p(
            "1）本地 SQLite financial_reports：688141.SH 2025Q4 收入 26.55 亿元、归母净利润 -7.52 亿元；2026Q1 收入 7.65 亿元、净利润 -2.93 亿元。注：SQLite 字段 net_profit 为净利润口径，研报归母口径为 -7.17 亿元。",
            s["small"],
        )
    )
    story.append(
        p(
            "2）国信证券《杰华特：2025年收入增长58%，高研发投入拖累利润》（2026-04-02）：2026-2028E 营收 36.6/48.8/63.3 亿元，归母净利 -2.75/0.60/2.48 亿元。",
            s["small"],
        )
    )
    story.append(
        p(
            "3）东吴证券《杰华特：乘国产算力芯片之风，平台型模拟龙头展DrMOS宏图》（2026-06-14）：2026-2028E 营收 44.5/75.8/121.7 亿元，归母净利 -4.88/6.22/21.40 亿元。",
            s["small"],
        )
    )
    story.append(
        p(
            "4）公开公告与研报摘要：2025 年毛利率 26.37%、研发费用 9.57 亿元、研发费率 36.06%；2026Q1 收入同比 +44.8%。",
            s["small"],
        )
    )

    doc.build(story)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build()
    print(OUT)
