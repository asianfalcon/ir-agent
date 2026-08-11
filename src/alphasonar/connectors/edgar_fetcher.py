"""SEC EDGAR fetcher —— 10-K/10-Q/8-K，免费公开 data.sec.gov JSON API。
输出格式完全镜像 refresh_company_data.py:fetch_announcements()，process_local_files() 零改动。"""
import json
import re
from datetime import date
from curl_cffi import requests

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
_HEADERS = {"User-Agent": "AlphaSonar research tool contact@example.com"}
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FILING_TYPES = ("10-K", "10-Q", "8-K")


def _cik_for_symbol(symbol: str) -> int | None:
    cache = _SETTINGS.external_source_root / "announcements" / "edgar" / "_company_tickers.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        resp = requests.get(_TICKER_MAP_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        cache.write_text(json.dumps(data))
    for row in data.values():
        if row.get("ticker", "").upper() == symbol.upper():
            return int(row["cik_str"])
    return None


def fetch_announcements_us(ticker: str, company_name: str, limit: int = 20) -> dict:
    """只抓公告的标题/日期/类型/链接（索引卡片），不抓 10-K/10-Q 正文全文——
    和 A股 fetch_announcements() 现状一致。"""
    symbol = ticker.split(".")[0]
    today = date.today().isoformat().replace("-", "")
    raw_dir = _SETTINGS.external_source_root / "announcements" / "edgar"
    processed_dir = _SETTINGS.derived_root / "announcements" / "edgar" / ticker
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    cik = _cik_for_symbol(symbol)
    if cik is None:
        return {"error": f"no CIK found for {symbol}", "raw": None, "files": []}

    resp = requests.get(_SUBMISSIONS_URL.format(cik=cik), headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    raw_path = raw_dir / f"{ticker}_submissions_{today}.json"
    raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    titles = recent.get("primaryDocDescription", [])

    paths = []
    count = 0
    for i, form in enumerate(forms):
        if form not in _FILING_TYPES:
            continue
        if count >= limit:
            break
        accn_nodash = accns[i].replace("-", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{docs[i]}"
        ann_date = dates[i].replace("-", "")
        title = titles[i] or f"{form} filing"
        path = processed_dir / f"{ann_date}_{count+1:03d}_{re.sub(r'[^A-Za-z0-9]+', '_', title)[:80]}.md"
        path.write_text(
            "\n".join([
                f"# {form}: {title}", "",
                f"公司：{company_name}({ticker})",
                f"公告日期：{dates[i]}",
                f"公告类型：{form}",
                f"链接：{doc_url}", "",
            ]),
            encoding="utf-8",
        )
        paths.append(path)
        count += 1
    return {"raw": raw_path, "files": paths}
