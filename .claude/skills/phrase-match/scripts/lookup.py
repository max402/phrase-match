#!/usr/bin/env python3
"""Look up idiomatic analogs of a Russian phrase in the local database.

This script does all retrieval locally (zero LLM tokens). It prints the
matched phrase with ALL its readings, glosses, context cues, and analogs —
choosing which reading the user's context selects is deliberately left to
the model (or the human) reading the output.

Usage:
  lookup.py --phrase "Не гони лошадей!" [--target de|en|all]
            [--context "..."] [--min-score 70] [--format json|text]
            [--data path/to/idioms.json]

Exit codes: 0 = match found, 2 = no match above --min-score.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump_json, load_data, normalize, similarity


def score_phrases(data: dict[str, Any], query: str) -> list[tuple[float, dict[str, Any]]]:
    """Score every phrase (and its aliases) against the query, best first."""
    normalized_query = normalize(query)
    scored = []
    for phrase in data["phrases"]:
        variants = [phrase["phrase"], *phrase.get("aliases", [])]
        score = max(similarity(normalized_query, normalize(v)) for v in variants)
        scored.append((score, phrase))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def rank_readings(phrase: dict[str, Any], context: str) -> list[dict[str, Any]]:
    """Order readings by naive cue overlap with the context.

    This is only a hint for the model — cue overlap is a cheap heuristic,
    not a semantic judgment. All readings are always returned.
    """
    if not context:
        return phrase["readings"]
    nctx = normalize(context)
    ctx_tokens = set(nctx.split())

    def overlap(reading: dict[str, Any]) -> int:
        cues = {normalize(c) for c in reading.get("context_cues", [])}
        return len(cues & ctx_tokens)

    return sorted(phrase["readings"], key=overlap, reverse=True)


def filter_target(reading: dict[str, Any], target: str) -> dict[str, Any]:
    """Return a copy of the reading with analogs restricted to the target language."""
    if target == "all":
        return reading
    filtered = dict(reading)
    filtered["analogs"] = [a for a in reading["analogs"] if a["lang"] == target]
    return filtered


def render_text(score: float, phrase: dict[str, Any], readings: list[dict[str, Any]]) -> str:
    """Compact, LLM-friendly plain-text rendering."""
    lines = [f"MATCH (score {score:.0f}): «{phrase['phrase']}»  [{phrase['id']}]"]
    for reading in readings:
        lines.append(f"\n  READING [{reading['id']}]  register: {reading.get('register', '—')}")
        lines.append(f"    gloss_ru: {reading['gloss_ru']}")
        lines.append(f"    gloss_en: {reading['gloss_en']}")
        cues = ", ".join(reading.get("context_cues", []))
        lines.append(f"    context cues: {cues or '—'}")
        lines.extend(
            f"    source: {src['url']}  ({src.get('note', '')})"
            for src in reading.get("sources", [])
        )
        for analog in reading["analogs"]:
            lines.append(
                f"    ANALOG [{analog['lang']}] {analog['text']}"
                f"  ({analog.get('type', 'idiom')}; {analog.get('register', '—')})"
            )
            if analog.get("pragmatics"):
                lines.append(f"      pragmatics: {analog['pragmatics']}")
            if analog.get("sources"):
                lines.extend(f"      source: {src['url']}" for src in analog["sources"])
            else:
                lines.append(
                    "      source: NONE — unverified; present as paraphrase, never as cited fact"
                )
    return "\n".join(lines)


def main() -> int:
    """Parse CLI arguments, run the lookup, print the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phrase", required=True, help="phrase to look up (source language: ru)")
    parser.add_argument("--target", default="all", choices=["de", "en", "all"])
    parser.add_argument(
        "--context", default="", help="context sentence; used only to pre-rank readings"
    )
    parser.add_argument("--min-score", type=float, default=70.0)
    parser.add_argument("--format", default="text", choices=["text", "json"])
    parser.add_argument("--data", type=Path, default=None, help="path to idioms.json")
    args = parser.parse_args()

    scored = score_phrases(load_data(args.data), args.phrase)
    score, phrase = scored[0]

    if score < args.min_score:
        closest = "\n".join(f"  {s:5.1f}  «{p['phrase']}»" for s, p in scored[:3])
        print(f"NO MATCH above score {args.min_score:.0f} for: {args.phrase}")
        print(f"Closest candidates:\n{closest}")
        print("If the phrase is missing, add it to data/idioms.json and rerun seed_db.py.")
        return 2

    readings = [filter_target(r, args.target) for r in rank_readings(phrase, args.context)]

    if args.format == "json":
        result = {
            "score": round(score, 1),
            "phrase": phrase["phrase"],
            "id": phrase["id"],
            "readings": readings,
        }
        print(dump_json(result))
    else:
        print(render_text(score, phrase, readings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
