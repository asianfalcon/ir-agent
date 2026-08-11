"""
Skill 2: Deterministic financial calculator — YoY, QoQ, peer comparison.
All arithmetic done in Python; LLM never touches these numbers.
"""

import sqlite3
from typing import Any

from alphasonar.settings import get_settings

DB_PATH = get_settings().sqlite_path

NUMERIC_COLS = ["gross_margin", "net_profit", "roe", "revenue", "operating_cash_flow"]


def _fetch_periods(ticker: str, periods: list[str]) -> dict[str, dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(periods))
    rows = conn.execute(
        f"SELECT * FROM financial_reports WHERE ticker=? AND period IN ({placeholders})",
        [ticker, *periods],
    ).fetchall()
    conn.close()
    return {r["period"]: dict(r) for r in rows}


def _pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100, 2)


def _prev_period(period: str, delta: int) -> str:
    """Return period shifted by delta quarters (negative = earlier)."""
    year = int(period[:4])
    q = int(period[5])
    q += delta
    while q <= 0:
        q += 4
        year -= 1
    while q > 4:
        q -= 4
        year += 1
    return f"{year}Q{q}"


def compute(ticker: str, period: str) -> dict[str, Any]:
    """
    Return a dashboard dict for the given ticker/period including:
    - raw values
    - YoY change vs same quarter last year
    - QoQ change vs previous quarter
    """
    yoy_period = _prev_period(period, -4)
    qoq_period = _prev_period(period, -1)

    data = _fetch_periods(ticker, [period, yoy_period, qoq_period])
    current = data.get(period, {})
    yoy = data.get(yoy_period, {})
    qoq = data.get(qoq_period, {})

    result: dict[str, Any] = {"ticker": ticker, "period": period, "metrics": {}}
    for col in NUMERIC_COLS:
        result["metrics"][col] = {
            "value": current.get(col),
            "yoy_pct": _pct_change(current.get(col), yoy.get(col)),
            "qoq_pct": _pct_change(current.get(col), qoq.get(col)),
        }
    return result


def margin_elasticity(ticker: str, period: str, upstream_price_change: float) -> float | None:
    """
    gross_margin elasticity = Δgross_margin / Δupstream_price
    upstream_price_change: percentage point change in upstream price
    """
    qoq = _prev_period(period, -1)
    data = _fetch_periods(ticker, [period, qoq])
    cur_gm = data.get(period, {}).get("gross_margin")
    prev_gm = data.get(qoq, {}).get("gross_margin")
    if cur_gm is None or prev_gm is None or upstream_price_change == 0:
        return None
    delta_gm = cur_gm - prev_gm
    return round(delta_gm / upstream_price_change, 4)
