"""
Skill 4: Multi-source adversarial verifier — collects outputs from Skills 1-3
and forces the LLM to find contradictions across official, sell-side, and market data.
"""

from typing import Any
from src.utils.prompts import load

SYSTEM_PROMPT = load("skill4_system.md")
REPORT_TEMPLATE = load("skill4_report_template.md")
RESEARCH_DATA_SOURCES = {"broker_report", "acecamp_expert_column"}


def run(
    ticker: str,
    company_name: str,
    financial_dashboard: dict[str, Any],
    vector_chunks: list[dict],
    market_snippets: list[str],
    chain_companies: list[dict],
    llm_caller,
) -> str:
    """
    llm_caller: callable(system_prompt, user_prompt) -> str
    Returns a fully rendered Markdown report string.
    """
    fin = financial_dashboard.get("metrics", {})
    gm = fin.get("gross_margin", {})
    period = financial_dashboard.get("period", "")

    official_data = (
        f"毛利率: {gm.get('value')}  YoY: {gm.get('yoy_pct')}%  QoQ: {gm.get('qoq_pct')}%"
    )

    # LanceDB returns flat rows; metadata fields are top-level
    sellside_snippets = [
        c["text"][:120]
        for c in vector_chunks
        if c.get("data_source") in RESEARCH_DATA_SOURCES
    ][:3]
    sellside_data = " | ".join(sellside_snippets) or "无研报/专家专栏切片"

    market_data = " | ".join(market_snippets[:3]) or "无爬虫数据"

    chain_text = "\n".join(
        f"- {r['company_name']} ({r['ticker']}) 生产 {r['product']}" for r in chain_companies
    ) or "图谱暂无传导路径"

    # Build financial table markdown
    rows = []
    for col, vals in fin.items():
        rows.append(f"| **{col}** | {vals.get('value')} | {vals.get('yoy_pct')}% | {vals.get('qoq_pct')}% |")
    header = "| 指标 | 最新值 | YoY | QoQ |\n| :--- | :--- | :--- | :--- |"
    financial_table = header + "\n" + "\n".join(rows)

    user_prompt = f"""
公司: {company_name} ({ticker})  周期: {period}

【官方财务数据】(来源: SQLite financial_reports 表)
{official_data}

【卖方研报/专家专栏摘要】(来源: LanceDB broker_report + acecamp_expert_column 向量切片)
{sellside_data}

【市场实时数据】(来源: 爬虫)
{market_data}

【产业链传导公司池】(来源: Kùzu 图谱)
{chain_text}

请严格按如下格式输出，不得省略任何章节：

===RATING===
(风险/机会评级，如：中性偏多 / 警惕下行)

===SUMMARY===
(一句话定调，30字以内)

===CONFLICT===
(三源数据中发现的具体矛盾点；若数据不足，写"信息链完整性风险：缺少X数据")

===REASONING_CHAIN===
(请逐步写出推理链，格式如下：)
步骤1 · 证据：[引用原始数据原文或数字] [来源: SQLite/LanceDB/Kùzu] → 推论：[从该数据得出的直接结论]
步骤2 · 证据：[...] [来源: ...] → 推论：[...]
(每条结论必须有对应的原始数据支撑，禁止引用本 prompt 未出现的数字，所有数字必须带 [来源:] 标注)
"""
    llm_output = llm_caller(SYSTEM_PROMPT, user_prompt)

    def _extract(tag: str) -> str:
        import re
        m = re.search(rf"==={tag}===\s*(.*?)(?:===|\Z)", llm_output, re.DOTALL)
        return m.group(1).strip() if m else "[解析失败]"

    rating = _extract("RATING")
    summary = _extract("SUMMARY")
    conflict = _extract("CONFLICT")
    reasoning_chain = _extract("REASONING_CHAIN")

    # Inject deterministic sections (LLM cannot overwrite these)
    report = REPORT_TEMPLATE.format(
        company_name=company_name,
        ticker=ticker,
        rating=rating,
        summary=summary,
        official_data=official_data,
        conflict=conflict,
        sellside_data=sellside_data,
        market_data=market_data,
        financial_table=financial_table,
        chain_text=chain_text,
        reasoning_chain=reasoning_chain,
    )
    return report
