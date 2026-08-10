#!/usr/bin/env python3
"""Synchronize locally fetched WeChat articles into IRA's evidence store.

The companion service owns WeChat login, subscriptions and rate limiting. This
script only reads its local feed API, persists source Markdown under
``data/inputs/news/<folder>/wechat/`` and optionally invokes IRA's existing
text processor. No WeChat cookie or token is accepted by this script.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ira.settings import get_settings

DEFAULT_CONFIG = ROOT / "config" / "wechat_sources.json"
DEFAULT_STATE = get_settings().derived_root / "wechat_sync_state.json"
CHINA_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Source:
    nickname: str
    fakeid: str
    ticker: str
    folder: str
    enabled: bool = True


def _json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_sources(path: Path) -> list[Source]:
    rows = _json(path, [])
    result: list[Source] = []
    for row in rows:
        source = Source(
            nickname=str(row.get("nickname", "")).strip(),
            fakeid=str(row.get("fakeid", "")).strip(),
            ticker=str(row.get("ticker", "")).strip(),
            folder=str(row.get("folder", "")).strip(),
            enabled=bool(row.get("enabled", True)),
        )
        if source.enabled:
            if not source.fakeid or not source.ticker or not source.folder:
                raise ValueError(
                    f"Enabled WeChat source requires fakeid/ticker/folder: {row}"
                )
            result.append(source)
    return result


def _request_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "IRA-WeChat-Sync/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"WeChat API request failed: {url}: {exc}") from exc


def _request_text(base_url: str, path: str) -> str:
    url = base_url.rstrip("/") + path
    request = Request(url, headers={"Accept": "text/markdown", "User-Agent": "IRA-WeChat-Sync/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 422:
            raise RuntimeError(f"Article content has not been fetched yet: {url}") from exc
        raise RuntimeError(f"WeChat API request failed: {url}: HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"WeChat API request failed: {url}: {exc}") from exc


def _safe_name(value: str, limit: int = 90) -> str:
    value = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:limit] or "untitled"


def _article_path(source: Source, article: dict[str, Any]) -> Path:
    timestamp = int(article.get("publish_time") or 0)
    date_prefix = datetime.fromtimestamp(timestamp, CHINA_TZ).strftime("%Y%m%d") if timestamp else "00000000"
    article_id = str(article.get("id", "unknown"))
    title = _safe_name(str(article.get("title", "")))
    return get_settings().manual_source_root / "news" / source.folder / "wechat" / f"{date_prefix}-{title}-{article_id}.md"


def _source_for_article(sources: list[Source], article: dict[str, Any]) -> Source | None:
    fakeid = str(article.get("fakeid", ""))
    nickname = str(article.get("nickname", ""))
    for source in sources:
        if source.fakeid == fakeid or (source.nickname and source.nickname == nickname):
            return source
    return None


def _ingest(path: Path, ticker: str) -> int:
    from ira.pipelines.text_processor import process_file

    return len(process_file(path, ticker_override=ticker))


def sync(
    *,
    base_url: str,
    sources: list[Source],
    state_path: Path,
    ingest: bool,
    limit: int,
) -> dict[str, int]:
    state = _json(state_path, {"sources": {}})
    cursors: dict[str, int] = state.setdefault("sources", {})
    totals = {"downloaded": 0, "ingested_chunks": 0, "skipped_unmapped": 0, "pending_content": 0}

    for configured_source in sources:
        cursor = int(cursors.get(configured_source.fakeid, 0))
        while True:
            payload = _request_json(
                base_url,
                "/api/feed/articles.json",
                {"since": cursor, "fakeid": configured_source.fakeid, "limit": limit},
            )
            articles = payload.get("articles") or []
            if not articles:
                break

            batch_cursor = cursor
            earliest_pending: int | None = None
            for article in articles:
                source = _source_for_article(sources, article)
                if source is None:
                    totals["skipped_unmapped"] += 1
                    continue
                publish_time = int(article.get("publish_time") or 0)
                batch_cursor = max(batch_cursor, publish_time)
                if not article.get("content_fetched"):
                    totals["pending_content"] += 1
                    earliest_pending = publish_time if earliest_pending is None else min(earliest_pending, publish_time)
                    continue

                path = _article_path(source, article)
                path.parent.mkdir(parents=True, exist_ok=True)
                markdown = _request_text(base_url, f"/api/feed/article/{article['id']}.md")
                changed = not path.exists() or path.read_text(encoding="utf-8") != markdown
                if changed:
                    path.write_text(markdown, encoding="utf-8")
                    totals["downloaded"] += 1
                if ingest:
                    totals["ingested_chunks"] += _ingest(path, source.ticker)

            next_since = int(payload.get("next_since") or batch_cursor)
            if earliest_pending is not None:
                # Do not permanently skip an article whose body is still being fetched.
                next_since = min(next_since, max(0, earliest_pending - 1))
            # Equal timestamps can cause a cursor loop; advance only after the full batch.
            if next_since <= cursor:
                break
            cursor = next_since
            cursors[configured_source.fakeid] = cursor
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

            if earliest_pending is not None or len(articles) < limit:
                break

    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync wechat-download-api articles into IRA")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--limit", type=int, default=100, choices=range(1, 201), metavar="1..200")
    parser.add_argument("--no-ingest", action="store_true", help="Download Markdown without LanceDB ingestion")
    parser.add_argument("--reset-cursor", action="store_true", help="Rescan all locally cached articles")
    args = parser.parse_args()

    sources = _load_sources(args.config)
    if not sources:
        raise SystemExit(f"No enabled sources in {args.config}")
    if args.reset_cursor and args.state.exists():
        args.state.unlink()

    health = _request_json(args.base_url, "/api/health")
    print(f"[wechat-sync] health={health}")
    result = sync(
        base_url=args.base_url,
        sources=sources,
        state_path=args.state,
        ingest=not args.no_ingest,
        limit=args.limit,
    )
    print("[wechat-sync] " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
