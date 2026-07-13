"""
MCP server entry point — exposes the 4 Skills as MCP tools for Claude Desktop.
Run with: python src/mcp_server.py
"""

import anthropic
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.skills import skill1_text2sql, skill2_calculator, skill3_graph_propagator, skill4_verifier, skill5_focused, skill6_event_catalyst
from src.agents import orchestrator
from src.utils.prompts import load

_INSTRUCTIONS = load("instructions.md")

app = Server("ira-mcp", instructions=_INSTRUCTIONS)

# Shared LLM caller using Anthropic SDK. Keep this lazy so startup diagnostics
# reflect the environment used by the actual MCP process.
_client: anthropic.Anthropic | None = None


def _client_context() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    host = urlparse(base).netloc if base else "api.anthropic.com(default)"
    return f"ANTHROPIC_API_KEY set={bool(key)} len={len(key)}; ANTHROPIC_BASE_URL host={host}"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

def _llm(system: str, user: str) -> str:
    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
    except Exception as e:
        if "401" in str(e) or "authentication" in str(e).lower():
            raise Exception(
                "401 authentication_error: Anthropic 鉴权失败，请检查 MCP 启动配置中的 "
                f"ANTHROPIC_API_KEY 与 ANTHROPIC_BASE_URL 是否匹配。当前进程环境: {_client_context()}。"
                f"原始错误: {e}"
            )
        raise


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="text2sql",
            description="将自然语言问题转换为 SQL 并查询本地 SQLite 财务数据库，返回原始数字行。【返回结果即为唯一真实来源，若 rows 为空则代表本地无此数据，不得用训练记忆补充】",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "自然语言提问"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="financial_dashboard",
            description="对指定 ticker 和财报周期计算同比/环比财务指标看板（Python 硬编码，无 LLM 参与）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string", "description": "如 2026Q2"},
                },
                "required": ["ticker", "period"],
            },
        ),
        Tool(
            name="graph_propagation",
            description="输入上游商品名，查询 Kùzu 图数据库返回受该商品价格波动影响的上市公司列表。",
            inputSchema={
                "type": "object",
                "properties": {"product": {"type": "string", "description": "如 钛白粉"}},
                "required": ["product"],
            },
        ),
        Tool(
            name="adversarial_report",
            description="调用多源对抗互证器，生成完整的 IRA 辩证投研 Markdown 报告。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="earnings_forecast",
            description="【预测业绩】分层使用历史实际值、公司官方指引、卖方一致预期与专家增量修正，预测未来2季度营收/净利润区间。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string", "description": "基准周期，如 2026Q1"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="price_target",
            description="【预测股价】基于本地财务数据 + 券商目标价研报，估算合理股价区间（PE/PS/PB法）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="marginal_change",
            description="【边际改变】提取最新催化剂、环比增量变化、尚未price-in的预期。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="relationship_graph",
            description="【关系图谱】产业链传导、竞争格局文字分析，并生成可交互 HTML 图谱文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                },
                "required": ["ticker", "company_name"],
            },
        ),
        Tool(
            name="opportunity_risk",
            description="【机会与风险】多空双向辩证分析，输出 Bull Case / Bear Case 及关键观测指标。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="full_analysis",
            description="【完整多 Agent 分析】依次调用研究员→风控→策略→交易员→PM 五个 Agent，输出完整投研决策报告。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "company_name": {"type": "string"},
                    "period": {"type": "string", "description": "如 2026Q1"},
                },
                "required": ["ticker", "company_name", "period"],
            },
        ),
        Tool(
            name="event_catalyst",
            description="【事件驱动分析】输入热门事件描述，结合宏观指标（YFinance）和新闻（Tushare），分析对 watchlist 各公司的催化/压制影响及传导路径。",
            inputSchema={
                "type": "object",
                "properties": {
                    "event": {"type": "string", "description": '事件描述，如"英伟达 Blackwell 供应链砍单"'},
                },
                "required": ["event"],
            },
        ),
    ]


_VOCAB_CACHE: list[dict] | None = None


def _load_vocab_entries() -> list[dict]:
    global _VOCAB_CACHE
    if _VOCAB_CACHE is None:
        vpath = Path(__file__).parent.parent / "config" / "vocab_dictionary.json"
        _VOCAB_CACHE = json.loads(vpath.read_text()) if vpath.exists() else []
    return _VOCAB_CACHE


