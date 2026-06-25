"""Unit tests for the dedupe stage — fixture embeddings only, no model/network."""
import numpy as np

from scraper.dedupe import cluster_indices, merge_cluster, run_dedupe


def _unit(vec):
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def _idea(title, desc="", source="github", url="", tags=None, engagement=0,
          created="2024-01-01", embedding=None):
    vec = embedding if embedding is not None else _unit([1, 0])
    return {
        "id": title,
        "title": title,
        "description": desc,
        "source": source,
        "url": url or f"https://example.com/{title}",
        "tags": tags or [],
        "engagement": engagement,
        "raw_difficulty_guess": None,
        "created": created,
        "date_collected": "2026-06-25",
        "embedding": np.asarray(vec, dtype=np.float32).tolist(),
    }


# --------------------------------------------------------------------------- #
# clustering
# --------------------------------------------------------------------------- #
def test_identical_vectors_cluster_together():
    emb = np.vstack([_unit([1, 0]), _unit([1, 0]), _unit([0, 1])])
    clusters = cluster_indices(emb, threshold=0.85)
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]  # the two identical vectors merge; the orthogonal one stays


def test_below_threshold_stays_separate():
    # cos(45 deg) ~= 0.707, which is below 0.85 -> no merge.
    emb = np.vstack([_unit([1, 0]), _unit([1, 1])])
    clusters = cluster_indices(emb, threshold=0.85)
    assert len(clusters) == 2


def test_single_linkage_is_transitive():
    # A~B and B~C (each cos ~0.97) but A and C are further apart; single linkage
    # should still place all three in one cluster.
    a, b, c = _unit([1, 0]), _unit([0.95, 0.31]), _unit([0.81, 0.59])
    emb = np.vstack([a, b, c])
    clusters = cluster_indices(emb, threshold=0.90)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == [0, 1, 2]


# --------------------------------------------------------------------------- #
# merging
# --------------------------------------------------------------------------- #
def test_merge_keeps_longest_description():
    members = [
        _idea("URL shortener", desc="short", engagement=5),
        _idea("Build a URL shortener", desc="A much longer, better-written blurb.", engagement=1),
    ]
    merged = merge_cluster(members)
    assert merged["description"] == "A much longer, better-written blurb."
    assert merged["title"] == "Build a URL shortener"


def test_merge_collects_all_sources_and_dates():
    members = [
        _idea("Idea", source="github", url="https://gh/x", engagement=100, created="2022-05-01"),
        _idea("Idea", source="devto", url="https://devto/x", engagement=20, created="2026-01-10"),
    ]
    merged = merge_cluster(members)
    assert {s["platform"] for s in merged["sources"]} == {"github", "devto"}
    assert merged["first_seen"] == "2022-05-01"
    assert merged["last_seen"] == "2026-01-10"
    assert sorted(merged["source_platforms"]) == ["devto", "github"]


def test_merge_dedupes_identical_urls():
    members = [
        _idea("Idea", url="https://same/x", engagement=3),
        _idea("Idea", url="https://same/x", engagement=3),
    ]
    merged = merge_cluster(members)
    assert len(merged["sources"]) == 1


def test_merge_unions_tags_without_duplicates():
    members = [
        _idea("Idea", tags=["web", "api"]),
        _idea("Idea", tags=["api", "cli"]),
    ]
    merged = merge_cluster(members)
    assert merged["tags"] == ["web", "api", "cli"]


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def test_run_dedupe_merges_duplicates():
    ideas = [
        _idea("A", desc="alpha", embedding=_unit([1, 0])),
        _idea("A copy", desc="alpha too", embedding=_unit([1, 0])),
        _idea("B", desc="beta", embedding=_unit([0, 1])),
    ]
    out = run_dedupe(ideas, threshold=0.85, verbose=False)
    assert len(out) == 2
    # No embedding field should leak into the merged output.
    assert all("embedding" not in i for i in out)


def test_run_dedupe_empty_input():
    assert run_dedupe([], verbose=False) == []
