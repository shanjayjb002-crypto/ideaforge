"""Common data schema + normalization helpers shared across the pipeline.

A *raw idea* (output of the fetch stage) is a plain dict with the keys defined
in ``raw_idea``. Keeping it a dict (rather than a dataclass) makes it trivial to
serialize to JSON between stages while we develop.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date


def normalize_title(title: str) -> str:
    """Lowercase, strip noise words/punctuation so near-identical titles collide.

    Used both for the stable id hash and as a cheap pre-filter signal.
    """
    t = title.lower().strip()
    # Drop common filler that doesn't change the idea ("build a", "create an", ...)
    t = re.sub(r"^\s*(build|create|make|a|an|the|how to|project[: ]+)\s+", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)        # punctuation -> space
    t = re.sub(r"\s+", " ", t).strip()
    return t


def idea_id(title: str) -> str:
    """Stable short id derived from the normalized title."""
    return hashlib.sha1(normalize_title(title).encode("utf-8")).hexdigest()[:12]


def raw_idea(
    *,
    title: str,
    description: str,
    source: str,
    url: str,
    tags: list[str] | None = None,
    raw_difficulty_guess: str | None = None,
    engagement: int = 0,
    created: str | None = None,
) -> dict:
    """Build one normalized raw-idea record (the common schema for the fetch stage).

    Parameters mirror the spec's common schema; ``engagement`` is carried through
    so the rank stage can use stars/reactions later.
    """
    title = (title or "").strip()
    description = (description or "").strip()
    return {
        "id": idea_id(title),
        "title": title,
        "description": description,
        "source": source,                 # platform name: "github" | "devto"
        "url": url,
        "tags": [t.strip().lower() for t in (tags or []) if t and t.strip()],
        "raw_difficulty_guess": raw_difficulty_guess,
        "engagement": int(engagement or 0),
        "created": created,               # ISO date string from the source, if any
        "date_collected": date.today().isoformat(),
    }
