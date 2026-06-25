"""Rank stage: score each idea by recency + source diversity + engagement.

All three components are normalized to roughly [0, 1] and combined with fixed
weights, so the final ``score`` is comparable across ideas and stable run-to-run.

  recency    - exponential decay on days since last_seen (newer scores higher)
  diversity  - more distinct source platforms == more independent validation
  engagement - log-scaled total stars/reactions, normalized against the corpus max

Engagement is log-scaled because GitHub stars (thousands) and Dev.to reactions
(tens) live on very different scales; log1p keeps a 5000-star repo from dwarfing
everything else.
"""
from __future__ import annotations

import math
from datetime import date

# component weights (sum to 1.0). Engagement leads: stars/reactions are the
# strongest validation signal. Recency is a milder freshness nudge so that
# evergreen, highly-starred idea lists aren't buried just for being a few years old.
W_RECENCY = 0.25
W_DIVERSITY = 0.25
W_ENGAGEMENT = 0.50

# Long half-life: a 1-year-old project-idea list is still perfectly useful.
RECENCY_HALF_LIFE_DAYS = 365
MAX_PLATFORMS = 4  # github + devto + hackernews + reddit


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _recency_score(idea: dict, today: date) -> float:
    d = _parse_date(idea.get("last_seen", "")) or today
    age = max((today - d).days, 0)
    return 0.5 ** (age / RECENCY_HALF_LIFE_DAYS)


def _diversity_score(idea: dict) -> float:
    platforms = {s.get("platform") for s in idea.get("sources", []) if s.get("platform")}
    if MAX_PLATFORMS <= 1:
        return 1.0
    return min(len(platforms), MAX_PLATFORMS) / MAX_PLATFORMS


def _total_engagement(idea: dict) -> int:
    return sum(int(s.get("engagement_score", 0)) for s in idea.get("sources", []))


def run_rank(ideas: list[dict], today: date | None = None) -> list[dict]:
    """Compute and attach a ``score`` to each idea, then sort high-to-low."""
    if not ideas:
        return []
    today = today or date.today()

    # Corpus-wide normalizer for engagement (log scale).
    max_eng_log = max((math.log1p(_total_engagement(i)) for i in ideas), default=0.0)

    for idea in ideas:
        rec = _recency_score(idea, today)
        div = _diversity_score(idea)
        eng = (math.log1p(_total_engagement(idea)) / max_eng_log) if max_eng_log else 0.0
        score = W_RECENCY * rec + W_DIVERSITY * div + W_ENGAGEMENT * eng
        idea["score"] = round(score, 4)
        idea["_score_parts"] = {  # kept for debugging; dropped at write stage
            "recency": round(rec, 3),
            "diversity": round(div, 3),
            "engagement": round(eng, 3),
        }

    ideas.sort(key=lambda i: i["score"], reverse=True)
    top = ideas[0]
    print(f"  [rank] scored {len(ideas)} ideas; top score {top['score']} "
          f"-> {top['title'][:50]!r}")
    return ideas
