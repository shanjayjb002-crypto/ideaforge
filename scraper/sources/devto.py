"""Dev.to source: articles tagged with project-idea-ish tags.

The Dev.to public API needs no auth for reading published articles.
Each article becomes one raw idea; positive reactions become the engagement
signal for ranking.
"""
from __future__ import annotations

import time

import requests

from ..schema import raw_idea

ARTICLES_URL = "https://dev.to/api/articles"
DEFAULT_TAGS = ["beginners", "projectideas", "showdev", "100daysofcode", "tutorial"]
PER_PAGE = 80


def fetch(tags: list[str] | None = None) -> list[dict]:
    """Fetch articles for each tag and normalize to raw ideas.

    Per-tag failures are isolated so one failing tag can't break the source.
    """
    tags = tags or DEFAULT_TAGS
    out: list[dict] = []

    for tag in tags:
        try:
            resp = requests.get(
                ARTICLES_URL,
                headers={"User-Agent": "IdeaForge-scraper", "Accept": "application/json"},
                params={"tag": tag, "per_page": PER_PAGE, "top": 365},
                timeout=20,
            )
            resp.raise_for_status()
            articles = resp.json()
        except Exception as exc:  # noqa: BLE001 - isolate per-tag failures
            print(f"  [devto] tag '{tag}' failed: {exc}")
            continue

        for art in articles:
            title = art.get("title") or ""
            if not title:
                continue
            out.append(
                raw_idea(
                    title=title,
                    description=art.get("description") or "",
                    source="devto",
                    url=art.get("url", ""),
                    tags=art.get("tag_list", []),
                    raw_difficulty_guess=None,
                    engagement=art.get("positive_reactions_count", 0),
                    created=(art.get("published_at") or "")[:10] or None,
                )
            )
        time.sleep(0.5)

    print(f"  [devto] collected {len(out)} raw ideas from {len(tags)} tags")
    return out
