# phrase-match

Multilingual application that matches idioms by their core meaning.

Given a **phrase**, its **context**, and a **target language**, it returns
idiomatic analogs with the context effect explained and every claim backed by
a **verified open-internet source**. First direction: Russian → German /
English; reverse direction and more pairs are planned.

Implemented as a [Claude Code skill](https://code.claude.com/docs/en/skills)
with a token-saving division of labor: **local Python scripts retrieve, the
model judges**. Retrieval, fuzzy matching, and citation checking cost zero
LLM tokens; the model only decides which reading the context selects and
explains the trade-offs between analogs.

## Repository layout

```
phrase-match/
├── README.md                        ← this file: overview, layout, quickstart, principles
├── requirements.txt                 — optional deps (rapidfuzz, pymorphy3); scripts run on stdlib alone
├── .gitignore                       — excludes the derived SQLite index, __pycache__, local settings
│
├── data/
│   ├── idioms.json                  — SOURCE OF TRUTH: phrases → readings (glosses, context
│   │                                  cues) → analogs per language, each with verified source URLs
│   └── idioms.sqlite                — derived index, git-ignored; rebuilt by scripts/seed_db.py
│
├── .claude/
│   ├── settings.json                — shared Claude Code permissions for this repo
│   └── skills/
│       └── phrase-match/
│           ├── SKILL.md             — the skill prompt: role, lookup-first pipeline, reading
│           │                          selection rules, output contract, contrastive example
│           └── scripts/
│               ├── common.py        — shared helpers: repo-root discovery, data loading,
│               │                      RU normalization/lemmatization, fuzzy similarity
│               ├── lookup.py        — phrase → readings + analogs, fuzzy-matched locally
│               │                      (zero LLM tokens); exit 2 when nothing matches
│               ├── verify_refs.py   — HTTP-checks URLs (args or --from-data); only URLs
│               │                      reported OK may ever be cited
│               └── seed_db.py       — rebuilds data/idioms.sqlite from data/idioms.json
│
└── Info/
    └── phrase-match-design-and-prompting.md
                                     — design rationale: agent-vs-skill decision, prompt
                                       anatomy, format comparison, Claude model/effort
                                       guidance, research references (all links verified)
```

## Quickstart

Pure-stdlib (Python ≥ 3.10) — optional extras in `requirements.txt` improve
matching quality:

```bash
cd .claude/skills/phrase-match/scripts

# look up a phrase (fuzzy: inflected forms and variants match too)
python3 lookup.py --phrase "Не гони лошадей!" --target de \
    --context "Коллега торопит с решением по сделке"

# verify every source URL in the database
python3 verify_refs.py --from-data

# rebuild the derived SQLite index after editing data/idioms.json
python3 seed_db.py
```

In Claude Code, the skill triggers automatically on requests like
*"Find a German analog of «От работы кони дохнут» — a colleague jokingly
tells me to take a break"*, or explicitly via `/phrase-match`.

## Data model

Each phrase in `data/idioms.json` has one or more **readings** (meaning
variants selected by context), each with:

- `gloss_ru` / `gloss_en` — the meaning, stored explicitly (research shows
  gloss-anchoring is what prevents LLMs' literal-translation bias),
- `context_cues` — words that hint which reading a context selects,
- `analogs` per target language with register, pragmatics, and `sources`
  (URLs that must pass `verify_refs.py` before being committed).

Analogs without sources are allowed only as explicitly-flagged paraphrases.

## Principles

1. **Never answer from model memory alone** — lookup first, web + verification second.
2. **Context decides the reading** — the same phrase gets different analogs in different contexts.
3. **A citation is a URL that a script saw return HTTP 200**, not one the model recalls.
4. **JSON leaving Python always uses `ensure_ascii=False`** — escaped Cyrillic wastes ~6× tokens.

Design rationale, model/effort recommendations, and the research references
live in [Info/phrase-match-design-and-prompting.md](Info/phrase-match-design-and-prompting.md).
