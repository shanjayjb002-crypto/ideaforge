"""GitHub source: repositories tagged with project-idea topics.

The GitHub REST search API returns *repositories*, not line-item ideas, so in v1
each "idea" is a curated/awesome-list-style repo: its name + description + stars.
Stars become the engagement signal for ranking.

Free tier note: authenticated search allows 30 requests/min, which is plenty.
The token is read from the GH_TOKEN env var (never hardcoded).
"""
from __future__ import annotations

import os
import time

import requests

from ..schema import raw_idea

SEARCH_URL = "https://api.github.com/search/repositories"
DEFAULT_TOPICS = [
    "project-ideas",
    "beginner-projects",
    "hacktoberfest-ideas",
    "app-ideas",
    "project-based-learning",
    "coding-challenges",
]
PER_PAGE = 100  # GitHub search caps per_page at 100; one request per topic.

# Map the topic an idea was found under to a difficulty hint.
_TOPIC_DIFFICULTY = {
    "beginner-projects": "beginner",
    "hacktoberfest-ideas": "beginner",
}


def _headers(token: str | None) -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "IdeaForge-scraper",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch(token: str | None = None, topics: list[str] | None = None) -> list[dict]:
    """Fetch repos for each topic and normalize to raw ideas.

    Returns a flat list of raw-idea dicts. Network/parse errors for a single
    topic are swallowed so one bad topic can't sink the whole source.
    """
    token = token or os.environ.get("GH_TOKEN")
    topics = topics or DEFAULT_TOPICS
    out: list[dict] = []

    for topic in topics:
        try:
            resp = requests.get(
                SEARCH_URL,
                headers=_headers(token),
                params={
                    "q": f"topic:{topic}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": PER_PAGE,
                },
                timeout=20,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:  # noqa: BLE001 - isolate per-topic failures
            print(f"  [github] topic '{topic}' failed: {exc}")
            continue

        for repo in items:
            title = repo.get("name") or repo.get("full_name") or ""
            desc = repo.get("description") or ""
            if not title:
                continue
            out.append(
                raw_idea(
                    title=title.replace("-", " ").replace("_", " ").strip(),
                    description=desc,
                    source="github",
                    url=repo.get("html_url", ""),
                    tags=repo.get("topics", []),
                    raw_difficulty_guess=_TOPIC_DIFFICULTY.get(topic),
                    engagement=repo.get("stargazers_count", 0),
                    created=(repo.get("created_at") or "")[:10] or None,
                )
            )
        time.sleep(1)  # be polite to the search API between topics

    print(f"  [github] collected {len(out)} raw ideas from {len(topics)} topics")
    return out
