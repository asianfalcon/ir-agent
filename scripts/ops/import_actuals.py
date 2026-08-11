#!/usr/bin/env python3
"""
Import actual financial results from CSV into:
1. financial_reports (主表)
2. forecast_events (actual 事件, 统一口径)

护栏:
- ticker 统一加 .US 后缀
- revenue 必须使用 Reported 口径 (GAAP收入)
- 利润类指标保留 GAAP/Non-GAAP 双轨
- 所有 actual 必须有 source_id
- 精确重跑幂等；修订只追加，不覆盖历史
"""

import csv
import sqlite3
from datetime import date
from pathlib import Path

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
DB_PATH = _SETTINGS.sqlite_path

FINANCIAL_COLUMN_MAP = {
    "revenue": "revenue",
    "net_income": "net_profit",
    "gross_margin": "gross_margin",
    "operating_cash_flow": "operating_cash_flow",
}
METRIC_ALIASES = {"diluted_eps": "eps"}


def normalize_ticker(ticker: str) -> str:
    """统一ticker格式: AMD -> AMD.US"""
    if "." not in ticker:
        return f"{ticker}.US"
    return ticker


def csv_to_financial_reports(csv_path: Path, source_date: str):
    """导入 financial_reports 主表 (只含GAAP,主表是官方原值)"""
    date.fromisoformat(source_date)

    # 读取CSV
    rows = list(csv.DictReader(csv_path.read_text().splitlines()))

    # 按 ticker+period 分组
    groups = {}
    for row in rows:
        ticker = normalize_ticker(row["ticker"])
        period = row["period"]
        if "_guidance" in period:  # 跳过指引行
            continue

        key = (ticker, period)
        if key not in groups:
            groups[key] = {}

        # 只保留 GAAP (主表是官方原值)
        if row["accounting_basis"] == "GAAP":
            metric = row["metric"]
            column = FINANCIAL_COLUMN_MAP.get(metric)
            if column is None:
                continue
            value = float(row["value"]) if row["value"] else None

            # 单位标准化: USD_millions -> 美元
            if row["unit"] == "USD_millions":
                value = value * 1_000_000 if value is not None else None

            groups[key][column] = value

    # 写入 financial_reports
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for (ticker, period), metrics in groups.items():
            ticker_period = f"{ticker}_{period}"

            # 检查是否存在
            existing = cursor.execute(
                "SELECT 1 FROM financial_reports WHERE ticker_period = ?", (ticker_period,)
            ).fetchone()

            if existing:
                update_fields = []
                values = []
                for column, value in metrics.items():
                    update_fields.append(f"{column} = ?")
                    values.append(value)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    values.append(ticker_period)
                    sql = f"UPDATE financial_reports SET {', '.join(update_fields)} WHERE ticker_period = ?"
                    cursor.execute(sql, values)
                    print(f"✓ 更新 financial_reports: {ticker} {period}")
            else:
                cursor.execute(
                    """
                    INSERT INTO financial_reports (ticker, period, ticker_period, revenue, net_profit,
                                                   gross_margin, operating_cash_flow)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        ticker,
                        period,
                        ticker_period,
                        metrics.get("revenue"),
                        metrics.get("net_profit"),
                        metrics.get("gross_margin"),
                        metrics.get("operating_cash_flow"),
                    ),
                )
                print(f"✓ 插入 financial_reports: {ticker} {period}")


def _normalize_unit(unit: str) -> str:
    return {
        "USD_millions": "M_USD",
        "USD_per_share": "USD",
        "million_shares": "M",
    }.get(unit, unit)


def _insert_event(
    cursor,
    *,
    ticker: str,
    source_date: str,
    period: str,
    event_type: str,
    metric: str,
    basis: str,
    unit: str,
    source_id: str,
    low=None,
    mid=None,
    high=None,
) -> bool:
    """Append one revision, but make an exact rerun idempotent."""
    values = (ticker, source_date, period, event_type, metric, basis, low, mid, high, unit, source_id)
    exists = cursor.execute(
        """
        SELECT 1 FROM forecast_events
        WHERE ticker=? AND as_of_date=? AND target_period=? AND event_type=?
          AND metric=? AND accounting_basis=?
          AND value_low IS ? AND value_mid IS ? AND value_high IS ?
          AND unit=? AND source_id=?
        LIMIT 1
    """,
        values,
    ).fetchone()
    if exists:
        return False
    cursor.execute(
        """
        INSERT INTO forecast_events
        (ticker, as_of_date, target_period, event_type, metric, accounting_basis,
         value_low, value_mid, value_high, unit, source_type, source_id,
         information_cutoff)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'earnings_release', ?, ?)
    """,
        (*values, source_date),
    )
    return True


def csv_to_forecast_events(csv_path: Path, source_date: str, source_id: str):
    """Append actual and guidance events; never clean or overwrite history."""
    if not source_id:
        raise ValueError("source_id is required for earnings-release imports")
    date.fromisoformat(source_date)
    rows = list(csv.DictReader(csv_path.read_text().splitlines()))

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        guidance_revenue = {}
        inserted = skipped = 0

        for row in rows:
            ticker = normalize_ticker(row["ticker"])
            raw_period = row["period"]
            is_guidance = raw_period.endswith("_guidance")
            period = raw_period.removesuffix("_guidance")
            event_type = "guidance" if is_guidance else "actual"
            metric = METRIC_ALIASES.get(row["metric"], row["metric"])
            basis = row["accounting_basis"].removesuffix("_guidance")
            value = float(row["value"]) if row["value"] else None
            unit = _normalize_unit(row["unit"])

            if is_guidance and metric in {"revenue_low", "revenue_midpoint", "revenue_high"}:
                key = (ticker, period, unit)
                guidance_revenue.setdefault(key, {})[metric] = value
                continue

            if metric == "revenue":
                if not is_guidance and basis != "GAAP":
                    continue
                basis = "Reported"
            elif basis == "Guidance":
                basis = ""

            changed = _insert_event(
                cursor,
                ticker=ticker,
                source_date=source_date,
                period=period,
                event_type=event_type,
                metric=metric,
                basis=basis,
                unit=unit,
                source_id=source_id,
                mid=value,
            )
            inserted += int(changed)
            skipped += int(not changed)

        for (ticker, period, unit), values in guidance_revenue.items():
            changed = _insert_event(
                cursor,
                ticker=ticker,
                source_date=source_date,
                period=period,
                event_type="guidance",
                metric="revenue",
                basis="Reported",
                unit=unit,
                source_id=source_id,
                low=values.get("revenue_low"),
                mid=values.get("revenue_midpoint"),
                high=values.get("revenue_high"),
            )
            inserted += int(changed)
            skipped += int(not changed)

    print(f"✓ forecast_events: 新增 {inserted} 条，精确重复跳过 {skipped} 条")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python import_actuals.py <csv_path> <source_date> <source_id>")
        print(
            "Example: python import_actuals.py data/processed/financials/AMD_2026Q2_actuals.csv 2026-08-04 AMD_Q2_2026_earnings_release"
        )
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if len(sys.argv) < 4:
        print("❌ source_date 和 source_id 必须显式提供，禁止用默认日期回填实际值")
        sys.exit(1)
    source_date = sys.argv[2]
    source_id = sys.argv[3]

    if not csv_path.exists():
        print(f"❌ CSV文件不存在: {csv_path}")
        sys.exit(1)

    print(f"=== 导入 {csv_path.name} ===")
    print(f"source_date: {source_date}")
    print(f"source_id: {source_id}")
    print()

    # 1. 导入 financial_reports
    print("1. 导入 financial_reports (GAAP only)...")
    csv_to_financial_reports(csv_path, source_date)
    print()

    # 2. 追加 actual + guidance 事件；精确重跑自动跳过
    print("2. 导入 forecast_events actual + guidance...")
    csv_to_forecast_events(csv_path, source_date, source_id)
    print()

    print("✓ 导入完成")
