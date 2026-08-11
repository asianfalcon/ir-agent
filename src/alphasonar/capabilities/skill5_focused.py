"""
Skill 5: Five focused analysis shortcuts.
Each function returns a Markdown string grounded in local data.
"""

import re
from typing import Any
from alphasonar.utils.prompts import load

_GROUNDING_RULE = load("skill5_grounding_rule.md")
# 严格的卖方一致预期只由券商研报构成。专家专栏是第三方补充观点，但未必是有
# 完整财务模型的独立卖方预测，因此只能进入修正证据层，不能混入 consensus 均值。
# 公司官方财报/公告则是公司自述事实与管理层指引，必须单列为官方锚点。
RESEARCH_DATA_SOURCES = {"broker_report"}
SUPPLEMENTAL_DATA_SOURCES = {"acecamp_expert_column"}
OFFICIAL_DATA_SOURCES = {"company_filing", "announcement"}
NEWS_DATA_SOURCES = {"web_news"}
_TEAM_RE = re.compile(r"^\d{8}-([^-]+)-")
FORECAST_KEYWORDS = (
    "盈利预测",
    "业绩预测",
    "财务预测",
    "2026E",
    "2027E",
    "2028E",
    "营业收入",
    "归母净利润",
    "归属于母公司净利润",
    "每股收益",
    "EPS",
    "PE",
    "PS",
)


def _research_chunks(vector_chunks: list[dict]) -> list[dict]:
    """严格的"卖方一致预期"检索：只含第三方卖方研报与专家专栏。
    专供 _forecast_chunks()/一致预期基准表——公司官方财报绝不进卖方共识。"""
    return [c for c in vector_chunks if c.get("data_source") in RESEARCH_DATA_SOURCES]


# 事实证据检索：在卖方研报之外，额外纳入专家观点、公司官方财报/公告和新闻。
# web_news 可进入经营驱动、边际变化、关系图谱与机会风险，但绝不进入卖方一致预期；
# 未经交叉确认的新闻默认是弱证据，只调整情景概率，不修改 Base 金额。
_EVIDENCE_DATA_SOURCES = (
    RESEARCH_DATA_SOURCES
    | SUPPLEMENTAL_DATA_SOURCES
    | OFFICIAL_DATA_SOURCES
    | NEWS_DATA_SOURCES
)


def _evidence_chunks(vector_chunks: list[dict]) -> list[dict]:
    return [c for c in vector_chunks if c.get("data_source") in _EVIDENCE_DATA_SOURCES]


def _official_chunks(vector_chunks: list[dict]) -> list[dict]:
    """公司官方财报/公告：只作实际值与管理层指引锚点，不进入卖方一致预期。"""
    return [c for c in vector_chunks if c.get("data_source") in OFFICIAL_DATA_SOURCES]


def _supplemental_chunks(vector_chunks: list[dict]) -> list[dict]:
    """专家专栏等补充证据：可用于修正，但不进入严格卖方共识。"""
    return [c for c in vector_chunks if c.get("data_source") in SUPPLEMENTAL_DATA_SOURCES]


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for chunk in chunks:
        key = chunk.get("chunk_id") or (chunk.get("source_file"), chunk.get("text", "")[:120])
        if key in seen:
            continue
        seen.add(key)
        result.append(chunk)
    return result


def _latest_one_per_source(chunks: list[dict], limit: int) -> list[dict]:
    """Newest evidence with at most one snippet from each document/article."""
    ordered = sorted(
        chunks,
        key=lambda c: (c.get("release_time") or 0, c.get("pub_date", "")),
        reverse=True,
    )
    result = []
    seen_sources = set()
    for chunk in ordered:
        source = chunk.get("source_file") or chunk.get("chunk_id")
        if source in seen_sources:
            continue
        seen_sources.add(source)
        result.append(chunk)
        if len(result) >= limit:
            break
    return result


def _team_of(chunk: dict) -> str | None:
    """从source_file文件名提取研报团队名（如"华泰证券"），提取不出来（文件名
    不是"YYYYMMDD-团队-..."格式，如年报/财报电话会/SEC文件）时返回None——
    团队不明的chunk不参与同团队去重，宁可留着不去重，也不误删。"""
    source_file = chunk.get("source_file", "")
    file_name = source_file.rsplit("/", 1)[-1]
    m = _TEAM_RE.match(file_name)
    return m.group(1) if m else None


