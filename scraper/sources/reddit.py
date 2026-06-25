"""Reddit source via public JSON endpoints — DISABLED BY DEFAULT.

Reddit exposes read-only JSON at https://www.reddit.com/r/<sub>/top.json, but in
practice it now blocks unauthenticated / datacenter traffic with HTTP 403 (verified
locally and certain to fail on GitHub Actions IPs). To use this reliably you need
OAuth credentials (which is the app-registration step the project deferred).

The module is kept as a working reference and is NOT wired into pipeline.run_fetch.
To enable it: obtain Reddit OAuth creds, add bearer-token auth to the request
below, then add ("reddit", reddit.fetch) back to the sources list in pipeline.py.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from ..schema import raw_idea

# Subreddits that are explicitly about project/app ideas.
DEFAULT_SUBS = ["SomebodyMakeThis", "AppIdeas", "SideProject", "Lightbulb"]
LIMIT = 50
TIMEFRAME = "year"  # top posts of the past year


def _epoch_to_date(ts) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()


def fetch(subs: list[str] | None = None) -> list[dict]:
    """Pull top posts from idea subreddits and normalize to raw ideas."""
    subs = subs or DEFAULT_SUBS
    out: list[dict] = []

    for sub in subs:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                headers={"User-Agent": "IdeaForge-scraper/1.0 (project idea aggregator)"},
                params={"t": TIMEFRAME, "limit": LIMIT},
                timeout=20,
            )
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
        except Exception as exc:  # noqa: BLE001 - isolate per-sub failures
            print(f"  [reddit] r/{sub} failed: {exc}")
            continue

        for child in children:
            post = child.get("data", {})
            title = (post.get("title") or "").strip()
            if not title or post.get("stickied"):
                continue
            tags = [sub.lower()]
            if post.get("link_flair_text"):
                tags.append(post["link_flair_text"].lower())
            out.append(
                raw_idea(
                    title=title,
                    description=(post.get("selftext") or "")[:400],
                    source="reddit",
                    url="https://www.reddit.com" + post.get("permalink", ""),
                    tags=tags,
                    engagement=post.get("score", 0),
                    created=_epoch_to_date(post.get("created_utc")),
                )
            )
        time.sleep(1)  # be gentle with unauthenticated Reddit

    print(f"  [reddit] collected {len(out)} raw ideas from {len(subs)} subreddits")
    return out
