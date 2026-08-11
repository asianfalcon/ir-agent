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
- 写入前清理历史违规数据
"""
import csv
import sqlite3
from pathlib import Path

from ira.settings import get_settings

_SETTINGS = get_settings()
DB_PATH = _SETTINGS.sqlite_path


def normalize_ticker(ticker: str) -> str:
    """统一ticker格式: AMD -> AMD.US"""
    if "." not in ticker:
        return f"{ticker}.US"
    return ticker


def csv_to_financial_reports(csv_path: Path, source_date: str):
    """导入 financial_reports 主表 (只含GAAP,主表是官方原值)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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
            value = float(row["value"]) if row["value"] else None

            # 单位标准化: USD_millions -> 美元
            if row["unit"] == "USD_millions":
                value = value * 1_000_000 if value else None

            groups[key][metric] = value

    # 写入 financial_reports
    for (ticker, period), metrics in groups.items():
        ticker_period = f"{ticker}_{period}"

        # 检查是否存在
        existing = cursor.execute(
            "SELECT 1 FROM financial_reports WHERE ticker_period = ?",
            (ticker_period,)
        ).fetchone()

        if existing:
            # 更新
            update_fields = []
            values = []
            for metric, value in metrics.items():
                update_fields.append(f"{metric} = ?")
                values.append(value)

            if update_fields:
                values.append(ticker_period)
                sql = f"UPDATE financial_reports SET {', '.join(update_fields)} WHERE ticker_period = ?"
                cursor.execute(sql, values)
                print(f"✓ 更新 financial_reports: {ticker} {period}")
        else:
            # 插入 (schema只有 revenue, gross_margin, net_profit, roe, operating_cash_flow)
            cursor.execute("""
                INSERT INTO financial_reports (ticker, period, ticker_period, revenue, net_profit,
                                               gross_margin, operating_cash_flow)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, period, ticker_period,
                metrics.get("revenue"),
                metrics.get("net_income"),
                metrics.get("gross_margin"),
                metrics.get("operating_cash_flow")
            ))
            print(f"✓ 插入 financial_reports: {ticker} {period}")

    conn.commit()
    conn.close()


def csv_to_forecast_events(csv_path: Path, source_date: str, source_id: str):
    """导入 forecast_events actual 事件, 统一口径"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 清理历史违规数据: revenue actual 使用了 Non-GAAP
    cursor.execute("""
        DELETE FROM forecast_events
        WHERE event_type = 'actual'
          AND metric = 'revenue'
          AND accounting_basis = 'Non-GAAP'
    """)
    deleted = cursor.rowcount
    if deleted > 0:
        print(f"✓ 清理历史违规数据: {deleted} 条 revenue actual 错误使用 Non-GAAP")

    # 2. 清理缺失 source_id 的 actual
    cursor.execute("""
        DELETE FROM forecast_events
        WHERE event_type = 'actual'
          AND (source_id IS NULL OR source_id = '')
    """)
    deleted = cursor.rowcount
    if deleted > 0:
        print(f"✓ 清理历史违规数据: {deleted} 条 actual 缺失 source_id")

    # 读取CSV
    rows = list(csv.DictReader(csv_path.read_text().splitlines()))

    for row in rows:
        ticker = normalize_ticker(row["ticker"])
        period = row["period"]
        if "_guidance" in period:  # 跳过指引行
            continue

        metric = row["metric"]
        accounting_basis = row["accounting_basis"]
        value = float(row["value"]) if row["value"] else None
        unit = row["unit"]

        # 口径护栏: revenue 必须使用 Reported (即GAAP收入)
        if metric == "revenue":
            if accounting_basis != "GAAP":
                continue  # 跳过 Non-GAAP revenue
            accounting_basis = "Reported"  # 标准化为 Reported

        # 单位标准化
        if unit == "USD_millions":
            value = value  # 保持百万美元
            unit = "M_USD"
        elif unit == "USD_per_share":
            unit = "USD"
        elif unit == "million_shares":
            unit = "M"

        # 检查是否已存在
        existing = cursor.execute("""
            SELECT 1 FROM forecast_events
            WHERE ticker = ? AND target_period = ? AND event_type = 'actual'
              AND metric = ? AND accounting_basis = ?
        """, (ticker, period, metric, accounting_basis)).fetchone()

        if existing:
            # 更新
            cursor.execute("""
                UPDATE forecast_events
                SET value_mid = ?, unit = ?, as_of_date = ?, source_id = ?
                WHERE ticker = ? AND target_period = ? AND event_type = 'actual'
                  AND metric = ? AND accounting_basis = ?
            """, (value, unit, source_date, source_id,
                  ticker, period, metric, accounting_basis))
            print(f"✓ 更新 forecast_events actual: {ticker} {period} {metric} {accounting_basis}")
        else:
            # 插入
            cursor.execute("""
                INSERT INTO forecast_events
                (ticker, as_of_date, target_period, event_type, metric, accounting_basis,
                 value_mid, unit, source_type, source_id)
                VALUES (?, ?, ?, 'actual', ?, ?, ?, ?, 'earnings_release', ?)
            """, (ticker, source_date, period, metric, accounting_basis, value, unit, source_id))
            print(f"✓ 插入 forecast_events actual: {ticker} {period} {metric} {accounting_basis}")

    conn.commit()
    conn.close()


def clean_forecast_events_basis():
    """清理 forecast_events 中 revenue 预测的空口径, 统一为 Reported"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE forecast_events
        SET accounting_basis = 'Reported'
        WHERE metric = 'revenue'
          AND event_type IN ('consensus', 'guidance', 'forecast')
          AND (accounting_basis IS NULL OR accounting_basis = '')
    """)
    updated = cursor.rowcount
    if updated > 0:
        print(f"✓ 统一 revenue 预测口径: {updated} 条空口径 -> Reported")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python import_actuals.py <csv_path> [source_date] [source_id]")
        print("Example: python import_actuals.py data/processed/financials/AMD_2026Q2_actuals.csv 2026-07-30 Q2_2026_earnings_release")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    source_date = sys.argv[2] if len(sys.argv) > 2 else "2026-07-30"
    source_id = sys.argv[3] if len(sys.argv) > 3 else csv_path.stem

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

    # 2. 清理并导入 forecast_events actual
    print("2. 清理并导入 forecast_events actual...")
    csv_to_forecast_events(csv_path, source_date, source_id)
    print()

    # 3. 统一 revenue 预测口径
    print("3. 统一 revenue 预测口径...")
    clean_forecast_events_basis()
    print()

    print("✓ 导入完成")
