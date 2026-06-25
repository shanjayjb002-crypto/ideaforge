"""Dedupe stage: semantically cluster near-duplicate ideas and merge them.

Ideas are embedded (stage 2); here we treat two ideas as the "same idea" when
their cosine similarity is above a threshold (default 0.85). Because embeddings
are L2-normalized, cosine similarity is just the dot product.

Clustering is greedy single-linkage (union-find): if A~B and B~C, all three end
up in one cluster. For ~hundreds of ideas the O(n^2) similarity matrix is fine.

The merge keeps the best-written representative and preserves every source link
+ engagement signal, so the rank stage can reward cross-source validation.
"""
from __future__ import annotations

import numpy as np

DEFAULT_THRESHOLD = 0.85


# --------------------------------------------------------------------------- #
# clustering
# --------------------------------------------------------------------------- #
def _embeddings_matrix(ideas: list[dict]) -> np.ndarray:
    return np.asarray([i["embedding"] for i in ideas], dtype=np.float32)


def cluster_indices(embeddings: np.ndarray, threshold: float) -> list[list[int]]:
    """Single-linkage clustering via union-find. Returns lists of row indices."""
    n = len(embeddings)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    sim = embeddings @ embeddings.T  # cosine because normalized
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #
def _seen_date(idea: dict) -> str:
    """Best available date for an idea: source's created date, else collected date."""
    return idea.get("created") or idea.get("date_collected") or ""


def _representative(members: list[dict]) -> dict:
    """Pick the best-written member: longest description, tiebreak by engagement."""
    return max(
        members,
        key=lambda m: (len((m.get("description") or "").strip()), m.get("engagement", 0)),
    )


def merge_cluster(members: list[dict]) -> dict:
    """Collapse a cluster of duplicate ideas into one canonical idea."""
    rep = _representative(members)

    # Union of tags, order-preserving + de-duplicated.
    tags: list[str] = []
    for m in members:
        for t in m.get("tags", []):
            if t not in tags:
                tags.append(t)

    # One source entry per member (dedupe identical urls).
    sources: list[dict] = []
    seen_urls = set()
    for m in members:
        url = m.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(
            {
                "platform": m.get("source", ""),
                "url": url,
                "engagement_score": int(m.get("engagement", 0)),
            }
        )

    dates = [d for d in (_seen_date(m) for m in members) if d]
    # First non-null difficulty hint from any member.
    diff_hint = next((m.get("raw_difficulty_guess") for m in members
                      if m.get("raw_difficulty_guess")), None)

    return {
        "id": rep["id"],
        "title": rep["title"],
        "description": rep.get("description", ""),
        "tags": tags,
        "raw_difficulty_guess": diff_hint,
        "sources": sources,
        "source_platforms": sorted({s["platform"] for s in sources}),
        "first_seen": min(dates) if dates else "",
        "last_seen": max(dates) if dates else "",
    }


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def _print_cluster_examples(clusters: list[list[int]], ideas: list[dict],
                            embeddings: np.ndarray, limit: int = 12) -> None:
    """Print multi-member clusters so the threshold can be tuned by eye."""
    multi = [c for c in clusters if len(c) > 1]
    multi.sort(key=len, reverse=True)
    print(f"\n  [dedupe] {len(multi)} multi-idea clusters (showing up to {limit}):")
    for c in multi[:limit]:
        sims = [embeddings[a] @ embeddings[b] for k, a in enumerate(c) for b in c[k + 1:]]
        lo, hi = (min(sims), max(sims)) if sims else (1.0, 1.0)
        print(f"    cluster of {len(c)}  (pairwise cos {lo:.3f}-{hi:.3f}):")
        for idx in c:
            it = ideas[idx]
            print(f"        [{it['source']:6}] {it['title'][:70]}")
    print()


def run_dedupe(ideas: list[dict], threshold: float = DEFAULT_THRESHOLD,
               verbose: bool = True) -> list[dict]:
    """Cluster + merge. Returns canonical ideas (embeddings stripped)."""
    if not ideas:
        return []

    embeddings = _embeddings_matrix(ideas)
    clusters = cluster_indices(embeddings, threshold)

    if verbose:
        _print_cluster_examples(clusters, ideas, embeddings)

    merged = [merge_cluster([ideas[i] for i in c]) for c in clusters]
    merged.sort(key=lambda m: len(m["sources"]), reverse=True)

    dupes = len(ideas) - len(merged)
    print(f"  [dedupe] {len(ideas)} ideas -> {len(merged)} unique "
          f"(threshold {threshold}, merged {dupes} duplicates)")
    return merged
