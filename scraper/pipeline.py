"""IdeaForge pipeline orchestrator.

Runs: fetch -> embed -> dedupe -> classify -> rank -> write.

During development each stage can be run on its own and its output inspected,
because intermediates are cached under ``data/_intermediate/``:

    py -m scraper.pipeline --only fetch       # run just fetch, dump raw ideas
    py -m scraper.pipeline --from dedupe       # resume from a cached stage
    py -m scraper.pipeline                     # full run -> data/ideas.json

The intermediate cache is dev-only scaffolding; CI runs the full pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import classify as classify_stage
from . import dedupe as dedupe_stage
from . import embed as embed_stage
from . import rank as rank_stage
from .sources import devto, github, hackernews
# reddit is implemented (scraper/sources/reddit.py) but disabled by default:
# Reddit blocks unauthenticated/datacenter traffic (403), so it needs OAuth to be
# reliable. Add it back to the sources list below once OAuth credentials exist.

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
INTERMEDIATE = DATA_DIR / "_intermediate"

STAGES = ["fetch", "embed", "dedupe", "classify", "rank", "write"]


# --------------------------------------------------------------------------- #
# stage 1: fetch
# --------------------------------------------------------------------------- #
def run_fetch() -> list[dict]:
    """Pull from every source and return a flat list of normalized raw ideas.

    Each source is isolated: if one raises, we log and keep the others.
    """
    ideas: list[dict] = []

    sources = [
        ("github", github.fetch),
        ("devto", devto.fetch),
        ("hackernews", hackernews.fetch),
    ]
    for name, fn in sources:
        try:
            ideas.extend(fn())
        except Exception as exc:  # noqa: BLE001 - one source must not sink the run
            print(f"  [{name}] source failed entirely: {exc}", file=sys.stderr)

    print(f"fetch: {len(ideas)} raw ideas total")
    return ideas


# --------------------------------------------------------------------------- #
# stage 2: embed
# --------------------------------------------------------------------------- #
def run_embed(ideas: list[dict]) -> list[dict]:
    return embed_stage.run_embed(ideas)


# --------------------------------------------------------------------------- #
# stage 3: dedupe
# --------------------------------------------------------------------------- #
def run_dedupe(ideas: list[dict]) -> list[dict]:
    return dedupe_stage.run_dedupe(ideas)


# --------------------------------------------------------------------------- #
# stage 4: classify
# --------------------------------------------------------------------------- #
def run_classify(ideas: list[dict]) -> list[dict]:
    return classify_stage.run_classify(ideas)


# --------------------------------------------------------------------------- #
# stage 5: rank
# --------------------------------------------------------------------------- #
def run_rank(ideas: list[dict]) -> list[dict]:
    return rank_stage.run_rank(ideas)


# --------------------------------------------------------------------------- #
# stage 6: write
# --------------------------------------------------------------------------- #
# The clean public fields exposed in data/ideas.json (internal/working fields dropped).
_PUBLIC_FIELDS = [
    "id", "title", "description", "difficulty", "tags", "domain",
    "sources", "score", "first_seen", "last_seen",
]


def run_write(ideas: list[dict]) -> dict:
    """Project ideas to the public schema and write data/ideas.json."""
    clean = [{k: idea.get(k) for k in _PUBLIC_FIELDS} for idea in ideas]
    payload = {
        "generated_at": date.today().isoformat(),
        "count": len(clean),
        "ideas": clean,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "ideas.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [write] wrote {len(clean)} ideas -> {out.relative_to(ROOT)}")
    return payload


# --------------------------------------------------------------------------- #
# intermediate cache helpers (dev convenience)
# --------------------------------------------------------------------------- #
def _dump(stage: str, payload) -> None:
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    path = INTERMEDIATE / f"{stage}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  cached -> {path.relative_to(ROOT)}")


def _load(stage: str):
    path = INTERMEDIATE / f"{stage}.json"
    if not path.exists():
        raise SystemExit(f"no cached output for stage '{stage}' at {path}; run it first")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# stage dispatch
# --------------------------------------------------------------------------- #
# Each stage: (function, needs_previous_stage_output_or_None).
_IMPLEMENTED = {
    "fetch": (lambda _prev: run_fetch(), None),
    "embed": (lambda prev: run_embed(prev), "fetch"),
    "dedupe": (lambda prev: run_dedupe(prev), "embed"),
    "classify": (lambda prev: run_classify(prev), "dedupe"),
    "rank": (lambda prev: run_rank(prev), "classify"),
    "write": (lambda prev: run_write(prev), "rank"),
}


def run_all() -> dict:
    """Full end-to-end run, entirely in memory (no intermediate cache)."""
    ideas = run_fetch()
    ideas = run_embed(ideas)
    ideas = run_dedupe(ideas)
    ideas = run_classify(ideas)
    ideas = run_rank(ideas)
    return run_write(ideas)


def _run_stage(stage: str):
    fn, prev = _IMPLEMENTED[stage]
    data = _load(prev) if prev else None
    result = fn(data)
    _dump(stage, result)
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="IdeaForge pipeline")
    p.add_argument("--only", choices=STAGES, help="run a single stage (uses cached predecessor)")
    args = p.parse_args(argv)

    if args.only:
        if args.only not in _IMPLEMENTED:
            raise SystemExit(f"stage '{args.only}' not wired up yet")
        _run_stage(args.only)
        return

    run_all()


if __name__ == "__main__":
    main()