def _normalize_ticker_arg(ticker: str) -> str:
    """把调用方传入的 ticker 归一化成 vocab 里的标准代码（带市场后缀）。
    命中规则（按可信度）：
      1) 已带 . 后缀且能在 vocab 精确匹配 → 原样返回（如 INTC.US、688141.SH）
      2) 裸代码/别名 → 用 vocab 的 ticker 前缀、standard_name、aliases 反查补全后缀
         （INTC→INTC.US、Intel→INTC.US、英特尔→INTC.US）
    查不到任何映射 → 原样返回（不猜、不改，让下游照常"无数据"，避免误映射到错标的）。"""
    if not ticker:
        return ticker
    t = ticker.strip()
    entries = [e for e in _load_vocab_entries() if e.get("entity_type") == "Company" and e.get("ticker")]
    # 1) 精确匹配已带后缀的标准代码
    for e in entries:
        if e["ticker"].upper() == t.upper():
            return e["ticker"]
    # 2) 裸代码：匹配 ticker 的 "." 前缀部分（INTC == INTC.US 的 INTC）
    for e in entries:
        if e["ticker"].split(".")[0].upper() == t.upper():
            return e["ticker"]
    # 3) 公司名/别名反查
    for e in entries:
        names = [e.get("standard_name", "")] + e.get("aliases", [])
        if any(t.upper() == n.upper() for n in names if n):
            return e["ticker"]
    return ticker


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # 清洗后数据库标准代码带市场后缀（INTC.US / AMD.US / 688141.SH）。用户/调用方常
    # 只传裸代码 INTC，直接查库会命中不到、错误返回"无数据"。这里在入口统一把 ticker
    # 归一化成 vocab 里的标准代码（INTC→INTC.US），所有下游 skill 自动受益。
    if isinstance(arguments, dict) and arguments.get("ticker"):
        arguments = {**arguments, "ticker": _normalize_ticker_arg(arguments["ticker"])}

    if name == "text2sql":
        result = skill1_text2sql.run(arguments["query"], _llm)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "financial_dashboard":
        result = skill2_calculator.compute(arguments["ticker"], arguments["period"])
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "graph_propagation":
        result = skill3_graph_propagator.query(arguments["product"])
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "adversarial_report":
        ticker = arguments["ticker"]
        period = arguments["period"]
        company_name = arguments["company_name"]

        dashboard = skill2_calculator.compute(ticker, period)

        # resolve product from vocab for graph query
        import json as _json
        from pathlib import Path as _Path
        _vocab_path = _Path(__file__).parent.parent / "config" / "vocab_dictionary.json"
        _vocab = _json.loads(_vocab_path.read_text()) if _vocab_path.exists() else []
        _ticker_entry = next((e for e in _vocab if e.get("ticker") == ticker), None)
        _product = _ticker_entry.get("product", "") if _ticker_entry else ""
        chain = skill3_graph_propagator.query(_product) if _product else []

        # 分层检索：卖方预测与公司官方指引使用不同查询，再合并交给 verifier；
        # verifier 会按 data_source 物理隔离，官方材料绝不进入卖方一致预期。
        from src.db.vector_store import search as vector_search
        sellside_chunks = vector_search(
            query=f"{company_name} 财务 业绩",
            ticker=ticker,
            top_k=15,
        )
        official_chunks = vector_search(
            query=f"{company_name} 公司官方 下一季度 收入指引 毛利率 EPS outlook guidance",
            ticker=ticker,
            top_k=15,
        )
        vector_chunks = []
        seen_ids = set()
        for chunk in sellside_chunks + official_chunks:
            key = chunk.get("chunk_id")
            if key in seen_ids:
                continue
            seen_ids.add(key)
            vector_chunks.append(chunk)

        report = skill4_verifier.run(
            ticker=ticker,
            company_name=company_name,
            financial_dashboard=dashboard,
            vector_chunks=vector_chunks,
            market_snippets=[],
            chain_companies=chain,
            llm_caller=_llm,
        )
        return [TextContent(type="text", text=report)]

    # ── Skill 5: focused analysis shortcuts ──────────────────────────────────
    if name in ("earnings_forecast", "price_target", "marginal_change",
                "relationship_graph", "opportunity_risk"):
        ticker       = arguments["ticker"]
        company_name = arguments["company_name"]
        period       = arguments.get("period", "2026Q1")

        import json as _json
        from pathlib import Path as _Path
        from src.db.vector_store import search as vector_search

        # shared data fetching
        dashboard = skill2_calculator.compute(ticker, period)
        _vocab_path = _Path(__file__).parent.parent / "config" / "vocab_dictionary.json"
        _vocab = _json.loads(_vocab_path.read_text()) if _vocab_path.exists() else []
        _entry  = next((e for e in _vocab if e.get("ticker") == ticker), None)
        product = _entry.get("product", "") if _entry else ""
        chain   = skill3_graph_propagator.query(product) if product else []
        if name == "earnings_forecast":
            chunk_query = f"{company_name} 盈利预测 2026E 2027E 2028E 营业收入 归母净利润 EPS PE PS 东吴证券 国信证券"
            top_k = 30
        elif name == "price_target":
            chunk_query = f"{company_name} 目标价 估值 PE PS PB 合理价值 盈利预测"
            top_k = 20
        else:
            chunk_query = f"{company_name} 业绩 研报 专家纪要 边际变化"
            top_k = 15
        chunks  = vector_search(query=chunk_query, ticker=ticker, top_k=top_k)

        if name == "earnings_forecast":
            result = skill5_focused.earnings_forecast(ticker, company_name, dashboard, chunks, _llm)
        elif name == "price_target":
            result = skill5_focused.price_target(ticker, company_name, dashboard, chunks, _llm)
        elif name == "marginal_change":
            result = skill5_focused.marginal_change(ticker, company_name, dashboard, chunks, _llm)
        elif name == "relationship_graph":
            result = skill5_focused.relationship_graph(ticker, company_name, product, chain, chunks, _llm)
        elif name == "opportunity_risk":
            result = skill5_focused.opportunity_risk(ticker, company_name, dashboard, chunks, chain, _llm)
        return [TextContent(type="text", text=result)]

    if name == "full_analysis":
        result = orchestrator.run(
            ticker=arguments["ticker"],
            company_name=arguments["company_name"],
            period=arguments["period"],
            llm_caller=_llm,
        )
        return [TextContent(type="text", text=result)]

    if name == "event_catalyst":
        result = skill6_event_catalyst.run(arguments["event"], _llm)
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
