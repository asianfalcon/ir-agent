"""
从 data/inputs/minutes/*.json 读取 AceCamp 纪要并入库 LanceDB。

用法：
    python -m src.ingestion.acecamp.minutes_processor
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
MINUTES_DIR = ROOT / "data" / "inputs" / "minutes"


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
    from src.db.vector_store import upsert_chunks

    _splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=70)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    article = data.get("data") or data

    article_id = article.get("id")
    if not article_id:
        print(f"[minutes] {json_path.name}: 无 id 字段，跳过")
        return 0

    if article.get("masked_state") == "all_masked" and article.get("need_to_pay"):
        print(f"[minutes] {article_id}: 付费墙，跳过")
        return 0

    title = article.get("title") or str(article_id)
    ts = article.get("release_time", 0)
    pub_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""

    # 优先用 summary（干净）+ content（完整）组合
    summary = article.get("summary", "").strip()
    content_html = article.get("content", "")
    content = strip_html(content_html) if content_html else ""

    text = f"{summary}\n\n{content}" if summary and content else (summary or content)
    if not text:
        print(f"[minutes] {article_id} '{title[:30]}': summary 和 content 均为空")
        return 0

    source_id = hashlib.md5(f"acecamp_{article_id}".encode()).hexdigest()

    # chunk directly
    raw_chunks = _splitter.split_text(text)
    chunks = []
    for c in raw_chunks:
        chunks.append({
            "chunk_id": hashlib.md5(c.encode()).hexdigest(),
            "text": c,
            "ticker": ticker,
            "pub_date": pub_date,
            "period": "",
            "data_source": "broker_report",
            "source_id": source_id,
            "source_uri": f"acecamp://article/{article_id}",
            "source_file": f"acecamp://article/{article_id}",
            "title": title,
            "associated_vars": [title],
        })

    if chunks:
        upsert_chunks(chunks)
    print(f"[minutes] {article_id} '{title[:30]}': {len(chunks)} chunks")
    return len(chunks)


def batch_process(ticker: str = "688141.SH") -> int:
    """批量处理 data/inputs/minutes/ 下所有 JSON。"""
    if not MINUTES_DIR.exists():
        print(f"[minutes] 目录不存在: {MINUTES_DIR}")
        return 0

    files = sorted(MINUTES_DIR.glob("*.json"))
    if not files:
        print(f"[minutes] 无 JSON 文件: {MINUTES_DIR}")
        return 0

    print(f"[minutes] 找到 {len(files)} 个 JSON 文件")
    total = 0
    for f in files:
        try:
            n = process_article(f, ticker=ticker)
            total += n
        except Exception as e:
            print(f"[minutes] {f.name} ERROR: {e}")
    return total


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "688141.SH"
    n = batch_process(ticker)
    print(f"\n完成：共存入 {n} chunks")
