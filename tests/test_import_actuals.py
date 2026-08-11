import csv
import sqlite3
from pathlib import Path

from scripts.ops import import_actuals as ia

DDL = """
CREATE TABLE financial_reports(
  ticker TEXT, period TEXT, ticker_period TEXT PRIMARY KEY, revenue REAL,
  gross_margin REAL, net_profit REAL, roe REAL, operating_cash_flow REAL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE forecast_events(
  event_id INTEGER PRIMARY KEY, run_id TEXT, ticker TEXT NOT NULL,
  as_of_date TEXT NOT NULL, target_period TEXT NOT NULL, event_type TEXT NOT NULL,
  metric TEXT NOT NULL, accounting_basis TEXT DEFAULT '', value_low REAL,
  value_mid REAL, value_high REAL, unit TEXT DEFAULT '', source_type TEXT DEFAULT '',
  source_id TEXT DEFAULT '', model_version TEXT DEFAULT '', information_cutoff TEXT DEFAULT '',
  note TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _write_csv(path: Path):
    rows = [
        {
            "ticker": "AMD",
            "period": "2026Q2",
            "metric": "revenue",
            "accounting_basis": "GAAP",
            "value": "100",
            "unit": "USD_millions",
        },
        {
            "ticker": "AMD",
            "period": "2026Q2",
            "metric": "gross_profit",
            "accounting_basis": "GAAP",
            "value": "50",
            "unit": "USD_millions",
        },
        {
            "ticker": "AMD",
            "period": "2026Q2",
            "metric": "diluted_eps",
            "accounting_basis": "Non-GAAP",
            "value": "1.2",
            "unit": "USD_per_share",
        },
        {
            "ticker": "AMD",
            "period": "2026Q3_guidance",
            "metric": "revenue_low",
            "accounting_basis": "Guidance",
            "value": "110",
            "unit": "USD_millions",
        },
        {
            "ticker": "AMD",
            "period": "2026Q3_guidance",
            "metric": "revenue_midpoint",
            "accounting_basis": "Guidance",
            "value": "115",
            "unit": "USD_millions",
        },
        {
            "ticker": "AMD",
            "period": "2026Q3_guidance",
            "metric": "revenue_high",
            "accounting_basis": "Guidance",
            "value": "120",
            "unit": "USD_millions",
        },
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_import_is_idempotent_scoped_and_canonical(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    csv_path = tmp_path / "actuals.csv"
    _write_csv(csv_path)
    conn = sqlite3.connect(db)
    conn.executescript(DDL)
    conn.execute(
        "INSERT INTO financial_reports(ticker,period,ticker_period,revenue) VALUES('AMD.US','2026Q2','AMD.US_2026Q2',1)"
    )
    conn.execute(
        "INSERT INTO forecast_events(ticker,as_of_date,target_period,event_type,metric,accounting_basis,value_mid,source_id) VALUES('OTHER.US','2026-01-01','2025Q4','actual','revenue','Reported',1,'')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(ia, "DB_PATH", db)

    ia.csv_to_financial_reports(csv_path, "2026-08-04")
    ia.csv_to_financial_reports(csv_path, "2026-08-04")
    ia.csv_to_forecast_events(csv_path, "2026-08-04", "release")
    ia.csv_to_forecast_events(csv_path, "2026-08-04", "release")

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT revenue FROM financial_reports").fetchone()[0] == 100_000_000
    assert conn.execute("SELECT COUNT(*) FROM forecast_events WHERE ticker='OTHER.US'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM forecast_events WHERE ticker='AMD.US'").fetchone()[0] == 4
    eps = conn.execute("SELECT metric FROM forecast_events WHERE accounting_basis='Non-GAAP'").fetchone()[0]
    assert eps == "eps"
    guidance = conn.execute(
        "SELECT value_low,value_mid,value_high,accounting_basis FROM forecast_events WHERE event_type='guidance'"
    ).fetchone()
    assert guidance == (110.0, 115.0, 120.0, "Reported")
    conn.close()


def test_import_appends_changed_revision(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    csv_path = tmp_path / "actuals.csv"
    _write_csv(csv_path)
    conn = sqlite3.connect(db)
    conn.executescript(DDL)
    conn.close()
    monkeypatch.setattr(ia, "DB_PATH", db)

    ia.csv_to_forecast_events(csv_path, "2026-08-04", "release")
    ia.csv_to_forecast_events(csv_path, "2026-08-05", "corrected-release")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM forecast_events WHERE ticker='AMD.US'").fetchone()[0] == 8
    conn.close()
