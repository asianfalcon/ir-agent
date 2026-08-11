#!/usr/bin/env python3
"""我的预测 vs 实际的系统性偏差 —— 把"修正"从自觉变成可计算。

用法: python3 scripts/ops/forecast_bias.py [--ticker AMD.US]

输出我历史上每个 (标的,期) 的最终预测 vs 实际的带符号误差,以及中位数偏差。
report_skeleton 的强制步骤引用这个中位数作为 AI 算力链的周期修正先验。

ponytail: 直连 sqlite,无 ORM。样本少(<10),用中位数抗离群、不做花哨统计。
"""

import argparse
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ira.settings import get_settings

DB = get_settings().sqlite_path


def to_yi(v):
    """归一到"亿美元"。DB 混了美元原值和百万口径,按量级判。"""
    if v is None:
        return None
    # >1e8 视为美元原值(如 11536000000) -> /1e8
    # 否则视为百万美元口径(如 11536) -> /100
    return v / 1e8 if v > 1e8 else v / 100.0


def final_forecast(rows):
    """一个 (ticker,period,metric,basis) 可能有多版预测,取 as_of_date 最新的一条=最终定稿。
    同日多条时,取 event_id 最大(最后写入)的一条。"""
    return max(rows, key=lambda r: (r["as_of_date"] or "", r["event_id"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    # 默认同时衡量财报收入预测和下一季收入指引预测。
    ap.add_argument("--metric", default="revenue,guidance_revenue")
    args = ap.parse_args()
    metrics = [m.strip() for m in args.metric.split(",")]

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    ph = ",".join("?" * len(metrics))
    q = f"""SELECT event_id,ticker,target_period,metric,accounting_basis,event_type,value_mid,as_of_date,model_version
            FROM forecast_events WHERE metric IN ({ph}) AND value_mid IS NOT NULL"""
    params = list(metrics)
    if args.ticker:
        q += " AND ticker=?"
        params.append(args.ticker)
    all_rows = con.execute(q, params).fetchall()

    # 普通收入 forecast 对 actual revenue；guidance_revenue forecast 对公司 guidance revenue。
    from collections import defaultdict

    fc = defaultdict(list)
    actual_rows = defaultdict(list)
    for r in all_rows:
        metric = r["metric"]
        basis = r["accounting_basis"]
        if r["event_type"] == "forecast" and metric == "guidance_revenue":
            key = (r["ticker"], r["target_period"], "guidance_revenue", "Reported")
            fc[key].append(r)
        elif r["event_type"] == "forecast":
            key = (r["ticker"], r["target_period"], metric, basis)
            fc[key].append(r)
        elif r["event_type"] == "actual":
            key = (r["ticker"], r["target_period"], metric, basis)
            actual_rows[key].append(r)
        elif r["event_type"] == "guidance" and metric == "revenue":
            key = (r["ticker"], r["target_period"], "guidance_revenue", "Reported")
            actual_rows[key].append(r)
    act = {key: to_yi(final_forecast(rows)["value_mid"]) for key, rows in actual_rows.items()}

    errs = []
    print(f"{'标的期':<20} {'口径':<10} {'我(定稿)':>9} {'基准':>8} {'误差%':>8} {'符号':>4}  版本")
    for key in sorted(fc):
        if key not in act or act[key] is None:
            continue
        f = final_forecast(fc[key])
        mine = to_yi(f["value_mid"])
        a = act[key]
        if not a:
            continue
        e = (mine - a) / a * 100
        errs.append(e)
        tag = "guid" if key[2] == "guidance_revenue" else "rev"
        label = f"{key[0]} {key[1]} {tag}"
        basis = key[3] or "-"
        print(
            f"{label:<24} {basis:<10} {mine:>9.1f} {a:>8.1f} {e:>7.1f}% "
            f"{'低' if e < 0 else '高':>4}  {f['model_version'] or '-'}"
        )

    if not errs:
        print("\n无可对照样本(缺 actual/guidance 或单位异常)。")
        return
    print(
        f"\n样本 n={len(errs)}  中位偏差 {statistics.median(errs):+.1f}%  "
        f"均值 {statistics.mean(errs):+.1f}%  区间 [{min(errs):+.1f}%, {max(errs):+.1f}%]"
    )
    med = statistics.median(errs)
    if len(errs) >= 2 and all(e < 0 for e in errs):
        print(f"⚠️ 全部同号(低估)。周期修正先验 = +{abs(med):.1f}%(加在自下而上/因子结论上,要压回需列证据)。")
    else:
        print("偏差非单向,暂不施加固定修正——按个案判断。")


def _selfcheck():
    # 单位归一是唯一有坑的逻辑:美元原值 vs 百万口径
    assert abs(to_yi(11536000000.0) - 115.36) < 1e-6, "美元原值→亿"
    assert abs(to_yi(11536.0) - 115.36) < 1e-6, "百万→亿"
    assert to_yi(None) is None
    # 最新定稿选取 (同日按 event_id 排序)
    rows = [
        {"as_of_date": "2026-08-02", "event_id": 1},
        {"as_of_date": "2026-08-04", "event_id": 2},
        {"as_of_date": "2026-08-04", "event_id": 3},
    ]
    final = final_forecast(rows)
    assert final["as_of_date"] == "2026-08-04" and final["event_id"] == 3, "同日取最大event_id"
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
