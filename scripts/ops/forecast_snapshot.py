#!/usr/bin/env python3
"""预测事件表 forecast_events —— 让四层方法的每次修正都能被实际业绩证伪。

一张 append-only 表同时存：consensus / guidance / forecast(=IRA) / actual。
- record: 记一条事件（历史永不覆盖；同 as_of_date 重复插入视为修订新增，不删旧）。
- score : 对每个 target_period，把最新 forecast 与实际(actual) 比误差，同时对照
          consensus，裁决"IRA修正 vs 一致预期"谁更准；as_of_date 晚于 actual 入库
          则标可能穿越(look-ahead)。

事件类型(event_type)：consensus=卖方一致预期 | guidance=公司指引 | forecast=IRA修正 | actual=财报实际。
口径由 accounting_basis(GAAP/Non-GAAP) 决定——对比只在同 metric+同 basis 内进行。
只依赖 stdlib。
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ira.settings import get_settings

DB_PATH = get_settings().sqlite_path
EVENT_TYPES = ("consensus", "guidance", "forecast", "actual")
METRICS = ("revenue", "gross_margin", "eps", "net_income")
RECORD_METRICS = (*METRICS, "guidance_revenue")
BASES = ("GAAP", "Non-GAAP", "Reported", "")
# 口径护栏：这些指标存在 GAAP/Non-GAAP 两套口径，写入时必须显式标 basis，否则无法比对。
# revenue 只有一套 Reported 口径；空值在写入时直接规范化为 Reported。
BASIS_REQUIRED_METRICS = ("net_income", "eps", "gross_margin")

DDL = """
CREATE TABLE IF NOT EXISTS forecast_events (
    event_id         INTEGER PRIMARY KEY,        -- rowid
    run_id           TEXT,                       -- 生成该预测的运行标识，可空
    ticker           TEXT NOT NULL,
    as_of_date       TEXT NOT NULL,              -- YYYY-MM-DD 预测做出/事件发生日（无穿越基准）
    target_period    TEXT NOT NULL,              -- YYYYQ1..Q4，对齐 financial_reports.period
    event_type       TEXT NOT NULL,              -- consensus|guidance|forecast|actual
    metric           TEXT NOT NULL,              -- revenue|gross_margin|eps|net_income
    accounting_basis TEXT DEFAULT '',            -- GAAP|Non-GAAP|Reported|'' （与 db_initializer 同步）
    value_low        REAL,
    value_mid        REAL,
    value_high       REAL,
    unit             TEXT DEFAULT '',
    source_type      TEXT DEFAULT '',            -- company_filing|broker_report|acecamp|ira...
    source_id        TEXT DEFAULT '',            -- source_file / chunk_id，可追溯
    model_version    TEXT DEFAULT '',
    information_cutoff TEXT DEFAULT '',           -- 所用信息最新日；多数=as_of_date，回填历史时才分叉
    note             TEXT DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_fe_lookup ON forecast_events(ticker, target_period, metric, event_type);
"""


def _conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    return conn


def record(a, db_path=DB_PATH):
    if a.metric == "revenue" and not a.basis:
        a.basis = "Reported"
    if a.metric == "guidance_revenue":
        a.basis = "Reported"
    # 口径硬护栏：利润类指标不带 basis 就拒写——GAAP/Non-GAAP 混比是最隐蔽的错。
    if a.metric in BASIS_REQUIRED_METRICS and a.basis not in ("GAAP", "Non-GAAP"):
        raise ValueError(
            f"BASIS_REQUIRED: metric={a.metric} 必须显式指定 --basis GAAP 或 Non-GAAP，"
            f"当前为 {a.basis!r}。（利润/EPS/毛利率禁止无口径写入，防混比）"
        )
    # 所有 actual 都必须能回溯到公司官方原文；Non-GAAP 更不能由券商值代替。
    if a.event_type == "actual" and not a.source_id:
        raise ValueError(
            "ACTUAL_NEEDS_SOURCE: 实际值必须带 --source-id（公司官方 Earnings Release/对账表）。"
        )
    conn = _conn(db_path)
    conn.execute(
        "INSERT INTO forecast_events "
        "(run_id,ticker,as_of_date,target_period,event_type,metric,accounting_basis,"
        " value_low,value_mid,value_high,unit,source_type,source_id,model_version,"
        " information_cutoff,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            a.run_id,
            a.ticker,
            a.as_of_date,
            a.target_period,
            a.event_type,
            a.metric,
            a.basis,
            a.low,
            a.mid,
            a.high,
            a.unit,
            a.source_type,
            a.source_id,
            a.model_version,
            a.information_cutoff or a.as_of_date,
            a.note,
        ),
    )
    conn.commit()
    conn.close()
    print(
        f"recorded {a.ticker} {a.target_period} {a.event_type}:{a.metric}"
        f"({a.basis or '-'}) mid={a.mid} @ {a.as_of_date}"
    )


def _err(pred, actual):
    if pred is None or actual in (None, 0):
        return None
    return abs(pred - actual) / abs(actual)


def _comparable_value(row):
    """Normalize currency amounts to millions; percentage/EPS values stay unchanged."""
    if row is None or row["value_mid"] is None:
        return None
    value = row["value_mid"]
    if row["metric"] in ("revenue", "guidance_revenue", "net_income"):
        return value / 1_000_000 if abs(value) > 1e8 else value
    return value


def _latest(conn, ticker, event_type):
    """每组 (target_period,metric,basis) 只取一条最新事件。

    同一天可能插入多个修订版本（append-only），仅按 MAX(as_of_date) 会返回多行、
    再由字典构造随机覆盖。用确定性三级排序取唯一：as_of_date > created_at > event_id，
    保证"同日最后写入的修订"稳定胜出，无随机性。"""
    tk = "AND ticker = :tk" if ticker else ""
    params = {"et": event_type, "tk": ticker}
    return conn.execute(
        f"""
        SELECT * FROM (
            SELECT fe.*, ROW_NUMBER() OVER (
                PARTITION BY ticker, target_period, metric, accounting_basis
                ORDER BY as_of_date DESC, created_at DESC, event_id DESC
            ) AS rn
            FROM forecast_events fe
            WHERE event_type=:et {tk}
        ) WHERE rn = 1
    """,
        params,
    ).fetchall()


def score(a, db_path=DB_PATH):
    conn = _conn(db_path)
    conn.row_factory = sqlite3.Row
    key = lambda r: (r["ticker"], r["target_period"], r["metric"], r["accounting_basis"])
    actuals = {key(r): r for r in _latest(conn, a.ticker, "actual") if r["metric"] in METRICS}
    fores = {key(r): r for r in _latest(conn, a.ticker, "forecast") if r["metric"] in METRICS}
    cons = {key(r): r for r in _latest(conn, a.ticker, "consensus") if r["metric"] in METRICS}
    conn.close()

    print(
        f"{'ticker':10} {'period':7} {'metric':12} {'basis':9} {'actual':>12} {'cons_err':>9} {'ira_err':>9}  裁决"
    )
    print("-" * 90)
    wins = draws = losses = 0
    for k, act in sorted(actuals.items()):
        av = _comparable_value(act)
        fe = fores.get(k)
        ce_row = cons.get(k)
        ie = _err(_comparable_value(fe), av)
        ce = _err(_comparable_value(ce_row), av)
        if ce is None or ie is None:
            verdict = "—(缺consensus或forecast)"
        elif ce < 1e-12 or abs(ie - ce) / max(ce, 1e-12) < a.tol:
            verdict = "持平"
            draws += 1
        elif ie < ce:
            verdict = "✅修正加分"
            wins += 1
        else:
            verdict = "❌修正减分"
            losses += 1
        # 穿越：forecast 的 as_of 晚于 actual 事件日
        if fe and act and fe["as_of_date"] > act["as_of_date"]:
            verdict += "  ⚠可能穿越"
        elif fe and act and fe["as_of_date"] == act["as_of_date"]:
            verdict += "  △同日需核对时点"
        cs = f"{ce:8.2%}" if ce is not None else "     n/a"
        is_ = f"{ie:8.2%}" if ie is not None else "     n/a"
        print(f"{k[0]:10} {k[1]:7} {k[2]:12} {(k[3] or '-'):9} {av:12.2f} {cs:>9} {is_:>9}  {verdict}")
    print("-" * 90)
    print(f"IRA修正 vs 一致预期： 加分 {wins} · 持平 {draws} · 减分 {losses}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="记一条预测事件")
    r.add_argument("--ticker", required=True)
    r.add_argument("--as-of-date", dest="as_of_date", required=True, help="事件/预测日 YYYY-MM-DD")
    r.add_argument("--target-period", dest="target_period", required=True, help="YYYYQ1..Q4")
    r.add_argument("--event-type", dest="event_type", required=True, choices=EVENT_TYPES)
    r.add_argument("--metric", required=True, choices=RECORD_METRICS)
    r.add_argument("--basis", default="", choices=BASES, help="GAAP/Non-GAAP/空")
    r.add_argument("--low", type=float)
    r.add_argument("--mid", type=float, help="点值/中值；打分用它")
    r.add_argument("--high", type=float)
    r.add_argument("--unit", default="")
    r.add_argument("--source-type", dest="source_type", default="")
    r.add_argument("--source-id", dest="source_id", default="")
    r.add_argument("--run-id", dest="run_id", default="")
    r.add_argument("--model-version", dest="model_version", default="")
    r.add_argument(
        "--information-cutoff", dest="information_cutoff", default="", help="所用信息最新日；缺省=as_of_date"
    )
    r.add_argument("--note", default="")
    r.set_defaults(func=record)

    s = sub.add_parser("score", help="对比 forecast/consensus vs actual，裁决修正是否加分")
    s.add_argument("--ticker", help="只看某只；省略则全部")
    s.add_argument("--tol", type=float, default=0.02, help="误差差异在此比例内算持平（默认0.02）")
    s.set_defaults(func=score)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
