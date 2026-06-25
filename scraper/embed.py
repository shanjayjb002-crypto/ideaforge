"""Embed stage: local sentence-transformer embeddings (no API).

Uses ``all-MiniLM-L6-v2`` (384-dim), which runs comfortably on CPU in GitHub
Actions' free tier. The model is loaded lazily so importing this module (e.g. in
tests) doesn't pull in torch until embeddings are actually needed.
"""
from __future__ import annotations

import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # lazy import

        print(f"  [embed] loading model '{MODEL_NAME}' (first run downloads ~80MB)...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _text_for(idea: dict) -> str:
    """The text we embed: title carries most signal, description adds context."""
    return f"{idea.get('title', '')}. {idea.get('description', '')}".strip()


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return L2-normalized embeddings so dot product == cosine similarity."""
    model = _get_model()
    return model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )


def run_embed(ideas: list[dict]) -> list[dict]:
    """Attach an ``embedding`` (list[float]) to each idea, in place, and return them."""
    if not ideas:
        return ideas
    vecs = embed_texts([_text_for(i) for i in ideas])
    for idea, vec in zip(ideas, vecs):
        idea["embedding"] = vec.astype(float).tolist()
    print(f"  [embed] embedded {len(ideas)} ideas -> dim {len(ideas[0]['embedding'])}")
    return ideas
