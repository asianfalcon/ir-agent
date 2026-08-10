"""
从 data/inputs/expert_minutes/acecamp/export/*.json 读取 AceCamp 专家专栏导出并入库 LanceDB。

用法：
    python -m ira.connectors.acecamp.expert_processor
"""
import json
import re
from pathlib import Path

from ira.settings import get_settings

_SETTINGS = get_settings()
EXPERT_EXPORT_DIR = _SETTINGS.manual_source_root / "expert_minutes" / "acecamp" / "export"
LEGACY_MINUTES_DIR = _SETTINGS.manual_source_root / "minutes"
DATA_SOURCE = "acecamp_expert_column"
HOT_BADGES = {"hot"}
HOT_WEIGHT_BONUS = 0.2


def _normalize_acecamp_ticker(ticker: str | None) -> str:
    """Convert AceCamp tickers like SH.688141 to the local 688141.SH style."""
    if not ticker:
        return ""
    if "." not in ticker:
        return ticker
    prefix, code = ticker.split(".", 1)
    if len(prefix) <= 3 and code:
        return f"{code}.{prefix}"
    return ticker


def _article_tickers(article: dict) -> list[str]:
    tickers = []
    for corp in article.get("corporations", []):
        ticker = _normalize_acecamp_ticker(corp.get("ticker"))
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _article_badges(article: dict) -> list[str]:
    return [str(b) for b in article.get("badges", []) if b]


def _is_hot_article(article: dict) -> bool:
    return bool(HOT_BADGES.intersection(set(_article_badges(article))))


def _source_weight(article: dict) -> float:
    weight = 1.0
    if _is_hot_article(article):
        weight += HOT_WEIGHT_BONUS
    return weight


def strip_html(html: str) -> str:
    """移除 HTML 标签，保留纯文本。"""
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def process_article(json_path: Path, ticker: str = "") -> int:
    """
    读取单个 article_info JSON 并入库。
    返回 chunk 数。
    """
    from datetime import datetime
    import hashlib
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from ira.storage.vector_store import upsert_chunks, delete_by_source_file

    _splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=70)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    article = data.get("data") or data

    article_id = article.get("id")
    if not article_id:
        print(f"[acecamp-expert] {json_path.name}: 无 id 字段，跳过")
        return 0

    source_file = f"acecamp://article/{article_id}"
    delete_by_source_file(source_file)

    if article.get("masked_state") == "all_masked" and article.get("need_to_pay"):
        print(f"[acecamp-expert] {article_id}: 付费墙，跳过")
        return 0

    title = article.get("title") or str(article_id)
    ts = article.get("release_time", 0)
    pub_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
    badges = _article_badges(article)
    is_hot = _is_hot_article(article)
    source_weight = _source_weight(article)

    # 优先用 summary（干净）+ content（完整）组合
    summary = article.get("summary", "").strip()
    content_html = article.get("content", "")
    content = strip_html(content_html) if content_html else ""

    text = f"{summary}\n\n{content}" if summary and content else (summary or content)
    if not text:
        print(f"[acecamp-expert] {article_id} '{title[:30]}': summary 和 content 均为空")
        return 0

    source_id = hashlib.md5(f"acecamp_{article_id}".encode()).hexdigest()
    tickers = [ticker] if ticker else _article_tickers(article) or [""]

    # chunk directly
    raw_chunks = _splitter.split_text(text)
    chunks = []
    for ticker_value in tickers:
        for c in raw_chunks:
            chunks.append({
                "chunk_id": hashlib.md5(f"{source_file}:{ticker_value}:{c}".encode()).hexdigest(),
                "text": c,
                "ticker": ticker_value,
                "pub_date": pub_date,
                "period": "",
                "data_source": DATA_SOURCE,
                "source_id": source_id,
                "source_uri": source_file,
                "source_file": source_file,
                "release_time": int(ts or 0),
                "badges": badges,
                "is_hot": is_hot,
                "source_weight": source_weight,
                "title": title,
                "associated_vars": [title],
            })

    if chunks:
        upsert_chunks(chunks)
    print(f"[acecamp-expert] {article_id} '{title[:30]}': {len(chunks)} chunks")
    return len(chunks)


def _input_dir() -> Path:
    """Prefer the new AceCamp expert export directory, with old minutes path as fallback."""
    if any(EXPERT_EXPORT_DIR.glob("*.json")):
        return EXPERT_EXPORT_DIR
    return LEGACY_MINUTES_DIR


def batch_process(ticker: str = "") -> int:
    """批量处理 data/inputs/expert_minutes/acecamp/export/ 下所有 JSON。"""
    input_dir = _input_dir()
    if not input_dir.exists():
        print(f"[acecamp-expert] 目录不存在: {input_dir}")
        return 0

    files = sorted(input_dir.glob("*.json"))
    if not files:
        print(f"[acecamp-expert] 无 JSON 文件: {input_dir}")
        return 0

    print(f"[acecamp-expert] 从 {input_dir} 找到 {len(files)} 个 JSON 文件")
    total = 0
    for f in files:
        try:
            n = process_article(f, ticker=ticker)
            total += n
        except Exception as e:
            print(f"[acecamp-expert] {f.name} ERROR: {e}")
    return total


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else ""
    n = batch_process(ticker)
    print(f"\n完成：共存入 {n} chunks")
