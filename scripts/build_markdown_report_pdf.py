#!/usr/bin/env python3
"""Render a Chinese markdown research report to PDF with ReportLab."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "output/reports/joulwatt_research_report_v2_format_20260708.md"
DEFAULT_OUT = ROOT / "output/pdf/joulwatt_research_report_v2_format_20260708.pdf"


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Medium.ttc", subfontIndex=0))


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="CN",
            fontSize=21,
            leading=27,
            textColor=colors.HexColor("#0B2545"),
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=8.9,
            leading=12.6,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="CN",
            fontSize=14.5,
            leading=18,
            textColor=colors.HexColor("#183B59"),
            spaceBefore=9,
            spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="CN",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#0F766E"),
            spaceBefore=6,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=7.2,
            leading=9.8,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=3,
        ),
        "table": ParagraphStyle(
            "table",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=6.7,
            leading=8.9,
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
        ),
        "table_left": ParagraphStyle(
            "table_left",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=6.6,
            leading=8.8,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
        ),
        "header": ParagraphStyle(
            "header",
            parent=base["BodyText"],
            fontName="CN",
            fontSize=6.8,
            leading=9.0,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def xml_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_markup(text: str) -> str:
    text = xml_escape(text.strip())
    text = text.replace("🔼", "▲").replace("🔽", "▼")
    text = re.sub(r"`([^`]+)`", r'<font face="CN">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(▲[0-9.]+%|[+][0-9.]+ 亿 ▲[0-9.]+%|[+][0-9.]+亿 ▲[0-9.]+%)", r'<font color="#15803D"><b>\1</b></font>', text)
    text = re.sub(r"(▼[0-9.]+%|-[0-9.]+ 亿 ▼[0-9.]+%|-[0-9.]+亿 ▼[0-9.]+%)", r'<font color="#B91C1C"><b>\1</b></font>', text)
    return text


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(inline_markup(text), style)


def parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) >= 2 and all(set(c.strip()) <= {"-", ":"} for c in rows[1]):
        rows.pop(1)
    return rows


def col_widths(rows: list[list[str]]) -> list[float]:
    n = max(len(r) for r in rows)
    header = tuple(rows[0]) if rows else ()
    total = 253 * mm
    table_presets = {
        ("校验项", "结论", "证据"): [28 * mm, 52 * mm, 173 * mm],
        ("券商", "日期", "2026E营收", "2027E营收", "2028E营收", "2026E归母", "2027E归母", "2028E归母", "评级"): [
            17 * mm,
            19 * mm,
            21 * mm,
            21 * mm,
            21 * mm,
            21 * mm,
            21 * mm,
            21 * mm,
            90 * mm,
        ],
        ("项目", "2025A", "2026Q1", "2026E", "2027E", "2028E"): [
            34 * mm,
            36 * mm,
            36 * mm,
            49 * mm,
            49 * mm,
            49 * mm,
        ],
        ("项目", "判断", "证据与结论"): [34 * mm, 55 * mm, 164 * mm],
        ("情景", "概率", "触发条件", "业绩影响", "操作"): [28 * mm, 20 * mm, 83 * mm, 102 * mm, 20 * mm],
        ("关键跟踪点", "时间", "判断标准"): [38 * mm, 27 * mm, 188 * mm],
    }
    if header in table_presets:
        return table_presets[header]
    presets = {
        2: [62 * mm, 191 * mm],
        3: [34 * mm, 142 * mm, 77 * mm],
        4: [32 * mm, 74 * mm, 74 * mm, 73 * mm],
        5: [34 * mm, 25 * mm, 62 * mm, 70 * mm, 62 * mm],
        6: [25 * mm, 72 * mm, 22 * mm, 30 * mm, 24 * mm, 80 * mm],
        8: [21 * mm, 52 * mm, 15 * mm, 21 * mm, 23 * mm, 18 * mm, 31 * mm, 72 * mm],
    }
    return presets.get(n, [total / n] * n)


def make_table(rows: list[list[str]], st: dict[str, ParagraphStyle]) -> Table:
    n = max(len(r) for r in rows)
    normalized = [r + [""] * (n - len(r)) for r in rows]
    wrapped = []
    for r_idx, row in enumerate(normalized):
        out = []
        for c_idx, cell in enumerate(row):
            style = st["header"] if r_idx == 0 else (st["table_left"] if len(cell) > 22 or c_idx in (0, 1, n - 1) else st["table"])
            out.append(Paragraph(inline_markup(cell), style))
        wrapped.append(out)
    table = Table(wrapped, colWidths=col_widths(normalized), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B59")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C2CC")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.0),
                ("TOPPADDING", (0, 0), (-1, -1), 2.8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
            ]
        )
    )
    return table


def report_footer(text: str):
    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("CN", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(13 * mm, 8 * mm, text)
        canvas.drawRightString(266 * mm, 8 * mm, str(doc.page))
        canvas.restoreState()

    return footer


def first_heading(lines: list[str], fallback: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def build(src: Path, out: Path) -> None:
    register_fonts()
    st = styles()
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(out),
        pagesize=landscape(letter),
        leftMargin=13 * mm,
        rightMargin=13 * mm,
        topMargin=9 * mm,
        bottomMargin=10 * mm,
        title=src.stem,
        author="Codex",
    )
    story = []
    lines = src.read_text(encoding="utf-8").splitlines()
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=report_footer(first_heading(lines, src.stem)))])

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            story.append(p(line[2:], st["title"]))
            i += 1
            continue
        if line.startswith("## "):
            story.append(p(line[3:], st["h1"]))
            i += 1
            continue
        if line.startswith("### "):
            story.append(p(line[4:], st["h2"]))
            i += 1
            continue
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            story.append(make_table(parse_table(block), st))
            story.append(Spacer(1, 5))
            continue
        if line.startswith("- "):
            story.append(p("• " + line[2:], st["body"]))
            i += 1
            continue
        story.append(p(line, st["body"]))
        i += 1

    doc.build(story)
    print(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build(args.src, args.out)


if __name__ == "__main__":
    main()
