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

            -- 修正因子表：把"纪要挖掘→一致预期修正"从艺术变科学，让修正质量可回测。
            -- 核心：判断纪要是否产生 alpha 必须比较"纪要发布前一刻的一致预期快照"；判断
            -- 今天还能否修正要比较"今天的一致预期"。这两个问题不能混（时间穿越陷阱）。
            CREATE TABLE IF NOT EXISTS revision_factors (
                factor_id          INTEGER PRIMARY KEY,
                ticker             TEXT NOT NULL,
                event_date         TEXT NOT NULL,   -- YYYY-MM-DD 纪要/信息披露日
                source_id          TEXT,            -- chunk_id / source_file，可追溯原文
                information_cutoff TEXT,            -- 该信息基于哪天的知识
                factor_text        TEXT NOT NULL,   -- 一句话描述该因子（"18A良率85%"）
                evidence_type      TEXT,            -- quantified|timeline|sentiment|valuation
                affected_metric    TEXT,            -- revenue|gross_margin|eps|net_income|...
                affected_period    TEXT,            -- YYYYQ1 或 YYYY 或 range(2027-2028)
                baseline_snapshot_id TEXT,          -- 修正的是哪天的一致预期快照
                narrative_absorbed BOOLEAN DEFAULT 0, -- 研报文字提到该因素
                estimate_absorbed  BOOLEAN DEFAULT 0, -- 相关预测数值已随之修订
                price_absorbed     BOOLEAN DEFAULT 0, -- 股价/估值已反映
                overlap_evidence   TEXT,            -- 同一信息的其他来源（防重复计算）
                direction          TEXT,            -- bull|bear|neutral
                point_delta        REAL,            -- 对点预测的修正（收入亿美元、EPS美元）
                range_delta_low    REAL,
                range_delta_high   REAL,
                probability_delta  REAL,            -- 对 Bull/Bear 概率的调整（-0.1~+0.1）
                calculation_basis  TEXT,            -- 推导逻辑（"良率85%×产能×ASP"）
                invalidation_condition TEXT,        -- 何时失效（"10月0.9 PDK未交付"）
                verification_date  TEXT,            -- 验证日期（里程碑/财报日）
                verification_result TEXT,           -- confirmed|failed|pending
                realized_contribution REAL,         -- 财报后该因子实际贡献的准确率
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_rf_ticker ON revision_factors(ticker, event_date);

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
