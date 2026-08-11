"""
AceCamp transcript fetcher — uses browser session credentials to fetch 纪要/文章正文。

配置方式：在 config/api_keys.json 的 "acecamp_web" 键下填入从 DevTools 抓到的值：
{
  "acecamp_web": {
    "user_token": "eyJ...",
    "session":    "pVD1...",
    "x_wk": "k01",
    "x_wm": "...",    # 随 session 滚动，失效时重新从 DevTools 抓
    "x_ws": "..."
  },
  "acecamp_corp_ids": {
    "688141.SH": 26106
  }
}
"""
import json
import random
import string
import time
import warnings
from datetime import datetime
from pathlib import Path

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
_KEYS_PATH = _SETTINGS.config_root / "api_keys.json"
RAW_DIR = _SETTINGS.external_source_root / "expert_minutes" / "acecamp"
RAW_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://api.acecamptech.com/api/v1"
DATA_SOURCE = "acecamp_expert_column"
HOT_BADGES = {"hot"}
HOT_WEIGHT_BONUS = 0.2


def _creds() -> dict:
    data = json.loads(_KEYS_PATH.read_text())
    creds = data.get("acecamp_web", {})
    if not creds.get("user_token"):
        raise RuntimeError(
            "acecamp_web.user_token 未配置。"
            "请在浏览器 DevTools → Application → Cookies 复制 user_token 填入 config/api_keys.json"
        )
    return creds


def _corp_ids() -> dict:
    return json.loads(_KEYS_PATH.read_text()).get("acecamp_corp_ids", {})


def _headers(creds: dict) -> dict:
    ts = int(time.time() * 1000)
    rid = "".join(random.choices(string.ascii_lowercase, k=6))
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN",
        "content-type": "application/x-www-form-urlencoded; charset=utf-8",
        "web-version": "web@1.3.3",
        "x-client-app": "consume_pc",
        "x-client-request-id": f"consume_pc-{ts}-{rid}",
        "x-seq": "1",
        "x-wk": creds.get("x_wk", "k01"),
        "x-wm": creds.get("x_wm", ""),
        "x-ws": creds.get("x_ws", ""),
        "origin": "https://www.acecamptech.com",
        "referer": "https://www.acecamptech.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        ),
    }


def _cookies(creds: dict) -> dict:
    c = {"user_token": creds["user_token"]}
    if s := creds.get("session"):
        c["_ace_camp_tech_production_session"] = s
    return c


def _jitter(lo: float = 4.0, hi: float = 9.0) -> None:
    """随机等待，模拟真人阅读间隔，避免触发频率限制。"""
    time.sleep(lo + random.random() * (hi - lo))


def _get(path: str, params: dict) -> dict:
    import requests
    creds = _creds()
    params.setdefault("locale", "zh-CN")
    params.setdefault("version", "2.0")
    params.setdefault("ack", int(time.time() * 1000))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = requests.get(
            f"{API_BASE}{path}",
            params=params,
            headers=_headers(creds),
            cookies=_cookies(creds),
            verify=False,
            timeout=30,
        )
    if r.status_code == 429:
        print("[acecamp] 429 限速，等待 60s...", flush=True)
        time.sleep(60)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = requests.get(
                f"{API_BASE}{path}",
                params=params,
                headers=_headers(creds),
                cookies=_cookies(creds),
                verify=False,
                timeout=30,
            )
    r.raise_for_status()
    return r.json()


# ── 单篇文章 ──────────────────────────────────────────────────────────────────

def fetch_article(article_id: int | str) -> dict:
    """拉取单篇文章/纪要，返回原始 JSON。"""
    return _get("/articles/article_info", {"id": article_id})


# ── feeds 列表 ────────────────────────────────────────────────────────────────

def list_feeds(corp_id: int, page_size: int = 20, before_cursor: int | None = None) -> dict:
    """
    拉取公司 feed 列表（纪要 + 活动），支持 cursor 翻页。
    before_cursor: 上一页最后一条的 cursor 值，不传则从最新开始。
    返回原始 JSON，结构: {"data": {"feeds": [...], ...}, "meta": {...}}
    """
    params: dict = {
        "page_size": page_size,
        "topping": "false",
        "sort": "latest",
        "corporation_ids[]": corp_id,
    }
    if before_cursor is not None:
        params["before_cursor"] = before_cursor
    return _get("/feeds", params)


def list_all_feeds(corp_id: int, page_size: int = 20) -> list[dict]:
    """翻页拉取全部 feed，返回 feed 条目列表。"""
    feeds = []
    cursor = None
    while True:
        resp = list_feeds(corp_id, page_size=page_size, before_cursor=cursor)
        batch = resp.get("data", {}).get("feeds", [])
        if not batch:
            break
        feeds.extend(batch)
        if len(batch) < page_size:
            break
        cursor = batch[-1]["cursor"]
        _jitter(5, 12)  # 翻页间随机等待 5-12s
    return feeds


# ── 存储 ──────────────────────────────────────────────────────────────────────

