# Cross-Lingual Phrase-Analog Finder — Design & Prompting Guide

*Prepared 2026-07-14. All links below returned HTTP 200 on this date.*

## 0. Agent or Skill? → **Skill**

| Criterion | Your project | Favors |
|---|---|---|
| Invocation | User-triggered, on demand (`/phrase-match ...`) | Skill |
| Workflow shape | Fixed, repeatable pipeline (lookup → disambiguate → cite) | Skill |
| Local Python scripts | Skills bundle a `scripts/` dir; Claude runs them without loading their code into context | Skill |
| Token cost | Skill metadata costs ~dozens of tokens until invoked (progressive disclosure); a subagent starts cold and re-derives context every spawn | Skill |
| Interactivity | Results stay in the main conversation, so you can follow up ("and in this other context?") | Skill |

A **subagent** pays off only when a task is long-running and would pollute the main context (e.g., a 50-URL web-verification sweep). If that happens later, keep the skill as the entry point and let it optionally spawn a subagent — the two compose ([Skills docs](https://code.claude.com/docs/en/skills), [Subagents docs](https://code.claude.com/docs/en/sub-agents), [comparison article](https://dev.to/nunc/claude-code-skills-vs-subagents-when-to-use-what-4d12)).

## 1. What makes a good prompt (from the receiving LLM's point of view)

What an LLM actually needs, in priority order:

1. **Role** — one line: *"You are a Russian–German–English phraseologist."* Activates the right register/domain distribution.
2. **Purpose / motivation** — *why* the answer matters (e.g., "the user writes literary translations; register fidelity matters more than literal meaning"). Claude 4+ models measurably follow instructions better when given the motivation behind them ([Anthropic Claude 4 best practices](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)).
3. **Delimited inputs** — never mix data into prose. Use XML tags (Anthropic's documented preference):
   ```xml
   <phrase>Не гони лошадей</phrase>
   <context>Коллега торопит с решением по сделке.</context>
   <source_lang>ru</source_lang><target_lang>de</target_lang>
   ```
4. **Explicit task decomposition** — enumerate the steps: (a) list *all* readings of the phrase, (b) state which reading the context selects and *why*, (c) rank target-language analogs by register + frequency, (d) attach only script-verified references. Without step (a), models default to the most frequent reading and skip disambiguation.
5. **Output contract** — the exact structure of the expected answer. This constrains generation more effectively than any "be accurate" plea.
6. **One contrastive few-shot example** — the *same* phrase with *two different contexts* yielding *different* analogs. This is the single highest-value example type for your goal, because it demonstrates the context→reading mapping you care about.
7. **Escape hatch** — "If no idiomatic equivalent exists, say so and give a register-matched paraphrase; never invent a citation." Explicit permission to abstain is the cheapest hallucination defense there is.
8. **Grounding rule** — "Cite only URLs that `verify_refs.py` returned as live." LLMs fabricate plausible URLs; verification must live outside the model.

Also: keep the stable parts (role, rules, examples) *first* and the variable parts (phrase, context) *last* — this maximizes prompt-cache hits and cuts per-query cost.

## 2. Prompt format: Markdown vs YAML vs JSON

**Short answer: Markdown prose + XML-tagged input fields for the prompt; JSON only for machine-parsed *output*; YAML only for skill frontmatter/config.**

Evidence and reasoning:

- The main empirical study, ["Does Prompt Formatting Have Any Impact on LLM Performance?" (arXiv:2411.10541)](https://arxiv.org/abs/2411.10541), found performance swings up to **40%** between formats on smaller models, that **larger models are far more robust**, and that **there is no universally optimal format** — so consistency and structure matter more than the format religion.
- For Claude specifically, Anthropic documents Markdown headers + XML tags as the recommended structure ([prompt engineering docs](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)).
- **JSON is the most expensive wrapper for your data**: quotes, braces, and escaping add ~15–20% tokens, and — critical for Russian — `json.dumps(..., ensure_ascii=True)` (the Python default) turns each Cyrillic character into `\uXXXX`, a ~6× blowup. If a script passes JSON to Claude, always use `ensure_ascii=False`.
- **Where JSON wins**: the *response* your scripts must parse. Use a strict output schema (or Claude's structured outputs) so `lookup.py`/downstream code never regex-parses prose.

## 3. Model differences (Claude Code: Sonnet, Opus, Fable)

Current models (mid-2026): Sonnet 5, Opus 4.8, Fable 5. All have 1M-token context and the same five effort levels.

| | **Sonnet 5** (`claude-sonnet-5`) | **Opus 4.8** (`claude-opus-4-8`) | **Fable 5** (`claude-fable-5`) |
|---|---|---|---|
| Price in/out per MTok | $3 / $15 (intro $2 / $10 through 2026-08-31) | $5 / $25 | $10 / $50 |
| Thinking | Configurable | Configurable (adaptive) | **Always on** — cannot be disabled |
| Instruction-following | Most literal; follows output contracts exactly | Deliberate; conservative about triggering tools — say explicitly *when* to run each script | Literal, best long-horizon consistency |
| Style relevant to this task | Agentic by default; happily runs scripts | Warmest, most nuanced prose — best at explaining register/stylistic differences between analogs | Most capable reasoning; longest coherent multi-step turns |
| Token quirk | New tokenizer ⇒ ~30% more tokens for the same text | — | — |
| **Fit for phrase-match** | **Default choice.** Lookup + disambiguation is language knowledge, not deep reasoning; cheapest per query | Upgrade when the *explanation quality* (register, connotation, cultural nuance) is the product | Overkill for routine queries; useful for hard cases: no-equivalent phrases needing creative, register-faithful paraphrase |

Practical consequence for the skill: write script-trigger conditions explicitly ("Run `lookup.py` **before** answering; never answer from memory alone") — Sonnet and Fable will do this anyway, Opus needs it stated.

## 4. Effort levels

All three models share the same ladder: `low` → `medium` → `high` → `xhigh` → `max`. Your "Extra High" = `xhigh`, "Maximal" = `max` — the names are identical across Sonnet 5, Opus 4.8, and Fable 5, so no per-model translation is needed.

| Level | What changes | For phrase-match |
|---|---|---|
| `high` (API default) | Balanced thinking depth | Enough for a clean dictionary hit + single-reading context |
| `xhigh` (Claude Code default) | Substantially deeper deliberation, more tokens | Right level for **ambiguous phrases / competing readings** — exactly your differentiation-by-context step |
| `max` | Maximum deliberation, highest cost | Rarely pays off here; reserve for no-equivalent creative paraphrase or contested etymology |

Effort scales *thinking* depth (and cost), not knowledge — a wrong dictionary fact stays wrong at `max`. That's another argument for grounding answers in local data + verified URLs rather than buying more thinking.

## 5. Token-saving architecture (the actual design)

```
.claude/skills/phrase-match/
├── SKILL.md            # role, rules, output contract, 1 contrastive example
└── scripts/
    ├── lookup.py       # SQLite idiom DB; pymorphy3 lemmatization + rapidfuzz fuzzy match
    ├── verify_refs.py  # HTTP-checks every candidate URL; only 200s may be cited
    └── seed_db.py      # one-time: build DB from Wiktionary dumps / open datasets
```

Division of labor — **scripts retrieve, the model judges**:

1. `lookup.py` normalizes the Russian phrase (lemmatize, strip particles), fuzzy-matches against the local DB, and prints a compact candidate table (phrase, reading, per-language analogs, source URL). Zero model tokens spent on search.
2. Claude receives *only* that table + the user's context, picks the reading the context selects, ranks analogs, and explains the context effect.
3. `verify_refs.py` checks each URL Claude wants to cite; dead links are dropped before the answer is shown.

Typical query cost: a few hundred tokens instead of a multi-thousand-token web-search session.

**Data sources for `seed_db.py` and for citations:**

- [Russian Wiktionary](https://ru.wiktionary.org/) — proverb entries with glosses and translation tables; e.g. [без труда не выловишь и рыбку из пруда](https://ru.wiktionary.org/wiki/%D0%B1%D0%B5%D0%B7_%D1%82%D1%80%D1%83%D0%B4%D0%B0_%D0%BD%D0%B5_%D0%B2%D1%8B%D0%BB%D0%BE%D0%B2%D0%B8%D1%88%D1%8C_%D0%B8_%D1%80%D1%8B%D0%B1%D0%BA%D1%83_%D0%B8%D0%B7_%D0%BF%D1%80%D1%83%D0%B4%D0%B0) glosses the meaning and lists EN "no pain, no gain" / "no sweet without sweat" (the DE analog „Ohne Fleiß kein Preis" is verified separately via [its de.wiktionary entry](https://de.wiktionary.org/wiki/ohne_Flei%C3%9F_kein_Preis)). CC-licensed, dumpable → ideal DB seed *and* citable reference. Caveat learned while seeding: many proverb entries have empty translation/meaning sections — every claim must be checked against actual page content, not assumed.
- [Академик — dic.academic.ru](https://dic.academic.ru/) — Russian phraseological dictionaries online; good citation target for readings/definitions.
- [dict.cc](https://www.dict.cc/) and [Reverso Context](https://context.reverso.net/translation/german-russian/) — DE↔RU/EN idiom pairs with usage examples (cite; check ToS before bulk scraping).
- [OPUS parallel corpora](https://opus.nlpl.eu/) — free aligned RU/DE/EN corpora for authentic usage examples.
- [MAGPIE corpus (GitHub)](https://github.com/hslh/magpie-corpus) — 56k idiom-in-context instances (EN); [IdiomsResearch link collection](https://github.com/maafiah/IdiomsResearch) — curated index of idiom datasets across languages.
- [Master Russian idiom list](https://masterrussian.com/idioms/russian_idioms.htm) — ~500 RU idioms with EN equivalents.

## 6. What the research says about LLMs and idioms (why the design is this way)

- LLMs show a **systematic bias toward literal translation** of idioms; anchoring on a gloss/meaning representation fixes much of it — [G-IdiomAlign benchmark (arXiv:2606.18989)](https://arxiv.org/abs/2606.18989). → Your DB should store a *meaning gloss* per reading, not just phrase pairs.
- Even GPT-4-class models err on ~28% of idiom translations, and automatic metrics correlate poorly with human judgment — [IdiomEval (arXiv:2508.10421)](https://arxiv.org/abs/2508.10421). → Don't trust raw model output; ground it in the DB + citations.
- Giving the model a **knowledge-base of idiom meanings** before translating measurably improves results — [IdiomKB (arXiv:2308.13961)](https://arxiv.org/abs/2308.13961) and [Semantic Idiom Alignment (arXiv:2407.03518)](https://arxiv.org/abs/2407.03518). → This is exactly the `lookup.py`-first architecture.
- Overview of available idiom datasets: [survey (arXiv:2508.11828)](https://arxiv.org/abs/2508.11828).

## 7. Test cases

| Phrase | Context A → expected behavior | Context B → expected behavior |
|---|---|---|
| Не гони лошадей | Someone rushes a decision → idiomatic analog ("hold your horses" register) | Literal horse-driving scene → literal translation, note the idiom trap |
| От работы кони дохнут | Ironic excuse for laziness → humorous analog, matching irony | Serious warning about overwork → different, non-jocular rendering |
| Без труда не выловишь и рыбку из пруда | Neutral proverb use → dictionary-verified equivalents (see Wiktionary link above) | — |

## 8. From repo to lightweight service (decided 2026-07-14)

### 8.1 Collaborator usability — verified

The pushed repo is directly usable: it is publicly clonable
(`git clone https://github.com/max402/phrase-match.git`), the scripts run on
stdlib-only Python ≥ 3.10 (`pip install` is optional), and a fresh checkout
answers a query with exit 0. One friction point was fixed: the lookup script
was buried under `.claude/skills/…/scripts/`, so a top-level wrapper
`phrase_match.py` now forwards all arguments to it —
`python3 phrase_match.py --phrase "…" --target de` works from the repo root.
Open decision (not blocking): the repo has **no LICENSE file**, so outside
collaborators formally have no usage rights — pick one before advertising the
service ([choosealicense.com](https://choosealicense.com/)).

### 8.2 Saved-result format → JSON records that mirror the prompt anatomy

Applied to the three test phrases: see [`results/`](../results/) —
one file per phrase (`ne-goni-loshadej.json`, `ot-raboty-koni-dohnut.json`,
`bez-truda-ne-vylovish.json`).

**Decision: one UTF-8 JSON file per phrase, top-level fields
`prompt_components` + `analyses[]` + `verification`.** Why JSON and not
Markdown/YAML here:

- **It already is the service.** JSON is the interchange format of the web
  ([RFC 8259](https://datatracker.ietf.org/doc/html/rfc8259), media type
  `application/json`); every HTTP client parses it natively. A static
  `results/` directory served by any web server — or free via
  [GitHub Pages](https://pages.github.com/) — is a working read-only API with
  zero server code. That is the cheapest possible version of "a lightweight
  service available for everybody".
- **It preserves the whole prompt anatomy.** Each record carries a
  `prompt_components` block with all 8 elements of §1 (role, purpose, inputs,
  task decomposition, output contract, contrastive example, escape hatch,
  grounding rule), so any record can be replayed as a prompt or audited
  against the contract. The `analyses[]` array *is* the contrastive example:
  the same phrase stored under different contexts with different renderings
  (for single-reading phrases the slot is explicitly reserved).
- **It is machine-checkable.** A `schema_version` field today, a formal
  [JSON Schema](https://json-schema.org/) when the service goes live —
  Markdown has no comparable validation path, and YAML adds parsing
  ambiguity without adding capability.
- **No contradiction with §2.** §2 chose Markdown+XML for the *prompt the
  model reads*; this section chooses JSON for *stored/served results* — the
  two live on different layers, and §2's Cyrillic rule still applies: all
  files are written with `ensure_ascii=False` (no `\uXXXX` escapes).
- **Honest grounding is part of the schema.** Every analog's `sources` list
  contains only URLs that `verify_refs.py` saw return HTTP 200 (re-checked
  for the shipped records on 2026-07-14, 8/8 alive); paraphrases carry
  `sources: []` plus `escape_hatch_used: true` with a reason — the record
  cannot silently pass an unverified claim off as a cited one.

When the public site exists, human-readable pages are rendered *from* these
JSON records, never maintained in parallel — one source of truth per layer
(`data/idioms.json` for knowledge, `results/*.json` for answers).