def _latest_version_per_team(chunks: list[dict]) -> list[dict]:
    """同团队只保留最新的“含预测科目”报告。

    不能简单保留团队发布日期最新的任意报告：最新文件可能只是事件点评且没有完整
    财务预测，若用它淘汰稍早的盈利预测表，会让该团队从 consensus 中错误消失。
    """
    by_file: dict[str, list[dict]] = {}
    for chunk in chunks:
        source_file = chunk.get("source_file", "") or chunk.get("chunk_id", "")
        by_file.setdefault(source_file, []).append(chunk)

    report_meta: dict[str, tuple[str | None, str, bool]] = {}
    for source_file, report_chunks in by_file.items():
        team = _team_of(report_chunks[0])
        pub_date = max((c.get("pub_date", "") or "") for c in report_chunks)
        combined = "\n".join(c.get("text", "") for c in report_chunks)
        has_forecast = (
            any(k in combined for k in FORECAST_KEYWORDS)
            and any(y in combined for y in ("2026", "2027", "2028"))
        )
        report_meta[source_file] = (team, pub_date, has_forecast)

    selected_file_by_team: dict[str, str] = {}
    for source_file, (team, pub_date, has_forecast) in report_meta.items():
        if not team or not has_forecast:
            continue
        current = selected_file_by_team.get(team)
        if current is None or pub_date > report_meta[current][1]:
            selected_file_by_team[team] = source_file

    result = []
    for source_file, report_chunks in by_file.items():
        team, _, has_forecast = report_meta[source_file]
        if not has_forecast:
            continue
        if team and selected_file_by_team.get(team) != source_file:
            continue
        result.extend(report_chunks)
    return result


def _forecast_score(chunk: dict, company_name: str) -> int:
    text = chunk.get("text", "")
    source_file = chunk.get("source_file", "")
    file_name = source_file.rsplit("/", 1)[-1]
    ticker = chunk.get("ticker", "")
    score = 0
    for keyword in FORECAST_KEYWORDS:
        if keyword in text:
            score += 3
    if "E" in text and any(year in text for year in ("2026", "2027", "2028")):
        score += 4
    if any(metric in text for metric in ("营业收入", "归母净利润", "归属于母公司净利润")):
        score += 4
    directly_related = (
        (company_name and (company_name in text or company_name in file_name))
        or (ticker and (ticker in text or ticker in file_name))
    )
    if directly_related:
        score += 5
    if company_name and company_name in file_name:
        score += 4
    if any(broker in file_name for broker in ("国信证券", "东吴证券", "中信证券", "国金证券", "招商证券", "申万宏源")):
        score += 2
    if chunk.get("data_source") == "broker_report":
        score += 3
    if not directly_related:
        score -= 8
    if "行业" in file_name and not directly_related:
        score -= 5
    return score


def _forecast_chunks(ticker: str, company_name: str, vector_chunks: list[dict]) -> list[dict]:
    """从预检索池筛选最可能含卖方预测的 broker/expert chunk(不再独立调 vector_search)."""
    chunks = list(vector_chunks)
    scored = [
        (chunk, _forecast_score(chunk, company_name))
        for chunk in _latest_version_per_team(_dedupe_chunks(_research_chunks(chunks)))
    ]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [chunk for chunk, _ in scored]


GUIDANCE_KEYWORDS = (
    "指引", "业绩展望", "Outlook", "outlook", "Guidance", "guidance",
    "revenue range", "gross margin", "毛利率", "Earnings Per Share", "EPS",
)


def _guidance_chunks(ticker: str, company_name: str, vector_chunks: list[dict]) -> list[dict]:
    """从预检索池筛选公司下一期指引(不再独立调 vector_search);结果与卖方预测保持物理隔离."""
    official = _dedupe_chunks(_official_chunks(vector_chunks))
    scored = []
    for chunk in official:
        text = chunk.get("text", "")
        score = sum(3 for keyword in GUIDANCE_KEYWORDS if keyword in text)
        if any(term in text for term in ("下一季度", "Q1", "Q2", "Q3", "Q4", "quarter")):
            score += 3
        if any(term in text for term in ("收入", "Revenue", "revenue")):
            score += 2
        if score > 0:
            scored.append((chunk, score))
    scored.sort(key=lambda item: (item[1], item[0].get("pub_date", "")), reverse=True)
    return [chunk for chunk, _ in scored]


