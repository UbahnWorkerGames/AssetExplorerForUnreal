from __future__ import annotations

from functools import lru_cache
import os
from typing import List

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_THREADS = int(os.getenv("EMBED_THREADS", "0") or "0")
_EMBED_PARALLEL = int(os.getenv("EMBED_PARALLEL", "0") or "0")
_EMBED_INFER_BATCH = int(os.getenv("EMBED_INFER_BATCH", "1024") or "1024")


@lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    threads = _EMBED_THREADS if _EMBED_THREADS > 0 else None
    return TextEmbedding(model_name=MODEL_NAME, threads=threads)


def _normalize_vector(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def embed_text(text: str) -> List[float]:
    vectors = embed_texts([text])
    return vectors[0] if vectors else []


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_model()
    batch_size = max(1, min(_EMBED_INFER_BATCH, len(texts)))
    parallel = _EMBED_PARALLEL if _EMBED_PARALLEL > 0 else None
    vectors = list(model.embed(texts, batch_size=batch_size, parallel=parallel))
    out: List[List[float]] = []
    for vec in vectors:
        arr = np.array(vec, dtype=float)
        arr = _normalize_vector(arr)
        out.append(arr.tolist())
    return out


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
