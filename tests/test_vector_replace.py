from ira.storage import vector_store


def _chunk(chunk_id, text="text", source="source.md"):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": source,
        "ticker": "AMD.US",
        "pub_date": "2026-08-04",
        "period": "2026Q2",
        "data_source": "company_filing",
    }


def test_replace_source_keeps_new_and_removes_only_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "LANCE_PATH", tmp_path / "lance")
    monkeypatch.setattr(
        "ira.storage.embedder.embed", lambda texts: [[float(i), 0.0] for i, _ in enumerate(texts)]
    )

    vector_store.replace_source_chunks("source.md", [_chunk("old-a"), _chunk("old-b")])
    vector_store.replace_source_chunks("source.md", [_chunk("old-a", "updated"), _chunk("new-c")])

    table = vector_store._get_table()
    rows = table.search().where("source_file = 'source.md'").select(["chunk_id", "text"]).to_list()
    assert {row["chunk_id"] for row in rows} == {"old-a", "new-c"}
    assert next(row["text"] for row in rows if row["chunk_id"] == "old-a") == "updated"


def test_embedding_failure_does_not_touch_old_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "LANCE_PATH", tmp_path / "lance")
    monkeypatch.setattr("ira.storage.embedder.embed", lambda texts: [[0.0, 0.0] for _ in texts])
    vector_store.replace_source_chunks("source.md", [_chunk("old")])

    def fail(_texts):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr("ira.storage.embedder.embed", fail)
    try:
        vector_store.replace_source_chunks("source.md", [_chunk("new")])
        assert False, "replacement should fail"
    except RuntimeError:
        pass

    rows = (
        vector_store._get_table().search().where("source_file = 'source.md'").select(["chunk_id"]).to_list()
    )
    assert [row["chunk_id"] for row in rows] == ["old"]