def _one_snippet_per_report(chunks: list[dict], max_reports: int = 20) -> list[str]:
    """每份研报只输出一行，避免一份报告的多个chunk伪装成多个独立样本。"""
    by_file: dict[str, list[dict]] = {}
    for chunk in chunks:
        source_file = chunk.get("source_file", "") or chunk.get("chunk_id", "")
        by_file.setdefault(source_file, []).append(chunk)

    reports = []
    for source_file, report_chunks in by_file.items():
        report_chunks.sort(key=lambda c: _forecast_score(c, ""), reverse=True)
        best_text = " ".join(c.get("text", "")[:700] for c in report_chunks[:2])
        pub_date = max((c.get("pub_date", "") or "") for c in report_chunks)
        reports.append((pub_date, source_file, report_chunks[0], best_text))
    reports.sort(key=lambda item: item[0], reverse=True)
    return [
        f"[{_source_meta(chunk)} · {pub_date} · {source_file}] {text}"
        for pub_date, source_file, chunk, text in reports[:max_reports]
    ]


def _source_label(chunk: dict) -> str:
    source = chunk.get("data_source", "")
    if source == "acecamp_expert_column":
        return "AceCamp专家专栏"
    if source == "broker_report":
        return "券商研报"
    if source == "company_filing":
        return "公司官方财报"
    if source == "announcement":
        return "公司公告"
    if source == "web_news":
        return "新闻报道"
    return source or "未知来源"


def _source_meta(chunk: dict) -> str:
    parts = [_source_label(chunk)]
    if chunk.get("is_hot"):
        parts.append("hot")
    if "source_weight" in chunk:
        parts.append(f"weight={chunk.get('source_weight')}")
    return "/".join(parts)


