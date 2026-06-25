"""Unit tests for the classify stage heuristics — pure functions, no network."""
from scraper.classify import (
    classify_difficulty,
    infer_domain,
    looks_like_idea,
    normalize_tags,
    run_classify,
)


# --------------------------------------------------------------------------- #
# tag normalization
# --------------------------------------------------------------------------- #
def test_normalize_tags_collapses_web_synonyms():
    assert normalize_tags(["webapp", "web app", "website"]) == ["web"]


def test_normalize_tags_keeps_unknown_tags():
    assert normalize_tags(["python", "webapp", "education"]) == ["python", "web", "education"]


def test_normalize_tags_dedupes():
    assert normalize_tags(["react", "vue", "frontend"]) == ["web"]


# --------------------------------------------------------------------------- #
# domain inference
# --------------------------------------------------------------------------- #
def test_infer_domain_priority_ml_over_web():
    assert infer_domain(["web", "ml"]) == "ml"


def test_infer_domain_from_text_fallback():
    assert infer_domain([], "Build a roguelike game with pygame") == "game"


def test_infer_domain_no_substring_false_positive():
    # Regression: "unity" must not match inside "community".
    assert infer_domain([], "community project ideas catalog") == "other"


def test_infer_domain_defaults_to_other():
    assert infer_domain(["education"], "a curated list of things") == "other"


# --------------------------------------------------------------------------- #
# difficulty
# --------------------------------------------------------------------------- #
def test_difficulty_beginner_from_keywords():
    idea = {"title": "Simple beginner todo app", "description": "easy intro project", "tags": []}
    assert classify_difficulty(idea) == "beginner"


def test_difficulty_advanced_from_keywords():
    idea = {"title": "Build a distributed compiler",
            "description": "production-grade, scalable architecture", "tags": []}
    assert classify_difficulty(idea) == "advanced"


def test_difficulty_intermediate_default():
    idea = {"title": "A todo app", "description": "make a todo list", "tags": []}
    assert classify_difficulty(idea) == "intermediate"


def test_difficulty_source_hint_breaks_tie():
    idea = {"title": "Tracker", "description": "", "tags": [], "raw_difficulty_guess": "beginner"}
    assert classify_difficulty(idea) == "beginner"


# --------------------------------------------------------------------------- #
# relevance filter
# --------------------------------------------------------------------------- #
def test_github_items_always_kept():
    assert looks_like_idea({"source": "github", "title": "anything", "description": "", "tags": []})


def test_devto_with_project_signal_kept():
    assert looks_like_idea({"source": "devto", "title": "Build a weather app",
                            "description": "", "tags": ["beginners"]})


def test_devto_with_projectideas_tag_kept():
    assert looks_like_idea({"source": "devto", "title": "Random musings",
                            "description": "", "tags": ["projectideas"]})


def test_devto_opinion_post_dropped():
    idea = {"source": "devto", "title": "Why I quit my job",
            "description": "a reflective career story", "tags": ["career", "beginners"]}
    assert not looks_like_idea(idea)


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def test_run_classify_filters_and_annotates():
    ideas = [
        {"source": "github", "title": "awesome web app ideas",
         "description": "beginner project list", "tags": ["webapp", "beginner-projects"]},
        {"source": "devto", "title": "My personal blog post",
         "description": "just my thoughts on life", "tags": ["career"]},  # dropped
    ]
    out = run_classify(ideas)
    assert len(out) == 1
    kept = out[0]
    assert kept["domain"] == "web"
    assert kept["difficulty"] == "beginner"
    assert "web" in kept["tags"]
