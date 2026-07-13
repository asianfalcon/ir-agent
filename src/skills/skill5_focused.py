"""
Skill 5: Five focused analysis shortcuts.
Each function returns a Markdown string grounded in local data.
"""

import re
from typing import Any
from src.utils.prompts import load

_GROUNDING_RULE = load("skill5_grounding_rule.md")
RESEARCH_DATA_SOURCES = {"broker_report", "acecamp_expert_column"}
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
    return [c for c in vector_chunks if c.get("data_source") in RESEARCH_DATA_SOURCES]


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


def _team_of(chunk: dict) -> str | None:
    """从source_file文件名提取研报团队名（如"华泰证券"），提取不出来（文件名
    不是"YYYYMMDD-团队-..."格式，如年报/财报电话会/SEC文件）时返回None——
    团队不明的chunk不参与同团队去重，宁可留着不去重，也不误删。"""
    source_file = chunk.get("source_file", "")
    file_name = source_file.rsplit("/", 1)[-1]
    m = _TEAM_RE.match(file_name)
    return m.group(1) if m else None


def _latest_version_per_team(chunks: list[dict]) -> list[dict]:
    """同一团队（如华泰）对同一标的存在多份历史版本研报时，只保留 pub_date
    最新的一份用于当前一致预期基准——原则9"同一研报标题/同一分析师团队对同一
    科目存在多个历史版本时，只有pub_date最新的一份进入一致预期基准表"的机械
    落地。旧版本不删除、不影响历史准确性回测，只是不进入本次consensus baseline
    检索结果，避免1月/4月/6月三份华泰报告的预测数字被一起拿去做均值。"""
    best_pub_date: dict[str, str] = {}
    for chunk in chunks:
        team = _team_of(chunk)
        if not team:
            continue
        pub_date = chunk.get("pub_date", "") or ""
        if pub_date > best_pub_date.get(team, ""):
            best_pub_date[team] = pub_date

    result = []
    for chunk in chunks:
        team = _team_of(chunk)
        if team and chunk.get("pub_date", "") != best_pub_date.get(team):
            continue
        result.append(chunk)
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
    """Return broker/expert chunks most likely to contain sell-side forecasts."""
    chunks = list(vector_chunks)
    try:
        from src.db.vector_store import search as vector_search

        queries = [
            f"{company_name} 盈利预测 2026E 2027E 2028E 营业收入 归母净利润 EPS",
            f"{company_name} 财务预测与估值 营业收入 归属于母公司净利润 2026E 2027E 2028E",
            f"{company_name} 投资建议 盈利预测 每股收益 PE PS",
            f"{company_name} 2026E 2027E 2028E PE PS",
            f"东吴证券 {company_name} 2026E 2027E 2028E",
            f"国信证券 {company_name} 2026E 2027E 2028E",
        ]
        for query in queries:
            chunks.extend(vector_search(query=query, ticker=ticker, top_k=20))
    except Exception as exc:
        print(f"[skill5] forecast vector enrichment skipped: {exc}")

    scored = [
        (chunk, _forecast_score(chunk, company_name))
        for chunk in _latest_version_per_team(_dedupe_chunks(_research_chunks(chunks)))
    ]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [chunk for chunk, _ in scored]