def earnings_forecast(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """预测业绩：历史实际值 + 公司指引 + 卖方共识 + 增量修正。"""
    fin = dashboard.get("metrics", {})
    rev = fin.get("revenue", {})
    np_ = fin.get("net_profit", {})
    period = dashboard.get("period", "最新")

    fin_text = (
        f"营收: {rev.get('value')} YoY {rev.get('yoy_pct')}% QoQ {rev.get('qoq_pct')}%\n"
        f"净利润: {np_.get('value')} YoY {np_.get('yoy_pct')}% QoQ {np_.get('qoq_pct')}%"
    )

    sell_snips = _one_snippet_per_report(
        _forecast_chunks(ticker, company_name, vector_chunks), max_reports=20
    )
    sell_text = "\n".join(f"- {s}" for s in sell_snips) or "暂无本地研报预测数据"

    guidance_snips = [
        f"[{c.get('data_source')} · {c.get('pub_date', '?')} · {c.get('source_file', '')} · chunk={c.get('chunk_id','')}] {c.get('text','')[:900]}"
        for c in _guidance_chunks(ticker, company_name, vector_chunks)[:8]
    ]
    guidance_text = "\n".join(f"- {s}" for s in guidance_snips) or "暂无本地公司官方指引"

    # P0 护栏：本地存在官方文件（company_filing/announcement）却一条指引都没抽到 →
    # 抽取失败，绝不静默降级为"暂无指引"往下跑（AMD 本地有 109-115 亿指引却被漏读，
    # 生成了违反指引的结果）。区分"抽取失败" vs "本地本就无官方文件"（后者放行）。
    if not guidance_snips and _official_chunks(vector_chunks):
        raise RuntimeError(
            f"GUIDANCE_EXTRACTION_FAILED: {ticker} 本地存在官方财报/公告，但未能抽取到"
            f"目标期指引。禁止在缺指引的情况下生成预测（防止违反指引或机械拆季）。"
            f"请检查 _guidance_chunks 检索或指引关键词覆盖。"
        )

    supplemental_snips = [
        f"[{_source_meta(c)} · {c.get('pub_date', '?')} · {c.get('source_file', '')}] {c.get('text','')[:500]}"
        for c in _dedupe_chunks(_supplemental_chunks(vector_chunks))[:6]
    ]
    supplemental_text = "\n".join(f"- {s}" for s in supplemental_snips) or "暂无专家补充观点"

    # 业绩不能只从合并财务表外推。补充召回能解释分部/产品收入和利润形成过程的
    # 经营证据；这些证据可以来自官方、卖方或专家，但仍按各自身份使用，不能混成共识。
    operating_keywords = (
        "分部", "业务", "产品", "客户", "出货", "订单", "销量", "单价", "ASP",
        "产能", "供应", "供给", "需求", "良率", "封装", "晶圆", "库存", "份额",
        "竞争", "毛利", "费用", "segment", "product", "customer", "shipment", "unit",
        "capacity", "supply", "demand", "yield", "wafer", "inventory", "market share",
        "gross margin", "operating expense",
    )
    operating_chunks = [
        c for c in _dedupe_chunks(_evidence_chunks(vector_chunks))
        if any(keyword.lower() in c.get("text", "").lower() for keyword in operating_keywords)
    ][:16]
    operating_snips = [
        f"[{_source_meta(c)} · {c.get('pub_date', '?')} · {c.get('source_file', '')} · chunk={c.get('chunk_id','')}] {c.get('text','')[:700]}"
        for c in operating_chunks
    ]
    operating_text = "\n".join(f"- {s}" for s in operating_snips) or "暂无可用经营驱动证据"

    prompt = f"""你是卖方分析师。请基于以下本地数据预测 {company_name}({ticker}) 未来2个季度业绩区间。

【历史财务数据 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【公司官方指引｜独立锚点，不得计入卖方一致预期】(来源: LanceDB company_filing + announcement)
{guidance_text}

【卖方一致预期候选｜仅券商研报】(来源: LanceDB broker_report；每份报告仅一条)
{sell_text}

【专家/纪要补充｜仅用于增量修正，不得计入卖方一致预期】(来源: LanceDB acecamp_expert_column)
{supplemental_text}

【经营驱动证据｜用于拆分部/产品收入与利润桥，不改变来源身份；可含 web_news】
{operating_text}

{_GROUNDING_RULE}

强制计算顺序：
1. 先找出真正决定本期业绩的2—5项业务/产品驱动，解释数量、价格、结构和供给如何形成收入；不要求指标齐全；
2. 从收入与产品结构推导毛利率，再经运营费用、其他损益、税率和股本形成可审计EPS桥；
3. 历史实际值作基数校验；
4. 公司官方指引单列，作为预测边界与管理层锚点，绝不参与卖方均值；
5. 仅用口径可比的券商研报形成卖方一致预期；只有一个有效样本时必须写“单一卖方基准”，不得称为多家共识；
6. 专家/纪要只有在未被官方指引和卖方模型吸收时才能修正；
7. 给出 AlphaSonar 最终预测，并同时计算相对官方指引中值、相对卖方一致预期的差值。

【硬护栏 · 业绩拆解不是机械分摊】
只选择对该公司预测有解释力的分部、产品、客户或供给变量。没有分部数量证据时写“方向验证/待量化”，
不得按历史占比机械拆分合并收入。供给约束行业必须识别真正限制交付的环节，名义产能不能直接等同收入。
弱证据只调整Bull/Bear概率，不改变Base金额。
新闻报道（web_news）默认属于弱证据：单一媒体、券商转述或渠道传闻不得修改Base金额；
只有与公司公告/官方财报或另一独立高可信来源交叉确认后，才可作为已验证事实参与Base推导。

【硬护栏 · 禁止机械拆季度】
严禁用以下方法从全年数拆出季度：全年 ÷ 4、剩余收入 × 固定比例、仅凭"季节性"套 30%/33%/37%。
拆季必须至少有一种依据：公司季度指引 / 明确的季度一致预期 / 券商季度预测表 / 已披露的季度订单或出货计划。
若以上依据都缺失，该季度只输出"季度数据不足，无法从全年预测可靠拆分"，不得强行给数。
（极少数情况可用固定比例作为"明确标注的情景假设"，但必须显式标注为情景、不得当作基准点预测。）

【硬护栏 · 越界必须举证，不缩回】
AlphaSonar 点预测可以落在公司指引区间之外——这正是修正值的来源，不要为了贴合指引而缩回区间内。
但越界时必须同时满足：(a) 挂一条显式理由；(b) 指向具体证据来源(source_file/chunk)；(c) 标出 Δ=AlphaSonar预测−指引中值。
若越界却拿不出未被吸收的、可量化的证据 Δ → 判为无依据，此时才降回区间内或明确标注为 Bull/Bear case。

请输出：
## 📈 业绩预测 · {company_name}

### 核心业务判断与业绩拆解
| 业务/产品 | 最近实际表现 | 本期核心驱动 | 对收入的作用 | 对利润率的作用 | 证据与置信度 |
|:---|:---|:---|:---|:---|:---|

### 利润桥
| 环节 | 假设/计算 | 结果 | 变化原因 | 不确定性 |
|:---|:---|:---|:---|:---|

必须形成“分部/产品→合并收入→毛利→营业利润→税后利润→EPS”的完整链；缺数据处明确标待量化。

### 预测校验
（字段口径、历史基数、GAAP/Non-GAAP、样本覆盖度）

### 公司官方指引
| 期间 | 收入区间/中值 | 毛利率 | EPS | 口径 | 来源 |
|:---|:---|:---|:---|:---|:---|

### 卖方一致预期
| 券商 | 日期 | 收入预测 | 净利润/EPS预测 | 口径 | 权重/说明 |
|:---|:---|:---|:---|:---|:---|

### AlphaSonar修正后预测
| 期间 | 公司官方指引 | 卖方一致预期 | AlphaSonar预测 | AlphaSonar vs 指引中值 | AlphaSonar vs一致预期 |
|:---|:---|:---|:---|:---|:---|

差值必须用绝对值+百分比表示；上调用 **🔼**，下调用 **🔽**，无修正写 **0（维持）**。

### 预测依据（附来源标注）
（逐条列出，每条带 [来源: ...]）

### 主要预测风险
（可能导致预测偏差的因素）
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def price_target(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """预测股价：估值模型 + 券商目标价共识"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")

    fin_lines = []
    for k, v in fin.items():
        fin_lines.append(f"  {k}: {v.get('value')}")
    fin_text = "\n".join(fin_lines) or "暂无财务数据"

    # 找含目标价的切片
    target_snips = [
        f"[{_source_meta(c)}] {c['text'][:200]}"
        for c in _evidence_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["目标价", "目标市值", "PE", "PS", "估值", "合理价值"])
    ][:4]
    target_text = "\n".join(f"- {s}" for s in target_snips) or "暂无本地目标价数据"

    prompt = f"""你是量化分析师。请基于以下本地数据估算 {company_name}({ticker}) 合理股价区间。

【财务指标 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【目标价/估值参考】(来源: LanceDB broker_report + acecamp_expert_column + company_filing/announcement + web_news；只有券商研报可进入券商目标价共识，新闻转述不得重复计数)
{target_text}

{_GROUNDING_RULE}

请输出：
## 💹 股价目标 · {company_name}

### 估值区间
| 估值方法 | 假设 | 隐含价格 | 来源 |
|:---|:---|:---|:---|
| PE法 | ... | ... | [来源: ...] |
| PS法 | ... | ... | [来源: ...] |

### 券商目标价共识
（列出本地数据中出现的目标价，每条带来源标注）

### 当前定价隐含的预期
（若无本地股价数据，写"暂无本地价格数据"）
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def marginal_change(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """边际改变：最新催化剂 + 与上期对比的增量变化"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")

    deltas = []
    for k, v in fin.items():
        qoq = v.get("qoq_pct")
        yoy = v.get("yoy_pct")
        if qoq is not None:
            deltas.append(f"{k}: QoQ {qoq:+.1f}% / YoY {yoy:+.1f}%")
    delta_text = "\n".join(deltas) or "暂无环比数据"

    # 按 pub_date 排序取最新研报
    recent = _latest_one_per_source(_evidence_chunks(vector_chunks), limit=5)
    recent_text = "\n".join(f"- [{c.get('pub_date','?')}] [{_source_meta(c)}] {c['text'][:120]}"
                            for c in recent) or "暂无近期事实证据"

    prompt = f"""你是行业跟踪分析师。请聚焦于 {company_name}({ticker}) 的边际变化，输出增量信息。

【环比/同比变化 · 周期: {period}】(来源: SQLite financial_reports)
{delta_text}

【最新事实证据（按时间排序）】(来源: LanceDB broker_report + acecamp_expert_column + company_filing/announcement + web_news；新闻不进入卖方一致预期，未交叉确认时只作弱证据)
{recent_text}

{_GROUNDING_RULE}

请输出：
## 🔄 边际改变 · {company_name}

### 核心变化（3条以内，最重要的排第一）
1. **[变化描述]** [来源: ...]
   - 变化前：...
   - 变化后：...
   - 影响：...

### 催化剂时间线
（列出近期重要事件，格式：日期 · 事件 · 影响方向 · [来源: ...]）

### 哪些预期尚未price in
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def relationship_graph(
    ticker: str,
    company_name: str,
    product: str,
    chain_companies: list[dict],
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """关系图谱：产业链传导 + 竞争格局文字描述 + HTML路径"""
    chain_text = "\n".join(
        f"- {r['company_name']}({r['ticker']}) 生产 {r['product']}"
        for r in chain_companies
    ) or "图谱暂无传导路径"

    compete_snips = [
        f"[{_source_meta(c)}] {c['text'][:150]}"
        for c in _evidence_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["竞争", "市占率", "份额", "对手", "替代"])
    ][:3]
    compete_text = "\n".join(f"- {s}" for s in compete_snips) or "暂无本地竞争数据"

    # trigger pyvis rendering
    import subprocess, sys
    from alphasonar.settings import get_settings
    settings = get_settings()
    script = settings.project_root / "scripts" / "dev" / "visualize_graph.py"
    html_path = settings.artifact_root / "graphs" / f"graph_viz_{ticker}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([sys.executable, str(script), ticker])

    prompt = f"""你是产业链研究员。请描述 {company_name}({ticker}) 的关系图谱。

