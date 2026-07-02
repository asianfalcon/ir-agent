"""
Embedding helper — wraps sentence-transformers paraphrase-multilingual model.
Cached as a module-level singleton so the model loads once per process.
"""

from pathlib import Path
from functools import lru_cache

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # 420MB, 384-dim, good Chinese support


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Return list of 384-dim float vectors."""
    vecs = _model().encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
