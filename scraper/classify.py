"""Classify stage: rule-based difficulty + tag normalization + domain inference.

Deliberately lightweight and dependency-free (pure heuristics) so it's cheap to
run in CI and easy to unit-test with fixtures. Three jobs:

1. normalize_tags  - collapse synonyms ("webapp"/"web app"/"website" -> "web")
2. infer_domain    - pick a single primary domain from the normalized tags/text
3. classify_difficulty - beginner / intermediate / advanced from keywords + source hints

It also drops obvious non-ideas (opinion/career posts that sneak in via the
Dev.to "beginners" tag) using a conservative positive-signal filter.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# tag normalization
# --------------------------------------------------------------------------- #
# canonical_tag -> set of synonyms (all matched case-insensitively, non-alnum stripped)
_TAG_SYNONYMS: dict[str, set[str]] = {
    "web": {"web", "webapp", "web app", "website", "websites", "webdev", "webdevelopment",
            "web development", "frontend", "front end", "fullstack", "full stack",
            "html", "css", "javascript", "js", "react", "vue", "angular", "nextjs",
            "node", "nodejs", "tailwind"},
    "mobile": {"mobile", "android", "ios", "flutter", "reactnative", "react native",
               "mobileapp", "mobile app", "mobiledev"},
    "cli": {"cli", "commandline", "command line", "terminal", "shell", "bash", "clitool"},
    "ml": {"ml", "ai", "machinelearning", "machine learning", "deeplearning",
           "deep learning", "neuralnetwork", "neural network", "nlp",
           "artificialintelligence", "artificial intelligence", "computervision",
           "computer vision", "llm", "genai"},
    "data": {"data", "datascience", "data science", "dataanalysis", "data analysis",
             "dataviz", "datavisualization", "data visualization", "etl", "analytics",
             "bigdata", "big data", "pandas"},
    "game": {"game", "games", "gamedev", "game dev", "gamedevelopment",
             "game development", "gaming", "unity", "godot", "pygame"},
    "devops": {"devops", "docker", "kubernetes", "k8s", "cicd", "ci cd"},
    "api": {"api", "rest", "restapi", "rest api", "graphql", "backend", "back end"},
    "bot": {"bot", "bots", "chatbot", "discordbot", "discord bot", "telegrambot",
            "telegram bot"},
    "automation": {"automation", "automate", "scripting"},
}

# Build reverse lookup: synonym -> canonical
_SYNONYM_TO_CANON: dict[str, str] = {}
for canon, syns in _TAG_SYNONYMS.items():
    for s in syns:
        _SYNONYM_TO_CANON[re.sub(r"[^a-z0-9]", "", s)] = canon


def normalize_tags(tags: list[str]) -> list[str]:
    """Map known synonyms to canonical tags; keep unknown tags as-is. De-duplicated."""
    out: list[str] = []
    for t in tags:
        key = re.sub(r"[^a-z0-9]", "", (t or "").lower())
        if not key:
            continue
        canon = _SYNONYM_TO_CANON.get(key, (t or "").strip().lower())
        if canon not in out:
            out.append(canon)
    return out


# --------------------------------------------------------------------------- #
# domain inference
# --------------------------------------------------------------------------- #
# Higher-priority domains win when an idea spans several (e.g. "ml web app" -> ml).
_DOMAIN_PRIORITY = ["ml", "data", "game", "mobile", "bot", "devops", "cli", "api", "web"]


def infer_domain(normalized_tags: list[str], text: str = "") -> str:
    """Pick a single primary domain from normalized tags, falling back to text."""
    tagset = set(normalized_tags)
    for d in _DOMAIN_PRIORITY:
        if d in tagset:
            return d
    # Fall back to scanning text for a canonical keyword. Use word boundaries so
    # we don't match "unity" inside "community" or "go" inside "google".
    low = text.lower()
    for d in _DOMAIN_PRIORITY:
        for syn in _TAG_SYNONYMS[d]:
            if re.search(rf"\b{re.escape(syn)}\b", low):
                return d
    return "other"


# --------------------------------------------------------------------------- #
# difficulty
# --------------------------------------------------------------------------- #
_BEGINNER_KW = {"beginner", "beginners", "easy", "simple", "intro", "introduction",
                "first", "starter", "basic", "basics", "101", "newbie", "helloworld",
                "mini", "tiny", "gettingstarted", "learn", "tutorial"}
_ADVANCED_KW = {"advanced", "production", "productionready", "scalable", "distributed",
                "enterprise", "microservice", "microservices", "lowlevel", "compiler",
                "kernel", "operatingsystem", "realtime", "highperformance", "concurrent",
                "expert", "architecture"}


def _kw_hits(text: str, vocab: set[str]) -> int:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return len(tokens & vocab)


def classify_difficulty(idea: dict) -> str:
    """beginner / intermediate / advanced from keyword counts + source hint."""
    text = " ".join([idea.get("title", ""), idea.get("description", ""),
                     " ".join(idea.get("tags", []))])
    beg = _kw_hits(text, _BEGINNER_KW)
    adv = _kw_hits(text, _ADVANCED_KW)

    # A source-provided hint (e.g. github "beginner-projects" topic) is a strong nudge.
    hint = idea.get("raw_difficulty_guess")
    if hint == "beginner":
        beg += 2
    elif hint == "advanced":
        adv += 2

    if adv > beg:
        return "advanced"
    if beg > adv:
        return "beginner"
    return "intermediate"


# --------------------------------------------------------------------------- #
# relevance filter (conservative)
# --------------------------------------------------------------------------- #
_IDEA_SIGNALS = re.compile(
    r"\b(build|built|building|create|created|make|made|clone|implement|app|application|"
    r"project|projects|tool|tools|api|game|tracker|generator|bot|system|website|"
    r"dashboard|scraper|engine|cli|library|simulator|editor|visualizer|extension|"
    r"plugin|ideas?)\b",
    re.IGNORECASE,
)
# Tags/subreddits that are inherently idea sources -> always keep.
_IDEA_TAGS = {"projectideas", "showdev", "project-ideas", "somebodymakethis",
              "appideas", "lightbulb", "sideproject"}


def looks_like_idea(idea: dict) -> bool:
    """Keep GitHub items (curated idea repos) and any item with a project signal.

    Conservative on purpose: only drops items with no project-y signal at all,
    which in practice are the opinion/career posts riding the 'beginners' tag.
    """
    if idea.get("source") == "github":
        return True
    raw_tags = {re.sub(r"[^a-z0-9]", "", t.lower()) for t in idea.get("tags", [])}
    if raw_tags & _IDEA_TAGS:
        return True
    text = f"{idea.get('title', '')} {idea.get('description', '')}"
    return bool(_IDEA_SIGNALS.search(text))


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def classify_one(idea: dict) -> dict:
    """Attach difficulty, normalized tags and domain to a single idea."""
    norm = normalize_tags(idea.get("tags", []))
    text = f"{idea.get('title', '')} {idea.get('description', '')}"
    idea["tags"] = norm
    idea["domain"] = infer_domain(norm, text)
    idea["difficulty"] = classify_difficulty(idea)
    return idea


def run_classify(ideas: list[dict]) -> list[dict]:
    kept = [i for i in ideas if looks_like_idea(i)]
    dropped = len(ideas) - len(kept)
    for idea in kept:
        classify_one(idea)

    # Quick distribution print so we can sanity-check the heuristics by eye.
    from collections import Counter
    diff = Counter(i["difficulty"] for i in kept)
    dom = Counter(i["domain"] for i in kept)
    print(f"  [classify] kept {len(kept)} ideas, dropped {dropped} non-ideas")
    print(f"  [classify] difficulty: {dict(diff)}")
    print(f"  [classify] domain:     {dict(dom)}")
    return kept