【产业链传导（来自 Kùzu 图谱）】
{chain_text}
核心产品：{product}

【竞争格局证据摘要】(来源: LanceDB broker_report + acecamp_expert_column + company_filing/announcement + web_news；新闻不进入卖方一致预期，未交叉确认时只作弱证据)
{compete_text}

{_GROUNDING_RULE}

请输出：
## 🌐 关系图谱 · {company_name}

### 产业链位置
（上游 → 本公司({company_name}) → 下游，文字描述，附 [来源: Kùzu]）

### 核心竞争对手
| 竞争对手 | 优势 | 劣势 | 来源 |
|:---|:---|:---|:---|

### 产业链传导风险
（上游涨价/下游需求变化如何影响本公司）

---
📊 **交互式图谱已生成** → 用浏览器打开: `{html_path}`
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def opportunity_risk(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    chain_companies: list[dict],
    llm_caller,
) -> str:
    """机会与风险：多空双向辩证分析"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")
    gm = fin.get("gross_margin", {})

    fin_text = f"毛利率: {gm.get('value')} YoY {gm.get('yoy_pct')}%"

    bull_snips = [
        f"[{_source_meta(c)}] {c['text'][:150]}"
        for c in _evidence_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["买入", "增持", "催化", "机会", "上行", "超预期"])
    ][:3]
    bear_snips = [
        f"[{_source_meta(c)}] {c['text'][:150]}"
        for c in _evidence_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["风险", "减持", "不确定", "下行", "低于预期", "竞争加剧"])
    ][:3]

    bull_text = "\n".join(f"- {s}" for s in bull_snips) or "暂无看多研报"
    bear_text = "\n".join(f"- {s}" for s in bear_snips) or "暂无看空研报"

    chain_text = ", ".join(r["company_name"] for r in chain_companies) or "暂无图谱数据"

    prompt = f"""你是对冲基金研究员，对多空双方同样严苛。请对 {company_name}({ticker}) 做机会与风险分析。

