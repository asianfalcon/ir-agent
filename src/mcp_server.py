"""
MCP server entry point — exposes the 4 Skills as MCP tools for Claude Desktop.
Run with: python src/mcp_server.py
"""

import anthropic
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.skills import skill1_text2sql, skill2_calculator, skill3_graph_propagator, skill4_verifier

app = Server("ira-mcp")

# Shared LLM caller using Anthropic SDK
_client = anthropic.Anthropic()

def _llm(system: str, user: str) -> str:
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="text2sql",
            description="将自然语言问题转换为 SQL 并查询本地 SQLite 财务数据库，返回原始数字行。",
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

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
