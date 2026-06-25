"""Hacker News source via the Algolia search API (free, no auth).

We search a few idea-oriented queries (project ideas, "Show HN" launches, etc.).
"Show HN" posts are real projects people built, which make good idea fodder.
Story points become the engagement signal.

Docs: https://hn.algolia.com/api
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import requests

from ..schema import raw_idea

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
# Idea-intent queries. We deliberately avoid a bare "Show HN" query: it surfaces
# big product launches (e.g. "Homebrew 6.0.0") rather than buildable ideas, and
# its boilerplate titles cause false dedupe merges between unrelated projects.
DEFAULT_QUERIES = [
    "project ideas",
    "side project ideas",
    "programming projects for beginners",
    "what should I build",
]
HITS_PER_PAGE = 50
MIN_POINTS = 20  # filtered client-side; the API's numericFilters param 400s here
HN_ITEM = "https://news.ycombinator.com/item?id="

# Strip HN title boilerplate so the idea text drives the embedding, not "Show HN:".
_HN_PREFIX = re.compile(r"^\s*(show|ask|tell|launch)\s+hn:?\s*", re.IGNORECASE)


def _epoch_to_date(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def fetch(queries: list[str] | None = None) -> list[dict]:
    """Search HN for idea-oriented stories and normalize to raw ideas."""
    queries = queries or DEFAULT_QUERIES
    out: list[dict] = []
    seen: set[str] = set()

    for q in queries:
        try:
            resp = requests.get(
                SEARCH_URL,
                headers={"User-Agent": "IdeaForge-scraper"},
                params={
                    "query": q,
                    "tags": "story",
                    "hitsPerPage": HITS_PER_PAGE,
                },
                timeout=20,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as exc:  # noqa: BLE001 - isolate per-query failures
            print(f"  [hackernews] query '{q}' failed: {exc}")
            continue

        for hit in hits:
            obj_id = hit.get("objectID")
            title = _HN_PREFIX.sub("", (hit.get("title") or "").strip()).strip()
            if not title or obj_id in seen:
                continue
            if (hit.get("points") or 0) < MIN_POINTS:  # drop low-signal noise
                continue
            seen.add(obj_id)
            # Prefer the linked project URL; fall back to the HN discussion.
            url = hit.get("url") or (HN_ITEM + obj_id if obj_id else "")
            out.append(
                raw_idea(
                    title=title,
                    description=(hit.get("story_text") or "")[:400],
                    source="hackernews",
                    url=url,
                    tags=hit.get("_tags", []),
                    engagement=hit.get("points", 0),
                    created=_epoch_to_date(hit.get("created_at_i")),
                )
            )
        time.sleep(0.4)

    print(f"  [hackernews] collected {len(out)} raw ideas from {len(queries)} queries")
    return out