【财务数据 · {period}】(来源: SQLite)
{fin_text}

【看多证据摘要】(来源: LanceDB broker_report + acecamp_expert_column + company_filing/announcement + web_news；新闻不进入卖方一致预期，未交叉确认时只作弱证据)
{bull_text}

【看空/风险证据摘要】(来源: LanceDB broker_report + acecamp_expert_column + company_filing/announcement + web_news；新闻不进入卖方一致预期，未交叉确认时只作弱证据)
{bear_text}

【产业链相关公司】(来源: Kùzu)
{chain_text}

{_GROUNDING_RULE}

请输出：
## ⚖️ 机会与风险 · {company_name}

### 🟢 核心机会（Bull Case）
| 催化剂 | 概率估计 | 潜在影响 | 来源 |
|:---|:---|:---|:---|

### 🔴 核心风险（Bear Case）
| 风险因素 | 严重程度 | 触发条件 | 来源 |
|:---|:---|:---|:---|

### 🎯 关键观测指标
（未来3个月需要跟踪的3-5个指标，用于判断多空方向）

### AlphaSonar 综合评分
- 机会强度：⭐⭐⭐（仅基于本地数据）
- 风险程度：⭐⭐⭐
- 数据完整性：（缺少哪些关键数据）
"""
    return llm_caller(_GROUNDING_RULE, prompt)
