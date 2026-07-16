"""
SQLite schema initializer — run once at project startup.
Creates all tables and system tables required by IRA.
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "databases" / "ira.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema() -> None:
    with get_conn() as conn:
        conn.executescript("""
            -- ── Business tables ──────────────────────────────────────────

            CREATE TABLE IF NOT EXISTS companies (
                ticker     TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                sector     TEXT
            );

            CREATE TABLE IF NOT EXISTS financial_reports (
                ticker_period  TEXT PRIMARY KEY,  -- e.g. "002136.SZ_2026Q2"
                ticker         TEXT NOT NULL,
                period         TEXT NOT NULL,     -- YYYYQ1 / YYYYQ2 / YYYYQ3 / YYYYQ4
                revenue        REAL,
                gross_margin   REAL,
                net_profit     REAL,
                roe            REAL,
                operating_cash_flow REAL,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ticker) REFERENCES companies(ticker)
            );

            CREATE TABLE IF NOT EXISTS historical_prices (
                item_code   TEXT NOT NULL,   -- ticker or commodity name
                price_date  TEXT NOT NULL,   -- YYYY-MM-DD
                price_value REAL NOT NULL,
                PRIMARY KEY (item_code, price_date)
            );

            -- 预测事件表（反馈回路）：append-only，同存 consensus/guidance/forecast/actual
            -- 四类事件，让四层方法每次修正都能被实际业绩证伪。详见 scripts/forecast_snapshot.py。
            -- accounting_basis 隔离 GAAP/Non-GAAP，绝不混比；历史永不覆盖，同 as_of_date 重复=修订新增。
            CREATE TABLE IF NOT EXISTS forecast_events (
                event_id         INTEGER PRIMARY KEY,
                run_id           TEXT,
                ticker           TEXT NOT NULL,
                as_of_date       TEXT NOT NULL,   -- YYYY-MM-DD 事件/预测做出日（无穿越基准）
                target_period    TEXT NOT NULL,   -- YYYYQ1..Q4，对齐 financial_reports.period
                event_type       TEXT NOT NULL,   -- consensus|guidance|forecast|actual
                metric           TEXT NOT NULL,   -- revenue|gross_margin|eps|net_income
                accounting_basis TEXT DEFAULT '', -- GAAP|Non-GAAP|Reported|''
                value_low        REAL,
                value_mid        REAL,
                value_high       REAL,
                unit             TEXT DEFAULT '',
                source_type      TEXT DEFAULT '',
                source_id        TEXT DEFAULT '',
                model_version    TEXT DEFAULT '',
                information_cutoff TEXT DEFAULT '',
                note             TEXT DEFAULT '',
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_fe_lookup
                ON forecast_events(ticker, target_period, metric, event_type);

            -- ── System / lineage tables ───────────────────────────────────

            CREATE TABLE IF NOT EXISTS sys_data_lineage (
                source_id    TEXT PRIMARY KEY,  -- MD5(file_path)
                file_path    TEXT NOT NULL,
                origin_url   TEXT,
                access_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sys_file_log (
                file_path    TEXT PRIMARY KEY,
                mtime        REAL NOT NULL,     -- os.path.getmtime value
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS spider_crawl_log (
                crawl_id     TEXT PRIMARY KEY,  -- MD5(url + date)
                url          TEXT NOT NULL,
                crawl_date   TEXT NOT NULL       -- YYYY-MM-DD
            );
        """)
    print(f"Schema initialised at {DB_PATH}")


def source_id(file_path: str) -> str:
    return hashlib.md5(file_path.encode()).hexdigest()


if __name__ == "__main__":
    init_schema()