def _source_label(chunk: dict) -> str:
    source = chunk.get("data_source", "")
    if source == "acecamp_expert_column":
        return "AceCamp专家专栏"
    if source == "broker_report":
        return "券商研报"
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
    """预测业绩：历史趋势 + 券商预测共识 → 未来2季度区间预测"""
    fin = dashboard.get("metrics", {})
    rev = fin.get("revenue", {})
    np_ = fin.get("net_profit", {})
    period = dashboard.get("period", "最新")

    fin_text = (
        f"营收: {rev.get('value')} YoY {rev.get('yoy_pct')}% QoQ {rev.get('qoq_pct')}%\n"
        f"净利润: {np_.get('value')} YoY {np_.get('yoy_pct')}% QoQ {np_.get('qoq_pct')}%"
    )

    sell_snips = [
        (
            f"[{_source_meta(c)} · {c.get('pub_date', '?')} · {c.get('source_file', '')}] "
            f"{c['text'][:700]}"
        )
        for c in _forecast_chunks(ticker, company_name, vector_chunks)
    ][:8]
    sell_text = "\n".join(f"- {s}" for s in sell_snips) or "暂无本地研报预测数据"

    prompt = f"""你是卖方分析师。请基于以下本地数据预测 {company_name}({ticker}) 未来2个季度业绩区间。

【历史财务数据 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【券商研报/专家专栏预测摘要】(来源: LanceDB broker_report + acecamp_expert_column)
{sell_text}

{_GROUNDING_RULE}

请输出：
## 📈 业绩预测 · {company_name}

### 基准情景（中性）
| 季度 | 营收预测 | YoY | 净利润预测 | YoY |
|:---|:---|:---|:---|:---|
| 下一季度 | ... | ... | ... | ... |
| 再下季度 | ... | ... | ... | ... |

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
        for c in _research_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["目标价", "目标市值", "PE", "PS", "估值", "合理价值"])
    ][:4]
    target_text = "\n".join(f"- {s}" for s in target_snips) or "暂无本地目标价数据"

    prompt = f"""你是量化分析师。请基于以下本地数据估算 {company_name}({ticker}) 合理股价区间。

【财务指标 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【券商目标价/估值参考】(来源: LanceDB broker_report + acecamp_expert_column)
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
    recent = sorted(
        _research_chunks(vector_chunks),
        key=lambda c: (c.get("release_time") or 0, c.get("pub_date", "")),
        reverse=True,
    )
    recent_snips = [c["text"][:150] for c in recent[:5]]
    recent_text = "\n".join(f"- [{c.get('pub_date','?')}] [{_source_meta(c)}] {c['text'][:120]}"
                            for c in recent[:5]) or "暂无近期研报"

    prompt = f"""你是行业跟踪分析师。请聚焦于 {company_name}({ticker}) 的边际变化，输出增量信息。

【环比/同比变化 · 周期: {period}】(来源: SQLite financial_reports)
{delta_text}

【最新研报/专家专栏摘要（按时间排序）】(来源: LanceDB broker_report + acecamp_expert_column)
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
        for c in _research_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["竞争", "市占率", "份额", "对手", "替代"])
    ][:3]
    compete_text = "\n".join(f"- {s}" for s in compete_snips) or "暂无本地竞争数据"

    # trigger pyvis rendering
    import subprocess, sys
    from pathlib import Path
    root = Path(__file__).parent.parent.parent
    script = root / "scripts" / "visualize_graph.py"
    html_path = root / "data" / f"graph_viz_{ticker}.html"
    subprocess.Popen([sys.executable, str(script), ticker])

    prompt = f"""你是产业链研究员。请描述 {company_name}({ticker}) 的关系图谱。

【产业链传导（来自 Kùzu 图谱）】
{chain_text}
核心产品：{product}

【竞争格局研报/专家专栏摘要】(来源: LanceDB broker_report + acecamp_expert_column)
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
        for c in _research_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["买入", "增持", "催化", "机会", "上行", "超预期"])
    ][:3]
    bear_snips = [
        f"[{_source_meta(c)}] {c['text'][:150]}"
        for c in _research_chunks(vector_chunks)
        if any(kw in c["text"] for kw in ["风险", "减持", "不确定", "下行", "低于预期", "竞争加剧"])
    ][:3]

    bull_text = "\n".join(f"- {s}" for s in bull_snips) or "暂无看多研报"
    bear_text = "\n".join(f"- {s}" for s in bear_snips) or "暂无看空研报"

    chain_text = ", ".join(r["company_name"] for r in chain_companies) or "暂无图谱数据"

    prompt = f"""你是对冲基金研究员，对多空双方同样严苛。请对 {company_name}({ticker}) 做机会与风险分析。

【财务数据 · {period}】(来源: SQLite)
{fin_text}

【看多研报/专家专栏摘要】(来源: LanceDB broker_report + acecamp_expert_column)
{bull_text}

【看空/风险研报/专家专栏摘要】(来源: LanceDB broker_report + acecamp_expert_column)
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

### IRA 综合评分
- 机会强度：⭐⭐⭐（仅基于本地数据）
- 风险程度：⭐⭐⭐
- 数据完整性：（缺少哪些关键数据）
"""
    return llm_caller(_GROUNDING_RULE, prompt)
