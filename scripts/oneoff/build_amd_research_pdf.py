from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)


import os
# 一次性交付脚本也遵循统一运行目录；未配置时兼容旧 output/tmp。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = os.environ.get("IRA_RUNTIME_ROOT")
OUT = Path(os.environ.get("IRA_ARTIFACT_ROOT", Path(RUNTIME_ROOT) / "artifacts" if RUNTIME_ROOT else PROJECT_ROOT / "output")) / "pdf"
TMP = Path(os.environ.get("IRA_CACHE_ROOT", Path(RUNTIME_ROOT) / "cache" if RUNTIME_ROOT else PROJECT_ROOT / "tmp")) / "amd_report"
OUT.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT / "AMD_2026Q2_20260804_Codex独立研报.pdf"

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("AU", FONT_PATH))

NAVY = colors.HexColor("#15344A")
BLUE = colors.HexColor("#1F6A8A")
TEAL = colors.HexColor("#2A9D8F")
GOLD = colors.HexColor("#D69E2E")
RED = colors.HexColor("#B23A48")
INK = colors.HexColor("#17232D")
MID = colors.HexColor("#536270")
LIGHT = colors.HexColor("#EAF0F4")
PALE = colors.HexColor("#F5F7F9")
GRID = colors.HexColor("#CAD4DC")


def P(text, style):
    return Paragraph(text, style)


def styles():
    ss = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("BodyCN", parent=ss["BodyText"], fontName="AU", fontSize=9.3,
                               leading=14.0, textColor=INK, spaceAfter=6, wordWrap="CJK"),
        "small": ParagraphStyle("SmallCN", parent=ss["BodyText"], fontName="AU", fontSize=7.7,
                                leading=10.5, textColor=MID, spaceAfter=4, wordWrap="CJK"),
        "source": ParagraphStyle("SourceCN", parent=ss["BodyText"], fontName="AU", fontSize=7.1,
                                 leading=9.4, textColor=MID, spaceBefore=2, spaceAfter=5, wordWrap="CJK"),
        "title": ParagraphStyle("TitleCN", parent=ss["Title"], fontName="AU", fontSize=26,
                                leading=33, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("SubtitleCN", parent=ss["BodyText"], fontName="AU", fontSize=14,
                                   leading=19, textColor=BLUE, alignment=TA_CENTER, spaceAfter=12),
        "kicker": ParagraphStyle("KickerCN", parent=ss["BodyText"], fontName="AU", fontSize=9,
                                 leading=12, textColor=GOLD, alignment=TA_CENTER, spaceAfter=16),
        "h1": ParagraphStyle("H1CN", parent=ss["Heading1"], fontName="AU", fontSize=15,
                             leading=20, textColor=NAVY, spaceBefore=4, spaceAfter=8, keepWithNext=True),
        "h2": ParagraphStyle("H2CN", parent=ss["Heading2"], fontName="AU", fontSize=11.5,
                             leading=16, textColor=BLUE, spaceBefore=8, spaceAfter=5, keepWithNext=True),
        "h3": ParagraphStyle("H3CN", parent=ss["Heading3"], fontName="AU", fontSize=9.6,
                             leading=13, textColor=NAVY, spaceBefore=5, spaceAfter=3, keepWithNext=True),
        "callout": ParagraphStyle("CalloutCN", parent=ss["BodyText"], fontName="AU", fontSize=9.2,
                                  leading=14, textColor=INK, leftIndent=8, rightIndent=8,
                                  spaceBefore=4, spaceAfter=4, wordWrap="CJK"),
        "center": ParagraphStyle("CenterCN", parent=ss["BodyText"], fontName="AU", fontSize=8.7,
                                 leading=12, textColor=MID, alignment=TA_CENTER, wordWrap="CJK"),
    }


S = styles()


def page_header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    canvas.setFont("AU", 7.5)
    canvas.setFillColor(MID)
    canvas.drawString(0.83 * inch, h - 0.48 * inch, "AMD DEEP RESEARCH  |  CODEX版  |  2026.08.04")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.4)
    canvas.line(0.83 * inch, h - 0.57 * inch, w - 0.83 * inch, h - 0.57 * inch)
    canvas.drawRightString(w - 0.83 * inch, 0.39 * inch, f"独立研究草案 · 仅供研究讨论  |  {doc.page}")
    canvas.restoreState()


