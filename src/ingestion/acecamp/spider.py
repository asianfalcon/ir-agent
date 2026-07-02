"""
AceCamp ingestion pipeline:
  search articles → fetch full content → chunk → upsert LanceDB
"""

import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = ROOT / "databases" / "ira.db"
RAW_DIR = ROOT / "data" / "raw" / "acecamp"
RAW_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _client():
    from src.ingestion.acecamp.acecamp_client import AceCampClient
    cfg = json.loads(_CONFIG_PATH.read_text())
    return AceCampClient(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        timeout=cfg.get("timeout", 300),
        verify_ssl=cfg.get("verify_ssl", False),
    )


def _ensure_crawl_log_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spider_crawl_log (
            url_date_hash TEXT PRIMARY KEY,
            url           TEXT,
            title         TEXT,
            crawled_at    TEXT
        )
    """)
    conn.commit()
    conn.close()


def _crawl_log_exists(url_date_hash: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM spider_crawl_log WHERE url_date_hash=?", (url_date_hash,)
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def _mark_crawled(url_date_hash: str, url: str, title: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO spider_crawl_log (url_date_hash, url, title, crawled_at) VALUES (?,?,?,?)",
        (url_date_hash, url, title, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _chunk_and_store(text: str, metadata: dict[str, Any]):
    from src.processing.text_processor import chunk_text
    from src.db.vector_store import upsert_chunks
    chunks = chunk_text(text, metadata=metadata)
    if chunks:
        upsert_chunks(chunks)
    return len(chunks)


def _get_full_content(client, item: dict) -> str:
    """Return best available content: snippet is usually substantial."""
    return item.get("snippet", "") or ""


def fetch_and_store(
    query: str,
    ticker: str | None = None,
    limit: int = 5,
    data_source: str = "broker_report",
) -> int:
    """
    Search AceCamp, fetch content, chunk and store in LanceDB.
    Returns count of new chunks stored.
    """
    _ensure_crawl_log_table()
    c = _client()
    today = str(date.today())

    result = c.search(query=query, limit=limit, original_query=query)
    items = result.get("items", [])

    total_chunks = 0
    for item in items:
        article_id = item.get("id", "")
        url = item.get("url") or f"acecamp://article/{article_id}"
        url_date_hash = hashlib.md5(f"{article_id}_{today}".encode()).hexdigest()

        if _crawl_log_exists(url_date_hash):
            continue

        content = _get_full_content(c, item)
        if not content:
            continue

        pub_date = (item.get("published_at") or today)[:10]
        source_id = hashlib.md5(str(article_id).encode()).hexdigest()

        n = _chunk_and_store(content, metadata={
            "ticker": ticker or "",
            "pub_date": pub_date,
            "period": "",
            "associated_vars": [],
            "data_source": data_source,
            "source_id": source_id,
            "source_uri": url,
            "title": item.get("title", ""),
        })
        total_chunks += n

        _mark_crawled(url_date_hash, url, item.get("title", ""))

        # persist raw
        raw_path = RAW_DIR / f"{today}_{url_date_hash[:8]}.json"
        raw_path.write_text(json.dumps(item, ensure_ascii=False, indent=2))

    return total_chunks


def ask_and_store(
    question: str,
    ticker: str | None = None,
    mode: str = "deep",
) -> int:
    """
    Ask AceCamp a question (deep mode), store the answer as chunks.
    Returns chunk count.
    """
    _ensure_crawl_log_table()
    c = _client()
    today = str(date.today())

    url_date_hash = hashlib.md5(f"ask_{question}_{today}".encode()).hexdigest()
    if _crawl_log_exists(url_date_hash):
        return 0

    result = c.ask(question, mode=mode)
    answer = result.get("answer", "")
    if not answer:
        return 0

    source_id = url_date_hash
    n = _chunk_and_store(answer, metadata={
        "ticker": ticker or "",
        "pub_date": today,
        "period": "",
        "associated_vars": [],
        "data_source": "broker_report",
        "source_id": source_id,
        "source_uri": f"acecamp://ask/{url_date_hash[:8]}",
        "title": question,
    })

    _mark_crawled(url_date_hash, f"acecamp://ask/{url_date_hash[:8]}", question)

    raw_path = RAW_DIR / f"{today}_ask_{url_date_hash[:8]}.json"
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    return n


if __name__ == "__main__":
    n = fetch_and_store("中际旭创 光模块", ticker="300308.SZ", limit=5)
    print(f"stored {n} chunks from search")
