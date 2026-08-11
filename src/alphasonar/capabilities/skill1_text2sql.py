"""
Skill 1: Text2SQL — translates natural language to SQL, executes against SQLite,
returns raw rows. LLM is constrained to the registered variable schema columns only.
Falls back to SQL templates when LLM auth fails.
"""

import json
import re
import sqlite3
import time

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
DB_PATH = _SETTINGS.sqlite_path
VOCAB_PATH = _SETTINGS.vocab_path
VAR_SCHEMA_PATH = _SETTINGS.variable_schema_path

# ── SQL templates for common financial queries (LLM-free fallback) ────────────
_TEMPLATES = [
    (
        ["营收", "收入", "revenue"],
        "SELECT period, revenue FROM financial_reports WHERE ticker=? ORDER BY period DESC LIMIT 8",
    ),
    (
        ["净利润", "利润", "profit", "net"],
        "SELECT period, net_profit FROM financial_reports WHERE ticker=? ORDER BY period DESC LIMIT 8",
    ),
    (
        ["毛利", "gross"],
        "SELECT period, gross_margin, revenue FROM financial_reports WHERE ticker=? ORDER BY period DESC LIMIT 8",
    ),
    (
        ["现金流", "cash"],
        "SELECT period, operating_cash_flow FROM financial_reports WHERE ticker=? ORDER BY period DESC LIMIT 8",
    ),
    (
        ["财务", "业绩", "全部", "所有", "overview", "all"],
        "SELECT period, revenue, net_profit, gross_margin FROM financial_reports WHERE ticker=? ORDER BY period DESC LIMIT 8",
    ),
    (
        ["股价", "价格", "price"],
        "SELECT price_date, price_value FROM historical_prices WHERE item_code=? ORDER BY price_date DESC LIMIT 30",
    ),
]


def _template_sql(query: str, ticker: str | None) -> str | None:
    q = query.lower()
    for keywords, sql in _TEMPLATES:
        if any(kw in q for kw in keywords):
            param = ticker or ""
            # historical_prices uses item_code without exchange suffix
            if "historical_prices" in sql:
                param = (ticker or "").split(".")[0]
            return sql, param
    return None


def _resolve_ticker(query: str) -> str | None:
    vocab = json.loads(VOCAB_PATH.read_text()) if VOCAB_PATH.exists() else []
    for entry in vocab:
        if entry.get("entity_type") == "Company":
            names = [entry["standard_name"]] + entry.get("aliases", [])
            if any(n in query for n in names):
                return entry.get("ticker")
    return None


def _schema_context() -> str:
    schema = json.loads(VAR_SCHEMA_PATH.read_text()) if VAR_SCHEMA_PATH.exists() else []
    lines = ["Available columns in financial_reports:"]
    for v in schema:
        mappings = ", ".join(v.get("source_field_mapping", []))
        lines.append(f"  {v['var_name']} REAL  -- {mappings}")
    lines += [
        "",
        "Other tables: companies(ticker, name, sector), historical_prices(item_code, price_date, price_value)",
        "financial_reports also has: ticker, period (e.g. 2026Q2), ticker_period (primary key)",
    ]
    return "\n".join(lines)


def _exec(sql: str, params: tuple = ()) -> list[dict]:
    # Read-only protection: reject any non-SELECT statement
    stmt = sql.strip().upper()
    if not stmt.startswith(("SELECT", "WITH")):
        raise sqlite3.OperationalError(f"REJECTED: Only SELECT/WITH queries allowed. Got: {sql[:50]}")

    # Multiple statements or write keywords = reject
    if ";" in sql[:-1]:  # allow trailing semicolon
        raise sqlite3.OperationalError("REJECTED: Multiple statements not allowed")

    write_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE", "ATTACH"]
    if any(kw in stmt for kw in write_keywords):
        raise sqlite3.OperationalError(
            f"REJECTED: Write operations not allowed. Statement contains: {[k for k in write_keywords if k in stmt]}"
        )

    # Open as read-only URI with query_only pragma
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    deadline = time.monotonic() + 5.0
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)

    try:
        cursor = conn.execute(sql, params)
        cursor.arraysize = 1000  # max rows
        rows = cursor.fetchmany(1000)
        return [dict(r) for r in rows]
    finally:
        conn.close()


def run(natural_query: str, llm_caller) -> dict:
    """
    llm_caller: callable(system_prompt, user_prompt) -> str
    Returns {"sql": ..., "rows": [...], "ticker": ..., "__mode": "llm"|"template"}
    """
    ticker = _resolve_ticker(natural_query)

    # ── Try LLM first ──────────────────────────────────────────────────────────
    try:
        schema_ctx = _schema_context()
        system = (
            __import__("alphasonar.utils.prompts", fromlist=["load"])
            .load("skill1_sql_system.md")
            .format(schema_ctx=schema_ctx)
        )
        user = natural_query + (f"\n\n(Resolved ticker: {ticker})" if ticker else "")
        sql_raw = llm_caller(system, user).strip()
        sql = re.sub(r"^```[a-z]*\n?|```$", "", sql_raw, flags=re.MULTILINE).strip()

        rows = _exec(sql)
        if not rows:
            return {
                "sql": sql,
                "rows": [],
                "ticker": ticker,
                "__mode": "llm",
                "__status": "NO_LOCAL_DATA — 本地SQLite无此查询结果，严禁补充推断，请如实告知用户",
            }
        return {"sql": sql, "rows": rows, "ticker": ticker, "__mode": "llm"}

    except Exception as e:
        err_str = str(e)
        is_auth = "401" in err_str or "authentication" in err_str.lower() or "api_key" in err_str.lower()

        # ── LLM auth failed → template fallback ───────────────────────────────
        if is_auth or "invalid" in err_str.lower():
            result = _template_sql(natural_query, ticker)
            if result and ticker:
                sql, param = result
                try:
                    rows = _exec(sql, (param,))
                    return {
                        "sql": sql,
                        "rows": rows,
                        "ticker": ticker,
                        "__mode": "template",
                        "__warning": "LLM_AUTH_ERROR — 已降级为SQL模板，仅支持常用财务查询",
                    }
                except sqlite3.Error:
                    pass

            return {
                "sql": "",
                "rows": [],
                "ticker": ticker,
                "__mode": "template",
                "__status": "LLM_AUTH_ERROR — API Key 无效，且无匹配模板。请更新 ANTHROPIC_API_KEY 后重试。",
            }

        # ── other DB / parse error ─────────────────────────────────────────────
        return {"sql": "", "rows": [], "error": err_str, "ticker": ticker, "__mode": "error"}
