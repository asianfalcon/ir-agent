"""
LanceDB vector store — upserts text chunks and runs hybrid (vector + metadata) search.
Auto-builds IVF-PQ index when row count crosses 10,000.
"""

from pathlib import Path
from typing import Any

import lancedb
import numpy as np

ROOT = Path(__file__).parent.parent.parent
LANCE_PATH = ROOT / "data" / "storage" / "lancedb_root"
TABLE_NAME = "chunks"
IVF_PQ_THRESHOLD = 10_000


def _get_table():
    db = lancedb.connect(str(LANCE_PATH))
    if TABLE_NAME in db.table_names():
        return db.open_table(TABLE_NAME)
    return None


def upsert_chunks(chunks: list[dict]) -> None:
    """Embed and write chunks into LanceDB."""
    from src.db.embedder import embed
    if not chunks:
        return
    texts = [c["text"] for c in chunks]
    embeddings = embed(texts)

    db = lancedb.connect(str(LANCE_PATH))
    rows = []
    for chunk, vec in zip(chunks, embeddings):
        # support both flat chunks and legacy nested-metadata chunks
        meta = chunk.get("metadata", chunk)
        rows.append({
            "chunk_id":       chunk["chunk_id"],
            "text":           chunk["text"],
            "vector":         vec,
            "ticker":         meta.get("ticker", ""),
            "pub_date":       str(meta.get("pub_date", "")),
            "period":         meta.get("period", ""),
            "data_source":    meta.get("data_source", ""),
            "source_file":    meta.get("source_file", ""),
            "associated_vars": ",".join(meta.get("associated_vars", [])),
        })

    if TABLE_NAME in db.table_names():
        tbl = db.open_table(TABLE_NAME)
        chunk_ids = [r["chunk_id"] for r in rows]
        if chunk_ids:
            quoted = ",".join("'" + cid.replace("'", "''") + "'" for cid in chunk_ids)
            tbl.delete(f"chunk_id IN ({quoted})")
        tbl.add(rows)
    else:
        tbl = db.create_table(TABLE_NAME, data=rows)

    # ponytail: only build index after threshold — lancedb brute-forces below it fine
    if tbl.count_rows() >= IVF_PQ_THRESHOLD:
        _maybe_build_index(tbl)


def _maybe_build_index(tbl) -> None:
    try:
        tbl.create_index(
            num_partitions=256,
            num_sub_vectors=96,
            replace=True,
        )
        print("[vector_store] IVF-PQ index built")
    except Exception as e:
        print(f"[vector_store] index build skipped: {e}")


def search(
    query: str,
    ticker: str | None = None,
    period: str | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    tbl = _get_table()
    if tbl is None:
        return []

    from src.db.embedder import embed_one
    query_vec = embed_one(query)

    q = tbl.search(query_vec).limit(top_k)
    if ticker:
        q = q.where(f"ticker = '{ticker}'")
    if period:
        q = q.where(f"period = '{period}'")

    return q.to_list()
