"""
APScheduler-based data ingestion — market quotes and financial snapshots via AkShare.
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


def _watchlist() -> list[str]:
    if WATCHLIST_PATH.exists():
        return json.loads(WATCHLIST_PATH.read_text())
    return []


def _fetch_market(ticker: str) -> None:
    today = date.today().isoformat()
    out = ROOT / "data/raw/market" / f"{today}_{ticker}.json"
    if out.exists():
        return  # cache hit

    try:
        df = ak.stock_individual_fund_flow(stock=ticker.split(".")[0], market="sh" if ticker.endswith("SH") else "sz")
        out.write_text(df.to_json(orient="records", force_ascii=False))
        print(f"[scheduler] market saved: {out.name}")
    except Exception as e:
        print(f"[scheduler] market ERROR {ticker}: {e}")


def _fetch_financials(ticker: str) -> None:
    # Determine current period label (approximate)
    today = date.today()
    q = (today.month - 1) // 3 + 1
    period = f"{today.year}Q{q}"
    out = ROOT / "data/raw/financials" / f"{ticker}_{period}.json"
    if out.exists():
        return  # cache hit

    try:
        df = ak.stock_financial_abstract(symbol=ticker.split(".")[0])
        out.write_text(df.to_json(orient="records", force_ascii=False))
        print(f"[scheduler] financials saved: {out.name}")
    except Exception as e:
        print(f"[scheduler] financials ERROR {ticker}: {e}")


def _job_market() -> None:
    for ticker in _watchlist():
        _fetch_market(ticker)


def _job_financials() -> None:
    for ticker in _watchlist():
        _fetch_financials(ticker)


def _job_spider() -> None:
    from src.ingestion.acecamp.spider import fetch_broker_reports
    import json
    vocab_path = ROOT / "config" / "vocab_dictionary.json"
    vocab = json.loads(vocab_path.read_text()) if vocab_path.exists() else []
    for entry in vocab:
        if entry.get("entity_type") == "Company":
            ticker = entry.get("ticker")
            name = entry.get("standard_name", "")
            fetch_broker_reports(name, ticker=ticker, limit=5)


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 15:30 every weekday — market close
    scheduler.add_job(_job_market, "cron", day_of_week="mon-fri", hour=15, minute=30)
    # 22:00 every day during reporting season (Apr / Aug / Oct)
    scheduler.add_job(_job_financials, "cron", month="4,8,10", hour=22, minute=0)
    # 16:00 every weekday — fetch AceCamp broker reports after market close
    scheduler.add_job(_job_spider, "cron", day_of_week="mon-fri", hour=16, minute=0)
    scheduler.start()
    print("[scheduler] started")
    return scheduler


if __name__ == "__main__":
    import time
    s = start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        s.shutdown()
