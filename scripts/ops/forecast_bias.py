#!/usr/bin/env python3
"""我的预测 vs 实际的系统性偏差 —— 把"修正"从自觉变成可计算。

用法: python3 scripts/ops/forecast_bias.py [--ticker AMD.US]

输出我历史上每个 (标的,期) 的最终预测 vs 实际的带符号误差,以及中位数偏差。
report_skeleton 的强制步骤引用这个中位数作为 AI 算力链的周期修正先验。

ponytail: 直连 sqlite,无 ORM。样本少(<10),用中位数抗离群、不做花哨统计。
"""
import argparse, sqlite3, statistics, sys
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
    """一个 (ticker,period) 可能有多版预测,取 as_of_date 最新的一条=最终定稿。"""
    return max(rows, key=lambda r: (r["as_of_date"] or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    # 默认池化"收入类"维度:实际收入 + 指引收入。都是同一种"营收判断",一起衡量我的符号偏差。
    ap.add_argument("--metric", default="revenue,guidance_revenue")
    args = ap.parse_args()
    metrics = [m.strip() for m in args.metric.split(",")]

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    ph = ",".join("?" * len(metrics))
    q = f"""SELECT ticker,target_period,metric,event_type,value_mid,as_of_date,model_version
            FROM forecast_events WHERE metric IN ({ph}) AND value_mid IS NOT NULL"""
    params = list(metrics)
    if args.ticker:
        q += " AND ticker=?"
        params.append(args.ticker)
    all_rows = con.execute(q, params).fetchall()

    # 按 (ticker,period) 分组,分出 forecast / actual
    from collections import defaultdict
    fc = defaultdict(list)
    act = {}
    for r in all_rows:
        key = (r["ticker"], r["target_period"], r["metric"])
        if r["event_type"] == "forecast":
            fc[key].append(r)
        elif r["event_type"] == "actual":
            act[key] = to_yi(r["value_mid"])

    errs = []
    print(f"{'标的期':<20} {'我(定稿)':>9} {'实际':>8} {'误差%':>8} {'符号':>4}  版本")
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
        tag = 'guid' if key[2] == 'guidance_revenue' else 'rev'
        label = f"{key[0]} {key[1]} {tag}"
        print(f"{label:<24} {mine:>9.1f} {a:>8.1f} {e:>7.1f}% "
              f"{'低' if e < 0 else '高':>4}  {f['model_version'] or '-'}")

    if not errs:
        print("\n无可对照样本(缺 actual 或单位异常)。")
        return
    print(f"\n样本 n={len(errs)}  中位偏差 {statistics.median(errs):+.1f}%  "
          f"均值 {statistics.mean(errs):+.1f}%  区间 [{min(errs):+.1f}%, {max(errs):+.1f}%]")
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
    # 最新定稿选取
    rows = [{"as_of_date": "2026-08-02"}, {"as_of_date": "2026-08-04"}]
    assert final_forecast(rows)["as_of_date"] == "2026-08-04"
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
