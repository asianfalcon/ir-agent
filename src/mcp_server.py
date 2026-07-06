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
            description="【预测业绩】基于历史财务趋势 + 本地券商研报共识，预测未来2季度营收/净利润区间。",
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


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
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

        # vector search for sell-side chunks
        from src.db.vector_store import search as vector_search
        vector_chunks = vector_search(
            query=f"{company_name} 财务 业绩",
            ticker=ticker,
            top_k=8,
        )

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
        chunks  = vector_search(query=f"{company_name} 业绩 研报", ticker=ticker, top_k=10)

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
