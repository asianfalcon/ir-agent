"""
APScheduler-based data ingestion — AkShare + Tushare + YFinance.
Cache-intercept: skips API call if today's raw file already exists on disk.
"""

import json
import os
from datetime import date
from pathlib import Path

import akshare as ak
from apscheduler.schedulers.background import BackgroundScheduler

ROOT = Path(__file__).parent.parent.parent
WATCHLIST_PATH = ROOT / "config" / "watchlist.json"
VOCAB_PATH = ROOT / "config" / "vocab_dictionary.json"


def _watchlist() -> list[str]:
    if WATCHLIST_PATH.exists():
        return json.loads(WATCHLIST_PATH.read_text())
    return []


def _company_names() -> list[str]:
    if not VOCAB_PATH.exists():
        return []
    vocab = json.loads(VOCAB_PATH.read_text())
    return [e["standard_name"] for e in vocab if e.get("entity_type") == "Company"]


# ── AkShare ───────────────────────────────────────────────────────────────────

def _fetch_market(ticker: str) -> None:
    today = date.today().isoformat()
    out = ROOT / "data/raw/market" / f"{today}_{ticker}.json"
    if out.exists():
        return
    try:
        df = ak.stock_zh_a_hist(symbol=ticker.split(".")[0], period="daily",
                                start_date=(date.today().replace(day=1)).strftime("%Y%m%d"),
                                adjust="qfq")
        out.write_text(df.to_json(orient="records", force_ascii=False))
        print(f"[akshare] market saved: {out.name}")
    except Exception as e:
        print(f"[akshare] market ERROR {ticker}: {e}")


def _fetch_financials(ticker: str) -> None:
    today = date.today()
    q = (today.month - 1) // 3 + 1
    period = f"{today.year}Q{q}"
    out = ROOT / "data/raw/financials" / f"{ticker}_{period}.json"
    if out.exists():
        return
    try:
        df = ak.stock_financial_abstract(symbol=ticker.split(".")[0])
        out.write_text(df.to_json(orient="records", force_ascii=False))
        print(f"[akshare] financials saved: {out.name}")
    except Exception as e:
        print(f"[akshare] financials ERROR {ticker}: {e}")


# ── Tushare ───────────────────────────────────────────────────────────────────

def _job_tushare_daily() -> None:
    from src.ingestion.tushare_fetcher import fetch_daily
    for ticker in _watchlist():
        # Tushare 格式: 688141.SH (与 watchlist 一致)
        fetch_daily(ticker)


def _job_tushare_news() -> None:
    from src.ingestion.tushare_fetcher import fetch_news
    names = _company_names()
    if names:
        fetch_news(names, limit=30)


# ── YFinance ──────────────────────────────────────────────────────────────────

def _job_yfinance_macro() -> None:
    from src.ingestion.yfinance_fetcher import fetch_macro
    fetch_macro()


# ── AceCamp spider ────────────────────────────────────────────────────────────

def _job_spider() -> None:
    try:
        from src.ingestion.acecamp.spider import fetch_and_store
    except ImportError:
        return
    vocab = json.loads(VOCAB_PATH.read_text()) if VOCAB_PATH.exists() else []
    for entry in vocab:
        if entry.get("entity_type") == "Company":
            fetch_and_store(entry["standard_name"], ticker=entry.get("ticker"), limit=5)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _job_market() -> None:
    for ticker in _watchlist():
        _fetch_market(ticker)


def _job_financials() -> None:
    for ticker in _watchlist():
        _fetch_financials(ticker)


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 15:35 每个交易日 — AkShare 行情
    scheduler.add_job(_job_market, "cron", day_of_week="mon-fri", hour=15, minute=35)
    # 15:40 每个交易日 — Tushare 日线
    scheduler.add_job(_job_tushare_daily, "cron", day_of_week="mon-fri", hour=15, minute=40)
    # 16:05 每个交易日 — Tushare 新闻 + AceCamp 研报
    scheduler.add_job(_job_tushare_news, "cron", day_of_week="mon-fri", hour=16, minute=5)
    scheduler.add_job(_job_spider, "cron", day_of_week="mon-fri", hour=16, minute=10)
    # 8:00 每天 — YFinance 宏观（前一日收盘）
    scheduler.add_job(_job_yfinance_macro, "cron", hour=8, minute=0)
    # 22:00 财报季 — AkShare 财务摘要
    scheduler.add_job(_job_financials, "cron", month="4,8,10", hour=22, minute=0)
    scheduler.start()
    print("[scheduler] started — AkShare + Tushare + YFinance + AceCamp")
    return scheduler


if __name__ == "__main__":
    import time
    s = start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        s.shutdown()

