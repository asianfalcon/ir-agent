"""
Skill 1: Text2SQL — translates natural language to SQL, executes against SQLite,
returns raw rows. LLM is constrained to the registered variable schema columns only.
"""

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DB_PATH = ROOT / "databases" / "ira.db"
VOCAB_PATH = ROOT / "config" / "vocab_dictionary.json"
VAR_SCHEMA_PATH = ROOT / "config" / "variable_schema.json"


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


def run(natural_query: str, llm_caller) -> dict:
    """
    llm_caller: callable(system_prompt, user_prompt) -> str
    Returns {"sql": ..., "rows": [...], "ticker": ...}
    """
    ticker = _resolve_ticker(natural_query)
    schema_ctx = _schema_context()

    system = (
        "You are a SQL generator for a financial database. "
        "Output ONLY a single valid SQLite SELECT statement — no explanation, no markdown fences.\n\n"
        f"{schema_ctx}\n\n"
        "Rules:\n"
        "- Only use column names listed above.\n"
        "- Never modify or fabricate numbers.\n"
        "- If ticker is provided, filter by it.\n"
    )
    user = natural_query
    if ticker:
        user += f"\n\n(Resolved ticker: {ticker})"

    sql_raw = llm_caller(system, user).strip()
    # Strip accidental markdown fences
    sql = re.sub(r"^```[a-z]*\n?|```$", "", sql_raw, flags=re.MULTILINE).strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    except sqlite3.Error as e:
        return {"sql": sql, "rows": [], "error": str(e), "ticker": ticker}
    finally:
        conn.close()

    return {"sql": sql, "rows": rows, "ticker": ticker}
