from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "joulwatt_mcp_brief_report_20260703.pdf"


def register_font():
    pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="CN",
            fontSize=21,
            leading=27,
            textColor=colors.HexColor("#17324D"),
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="CN",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#5E6A72"),
            spaceAfter=10,
        ),
        "h": ParagraphStyle(
            "h",
            parent=base["Heading1"],
            fontName="CN",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=9.0,
            leading=13.2,
            textColor=colors.HexColor("#263238"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=7.4,
            leading=10.0,
            textColor=colors.HexColor("#65737B"),
            spaceAfter=3,
        ),
        "tag": ParagraphStyle(
            "tag",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=8.2,
            leading=10.5,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def para(text, style):
    return Paragraph(text, style)


def wrap_table(data, font_size=8.2):
    header = ParagraphStyle("th", fontName="CN", fontSize=font_size, leading=font_size + 3, textColor=colors.white, alignment=TA_CENTER)
    body = ParagraphStyle("td", fontName="CN", fontSize=font_size, leading=font_size + 3, textColor=colors.black, alignment=TA_CENTER)
    rows = []
    for i, row in enumerate(data):
        st = header if i == 0 else body
        rows.append([cell if hasattr(cell, "wrap") else Paragraph(str(cell), st) for cell in row])
    return rows


def table(data, widths, font_size=8.2):
    t = Table(wrap_table(data, font_size), colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "CN"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DEE3")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7F9")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#6B7780"))
    canvas.drawString(16 * mm, 10 * mm, "杰华特 MCP 简明研报 | 仅供研究讨论，不构成投资建议")
    canvas.drawRightString(194 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def build():
    register_font()
    s = make_styles()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="杰华特 MCP 简明研报",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    story = [
        para("杰华特（688141.SH）MCP 简明研报", s["title"]),
        para("日期：2026-07-03 | 数据底座：ir-agent MCP / SQLite financial_reports / 本地研报切片", s["subtitle"]),
    ]

    thesis = [
        [para("核心结论", s["tag"]), para("中性偏多。2026 年仍亏，2027 年看扭亏，2028 年看 AI 服务器电源利润弹性。", s["body"])],
        [para("投资主线", s["tag"]), para("DrMOS / 多相控制器 / 大电流 DC-DC 放量，叠加毛利率修复和研发费率摊薄。", s["body"])],
        [para("最大风险", s["tag"]), para("订单放量不等于利润释放。若毛利率停在 26%-28%，扭亏将后移。", s["body"])],
    ]
    t = Table(thesis, colWidths=[27 * mm, 147 * mm], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "CN"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2E5E7E")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#EEF4F7")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DEE3")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [t, Spacer(1, 6)]

    story.append(para("1. MCP 硬数据", s["h"]))
    data = [
        ["期间", "营收", "净利润", "说明"],
        ["2024Q4", "16.79亿", "-6.11亿", "全年收入基数形成"],
        ["2025Q1", "5.28亿", "-1.15亿", "季度低点"],
        ["2025Q2", "11.87亿", "-3.01亿", "收入环比恢复"],
        ["2025Q3", "19.42亿", "-4.67亿", "增长延续"],
        ["2025Q4", "26.55亿", "-7.52亿", "年度高增但亏损扩大"],
        ["2026Q1", "7.65亿", "-2.93亿", "营收同比 +44.8%，亏损环比收窄 61.0%"],
    ]
    story.append(table(data, [24 * mm, 31 * mm, 31 * mm, 88 * mm], font_size=8))

    story.append(para("2. 未来三年预测", s["h"]))
    forecast = [
        ["情景", "2026E", "2027E", "2028E", "判断"],
        ["保守", "营收 36-38亿 / 净利 -6.5至-5亿", "营收 48-52亿 / 净利 -2至0亿", "营收 63-70亿 / 净利 2-4亿", "毛利率修复慢，AI 服务器订单不及预期"],
        ["基准", "营收 42-45亿 / 净利 -5至-3亿", "营收 58-65亿 / 净利 1-5亿", "营收 80-95亿 / 净利 7-13亿", "H 客户延续放量，研发费率下降"],
        ["乐观", "营收 48-52亿 / 净利 -2至0亿", "营收 75-85亿 / 净利 8-12亿", "营收 110-125亿 / 净利 18-24亿", "DrMOS/多相控制器进入 AI 服务器大客户"],
    ]
    story.append(table(forecast, [16 * mm, 39 * mm, 39 * mm, 39 * mm, 41 * mm], font_size=7.2))
    story.append(para("基准判断：2026 年仍亏，2027 年扭亏，2028 年利润放大。预测上修需要订单质量和毛利率同步改善。", s["body"]))

    story.append(para("3. 订单与验证", s["h"]))
    orders = [
        ["方向", "状态", "含义"],
        ["AI 服务器电源", "最关键订单主线", "DrMOS、多相控制器、大电流 DC-DC 决定上修空间"],
        ["H 客户", "调研线索显示为 2025 放量主线", "若持续放量，2027 扭亏概率提高；也需警惕单一客户依赖"],
        ["车规产品", "车规 DrMOS、eFuse、PMIC 量产/送样推进", "中期储备，兑现慢于服务器"],
        ["信号链", "2025 年收入已快速增长", "第二曲线，但当前不是最大订单来源"],
    ]
    story.append(table(orders, [34 * mm, 65 * mm, 75 * mm], font_size=7.8))

    story.append(para("4. 关键跟踪指标", s["h"]))
    checklist = [
        ["指标", "判断标准", "投资含义"],
        ["毛利率", "2026H2 是否站上 30%", "低于 28%，扭亏后移"],
        ["研发费率", "是否降至 30%以下", "费用率下降才有经营杠杆"],
        ["AI 服务器客户", "是否披露批量出货", "决定 2027-2028 上修空间"],
        ["经营现金流", "是否随收入改善", "验证订单质量"],
        ["存货减值", "是否继续扩大", "反映价格竞争和迭代压力"],
    ]
    story.append(table(checklist, [38 * mm, 72 * mm, 64 * mm], font_size=7.8))

    story.append(PageBreak())
    story.append(para("5. 证据链", s["h"]))
    story.append(para("MCP text2sql：2024Q4-2026Q1 营收与净利润来自 SQLite financial_reports。", s["small"]))
    story.append(para("MCP financial_dashboard：2026Q1 营收 7.65 亿元，同比 +44.8%；净利润 -2.93 亿元，环比亏损收窄 61.0%。", s["small"]))
    story.append(para("本地研报切片：国信证券与东吴证券分别提供保守与乐观盈利预测锚，本文采用中间基准情景。", s["small"]))

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
