"""研究员 Agent — 整理原始数据，输出结构化事实清单。"""
from src.utils.prompts import load

_SYSTEM = load("agent_researcher.md")


def run(ticker: str, company_name: str, shared_data: dict, llm_caller) -> str:
    fin = shared_data.get("dashboard", {}).get("metrics", {})
    period = shared_data.get("dashboard", {}).get("period", "")
    chunks = shared_data.get("chunks", [])
    chain = shared_data.get("chain", [])
    sql_rows = shared_data.get("sql_rows", [])

    fin_lines = "\n".join(
        f"  {k}: {v.get('value')} | YoY {v.get('yoy_pct')}% | QoQ {v.get('qoq_pct')}%"
        for k, v in fin.items()
    ) or "  暂无财务数据"

    chunk_lines = "\n".join(
        f"  [{c.get('pub_date','?')}] [{c.get('data_source','?')}]"
        f"{' [hot]' if c.get('is_hot') else ''}"
        f" [weight={c.get('source_weight', 1.0)}] {c.get('text','')[:120]}"
        f" [来源: LanceDB {c.get('source_file','')}]"
        for c in chunks[:6]
    ) or "  暂无研报/专家专栏数据"

    chain_lines = "\n".join(
        f"  {r['company_name']}({r['ticker']}) 生产 {r['product']} [来源: Kùzu]"
        for r in chain
    ) or "  暂无图谱数据"

    user = f"""
公司：{company_name}（{ticker}）  周期：{period}

【财务数据】来源: SQLite financial_reports
{fin_lines}

【研报/专家专栏摘要】来源: LanceDB broker_report + acecamp_expert_column
{chunk_lines}

【产业链】来源: Kùzu 图谱
{chain_lines}

请整理成结构化事实清单。
"""
    return llm_caller(_SYSTEM, user)
