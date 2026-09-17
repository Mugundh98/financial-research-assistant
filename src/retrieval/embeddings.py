"""Text embeddings for vector search.

Default backend is **LSA** (TF-IDF -> Truncated SVD): fully offline, deterministic,
no model downloads, and dependency-light. It yields dense, L2-normalized vectors
so cosine similarity is a dot product.

To upgrade to true semantic embeddings, install ``sentence-transformers`` and
swap :func:`get_embedder` to return a SentenceTransformer-backed embedder with
the same ``fit`` / ``encode`` interface.
"""
from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer


class LSAEmbedder:
    name = "lsa-tfidf-svd"

    def __init__(self, n_components: int = 128, ngram_range: tuple[int, int] = (1, 2), min_df: int = 1):
        self.vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=ngram_range, min_df=min_df, max_features=50000
        )
        self.svd: TruncatedSVD | None = None
        self.n_components = n_components
        self.dim = n_components

    def fit(self, texts: list[str]) -> "LSAEmbedder":
        matrix = self.vectorizer.fit_transform(texts)
        n_comp = max(2, min(self.n_components, matrix.shape[1] - 1, matrix.shape[0] - 1))
        self.svd = TruncatedSVD(n_components=n_comp, random_state=42)
        self.svd.fit(matrix)
        self.dim = n_comp
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.svd is None:
            raise RuntimeError("LSAEmbedder must be fitted before encoding")
        reduced = self.svd.transform(self.vectorizer.transform(texts)).astype(np.float32)
        norms = np.linalg.norm(reduced, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return reduced / norms


def get_embedder() -> LSAEmbedder:
    """Factory for the default embedder (swap here to upgrade backends)."""
    return LSAEmbedder()
