"""forecast_events 自检：加分裁决 / append-only / 口径隔离 / 穿越标记 各验一次。"""
import argparse
import sqlite3
import tempfile
from pathlib import Path

from scripts.ops import forecast_snapshot as fs


def _rec(db, **kw):
    d = dict(run_id="", ticker="INTC", as_of_date="", target_period="2026Q1",
             event_type="forecast", metric="revenue", basis="", low=None, mid=None,
             high=None, unit="", source_type="", source_id="", model_version="",
             information_cutoff="", note="")
    fs.record(argparse.Namespace(**{**d, **kw}), db_path=db)


def test_guardrails():
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        db = Path(tmp) / "g.db"
        # 利润类无 basis → 拒写
        try:
            _rec(db, metric="net_income", mid=1e9); assert False, "应拒写"
        except ValueError as e:
            assert "BASIS_REQUIRED" in str(e)
        # Non-GAAP actual 无 source_id → 拒写
        try:
            _rec(db, event_type="actual", metric="eps", basis="Non-GAAP", mid=1.4)
            assert False, "应拒写"
        except ValueError as e:
            assert "NONGAAP_ACTUAL_NEEDS_SOURCE" in str(e)
        # revenue 无 basis → 允许（不强制复制成两行）
        _rec(db, metric="revenue", as_of_date="2026-04-01", mid=13577e6)


def test_same_day_revision_deterministic():
    """同日多修订：必须确定性取最后写入的一条，不随机。"""
    import tempfile as _tf, sqlite3 as _sq
    with _tf.TemporaryDirectory() as tmp:
        db = Path(tmp) / "r.db"
        _rec(db, event_type="actual", metric="revenue", as_of_date="2026-04-23", mid=14000e6, source_id="a1")
        _rec(db, metric="revenue", basis="", as_of_date="2026-04-10", mid=13000e6)
        # 同一天两条 forecast 修订：13900 先，13950 后 → 应取 13950
        _rec(db, metric="revenue", as_of_date="2026-04-15", mid=13900e6)
        _rec(db, metric="revenue", as_of_date="2026-04-15", mid=13950e6)
        conn = _sq.connect(db); conn.executescript(fs.DDL); conn.row_factory = _sq.Row
        latest = fs._latest(conn, None, "forecast")
        conn.close()
        rev = [r for r in latest if r["metric"] == "revenue"]
        assert len(rev) == 1, f"每组应唯一一条，得 {len(rev)}"
        assert rev[0]["value_mid"] == 13950e6, rev[0]["value_mid"]


def _score_capture(db):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fs.score(argparse.Namespace(ticker=None, tol=0.02), db_path=db)
    return buf.getvalue()


def test_flow():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "t.db"
        # 误差纯函数
        assert abs(fs._err(13900, 14000) - 100 / 14000) < 1e-9
        assert fs._err(13300, 14000) > fs._err(13900, 14000)
        assert fs._err(None, 14000) is None and fs._err(13900, 0) is None

        # ira(13900) 比 consensus(13300) 更接近实际 14000 → 加分
        _rec(db, event_type="consensus", as_of_date="2026-04-01", mid=13300)
        _rec(db, event_type="forecast", as_of_date="2026-04-10", mid=13900)
        _rec(db, event_type="actual", as_of_date="2026-04-23", mid=14000)
        out = _score_capture(db)
        assert "加分 1" in out, out
        assert "⚠可能穿越" not in out, out  # forecast 早于 actual，不穿越

        # append-only：同键再插一条修订，旧的不删
        _rec(db, event_type="forecast", as_of_date="2026-04-15", mid=13950)
        conn = sqlite3.connect(db); conn.executescript(fs.DDL)
        n = conn.execute("SELECT COUNT(*) FROM forecast_events WHERE event_type='forecast'").fetchone()[0]
        conn.close()
        assert n == 2, n  # 两条 forecast 都在
        # score 用最新那条(13950)，仍加分
        assert "加分 1" in _score_capture(db)

        # 口径隔离：Non-GAAP eps 不与 GAAP eps 混比
        _rec(db, event_type="forecast", metric="eps", basis="Non-GAAP", as_of_date="2026-04-10", mid=1.37)
        _rec(db, event_type="actual", metric="eps", basis="Non-GAAP", as_of_date="2026-04-23", mid=1.40, source_id="rel")
        _rec(db, event_type="consensus", metric="eps", basis="Non-GAAP", as_of_date="2026-04-01", mid=1.30)
        out = _score_capture(db)
        assert "Non-GAAP" in out and "eps" in out, out

        # 穿越：forecast 在 actual 之后做出 → 打标
        _rec(db, ticker="AMD", target_period="2026Q2", event_type="consensus", as_of_date="2026-07-01", mid=112)
        _rec(db, ticker="AMD", target_period="2026Q2", event_type="actual", as_of_date="2026-08-05", mid=113)
        _rec(db, ticker="AMD", target_period="2026Q2", event_type="forecast", as_of_date="2026-08-10", mid=113)
        assert "⚠可能穿越" in _score_capture(db)

        print("ok")


if __name__ == "__main__":
    test_guardrails()
    test_same_day_revision_deterministic()
    test_flow()
    print("all ok")
