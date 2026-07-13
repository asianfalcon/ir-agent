"""
Orchestrator — 按研究员→风控/策略/交易员→PM 顺序编排 5 个 Agent。
"""
from src.agents import researcher, risk, strategy, trader, pm


def run(
    ticker: str,
    company_name: str,
    period: str,
    llm_caller,
) -> str:
    from src.skills import skill2_calculator, skill3_graph_propagator
    from src.db.vector_store import search as vector_search
    import json
    from pathlib import Path

    # ── 共享数据层（一次拉取，四个 Agent 复用）────────────────────────────
    dashboard = skill2_calculator.compute(ticker, period)

    vocab_path = Path(__file__).parent.parent.parent / "config" / "vocab_dictionary.json"
    vocab = json.loads(vocab_path.read_text()) if vocab_path.exists() else []
    entry = next((e for e in vocab if e.get("ticker") == ticker), None)
    product = entry.get("product", "") if entry else ""

    chain = skill3_graph_propagator.query(product) if product else []
    chunk_queries = [
        f"{company_name} 业绩 研报 专家纪要 边际变化",
        f"{company_name} 盈利预测 2026E 2027E 2028E 营业收入 归母净利润 EPS PE PS 东吴证券 国信证券",
        f"{company_name} 目标价 估值 PE PS PB 合理价值",
    ]
    chunks = []
    seen_chunk_ids = set()
    for query in chunk_queries:
        for chunk in vector_search(query=query, ticker=ticker, top_k=15):
            key = chunk.get("chunk_id")
            if key in seen_chunk_ids:
                continue
            seen_chunk_ids.add(key)
            chunks.append(chunk)
    forecast_keywords = ("盈利预测", "财务预测", "2026E", "2027E", "2028E", "营业收入", "归母净利润", "EPS", "PE", "PS")

    def chunk_score(chunk: dict) -> int:
        text = chunk.get("text", "")
        file_name = chunk.get("source_file", "").rsplit("/", 1)[-1]
        score = sum(3 for keyword in forecast_keywords if keyword in text)
        directly_related = company_name in text or company_name in file_name or ticker in text or ticker in file_name
        if directly_related:
            score += 5
        if chunk.get("data_source") == "broker_report":
            score += 2
        if not directly_related:
            score -= 8
        return score

    chunks.sort(key=chunk_score, reverse=True)

    # 四层证据物理隔离：历史实际值在 dashboard；官方指引、卖方预测、专家补充
    # 分开传递，避免下游 Agent 把公司自述当成卖方共识。
    official_chunks = [c for c in chunks if c.get("data_source") in {"company_filing", "announcement"}]
    sellside_chunks = [c for c in chunks if c.get("data_source") == "broker_report"]
    supplemental_chunks = [c for c in chunks if c.get("data_source") == "acecamp_expert_column"]
    shared_data = {
        "dashboard": dashboard,
        "chunks": chunks,
        "official_chunks": official_chunks,
        "sellside_chunks": sellside_chunks,
        "supplemental_chunks": supplemental_chunks,
        "chain": chain,
    }

    # ── Agent 调用链 ──────────────────────────────────────────────────────
    researcher_out = researcher.run(ticker, company_name, shared_data, llm_caller)
    risk_out       = risk.run(company_name, ticker, researcher_out, llm_caller)
    strategy_out   = strategy.run(company_name, ticker, researcher_out, llm_caller)
    trader_out     = trader.run(company_name, ticker, researcher_out, llm_caller)
    pm_out         = pm.run(company_name, ticker,
                            researcher_out, risk_out, strategy_out, trader_out,
                            llm_caller)

    # ── 拼装完整报告 ──────────────────────────────────────────────────────
    return f"""# 🏦 IRA 多 Agent 投研报告 · {company_name}（{ticker}）· {period}

---

## 📋 研究员
{researcher_out}

---

## 🛡️ 风控
{risk_out}

---

## 📊 策略
{strategy_out}

---

## ⚡ 交易员
{trader_out}

---

## 🎯 PM 决策
{pm_out}
"""
