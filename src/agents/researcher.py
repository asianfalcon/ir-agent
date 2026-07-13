"""研究员 Agent — 整理原始数据，输出结构化事实清单。"""
from src.utils.prompts import load

_SYSTEM = load("agent_researcher.md")


def run(ticker: str, company_name: str, shared_data: dict, llm_caller) -> str:
    fin = shared_data.get("dashboard", {}).get("metrics", {})
    period = shared_data.get("dashboard", {}).get("period", "")
    official_chunks = shared_data.get("official_chunks", [])
    sellside_chunks = shared_data.get("sellside_chunks", [])
    supplemental_chunks = shared_data.get("supplemental_chunks", [])
    chain = shared_data.get("chain", [])
    sql_rows = shared_data.get("sql_rows", [])

    fin_lines = "\n".join(
        f"  {k}: {v.get('value')} | YoY {v.get('yoy_pct')}% | QoQ {v.get('qoq_pct')}%"
        for k, v in fin.items()
    ) or "  暂无财务数据"

    official_lines = "\n".join(
        f"  [{c.get('pub_date','?')}] [{c.get('data_source','?')}]"
        f"{' [hot]' if c.get('is_hot') else ''}"
        f" [weight={c.get('source_weight', 1.0)}] {c.get('text','')[:120]}"
        f" [来源: LanceDB {c.get('source_file','')}]"
        for c in official_chunks[:6]
    ) or "  暂无公司官方指引数据"

    sellside_lines = "\n".join(
        f"  [{c.get('pub_date','?')}] [broker_report] {c.get('text','')[:120]}"
        f" [来源: LanceDB {c.get('source_file','')}]"
        for c in sellside_chunks[:8]
    ) or "  暂无券商研报数据"

    supplemental_lines = "\n".join(
        f"  [{c.get('pub_date','?')}] [acecamp_expert_column] {c.get('text','')[:120]}"
        f" [来源: LanceDB {c.get('source_file','')}]"
        for c in supplemental_chunks[:5]
    ) or "  暂无专家补充观点"

    chain_lines = "\n".join(
        f"  {r['company_name']}({r['ticker']}) 生产 {r['product']} [来源: Kùzu]"
        for r in chain
    ) or "  暂无图谱数据"

    user = f"""
公司：{company_name}（{ticker}）  周期：{period}

【财务数据】来源: SQLite financial_reports
{fin_lines}

【公司官方指引】来源: LanceDB company_filing + announcement
{official_lines}

【卖方一致预期候选】来源: LanceDB broker_report
{sellside_lines}

【专家补充观点】来源: LanceDB acecamp_expert_column（不进入卖方均值）
{supplemental_lines}

【产业链】来源: Kùzu 图谱
{chain_lines}

请整理成结构化事实清单。
"""
    return llm_caller(_SYSTEM, user)
