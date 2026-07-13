#!/usr/bin/env python3
"""
Universal company data refresh entrypoint.

Refreshes, de-duplicates and ingests the five local evidence types:
news, financials, announcements, broker reports, and expert minutes.

Directory policy:
- data/inputs: manual uploads and official exports only.
- data/raw: untouched API/public-interface responses.
- data/processed: generated/cleaned artifacts ready for local ingestion.

AceCamp safety policy:
- Never calls browser-session fetchers.
- Never calls AceCamp spider/search/ask ingestion.
- Only processes official/manual exported JSON under data/inputs/expert_minutes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import akshare as ak
from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion import yfinance_fetcher
from src.ingestion.edgar_fetcher import fetch_announcements_us
from src.ingestion.akshare_hk_fetcher import fetch_financials_hk


@dataclass(frozen=True)
class Company:
    ticker: str
    code: str
    name: str


def _json_default(value: Any) -> str:
    return str(value)


def _slug(text: str, limit: int = 80) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:limit] or "untitled"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _code_from_ticker(ticker: str) -> str:
    return ticker.split(".", 1)[0]


def _market_prefix(ticker: str) -> str:
    suffix = ticker.split(".", 1)[1].upper() if "." in ticker else ""
    if suffix == "SH":
        return "SH"
    if suffix == "SZ":
        return "SZ"
    if suffix == "BJ":
        return "BJ"
    return "SH"


def _market(ticker: str) -> str:
    suffix = ticker.split(".", 1)[1].upper() if "." in ticker else ""
    if suffix in ("SH", "SZ", "BJ"):
        return "cn"
    if suffix == "US":
        return "us"
    if suffix == "HK":
        return "hk"
    return "cn"  # 保持无后缀时默认落到现有 SH 行为


def ensure_company_row(company: Company, sector: str = "") -> None:
    conn = sqlite3.connect(ROOT / "databases/ira.db")
    conn.execute(
        "INSERT INTO companies (ticker, name, sector) VALUES (?,?,?) "
        "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name",
        (company.ticker, company.name, sector),
    )
    conn.commit()
    conn.close()


def _company_from_vocab(ticker: str, fallback_name: str = "") -> Company:
    vocab = _load_json(ROOT / "config/vocab_dictionary.json", [])
    for entry in vocab:
        if entry.get("entity_type") == "Company" and entry.get("ticker") == ticker:
            return Company(ticker=ticker, code=_code_from_ticker(ticker), name=entry.get("standard_name") or fallback_name or ticker)
    return Company(ticker=ticker, code=_code_from_ticker(ticker), name=fallback_name or ticker)


def _watchlist_companies() -> list[Company]:
    tickers = _load_json(ROOT / "config/watchlist.json", [])
    return [_company_from_vocab(t) for t in tickers]


def fetch_financials(company: Company) -> list[dict]:
    market = _market(company.ticker)
    if market == "us":
        records = yfinance_fetcher.fetch_financials_us(company.ticker)
        yfinance_fetcher.upsert_sqlite_financials_us(company.ticker, records)
        return [{"name": "yfinance_quarterly", "rows": len(records)}]
    if market == "hk":
        records = fetch_financials_hk(company.ticker)
        return [{"name": "akshare_hk_quarterly", "rows": len(records)}]

    out_dir = ROOT / "data/raw/financials/akshare"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat().replace("-", "")
    em_symbol = f"{_market_prefix(company.ticker)}{company.code}"
    jobs = [
        ("financial_abstract", ak.stock_financial_abstract, {"symbol": company.code}),
        ("financial_indicator_report", ak.stock_financial_analysis_indicator_em, {"symbol": company.ticker, "indicator": "按报告期"}),
        ("profit_sheet_report", ak.stock_profit_sheet_by_report_em, {"symbol": em_symbol}),
        ("balance_sheet_report", ak.stock_balance_sheet_by_report_em, {"symbol": em_symbol}),
        ("cash_flow_report", ak.stock_cash_flow_sheet_by_report_em, {"symbol": em_symbol}),
    ]
    results = []
    for name, func, kwargs in jobs:
        try:
            df = func(**kwargs)
            records = df.to_dict(orient="records")
            path = out_dir / f"{company.ticker}_{name}_{today}.json"
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            results.append({"name": name, "rows": len(records), "path": str(path.relative_to(ROOT))})
        except Exception as exc:
            results.append({"name": name, "error": repr(exc)})
    return results


def update_sqlite_financial_supplements(company: Company) -> int:
    """Conservatively supplements existing financial_reports rows.

    Currently only fills gross_margin from AkShare indicator rows. Revenue and
    profit are not overwritten here to avoid mixing cumulative, single-quarter,
    net profit and parent-net-profit口径.
    """
    if _market(company.ticker) != "cn":
        return 0  # us 已在 fetch_financials_us 内部 upsert 完成；hk 暂无数据可补
    candidates = sorted((ROOT / "data/raw/financials/akshare").glob(f"{company.ticker}_financial_indicator_report_*.json"))
    if not candidates:
        return 0
    rows = json.loads(candidates[-1].read_text(encoding="utf-8"))
    conn = sqlite3.connect(ROOT / "databases/ira.db")
    before = conn.total_changes
    for row in rows:
        name = str(row.get("REPORT_DATE_NAME") or "")
        year = str(row.get("REPORT_YEAR") or "")
        if not year:
            continue
        if "一季报" in name:
            period = f"{year}Q1"
        elif "中报" in name or "半年报" in name:
            period = f"{year}Q2"
        elif "三季报" in name:
            period = f"{year}Q3"
        elif "年报" in name:
            period = f"{year}Q4"
        else:
            continue
        conn.execute(
            """
            UPDATE financial_reports
            SET gross_margin=COALESCE(?, gross_margin), updated_at=CURRENT_TIMESTAMP
            WHERE ticker=? AND period=?
            """,
            (row.get("XSMLL"), company.ticker, period),
        )
    conn.commit()
    changed = conn.total_changes - before
    conn.close()
    return changed


def fetch_announcements(company: Company, start_date: str) -> dict:
    market = _market(company.ticker)
    if market == "us":
        return fetch_announcements_us(company.ticker, company.name, limit=20)
    if market == "hk":
        return {"raw": None, "files": []}  # 港股公告源暂缺

    today = date.today().isoformat().replace("-", "")
    raw_dir = ROOT / "data/raw/announcements/akshare"
    processed_dir = ROOT / f"data/processed/announcements/akshare/{company.ticker}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    df = ak.stock_individual_notice_report(
        security=company.code,
        symbol="全部",
        begin_date=start_date,
        end_date=today,
    ).astype(str)
    records = df.to_dict(orient="records")
    raw_path = raw_dir / f"{company.ticker}_announcements_{today}.json"
    raw_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    paths = []
    for index, row in enumerate(records, 1):
        ann_date = str(row.get("公告日期", "")).replace("-", "") or "unknown"
        title = str(row.get("公告标题", ""))
        path = processed_dir / f"{ann_date}_{index:03d}_{_slug(title)}.md"
        path.write_text(
            "\n".join([
                f"# {title}",
                "",
                f"公司：{company.name}({company.ticker})",
                f"公告日期：{row.get('公告日期', '')}",
                f"公告类型：{row.get('公告类型', '')}",
                f"链接：{row.get('网址', '')}",
                "",
            ]),
            encoding="utf-8",
        )
        paths.append(path)
    return {"raw": raw_path, "files": paths}


def fetch_news(company: Company, limit: int) -> dict:
    market = _market(company.ticker)
    if market == "us":
        return yfinance_fetcher.fetch_news_processed(company.ticker, company.name, limit)
    if market == "hk":
        return {"raw": None, "files": []}  # 港股新闻源暂缺

    today = date.today().isoformat().replace("-", "")
    raw_dir = ROOT / "data/raw/news/akshare"
    processed_dir = ROOT / f"data/processed/news/akshare/{company.ticker}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    try:
        df = ak.stock_news_em(symbol=company.code)
        records = df.astype(str).to_dict(orient="records")[:limit]
        source_api = "akshare.stock_news_em"
    except Exception as exc:
        try:
            records = _fetch_news_eastmoney_direct(company.code, limit)
            source_api = f"eastmoney.search_api_fallback; akshare_error={repr(exc)}"
        except Exception as fallback_exc:
            return {"error": f"akshare={repr(exc)}; fallback={repr(fallback_exc)}", "raw": None, "files": []}

    raw_path = raw_dir / f"{company.ticker}_news_{today}.json"
    raw_path.write_text(json.dumps({"source_api": source_api, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    paths = []
    for index, row in enumerate(records, 1):
        title = row.get("新闻标题") or row.get("标题") or row.get("title") or f"{company.name}新闻"
        pub_time = row.get("发布时间") or row.get("时间") or row.get("日期") or today
        pub_date = str(pub_time)[:10].replace("-", "") or today
        source = row.get("文章来源") or row.get("来源") or row.get("source") or ""
        url = row.get("新闻链接") or row.get("链接") or row.get("url") or ""
        content = row.get("新闻内容") or row.get("内容") or row.get("content") or ""
        path = processed_dir / f"{pub_date}_{index:03d}_{_slug(str(title))}.md"
        path.write_text(
            "\n".join([
                f"# {title}",
                "",
                f"公司：{company.name}({company.ticker})",
                f"日期：{pub_time}",
                f"来源：{source}",
                f"链接：{url}",
                "",
                str(content),
                "",
            ]),
            encoding="utf-8",
        )
        paths.append(path)
    return {"raw": raw_path, "files": paths}


def _clean_news_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"</?em>", "", text)
    text = text.replace("\\u3000", "").replace("\u3000", "")
    text = text.replace("\r\n", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _fetch_news_eastmoney_direct(code: str, limit: int) -> list[dict]:
    callback = f"jQuery351_{int(time.time() * 1000)}"
    inner_param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": max(10, min(limit, 100)),
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    params = {
        "cb": callback,
        "param": json.dumps(inner_param, ensure_ascii=False),
        "_": str(int(time.time() * 1000)),
    }
    response = requests.get(
        "https://search-api-web.eastmoney.com/search/jsonp",
        params=params,
        headers={
            "referer": f"https://so.eastmoney.com/news/s?keyword={code}",
            "user-agent": "Mozilla/5.0",
        },
        timeout=20,
    )
    response.raise_for_status()
    text = response.text.strip()
    prefix = f"{callback}("
    if text.startswith(prefix) and text.endswith(")"):
        text = text[len(prefix) : -1]
    payload = json.loads(text)
    rows = payload.get("result", {}).get("cmsArticleWebOld", [])
    records = []
    for row in rows[:limit]:
        article_code = row.get("code", "")
        records.append(
            {
                "关键词": code,
                "新闻标题": _clean_news_text(row.get("title")),
                "新闻内容": _clean_news_text(row.get("content")),
                "发布时间": str(row.get("date", "")),
                "文章来源": str(row.get("mediaName", "")),
                "新闻链接": f"http://finance.eastmoney.com/a/{article_code}.html" if article_code else "",
            }
        )
    return records


def report_files(company: Company) -> list[Path]:
    paths = sorted((ROOT / f"data/inputs/reports/{company.name}").rglob("*.pdf"))
    # ponytail: same-content PDFs re-uploaded under a different filename (e.g. "(1)"
    # suffix) previously got ingested twice — dedupe by file content hash, keep first.
    seen: dict[str, Path] = {}
    unique = []
    for p in paths:
        h = hashlib.md5(p.read_bytes()).hexdigest()
        if h in seen:
            print(f"[refresh] skip duplicate-content report: {p} (same as {seen[h]})")
            continue
        seen[h] = p
        unique.append(p)
    return unique


def gc_stale_report_rows(ticker: str, current_files: list[Path]) -> int:
    """删除LanceDB里source_file已不在当前report_files()清单中的broker_report行。

    文件被移动/改名/重组目录后，旧路径下的行永远不会被process_file()里的
    delete_by_source_file()自然清理（它只按当前computed source_file精确匹配删除），
    这里做一次基于"当前磁盘上实际存在的文件集合"的补充清理。
    """
    import lancedb

    current = {str(p.relative_to(ROOT)) for p in current_files}
    db = lancedb.connect(str(ROOT / "data/storage/lancedb_root"))
    if "chunks" not in db.table_names():
        return 0
    tbl = db.open_table("chunks")
    safe_ticker = ticker.replace("'", "''")
    rows = (
        tbl.search()
        .where(f"ticker = '{safe_ticker}' AND data_source = 'broker_report'")
        .select(["source_file"])
        .to_list()
    )
    stale = {r["source_file"] for r in rows} - current
    for sf in stale:
        tbl.delete(f"source_file = '{sf.replace(chr(39), chr(39) * 2)}'")
    if stale:
        print(f"[refresh] gc stale report rows: removed {len(stale)} orphaned source_file group(s)")
    return len(stale)


def process_local_files(paths: list[Path], ticker: str | None = None) -> int:
    from src.processing.text_processor import process_file

    chunks = 0
    for path in paths:
        try:
            chunks += len(process_file(path, ticker_override=ticker))
        except Exception as exc:
            print(f"[refresh] process ERROR {path}: {exc}")
    return chunks


def clear_lancedb_rows(ticker: str, data_source: str) -> None:
    import lancedb

    db = lancedb.connect(str(ROOT / "data/storage/lancedb_root"))
    if "chunks" not in db.table_names():
        return
    tbl = db.open_table("chunks")
    safe_ticker = ticker.replace("'", "''")
    safe_source = data_source.replace("'", "''")
    tbl.delete(f"ticker = '{safe_ticker}' AND data_source = '{safe_source}'")


def process_expert_minutes(skip_graph: bool) -> dict:
    from src.ingestion.acecamp.expert_processor import batch_process

    chunks = batch_process("")
    result = {"chunks": chunks}
    if not skip_graph:
        from src.ingestion.acecamp.graph_extractor import batch_process as graph_batch_process

        result["graph_relations"] = graph_batch_process()
    return result


def count_lancedb_rows(ticker: str) -> dict:
    import lancedb

    db = lancedb.connect(str(ROOT / "data/storage/lancedb_root"))
    tbl = db.open_table("chunks")
    result = {"total_rows": tbl.count_rows()}
    for key, where in {
        "ticker_rows": f"ticker = '{ticker}'",
        "broker_report": f"ticker = '{ticker}' AND data_source = 'broker_report'",
        "expert_minutes": f"ticker = '{ticker}' AND data_source = 'acecamp_expert_column'",
        "announcements": f"ticker = '{ticker}' AND data_source = 'announcement'",
        "news": f"ticker = '{ticker}' AND data_source = 'web_news'",
    }.items():
        result[key] = tbl.count_rows(where)
    return result


def refresh_company(company: Company, args) -> dict:
    print(f"\n[refresh] {company.name}({company.ticker})")
    ensure_company_row(company)
    summary: dict[str, Any] = {"ticker": company.ticker, "company": company.name}

    if not args.skip_financials:
        summary["financials"] = fetch_financials(company)
        summary["sqlite_financial_updates"] = update_sqlite_financial_supplements(company)

    if not args.skip_announcements:
        announcements = fetch_announcements(company, args.ann_start_date)
        summary["announcements"] = len(announcements["files"])
    else:
        announcements = {"files": []}

    if not args.skip_news:
        news = fetch_news(company, args.news_limit)
        summary["news"] = len(news["files"])
        if news.get("error"):
            summary["news_error"] = news["error"]
    else:
        news = {"files": []}

    if not args.skip_reports:
        reports = report_files(company)
        summary["report_files"] = len(reports)
        summary["gc_stale_report_rows"] = gc_stale_report_rows(company.ticker, reports)
    else:
        reports = []

    if not args.skip_announcements and announcements["files"]:
        # Announcements are fetched as a full date window. Rebuild the ticker's
        # announcement slice to avoid duplicate legacy paths after directory
        # migrations (for example inputs/... -> processed/...).
        clear_lancedb_rows(company.ticker, "announcement")

    summary["document_chunks"] = process_local_files(reports + announcements["files"] + news["files"], ticker=company.ticker)
    summary["lancedb"] = count_lancedb_rows(company.ticker)
    print(f"[refresh] summary: {json.dumps(summary, ensure_ascii=False, default=_json_default)}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh local evidence data for one company or the watchlist.")
    parser.add_argument("--ticker", help="Ticker like 688141.SH. Omit with --all-watchlist.")
    parser.add_argument("--company", help="Company display name. Defaults to vocab_dictionary lookup.")
    parser.add_argument("--code", help="Stock code. Defaults to ticker prefix.")
    parser.add_argument("--all-watchlist", action="store_true", help="Refresh all tickers in config/watchlist.json.")
    parser.add_argument("--ann-start-date", default="20260101")
    parser.add_argument("--news-limit", type=int, default=30)
    parser.add_argument("--skip-news", action="store_true")
    parser.add_argument("--skip-financials", action="store_true")
    parser.add_argument("--skip-announcements", action="store_true")
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--skip-expert-minutes", action="store_true")
    parser.add_argument("--skip-graph", action="store_true")
    args = parser.parse_args()

    if args.all_watchlist:
        companies = _watchlist_companies()
    else:
        if not args.ticker:
            parser.error("--ticker is required unless --all-watchlist is used")
        base = _company_from_vocab(args.ticker, args.company or "")
        companies = [Company(ticker=args.ticker, code=args.code or base.code, name=args.company or base.name)]

    summaries = [refresh_company(company, args) for company in companies]

    if not args.skip_expert_minutes:
        expert_summary = process_expert_minutes(skip_graph=args.skip_graph)
    else:
        expert_summary = {"skipped": True}

    final = {"companies": summaries, "expert_minutes": expert_summary}
    print("\n[refresh] final")
    print(json.dumps(final, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
