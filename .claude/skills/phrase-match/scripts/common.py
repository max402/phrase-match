"""Shared helpers for the phrase-match scripts.

Everything here runs on the Python 3.10+ standard library. Two optional
packages improve quality when installed (see requirements.txt):

- pymorphy3  — proper Russian lemmatization (fallback: light normalization)
- rapidfuzz  — better fuzzy scoring (fallback: difflib)
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DATA_RELPATH = Path("data") / "idioms.json"
DB_RELPATH = Path("data") / "idioms.sqlite"

try:
    import pymorphy3

    _MORPH = pymorphy3.MorphAnalyzer()
except ImportError:
    _MORPH = None

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:
    _fuzz = None

_PUNCT_RE = re.compile(r"[^\w\s-]")


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from `start` (default: this file) until data/idioms.json is found."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / DATA_RELPATH).is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate {DATA_RELPATH} above {here}. "
        "Run from inside the phrase-match repository or pass --data explicitly."
    )


def load_data(path: Path | None = None) -> dict[str, Any]:
    """Load the idiom database from JSON (the source of truth)."""
    data_path = path or (find_repo_root() / DATA_RELPATH)
    return json.loads(data_path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Case-fold, unify ё→е, drop punctuation, collapse whitespace, lemmatize.

    Lemmatization uses pymorphy3 when available so that inflected queries
    («не гоните лошадей») match the dictionary form; without it the light
    normalization alone still supports fuzzy matching.
    """
    text = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    tokens = _PUNCT_RE.sub(" ", text).split()
    if _MORPH is not None:
        tokens = [_MORPH.parse(tok)[0].normal_form for tok in tokens]
    return " ".join(tokens)


def similarity(a: str, b: str) -> float:
    """Fuzzy similarity of two normalized strings on a 0–100 scale."""
    if _fuzz is not None:
        return _fuzz.token_set_ratio(a, b)
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


def dump_json(obj: Any) -> str:
    r"""JSON for terminal/LLM consumption — never escape Cyrillic to \uXXXX."""
    return json.dumps(obj, ensure_ascii=False, indent=2)


def iter_source_urls(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Yield (url, location) for every source URL in the database."""
    for phrase in data["phrases"]:
        for reading in phrase["readings"]:
            where = f"{phrase['id']}/{reading['id']}"
            for src in reading.get("sources", []):
                yield src["url"], where
            for analog in reading.get("analogs", []):
                for src in analog.get("sources", []):
                    yield src["url"], f"{where}/{analog['lang']}:{analog['text'][:30]}"