def make_doc():
    doc = BaseDocTemplate(
        str(PDF_PATH), pagesize=letter,
        leftMargin=0.83 * inch, rightMargin=0.83 * inch,
        topMargin=0.72 * inch, bottomMargin=0.62 * inch,
        title="AMD 2026Q2 Codex独立研报",
        author="Codex Independent Research",
        subject="AMD公司研究与三情景估值",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=page_header_footer)])
    return doc


def table(data, widths, header=True, font=7.4, aligns=None, zebra=True):
    cooked = []
    for i, row in enumerate(data):
        out = []
        for j, value in enumerate(row):
            color = colors.white if header and i == 0 else INK
            st = ParagraphStyle(
                f"cell{i}_{j}_{id(data)}", fontName="AU", fontSize=font,
                leading=font + 2.6, textColor=color, wordWrap="CJK",
                alignment=(aligns[j] if aligns else (TA_LEFT if j == 0 else TA_CENTER)),
            )
            out.append(P(str(value), st))
        cooked.append(out)
    t = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        start = 1 if header else 0
        for i in range(start, len(data)):
            if (i - start) % 2 == 1:
                commands.append(("BACKGROUND", (0, i), (-1, i), PALE))
    t.setStyle(TableStyle(commands))
    return t


def callout(label, text, fill=LIGHT, accent=BLUE):
    content = P(f'<font color="{accent.hexval()}"><b>{label}</b></font>　{text}', S["callout"])
    t = Table([[content]], colWidths=[6.42 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.5, fill),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return KeepTogether([t, Spacer(1, 5)])


def source(text):
    return P("资料来源：" + text, S["source"])


def h1(text): return P(text, S["h1"])
def h2(text): return P(text, S["h2"])
def body(text): return P(text, S["body"])


def build():
    doc = make_doc()
    st = []

    # Cover
    st += [Spacer(1, 0.80 * inch), P("CODEX版 · 独立公司研究", S["kicker"]),
           P("超威半导体（AMD）", S["title"]),
           P("AI算力第二供应链的真实弹性与兑现门槛", S["subtitle"]),
           P("从GW合作公告回到出货、收入确认、毛利率与摊薄后EPS", S["center"]),
           Spacer(1, 0.34 * inch),
           callout("投资结论", "中性 / 观察。基准合理价值465美元，合理区间430-530美元；当前价格484.64美元，市场已计入相当部分2027年MI450与EPYC增长。"),
           Spacer(1, 0.17 * inch),
           P("基准日：2026年8月4日（AMD 2026Q2财报发布前）", S["center"]),
           P("当前价格：484.64美元　|　市值：约7,997亿美元　|　未来12个月核心事件：MI450量产与Helios机架交付", S["center"]),
           Spacer(1, 0.25 * inch), h2("核心观点"),
           body("<b>产业位置：</b>AMD已从CPU/GPU芯片商转向CPU、GPU、网络、机架和ROCm软件的系统供应商。"),
           body("<b>增长主线：</b>2026H2-2027增长主要来自MI450/Helios和EPYC服务器CPU，而非客户端业务。"),
           body("<b>主要分歧：</b>GW协议代表多年期潜在需求，不等于当期确认收入；权证、战略投资与客户集中降低每股价值确定性。"),
           body("<b>估值判断：</b>只有在2027年收入接近1,000亿美元、摊薄后EPS接近18美元时，600美元以上目标才成立。"),
           source("AMD公司公告、AMD 2026Q1财务报告、AMD Advancing AI 2026、UBS（2026-06-24）、公开市场数据；本报告测算。"),
           PageBreak()]

    # Page 2
    st += [h1("1. 投资摘要"),
           callout("一句话结论", "AMD的第二供应链地位正在得到客户合同验证，但当前股价交易的是2027年而不是2026年；应把MI450交付和权证摊薄同时纳入估值。", colors.HexColor("#E8F3F1"), TEAL),
           h2("关键指标"),
           table([
               ["指标", "2025A", "2026E", "2027E", "2028E"],
               ["收入（亿美元）", "346", "505", "820", "1,100"],
               ["同比", "34%", "46%", "62%", "34%"],
               ["数据中心收入（亿美元）", "166", "320", "645", "903"],
               ["Non-GAAP毛利率", "52.4%", "55.8%", "55.5%", "56.2%"],
               ["摊薄后Non-GAAP EPS（美元）", "4.17", "7.6", "14.1", "20.2"],
               ["估算摊薄股数（亿股）", "16.4", "16.6", "17.2", "18.0"],
           ], [2.35*inch, 1.02*inch, 1.02*inch, 1.02*inch, 1.02*inch], font=7.8),
           source("摊薄股数为研究情景，不代表权证一定全部归属；2025A EPS采用可比口径。"),
           h2("投资逻辑的三层证据"),
           body("<b>第一层｜CPU份额与ASP。</b>EPYC受益于核心数、能效与x86兼容性。Agentic AI提高控制面、检索、数据处理和传统软件负载，CPU有独立增量。"),
           body("<b>第二层｜GPU与机架。</b>OpenAI、Meta、Anthropic及微软的合作把MI450从产品路线图推进到部署阶段。真正决定收入的是机架价值、交付节奏和验收。"),
           body("<b>第三层｜开放软件。</b>ROCm与Coding Agent降低迁移成本，但生产稳定性、算子覆盖、多机通信和工具仍需验证。"),
           h2("最关键的跟踪变量"),
           table([
               ["变量", "基准假设", "验证信号", "失效信号"],
               ["MI450/Helios", "2026H2开始贡献，2027放量", "数据中心收入连续上台阶", "出货有但验收/确认延后"],
               ["服务器CPU", "2026收入约160亿美元", "单位与ASP同步提升", "Arm/定制芯片侵蚀负载"],
               ["ROCm", "迁移效率改善但仍需工程投入", "生产客户与利用率增加", "仅演示适配"],
               ["股本摊薄", "权证分阶段归属", "利润增量覆盖摊薄", "股数增长快于利润"],
           ], [1.15*inch, 1.8*inch, 1.75*inch, 1.73*inch], font=6.9),
           PageBreak()]

    # Page 3
    st += [h1("2. 公司定位：从芯片组合走向异构系统"),
           body("AMD的竞争方式不是复制英伟达的单一GPU优势，而是用EPYC CPU、Instinct GPU、Pensando NIC/DPU、Helios机架与ROCm软件形成可组合的平台。该组合对希望降低单一供应商依赖的云厂商尤其有吸引力。"),
           table([
               ["层级", "核心产品", "客户价值", "核心验证点"],
               ["计算控制面", "EPYC Turin/Venice/Verano", "任务编排、传统软件、数据处理", "单位、ASP、云实例份额"],
               ["加速计算", "MI350/MI450/MI500", "训练与高吞吐推理", "性能/美元、供货与利用率"],
               ["网络与数据面", "Pensando NIC/DPU", "机架互联、卸载与安全", "互联规模、客户采用"],
               ["系统", "Helios", "缩短部署周期、统一交付", "BOM、毛利率、验收节奏"],
               ["软件", "ROCm.AI", "开放生态与迁移自动化", "算子覆盖、稳定性、工具"],
           ], [1.08*inch, 1.78*inch, 1.9*inch, 1.67*inch], font=7.1),
           source("AMD Advancing AI 2026；本报告整理。"),
           h2("产品节奏"),
           table([
               ["时间", "GPU/系统", "CPU/网络", "研究判断"],
               ["2026H2", "MI450、Helios首批出货", "Venice、Pensando", "收入起点，看验收而非公告GW"],
               ["2027", "MI500、Helios 500", "Verano、Como/Monza", "规模放量与平台毛利率关键年"],
               ["2028", "MI600、Helios 600", "Florence/Ferrara、Palma/Levanzo", "验证年度迭代与客户留存"],
           ], [1.05*inch, 1.75*inch, 1.95*inch, 1.68*inch], font=7.1),
           h2("TAM可以扩大，但不能替代份额模型"),
           body("AMD给出的2030年AI芯片TAM约1.4万亿美元、数据中心CPU TAM约2,200亿美元，说明行业空间足够大；但TAM不是收入预测。模型仍需回答单位份额、ASP、机架价值量和确认时点。"),
           callout("判断", "“市场足够大”只解决天花板；“客户何时验收、AMD确认多少收入、付出多少稀释和投资”才决定每股价值。", colors.HexColor("#FFF7E6"), GOLD),
           h2("竞争优势与短板"),
           table([
               ["维度", "优势", "短板"],
               ["CPU", "x86生态、核心数与能效", "Arm与定制CPU持续渗透"],
               ["GPU", "开放采购池、性价比和客户定制", "软件与大规模生产验证不足"],
               ["系统", "CPU/GPU/网络协同", "机架交付与毛利率经验仍在形成"],
               ["软件", "开放、可由Agent加速迁移", "CUDA存量生态和工具成熟度"],
           ], [1.1*inch, 2.65*inch, 2.68*inch], font=7.3),
           PageBreak()]

    # Page 4
    st += [h1("3. 客户合作：GW是需求框架，不是收入数字"),
           table([
               ["客户", "合作规模", "首批节奏", "对价/条件", "模型处理"],
               ["OpenAI", "多年期6GW", "首个1GW自2026H2开始", "最高1.6亿股权证；多项条件", "2026仅计部分，2027-30分期"],
               ["Meta", "最高6GW", "首个1GW相关出货自2026H2", "最高1.6亿股权证；里程碑归属", "定制MI450，分期计入"],
               ["Anthropic", "最高2GW", "首个1GW自2027H1开始", "AMD未来最高50亿美元投资", "收入与投资现金流分开"],
               ["Microsoft", "计划部署Helios", "未披露数量", "合作与产品验证", "不提前计大额承诺"],
               ["Oracle", "首期5万颗MI450", "2026Q3开始", "云服务部署", "按季度供货爬坡"],
           ], [0.75*inch, 0.85*inch, 1.35*inch, 1.75*inch, 1.73*inch], font=6.4),
           source("AMD关于OpenAI、Meta、Anthropic、Microsoft和Oracle的官方公告；规模均为潜在/计划部署口径。"),
           h2("为什么不能用“美元/GW”直接乘"),
           body("一个GW可对应不同GPU数量、功耗配置、网络方案与系统边界。若AMD只确认GPU和部分网络收入，价值量较低、毛利率较高；若确认完整机架收入，收入更高但包含更多低毛利率部件。收入和毛利率必须成对假设。"),
           table([
               ["确认边界", "收入弹性", "毛利率倾向", "主要风险"],
               ["芯片为主", "较低", "较高", "GW标题难直接映射为AMD收入"],
               ["GPU+网络", "中等", "中高", "互联和客户定制影响价值量"],
               ["完整机架/系统", "较高", "可能较低", "供应链、验收及营运资金压力"],
           ], [1.25*inch, 1.05*inch, 1.15*inch, 2.98*inch], font=7.2),
           h2("客户集中与信用链条"),
           body("OpenAI与Meta潜在规模足以改变AMD收入结构，也提高单一客户、融资和项目节奏风险。对NeoCloud伙伴的投资或担保有助于形成需求，但会把供应商风险扩展为投资、信用和回收风险。"),
           h2("研究模型的处理原则"),
           body("1）2026只计入可在H2交付并验收的部分；2）多年期GW按2027-2030分期；3）完整系统收入与毛利率不同时采用最乐观假设；4）权证与战略投资从每股价值和现金用途两端处理。"),
           PageBreak()]

    # Page 5
    st += [h1("4. 财务模型：用季度桥约束全年预测"),
           Image(str(TMP / "revenue_scenarios.png"), width=6.42*inch, height=3.30*inch),
           source("AMD、UBS；2026E-2028E为本报告情景测算。"),
           h2("2026收入桥"),
           table([
               ["项目", "收入（亿美元）", "状态/含义"],
               ["2026Q1", "102.5", "已公布"],
               ["2026Q2", "112.0", "公司指引中值"],
               ["基准H2", "290.5", "单季均值145.3，较H1单季均值高35%"],
               ["基准全年", "505.0", "接近近期可验证卖方底模"],
               ["原华泰全年", "638.9", "要求H2收入424.4，单季均值212.2"],
           ], [1.55*inch, 1.45*inch, 3.43*inch], font=7.4),
           callout("关键差异", "本报告没有把首批GW“开始出货”解释为当年完整部署；2026收入主要由现有MI350、EPYC增长和MI450首批贡献构成。", colors.HexColor("#E8F3F1"), TEAL),
           h2("分部收入基准情景"),
           table([
               ["亿美元", "2025A", "2026E", "2027E", "2028E", "核心驱动"],
               ["数据中心", "166", "320", "645", "903", "MI450/Helios、EPYC、Pensando"],
               ["客户端", "106", "118", "105", "115", "份额提升后趋稳"],
               ["游戏", "39", "27", "23", "32", "半定制下行后恢复"],
               ["嵌入式", "35", "40", "47", "50", "库存周期修复"],
               ["合计", "346", "505", "820", "1,100", "数据中心占比提升"],
           ], [0.95*inch, 0.67*inch, 0.67*inch, 0.67*inch, 0.67*inch, 2.80*inch], font=6.9),
           PageBreak()]

    # Page 6
    st += [h1("5. 利润、现金流与股本摊薄"), h2("基准损益预测"),
           table([
               ["亿美元/美元", "2025A", "2026E", "2027E", "2028E"],
               ["收入", "346.4", "505.0", "820.0", "1,100.0"],
               ["Non-GAAP毛利润", "181.7", "281.8", "455.1", "618.2"],
               ["Non-GAAP毛利率", "52.4%", "55.8%", "55.5%", "56.2%"],
               ["Non-GAAP经营利润", "77.7", "144.0", "280.0", "418.0"],
               ["Non-GAAP经营利润率", "22.4%", "28.5%", "34.1%", "38.0%"],
               ["Non-GAAP净利润", "68.3", "126.2", "242.5", "363.6"],
               ["摊薄股数（亿股）", "16.4", "16.6", "17.2", "18.0"],
               ["Non-GAAP EPS", "4.17", "7.60", "14.10", "20.20"],
           ], [2.2*inch, 1.06*inch, 1.06*inch, 1.06*inch, 1.05*inch], font=7.4),
           source("2026E采用约13%的Non-GAAP税率；2027-28包含阶段性权证摊薄。"),
           h2("毛利率的会计分叉"),
           body("若AMD确认更多机架级硬件收入，收入会更高、毛利率可能更低；若以芯片收入为主，收入较低但毛利率更好。本模型将2027毛利率控制在55.5%，没有同时假设“完整机架收入”和“纯芯片毛利率”。"),
           h2("权证与战略投资"),
           table([
               ["项目", "最大规模", "本模型处理", "投资者应关注"],
               ["OpenAI权证", "1.6亿股", "随采购/技术/股价里程碑分期", "利润是否覆盖每股摊薄"],
               ["Meta权证", "1.6亿股", "随出货与商业条件分期", "定制产品毛利率和集中度"],
               ["Anthropic投资", "最高50亿美元", "不抵减收入；作为潜在现金用途", "投资时点、估值和退出"],
           ], [1.1*inch, 1.05*inch, 2.35*inch, 1.93*inch], font=6.9),
           callout("经济摊薄上限", "两项权证合计最高3.2亿股，约相当于当前基础股数的19.6%。即使会计EPS短期尚未体现，估值也不能忽略其条件性经济成本。", colors.HexColor("#FCEBED"), RED),
           h2("现金流判断"),
           body("AMD资本开支强度较低，盈利可转化为较强自由现金流；但系统放量会提高存货、应收和客户融资需求。50亿美元战略投资、NeoCloud支持及潜在回购会限制现金余额的机械累积。"),
           PageBreak()]

    # Page 7
    st += [h1("6. 软件生态：迁移成本下降，不等于CUDA壁垒消失"),
           body("ROCm.AI与Coding Agent可以帮助代码转换、算子适配和性能调优，降低首次迁移的人力成本。但生产系统由全生命周期TCO决定，不能只看示范代码是否运行。"),
           table([
               ["层面", "ROCm改善方向", "尚待验证"],
               ["代码迁移", "Agent自动修改与适配", "复杂自定义算子与长期维护成本"],
               ["性能", "编译器、内核和框架优化", "不同模型与集群规模的稳定领先"],
               ["多机扩展", "通信库和网络协同", "故障恢复、尾延迟与利用率"],
               ["开发运维", "开放工具链与社区", "调试、分析、兼容和企业支持"],
               ["人才生态", "开放标准降低绑定", "CUDA人才与存量代码沉没成本"],
           ], [1.2*inch, 2.35*inch, 2.88*inch], font=7.4),
           h2("应使用的验证指标"),
           body("建议每季跟踪四类硬指标：生产客户数量与规模、集群利用率和稳定性、主流模型性能/美元、从CUDA迁移到ROCm的实际工程周期。只有这些指标连续改善，软件生态才会转化为可持续份额。"),
           callout("研究结论", "把ROCm视为份额扩张的必要条件，而不是充分条件。客户合同证明AMD已进入采购池，生产效率决定其能否留在核心池。"),
           h2("ROCm对估值的正确映射"),
           table([
               ["证据阶段", "可支持的估值含义"],
               ["Demo可运行", "证明技术可行，不能直接上调份额"],
               ["生产部署", "可提高收入可见度"],
               ["规模利用率与复购", "可提高长期份额和估值倍数"],
               ["跨客户标准化", "可降低获客与支持成本，提高利润率"],
           ], [2.0*inch, 4.43*inch], font=7.6),
           PageBreak()]

    # Page 8
    st += [h1("7. 估值与情景分析"),
           Image(str(TMP / "valuation_scenarios.png"), width=6.42*inch, height=3.30*inch),
           source("本报告测算。目标价值未额外加入净现金溢价，以避免对潜在投资和营运资金形成双重乐观。"),
           table([
               ["情景", "2027收入", "2027 EPS", "目标PE", "目标价值", "核心条件"],
               ["审慎", "580亿美元", "9.0美元", "28x", "252美元", "MI450延后、CPU回落、摊薄较高"],
               ["基准", "820亿美元", "14.1美元", "33x", "465美元", "首批GW分期、EPYC继续扩份额"],
               ["乐观", "1,100亿美元", "18.0美元", "36x", "648美元", "多客户按期部署、利润率兑现"],
           ], [0.72*inch, 1.02*inch, 0.86*inch, 0.73*inch, 0.85*inch, 2.25*inch], font=6.8),
           callout("评级与目标", "中性 / 观察；基准合理价值465美元，合理区间430-530美元。相较当前484.64美元缺乏足够安全边际，等待Q2业绩、MI450首批收入与摊薄细节验证。", colors.HexColor("#FFF7E6"), GOLD),
           h2("为什么不使用640美元作为基准"),
           body("640美元基本等于18.28美元2027E EPS乘35倍。数学没有问题，但把接近乐观情景的盈利包装为基准。若采用14.1美元基准EPS，即使给35倍，价值也只有约494美元。核心争议是盈利兑现，而不是2-3倍PE差异。"),
           h2("估值上修条件"),
           body("<b>收入：</b>2026Q3-Q4数据中心收入持续高于基准，且披露2027可交付订单。<br/><b>利润：</b>系统收入放量后Non-GAAP毛利率仍稳定在55%以上。<br/><b>每股：</b>权证归属慢于利润增长，战略投资不侵蚀自由现金流。<br/><b>生态：</b>ROCm生产客户和大规模集群利用率出现量化改善。"),
           PageBreak()]

    # Page 9
    st += [h1("8. 催化剂与风险"), h2("未来12个月催化剂"),
           table([
               ["时间窗口", "事件", "正向观察点", "负向观察点"],
               ["2026Q2财报", "收入、毛利率及Q3指引", "数据中心继续超预期", "H2指引无法支撑爬坡"],
               ["2026Q3-Q4", "MI450/Helios首批出货", "验收和收入确认顺利", "出货与确认脱节"],
               ["2027H1", "Anthropic首个GW开始部署", "多客户并行交付", "融资、供电或建设延后"],
               ["2027", "MI500/Helios 500", "年度迭代、性能和TCO领先", "路线图或软件适配延误"],
           ], [1.1*inch, 1.75*inch, 1.8*inch, 1.78*inch], font=7.0),
           h2("主要风险排序"),
           body("<font color='#B23A48'><b>高｜交付与确认。</b></font>GW合作为多年期框架，系统建设、供电、融资和验收均可能推迟收入。"),
           body("<font color='#B23A48'><b>高｜客户与权证集中。</b></font>少数客户决定大部分增量，同时可能触发显著股本摊薄。"),
           body("<font color='#B23A48'><b>高｜软件与利用率。</b></font>峰值性能不等于生产TCO；ROCm稳定性不足会影响复购。"),
           body("<font color='#D69E2E'><b>中高｜毛利率。</b></font>完整机架收入可能稀释毛利率，定制产品也可能让利。"),
           body("<font color='#D69E2E'><b>中高｜供应链。</b></font>HBM、先进封装、互联、液冷与机架集成均可能成为瓶颈。"),
           body("<font color='#D69E2E'><b>中｜竞争与政策。</b></font>英伟达年度迭代、ASIC、Arm CPU与出口管制可能压缩份额。"),
           h2("投委会检查清单"),
           table([
               ["必须回答的问题", "当前状态"],
               ["客户GPU数量、机架价值量和季度确认是否可追踪？", "未充分披露"],
               ["系统与芯片收入的毛利率边界是否清楚？", "需Q3-Q4验证"],
               ["权证归属和摊薄是否进入每股模型？", "本报告已做情景处理"],
               ["50亿美元投资是否进入现金流？", "需进一步披露"],
               ["ROCm是否有生产规模和利用率证据？", "方向改善，数据不足"],
           ], [4.7*inch, 1.73*inch], font=7.2),
           PageBreak()]

    # Page 10
    st += [h1("附录：数据口径、来源与免责声明"), h2("主要数据口径"),
           body("本报告以AMD 2025财年实际数据、2026Q1实际和2026Q2公司指引为历史锚。2026-2028年均为研究情景，不是公司指引。Non-GAAP指标用于跨期经营比较；估值同时考虑潜在权证摊薄，不把最高权证股数机械视为必然归属。"),
           h2("主要公开来源"),
           body("1. AMD Reports First Quarter 2026 Financial Results，2026-05-05。<br/>2. AMD and OpenAI Announce Strategic Partnership to Deploy 6 Gigawatts，2025-10-06。<br/>3. AMD and Meta Announce Expanded Strategic Partnership to Deploy 6 Gigawatts，2026-02-24。<br/>4. AMD and Anthropic Announce Strategic Partnership to Deploy Up to 2 Gigawatts，2026-07-22。<br/>5. AMD Advancing AI 2026 Keynote及产品路线图，2026-07-23。<br/>6. AMD 2025 Form 10-K与2026Q1财务报告。<br/>7. UBS, Revisiting AMD and ARM Estimates Amid Agentic AI Acceleration，2026-06-24。<br/>8. 华泰证券，《软硬生态全面进击，剑指Agentic AI算力变局》，2026-07-26。<br/>9. 公开市场价格数据，截至2026-08-04 00:15 UTC。"),
           h2("关键网址"),
           P("https://www.amd.com/en/newsroom/press-releases/2026-5-5-amd-reports-first-quarter-2026-financial-results.html<br/>https://www.amd.com/en/newsroom/press-releases/2025-10-6-amd-and-openai-announce-strategic-partnership-to-d.html<br/>https://www.amd.com/en/newsroom/press-releases/2026-2-24-amd-and-meta-announce-expanded-strategic-partnersh.html<br/>https://ir.amd.com/news-events/press-releases/detail/1292/amd-and-anthropic-announce-strategic-partnership-to-deploy-up-to-2-gigawatts-of-amd-instinct-mi450-series-gpus<br/>https://www.amd.com/en/corporate/events/advancing-ai.html", S["small"]),
           h2("免责声明"),
           body("本报告仅用于研究讨论，不构成任何证券买卖建议、要约或保证。预测高度依赖产品交付、客户部署、会计确认、竞争和市场条件，实际结果可能显著不同。报告使用的公开信息被认为可靠，但不保证完整或无误。投资者应结合自身风险承受能力独立判断。"),
           Spacer(1, 0.35*inch),
           callout("版本识别", "本文件为Codex独立研报，文件名含“Codex独立研报”；与Claude生成的 AMD_2026Q2_20260804.md 明确区分。", LIGHT, BLUE)]

    doc.build(st)
    print(PDF_PATH)


if __name__ == "__main__":
    build()
