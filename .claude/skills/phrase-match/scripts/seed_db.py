#!/usr/bin/env python3
"""Build the SQLite index from data/idioms.json.

The JSON file is the human-edited source of truth; the SQLite file is a
derived index for fast lookup once the database outgrows a linear scan
(it is git-ignored and safe to delete/rebuild at any time).

Usage:
  seed_db.py [--data path/to/idioms.json] [--db path/to/idioms.sqlite]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DB_RELPATH, find_repo_root, load_data, normalize

SCHEMA = """
DROP TABLE IF EXISTS analogs;
DROP TABLE IF EXISTS readings;
DROP TABLE IF EXISTS phrases;

CREATE TABLE phrases (
    id         TEXT PRIMARY KEY,
    phrase     TEXT NOT NULL,
    lang       TEXT NOT NULL,
    normalized TEXT NOT NULL,   -- normalized/lemmatized form for matching
    aliases    TEXT NOT NULL    -- JSON array of normalized alias forms
);

CREATE TABLE readings (
    phrase_id    TEXT NOT NULL REFERENCES phrases(id),
    reading_id   TEXT NOT NULL,
    gloss_ru     TEXT NOT NULL,
    gloss_en     TEXT NOT NULL,
    register     TEXT,
    context_cues TEXT NOT NULL,  -- JSON array
    sources      TEXT NOT NULL,  -- JSON array of {url, note, verified}
    PRIMARY KEY (phrase_id, reading_id)
);

CREATE TABLE analogs (
    phrase_id  TEXT NOT NULL,
    reading_id TEXT NOT NULL,
    lang       TEXT NOT NULL,
    text       TEXT NOT NULL,
    type       TEXT,
    register   TEXT,
    pragmatics TEXT,
    sources    TEXT NOT NULL,   -- JSON array of {url, note, verified}
    FOREIGN KEY (phrase_id, reading_id) REFERENCES readings(phrase_id, reading_id)
);

CREATE INDEX idx_analogs_lang ON analogs(lang);
"""


def build(data: dict, db_path: Path) -> tuple[int, int, int]:
    """(Re)create the SQLite index; returns (phrases, readings, analogs) counts."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    with connection:
        connection.executescript(SCHEMA)
        n_read = n_ana = 0
        for phrase in data["phrases"]:
            connection.execute(
                "INSERT INTO phrases VALUES (?, ?, ?, ?, ?)",
                (
                    phrase["id"],
                    phrase["phrase"],
                    phrase["lang"],
                    normalize(phrase["phrase"]),
                    json.dumps(
                        [normalize(a) for a in phrase.get("aliases", [])], ensure_ascii=False
                    ),
                ),
            )
            for reading in phrase["readings"]:
                connection.execute(
                    "INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        phrase["id"],
                        reading["id"],
                        reading["gloss_ru"],
                        reading["gloss_en"],
                        reading.get("register"),
                        json.dumps(reading.get("context_cues", []), ensure_ascii=False),
                        json.dumps(reading.get("sources", []), ensure_ascii=False),
                    ),
                )
                n_read += 1
                for analog in reading["analogs"]:
                    connection.execute(
                        "INSERT INTO analogs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            phrase["id"],
                            reading["id"],
                            analog["lang"],
                            analog["text"],
                            analog.get("type"),
                            analog.get("register"),
                            analog.get("pragmatics"),
                            json.dumps(analog.get("sources", []), ensure_ascii=False),
                        ),
                    )
                    n_ana += 1
    connection.close()
    return len(data["phrases"]), n_read, n_ana


def main() -> int:
    """Parse CLI arguments and rebuild the SQLite index."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=None, help="path to idioms.json")
    parser.add_argument("--db", type=Path, default=None, help="path to output sqlite file")
    args = parser.parse_args()

    data = load_data(args.data)
    db_path = args.db or (find_repo_root() / DB_RELPATH)
    n_phrases, n_readings, n_analogs = build(data, db_path)
    print(f"Built {db_path}: {n_phrases} phrases, {n_readings} readings, {n_analogs} analogs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
