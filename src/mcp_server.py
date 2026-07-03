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

from src.skills import skill1_text2sql, skill2_calculator, skill3_graph_propagator, skill4_verifier, skill5_focused

_INSTRUCTIONS = """你是 IRA 投研助手，接入了本地私有知识库（SQLite 财务库 + LanceDB 研报向量库 + Kùzu 图谱）。

IRA 系统四原则（不可违反）：

【原则 1 · 第一性原则】
从数据本身推断，而非从行业印象或训练记忆推断。先问"数据说了什么"，再问"为什么"。

【原则 2 · 对抗式审查】
每个结论必须经过多源交叉验证：官方财报 vs 研报预期 vs 市场实时数据，三者不一致时优先保留矛盾而非平滑掉。

【原则 3 · 拒绝杜撰数据】
- 回答任何具体公司财务问题，必须先调用 MCP 工具。
- 工具返回空（rows:[] 或 __status:NO_LOCAL_DATA），如实告知"本地无此数据"，绝不用训练记忆补充数字。
- 所有数字必须能回溯到具体工具调用结果，无来源则不写。

【原则 4 · 推理链与证据链】
每个结论后面必须附上：
① 证据链：数据来源（哪个工具、哪条 SQL、哪个研报切片）
② 推理链：从原始数据到结论的逻辑步骤，不允许跳跃。

【原则 5 · 来源标注】
所有证据必须在行内标注来源，格式：[来源: 工具名/表名/切片ID]。
例如：毛利率 32.1% [来源: financial_dashboard · SQLite financial_reports]
例如：研报预测营收增速 25% [来源: text2sql · broker_report 切片 #3]
不允许出现无来源标注的数字或事实性陈述。"""

app = Server("ira-mcp", instructions=_INSTRUCTIONS)

# Shared LLM caller using Anthropic SDK
_client = anthropic.Anthropic()

def _llm(system: str, user: str) -> str:
    try:
        msg = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
    except Exception as e:
        if "401" in str(e) or "authentication" in str(e).lower():
            raise Exception(f"401 authentication_error: ANTHROPIC_API_KEY 无效或已过期，请在 MCP 启动配置中更新 Key。原始错误: {e}")
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

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
