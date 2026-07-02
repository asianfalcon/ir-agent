"""
Skill 4: Multi-source adversarial verifier — collects outputs from Skills 1-3
and forces the LLM to find contradictions across official, sell-side, and market data.
"""

from typing import Any

SYSTEM_PROMPT = """你是一个严苛的投研风控专家。请将以下三组数据放在天平两端进行比对：
1. 官方表述 (SQLite财务数据与公告文本)
2. 卖方预期 (券商研报向量切片)
3. 客观现实 (垂直行业网站抓取的实时商品价格与供需舆情)

请执行以下辩证对齐动作：
- 检查【官方自述】的毛利率趋势是否与【客观现实】的原材料涨价周期相冲突？
- 检查【卖方预期】给出的盈利预测，是否显著脱离了【官方自述】的历史时序连续性？
- 必须找出至少一个潜在的矛盾点。若无显著冲突，需提示信息链的完整性风险。
- 最终输出严格遵循以下 Markdown 报告骨架，不得省略任何章节。"""

REPORT_TEMPLATE = """# 📊 【IRA 辩证投研报告】{company_name} ({ticker}) 基本面深度穿透

---

## 核心辩证结论
> ⚡ **风险/机会评级：** {rating}
> **一句话定调：** {summary}

---

## ⚖️ 多源对抗互证天平

| 维度 | 数据源 | 核心立场/关键数据 | 冲突与矛盾 (IRA 警告) |
| :--- | :--- | :--- | :--- |
| **官方自述** | 公司财报 & 公告 | {official_data} | {conflict} |
| **卖方评价** | 券商研报切片 | {sellside_data} | |
| **客观现实** | 垂直网站爬虫 | {market_data} | |

---

## 🔢 确定性财务看板 (Python 硬编码计算)

{financial_table}

*(注：定量数字 100% 提取自 SQLite 本地关系库，未经 LLM 重组)*

---

## 🌐 产业链传导因果链条

{chain_text}
"""


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
    sellside_snippets = [c["text"][:120] for c in vector_chunks if c.get("data_source") == "broker_report"][:3]
    sellside_data = " | ".join(sellside_snippets) or "无研报切片"

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

【官方财务数据】
{official_data}

【卖方研报摘要】
{sellside_data}

【市场实时数据】
{market_data}

【产业链传导公司池】
{chain_text}

请严格按 Markdown 骨架输出报告，填写 rating、summary 和 conflict 字段。
"""
    llm_output = llm_caller(SYSTEM_PROMPT, user_prompt)

    # Inject deterministic sections (LLM cannot overwrite these)
    report = REPORT_TEMPLATE.format(
        company_name=company_name,
        ticker=ticker,
        rating="[见LLM输出]",
        summary="[见LLM输出]",
        official_data=official_data,
        conflict="[见LLM输出]",
        sellside_data=sellside_data,
        market_data=market_data,
        financial_table=financial_table,
        chain_text=chain_text,
    )
    # Append full LLM reasoning as an appendix
    report += f"\n\n---\n\n## LLM 辩证推演原文\n\n{llm_output}"
    return report