def _store_text(
    text: str,
    title: str,
    pub_date: str,
    article_id,
    ticker: str,
    release_time: int = 0,
    badges: list[str] | None = None,
) -> int:
    from alphasonar.pipelines.text_processor import chunk_text
    from alphasonar.storage.vector_store import upsert_chunks
    import hashlib
    badges = [str(b) for b in (badges or []) if b]
    is_hot = bool(HOT_BADGES.intersection(set(badges)))
    source_id = hashlib.md5(f"acecamp_{article_id}".encode()).hexdigest()
    chunks = chunk_text(text, metadata={
        "ticker": ticker,
        "pub_date": pub_date,
        "period": "",
        "associated_vars": [],
        "data_source": DATA_SOURCE,
        "source_id": source_id,
        "source_uri": f"acecamp://article/{article_id}",
        "source_file": f"acecamp://article/{article_id}",
        "release_time": int(release_time or 0),
        "badges": badges,
        "is_hot": is_hot,
        "source_weight": 1.0 + (HOT_WEIGHT_BONUS if is_hot else 0.0),
        "title": title,
    })
    if chunks:
        upsert_chunks(chunks)
    return len(chunks)


def store_summary(feed_item: dict, ticker: str = "") -> int:
    """
    直接把 feed 里的 summary 存入 LanceDB（无需额外 API 调用）。
    只处理 Minute 类型；Event 无正文跳过。
    """
    if feed_item.get("source_type") != "Minute":
        return 0
    src = feed_item.get("source", {})
    summary = src.get("summary", "").strip()
    if not summary:
        return 0
    title   = src.get("title", str(feed_item.get("source_id")))
    ts      = src.get("release_time", 0)
    pub_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
    article_id = src.get("id") or feed_item.get("source_id")
    n = _store_text(
        summary,
        title,
        pub_date,
        article_id,
        ticker,
        release_time=ts,
        badges=src.get("badges", []),
    )
    print(f"[acecamp] summary {article_id} '{title[:30]}': {n} chunks", flush=True)
    return n


def fetch_and_store(article_id: int | str, ticker: str = "") -> int:
    """
    拉取完整 article_info 并存入 LanceDB（优先 transcribe，次选 content）。
    已缓存或付费墙则跳过。
    """
    raw_path = RAW_DIR / f"transcript_{article_id}.json"
    if raw_path.exists():
        data = json.loads(raw_path.read_text())
    else:
        data = fetch_article(article_id)
        raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    article = data.get("data") or data
    if article.get("masked_state") == "all_masked" and article.get("need_to_pay"):
        print(f"[acecamp] {article_id}: 付费墙，跳过", flush=True)
        return 0

    title    = article.get("title") or str(article_id)
    ts       = article.get("release_time", 0)
    pub_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""

    transcribe = article.get("transcribe") or ""
    content    = article.get("content") or ""
    text = transcribe if len(transcribe) > len(content) else content
    if not text:
        print(f"[acecamp] {article_id}: 正文为空", flush=True)
        return 0

    n = _store_text(
        text,
        title,
        pub_date,
        article_id,
        ticker,
        release_time=ts,
        badges=article.get("badges", []),
    )
    print(f"[acecamp] full {article_id} '{title[:30]}': {n} chunks (transcribe={bool(transcribe)})", flush=True)
    return n


# ── 完整同步入口 ──────────────────────────────────────────────────────────────

def sync_company(ticker: str, full_content: bool = False) -> int:
    """
    同步某 ticker 的所有 AceCamp 纪要到 LanceDB。
    ticker: 如 "688141.SH"
    full_content: True 则进一步调 article_info 拉完整正文（较慢），False 只存 summary（快）
    返回总 chunk 数。
    """
    corp_ids = _corp_ids()
    corp_id = corp_ids.get(ticker)
    if not corp_id:
        raise ValueError(
            f"未找到 {ticker} 的 AceCamp corp_id，"
            "请在 config/api_keys.json 的 acecamp_corp_ids 中添加"
        )

    feeds = list_all_feeds(corp_id)
    minutes = [f for f in feeds if f.get("source_type") == "Minute"]
    print(f"[acecamp] {ticker}: {len(feeds)} feeds，其中 {len(minutes)} 篇纪要", flush=True)

    total = 0
    for i, feed in enumerate(minutes, 1):
        aid = feed.get("source_id")
        if full_content:
            try:
                n = fetch_and_store(aid, ticker=ticker)
                total += n
                print(f"[acecamp] ({i}/{len(minutes)}) done", flush=True)
                if n > 0:
                    _jitter(8, 20)   # 每篇正文请求后等 8-20s
                else:
                    _jitter(3, 6)    # 缓存命中/跳过后短等
            except Exception as e:
                print(f"[acecamp] {aid} full ERROR: {e}", flush=True)
                _jitter(10, 20)      # 出错后也等一会儿
        else:
            total += store_summary(feed, ticker=ticker)
            # summary 只是本地处理，无 API 调用，无需等待
    return total


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "688141.SH"
    full   = "--full" in sys.argv
    n = sync_company(ticker, full_content=full)
    print(f"\n完成：{ticker} 共存入 {n} chunks (full_content={full})", flush=True)
