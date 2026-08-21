"""Generate a synthetic vault and gold query sets, so the retrieval numbers are reproducible.

`retrieval_eval.py` has always worked, but only against the maintainer's own
vault. The case files are gitignored because they contain real notes, so every
number in BASELINE.md is a claim nobody outside can check or beat. That is the
opposite of what a benchmark is for.

This emits a corpus that is:

- **Deterministic.** Fixed seed, no clock, no randomness that varies by machine.
  Two people running this get byte-identical vaults, so their numbers compare.
  `--manifest` prints a hash to prove it.
- **Synthetic all the way down.** Every name, project and term is composed from
  invented syllables in this file. Nothing is drawn from any real vault.
- **Hard on purpose.** A corpus of 300 unrelated notes is trivially searchable
  and measures nothing. The difficulty here is built in the shape that real
  vaults actually fail on, and that this project's own evaluation kept hitting:
  for every topic there is one short canonical note and several longer
  derivative notes - daily logs, a meeting, a research write-up - that mention
  the topic more often than the canonical note does. Term-frequency ranking
  prefers the derivatives. Getting the canonical note back is the test.
- **Gold-labelled by construction.** The canonical note for each topic is known
  because this file created it, so no hand labelling and no judgement calls.

Three retrieval query sets, because they fail for different reasons and a
single number hides that: exact keyword, English paraphrase that avoids the
title words, and the same paraphrase in Spanish and Russian against English
notes. A fourth set, `behavior`, is for `behavior_eval.py` rather than
`retrieval_eval.py`: it asks fact/decision/relationship/synthesis/
contradiction questions and carries an `answer_key` (the canonical fact text)
so an LLM judge has ground truth without re-reading the vault.

    uv run python scripts/eval/corpus.py --out /tmp/bench-vault
    OBSIDIAN_VAULT_PATH=/tmp/bench-vault uv run python scripts/eval/retrieval_eval.py \\
        --cases /tmp/bench-vault/_cases/paraphrase.jsonl --mode lexical
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

# Every proper noun below is invented. The syllables are deliberately unusual so
# that a term is distinctive enough for a keyword query to be meaningful, and so
# that no entry can collide with a real product, person or company.
TOPICS = [
    {
        "kind": "concept", "title": "Driftlock Windowing",
        "term": "driftlock",
        "en": "the technique for keeping a stream aligned when clocks disagree",
        "es": "la tecnica para mantener alineado un flujo cuando los relojes no coinciden",
        "ru": "метод выравнивания потока когда часы расходятся",
        "body": "Buffers late arrivals against a moving reference instead of a wall clock. "
                "Chosen over fixed windows because replay must produce the same result twice.",
    },
    {
        "kind": "concept", "title": "Quillcast Fanout",
        "term": "quillcast",
        "en": "how one write gets delivered to many downstream readers at once",
        "es": "como una sola escritura llega a muchos lectores a la vez",
        "ru": "как одна запись доставляется многим читателям одновременно",
        "body": "One publish, many independent subscribers, no shared cursor. "
                "The tradeoff is duplicate delivery on retry, which consumers must absorb.",
    },
    {
        "kind": "concept", "title": "Nettlecode Review Gate",
        "term": "nettlecode",
        "en": "the rule about what has to pass before a change can merge",
        "es": "la regla sobre que debe pasar antes de que un cambio se integre",
        "ru": "правило о том что должно пройти перед слиянием изменения",
        "body": "Two approvals plus a green suite, and no exception for the author. "
                "Adopted after a hotfix bypassed review and shipped a regression.",
    },
    {
        "kind": "concept", "title": "Sparrowfold Compaction",
        "term": "sparrowfold",
        "en": "the way old records get collapsed so storage stops growing",
        "es": "la forma en que los registros viejos se colapsan para frenar el crecimiento",
        "ru": "способ сжатия старых записей чтобы хранилище перестало расти",
        "body": "Collapses superseded revisions on read rather than on a schedule. "
                "Keeps write latency flat at the cost of a slower first read.",
    },
    {
        "kind": "project", "title": "Tideglass",
        "term": "tideglass",
        "en": "the effort to replace the reporting pipeline that runs overnight",
        "es": "el esfuerzo para reemplazar la tuberia de informes que corre de noche",
        "ru": "проект по замене ночного конвейера отчетности",
        "body": "Replaces the nightly batch with incremental updates. "
                "Blocked twice on schema ownership, unblocked by moving the contract upstream.",
    },
    {
        "kind": "project", "title": "Marrowfen",
        "term": "marrowfen",
        "en": "the work on making the mobile client usable without a connection",
        "es": "el trabajo para que el cliente movil funcione sin conexion",
        "ru": "работа над тем чтобы мобильный клиент работал без соединения",
        "body": "Offline-first sync with conflict resolution deferred to the user. "
                "Scoped down from automatic merge after three unresolvable test cases.",
    },
    {
        "kind": "project", "title": "Hollowmere",
        "term": "hollowmere",
        "en": "the migration off the vendor that keeps raising prices",
        "es": "la migracion para dejar al proveedor que sigue subiendo precios",
        "ru": "переход от поставщика который постоянно повышает цены",
        "body": "Two-phase cutover with a read-only shadow period. "
                "The shadow period found a data-shape mismatch nobody had documented.",
    },
    {
        "kind": "project", "title": "Ashvault",
        "term": "ashvault",
        "en": "the plan for keeping backups that survive losing the main region",
        "es": "el plan para tener copias que sobrevivan a perder la region principal",
        "ru": "план резервных копий переживающих потерю основного региона",
        "body": "Cross-region snapshots with a restore drill every quarter. "
                "The first drill took eleven hours, which is the number that justified the work.",
    },
    {
        "kind": "person", "title": "Ilva Rennard",
        "term": "rennard",
        "en": "the person who owns the data contracts and keeps saying no to schema drift",
        "es": "la persona que gestiona los contratos de datos y frena los cambios de esquema",
        "ru": "человек отвечающий за контракты данных и не допускающий дрейфа схемы",
        "body": "Owns schema review. Prefers a written contract over a meeting. "
                "Escalate schema questions here before writing code, not after.",
    },
    {
        "kind": "person", "title": "Tobek Marsh",
        "term": "tobek",
        "en": "the person to ask about anything touching the payment provider",
        "es": "la persona a quien preguntar sobre el proveedor de pagos",
        "ru": "человек к которому обращаются по вопросам платежного провайдера",
        "body": "Runs the payments integration. Holds the only sandbox credentials. "
                "Has a standing rule that refunds are never automated.",
    },
    {
        "kind": "person", "title": "Wren Calloway",
        "term": "calloway",
        "en": "the person who runs the incident process and writes the postmortems",
        "es": "la persona que dirige el proceso de incidentes y escribe los postmortems",
        "ru": "человек ведущий процесс инцидентов и пишущий разборы",
        "body": "On-call coordinator. Postmortems are blameless and always written within a week. "
                "Will push back on any timeline that has no timestamps.",
    },
    {
        "kind": "concept", "title": "Gallowsprint Planning",
        "term": "gallowsprint",
        "en": "the short planning cycle used when a deadline is externally fixed",
        "es": "el ciclo corto de planificacion cuando la fecha viene impuesta desde fuera",
        "ru": "короткий цикл планирования когда срок задан извне",
        "body": "One week, scope cut rather than time extended, no carry-over. "
                "Used only when the date genuinely cannot move.",
    },
]

FOLDER = {"concept": "wiki/concepts", "project": "wiki/projects", "person": "wiki/entities"}

# Cross-note synthesis pairs for the behavior eval: a question whose answer
# requires combining two topics' `body` fields, not just retrieving one note.
# Each entry names two TOPICS terms and states the fact that only emerges by
# reading both. `q_alt` is a second phrasing of the same underlying question -
# behavior_cases() emits both as separate rows, which is how this set grows
# without inventing implausible new relationships between the 12 topics.
SYNTHESIS_PAIRS = [
    {
        "a": "tideglass", "b": "rennard",
        "q": "who should be looped in before touching Tideglass's data model, and why",
        "q_alt": "before changing anything in Tideglass's schema, whose review does it need",
        "answer_key": "Tideglass moved its schema contract upstream after being blocked "
                       "twice on schema ownership; Ilva Rennard owns schema review and "
                       "should be asked before writing code, not after.",
    },
    {
        "a": "hollowmere", "b": "tobek",
        "q": "if the Hollowmere migration touches payments, who holds the credentials "
             "and what is their rule about refunds",
        "q_alt": "who would you ask about payments during the Hollowmere cutover, and "
                 "would they automate a refund for you",
        "answer_key": "Hollowmere is a two-phase vendor cutover; Tobek Marsh runs the "
                       "payments integration, holds the only sandbox credentials, and "
                       "has a standing rule that refunds are never automated.",
    },
    {
        "a": "marrowfen", "b": "calloway",
        "q": "if Marrowfen's offline sync causes an incident, who runs that process and "
             "what do they require in the writeup",
        "q_alt": "who coordinates on-call for a Marrowfen sync failure, and what would "
                 "they push back on in the postmortem",
        "answer_key": "Marrowfen is offline-first sync with conflict resolution deferred "
                       "to the user; Wren Calloway is the on-call coordinator, writes "
                       "blameless postmortems within a week, and requires timestamps in "
                       "any incident timeline.",
    },
    {
        "a": "ashvault", "b": "rennard",
        "q": "before scheduling Ashvault's next restore drill, who should confirm the "
             "backup schema hasn't drifted, and why",
        "q_alt": "who owns sign-off on Ashvault's snapshot schema, and what do they "
                 "prefer over a meeting",
        "answer_key": "Ashvault runs cross-region snapshots with a quarterly restore "
                       "drill (the first took eleven hours); Ilva Rennard owns schema "
                       "review and prefers a written contract over a meeting, so she "
                       "should confirm the snapshot schema before a drill, not after.",
    },
    {
        "a": "driftlock", "b": "quillcast",
        "q": "if a Quillcast subscriber falls behind and has to replay past Driftlock's "
             "moving reference, what should it expect to receive twice",
        "q_alt": "what property of Quillcast delivery would a Driftlock-based replay "
                 "need to tolerate",
        "answer_key": "Driftlock buffers late arrivals against a moving reference (not "
                       "the wall clock) specifically so replay produces the same result "
                       "twice; Quillcast's tradeoff is duplicate delivery on retry, which "
                       "consumers must absorb - so a replaying subscriber should expect "
                       "duplicates.",
    },
    {
        "a": "nettlecode", "b": "sparrowfold",
        "q": "would a change to Sparrowfold's compaction logic need the same review as "
             "any other change under Nettlecode",
        "q_alt": "does Nettlecode's review gate make an exception for a change to how "
                  "Sparrowfold collapses old records",
        "answer_key": "Nettlecode requires two approvals plus a green suite with no "
                       "exception for the author, for any change; Sparrowfold's "
                       "compaction (collapsing superseded revisions on read) is not "
                       "exempt, so it would need the same two approvals and green suite.",
    },
    {
        "a": "gallowsprint", "b": "ashvault",
        "q": "if Ashvault's next restore drill lands during a Gallowsprint-planned week, "
             "what constraint from each applies",
        "q_alt": "can a Gallowsprint week be extended to fit in an Ashvault drill",
        "answer_key": "Ashvault's restore drill happens every quarter and the first one "
                       "took eleven hours; Gallowsprint cuts scope rather than extending "
                       "time and is used only when the date cannot move - so a drill "
                       "landing in a gallowsprint week has to be absorbed within scope, "
                       "the sprint itself cannot be extended for it.",
    },
    {
        "a": "tobek", "b": "nettlecode",
        "q": "does a change to the payment integration Tobek Marsh runs skip Nettlecode's "
             "review gate",
        "q_alt": "is there an author exception under Nettlecode for payment changes Tobek "
                 "Marsh makes himself",
        "answer_key": "Nettlecode has no exception for the author of a change - two "
                       "approvals plus a green suite are always required; Tobek Marsh "
                       "runs the payments integration and holds the only sandbox "
                       "credentials, but that does not exempt his changes from the gate.",
    },
    {
        "a": "calloway", "b": "gallowsprint",
        "q": "if an incident lands during a Gallowsprint week, does Wren Calloway's "
             "postmortem timeline requirement still apply",
        "q_alt": "would a fixed Gallowsprint deadline excuse a postmortem from having "
                 "timestamps",
        "answer_key": "Gallowsprint cuts scope rather than extending time when a deadline "
                       "is fixed, but that is about planning, not incident response; Wren "
                       "Calloway will push back on any timeline that has no timestamps "
                       "regardless, and postmortems are still written within a week.",
    },
]

# Contradiction pairs: one derivative note asserts a state, a later derivative
# note asserts the opposite, and only the canonical note (or reading both)
# reconciles them. Keyed by TOPICS term. `q_alt` (present on a few entries)
# is a second phrasing of the same reconciliation question, emitted as a
# second row by behavior_cases().
CONTRADICTIONS = {
    "tideglass": {
        "early": "Tideglass is still blocked on schema ownership with no path forward.",
        "late": "Tideglass is unblocked now that the schema contract moved upstream.",
        "q_alt": "did Tideglass ever get unblocked, or is the schema-ownership problem "
                 "still open",
        "answer_key": "Tideglass was blocked twice on schema ownership and was unblocked "
                       "by moving the contract upstream - both statements are true at "
                       "different times, and the later, reconciling state is unblocked.",
    },
    "hollowmere": {
        "early": "The Hollowmere shadow period found nothing unusual.",
        "late": "The Hollowmere shadow period found a data-shape mismatch nobody had documented.",
        "q_alt": "did the Hollowmere shadow period turn up any problems or not",
        "answer_key": "The Hollowmere shadow period did find a problem: an undocumented "
                       "data-shape mismatch. An earlier report that it found nothing is "
                       "superseded by this finding.",
    },
    "marrowfen": {
        "early": "Marrowfen will resolve sync conflicts automatically.",
        "late": "Marrowfen scoped down from automatic merge after three unresolvable test cases.",
        "q_alt": "does Marrowfen resolve sync conflicts automatically or does the user "
                 "have to",
        "answer_key": "Marrowfen does not resolve conflicts automatically - that plan was "
                       "scoped down after three unresolvable test cases, and conflict "
                       "resolution is now deferred to the user.",
    },
    "driftlock": {
        "early": "Driftlock uses a fixed window measured against the wall clock.",
        "late": "Driftlock buffers late arrivals against a moving reference instead of "
                "a wall clock.",
        "answer_key": "Driftlock does not use a fixed window or the wall clock - it "
                       "buffers late arrivals against a moving reference, chosen "
                       "specifically so replay produces the same result twice; an "
                       "earlier wall-clock/fixed-window description is wrong.",
    },
    "quillcast": {
        "early": "Quillcast delivery is exactly-once, with no duplicates.",
        "late": "Quillcast can duplicate delivery on retry, which consumers must absorb.",
        "answer_key": "Quillcast is not exactly-once - duplicate delivery on retry is a "
                       "known tradeoff consumers must absorb; an earlier claim of "
                       "exactly-once delivery is wrong.",
    },
    "nettlecode": {
        "early": "Nettlecode lets the author of a change self-approve in an emergency.",
        "late": "Nettlecode requires two approvals and a green suite with no exception "
                "for the author.",
        "answer_key": "Nettlecode has no author exception, ever - two approvals plus a "
                       "green suite are required always, adopted after a hotfix bypassed "
                       "review and shipped a regression; an earlier claim of an "
                       "emergency self-approval exception is wrong.",
    },
    "sparrowfold": {
        "early": "Sparrowfold compacts old records on a fixed nightly schedule.",
        "late": "Sparrowfold collapses superseded revisions on read rather than on a "
                "schedule.",
        "answer_key": "Sparrowfold compaction happens on read, not on a nightly schedule "
                       "- that keeps write latency flat at the cost of a slower first "
                       "read; an earlier claim of scheduled compaction is wrong.",
    },
    "gallowsprint": {
        "early": "A Gallowsprint cycle can be extended if the deadline needs more time.",
        "late": "Gallowsprint cuts scope rather than extending time, and is used only "
                "when the date genuinely cannot move.",
        "answer_key": "Gallowsprint never extends time - scope is cut instead, with no "
                       "carry-over, and it is used only when the date truly cannot move; "
                       "an earlier claim that its cycles can be extended is wrong.",
    },
    "ashvault": {
        "early": "Ashvault's first restore drill went smoothly with no surprises.",
        "late": "Ashvault's first drill took eleven hours, which is the number that "
                "justified the work.",
        "answer_key": "Ashvault's first restore drill was not smooth - it took eleven "
                       "hours, and that duration is exactly what justified the project; "
                       "an earlier report of a smooth drill is wrong.",
    },
    "rennard": {
        "early": "Ilva Rennard prefers a quick meeting over a written contract for "
                 "schema questions.",
        "late": "Ilva Rennard prefers a written contract over a meeting, and should be "
                "escalated to before writing code, not after.",
        "answer_key": "Ilva Rennard's preference is the opposite of the early claim - "
                       "she prefers a written contract over a meeting, and schema "
                       "questions should go to her before code is written, not after.",
    },
    "tobek": {
        "early": "Tobek Marsh has automated the refund process for the payment provider.",
        "late": "Tobek Marsh's standing rule is that refunds are never automated.",
        "answer_key": "Refunds are never automated under Tobek Marsh's standing rule - "
                       "an earlier claim that automation exists is wrong; he also holds "
                       "the only sandbox credentials for the payments integration.",
    },
    "calloway": {
        "early": "Wren Calloway allows postmortems to skip timestamps when the timeline "
                 "is informal.",
        "late": "Wren Calloway will push back on any timeline that has no timestamps.",
        "answer_key": "Wren Calloway does not allow timestamp-free timelines - she pushes "
                       "back on any timeline missing them, and postmortems are blameless "
                       "and written within a week regardless.",
    },
}

# Filler vocabulary, also invented, used to pad the corpus to a realistic size so
# that ranking has something to rank against.
FILLER_NOUNS = ["cadence", "rollout", "handoff", "budget", "roadmap", "retro", "onboarding",
                "runbook", "dashboard", "alerting", "staffing", "vendor", "latency", "backlog"]
FILLER_ADJ = ["quarterly", "regional", "internal", "draft", "revised", "interim", "annual"]


def _fm(note_type: str, date: str, tags: list[str]) -> str:
    tag_block = "\n".join(f"  - {t}" for t in tags)
    return (f"---\ntype: {note_type}\ndate: {date}\ntags:\n{tag_block}\n"
            f"ai-first: true\nsynthetic: true\n---\n\n")


def _dates(rng: random.Random, n: int) -> list[str]:
    return [f"2026-{m:02d}-{d:02d}"
            for m, d in ((rng.randint(1, 6), rng.randint(1, 28)) for _ in range(n))]


def build(total_notes: int, seed: int) -> dict[str, str]:
    """Return {vault-relative path: contents}. Pure; writes nothing."""
    rng = random.Random(seed)
    files: dict[str, str] = {}

    for t in TOPICS:
        # The canonical note, and the gold answer.
        #
        # It deliberately does NOT contain the `en` gloss. The first version of
        # this wrote "<title> is <en>." into the preamble, which put the exact
        # text of every paraphrase query inside its own answer: the paraphrase
        # set scored 83% on pure lexical search, which looked like a strong
        # result and was really the benchmark reading its own answer key. The
        # note describes the topic in the vocabulary of `body`; the query
        # describes it in the vocabulary of `en`; the two do not share wording,
        # which is what makes a paraphrase set a paraphrase set.
        rel = f"{FOLDER[t['kind']]}/{t['title']}.md"
        files[rel] = (
            _fm(t["kind"], "2026-02-01", [t["kind"], t["term"]])
            + f"## For future agent\nCanonical note for {t['title']}.\n\n"
            f"## What it is\n{t['body']}\n"
        )

        # Derivatives. Each mentions the term more often than the canonical note
        # does, which is exactly the shape that makes term-frequency ranking pick
        # the wrong note. A benchmark where the right answer is also the most
        # term-dense one would be measuring nothing.
        contradiction = CONTRADICTIONS.get(t["term"])
        for i, day in enumerate(_dates(rng, 2)):
            lines = [
                f"- Spent the morning on {t['term']}; {t['term']} still blocked on review. "
                f"Follow up on {t['term']} tomorrow. See [[{t['title']}]]."
                for _ in range(4 + i)
            ]
            # First derivative asserts the early (superseded) state, second
            # asserts the later (reconciling) one - the contradiction the
            # behavior eval's synthesis/reconciliation cases grade against.
            if contradiction:
                lines.append(f"- {contradiction['early' if i == 0 else 'late']}")
            files[f"wiki/daily/{day}-{t['term']}.md"] = (
                _fm("daily", day, ["daily"])
                + f"## For future agent\nDaily log for {day}.\n\n"
                + "\n".join(lines) + "\n"
            )
        m_day = _dates(rng, 1)[0]
        files[f"wiki/meetings/{m_day} - {t['title']} sync.md"] = (
            _fm("meeting", m_day, ["meeting"])
            + f"## For future agent\nSync about {t['term']}.\n\n"
            + f"Discussed {t['term']} at length. Actions on {t['term']} assigned. "
              f"Next {t['term']} checkpoint set. Ref [[{t['title']}]].\n" * 3
        )
        files[f"Research/{t['term']}-landscape-review.md"] = (
            _fm("source", "2026-03-15", ["research"])
            + f"## For future agent\nExternal review of {t['term']}.\n\n"
            + f"A survey of how others approach {t['term']}. {t['term']} appears in most "
              f"comparable systems. Our {t['term']} differs in scope. See [[{t['title']}]].\n" * 4
        )

    # Filler, so the corpus is a realistic size and every query has competition.
    i = 0
    while len(files) < total_notes:
        adj, noun = rng.choice(FILLER_ADJ), rng.choice(FILLER_NOUNS)
        day = _dates(rng, 1)[0]
        rel = f"wiki/notes/{adj}-{noun}-{i:03d}.md"
        files[rel] = (
            _fm("note", day, ["note", noun])
            + f"## For future agent\nNotes on the {adj} {noun}.\n\n"
            + " ".join(rng.choice(FILLER_NOUNS) for _ in range(60)) + "\n"
        )
        i += 1
    return files


def cases() -> dict[str, list[dict]]:
    """Gold sets. The answer is known because build() created it."""
    out: dict[str, list[dict]] = {"keyword": [], "paraphrase": [], "multilingual": []}
    for t in TOPICS:
        gold = [f"{FOLDER[t['kind']]}/{t['title']}.md"]
        out["keyword"].append({"q": t["term"], "gold": gold, "title": t["title"]})
        out["paraphrase"].append({"q": t["en"], "gold": gold, "title": t["title"]})
        for lang in ("es", "ru"):
            out["multilingual"].append({"q": t[lang], "gold": gold, "title": t["title"]})
    return out


BEHAVIOR_CATEGORIES = ("fact", "decision", "relationship", "synthesis", "contradiction")


def behavior_cases() -> list[dict]:
    """Cases for the behavior eval: fact/decision/relationship/synthesis/contradiction.

    Unlike the retrieval sets above, every row carries `answer_key` - the
    canonical fact text the judge grades an answer against - so the judge
    does not need to re-derive ground truth from the vault itself.

    Fact questions are the easy case for this eval: a closed-book model has no
    prior on an invented term like "driftlock", so vault-on wins trivially and
    the category adds little signal on its own. Every topic still gets its one
    unconditional fact row (dropping it would understate the corpus's easiest
    cases), but decision, relationship, synthesis and contradiction are grown
    instead - via `q_alt` second phrasings on SYNTHESIS_PAIRS and
    CONTRADICTIONS, and by extending decision/relationship coverage beyond a
    single kind - so fact's *share* of the total drops without touching its
    count. See `category_mix()`.
    """
    by_term = {t["term"]: t for t in TOPICS}
    out: list[dict] = []

    for t in TOPICS:
        gold = [f"{FOLDER[t['kind']]}/{t['title']}.md"]
        out.append({
            "q": f"What is {t['en']}?" if t["kind"] != "person" else f"Who is {t['en']}?",
            "gold": gold, "title": t["title"], "category": "fact", "answer_key": t["body"],
        })
        if t["kind"] == "project":
            out.append({
                "q": f"What caused {t['title']} to change scope or direction?",
                "gold": gold, "title": t["title"], "category": "decision",
                "answer_key": t["body"],
            })
        elif t["kind"] == "concept":
            out.append({
                "q": f"What was {t['title']} chosen over, or what prompted its adoption?",
                "gold": gold, "title": t["title"], "category": "decision",
                "answer_key": t["body"],
            })
        if t["kind"] == "person":
            out.append({
                "q": f"What should someone know before looping in {t['title']}?",
                "gold": gold, "title": t["title"], "category": "relationship",
                "answer_key": t["body"],
            })
            out.append({
                "q": f"What standing rule does {t['title']} hold?",
                "gold": gold, "title": t["title"], "category": "relationship",
                "answer_key": t["body"],
            })

    for pair in SYNTHESIS_PAIRS:
        a, b = by_term[pair["a"]], by_term[pair["b"]]
        gold = [f"{FOLDER[a['kind']]}/{a['title']}.md", f"{FOLDER[b['kind']]}/{b['title']}.md"]
        title = f"{a['title']} + {b['title']}"
        out.append({
            "q": pair["q"], "gold": gold, "title": title,
            "category": "synthesis", "answer_key": pair["answer_key"],
        })
        if "q_alt" in pair:
            out.append({
                "q": pair["q_alt"], "gold": gold, "title": title,
                "category": "synthesis", "answer_key": pair["answer_key"],
            })

    for term, c in CONTRADICTIONS.items():
        t = by_term[term]
        gold = [f"{FOLDER[t['kind']]}/{t['title']}.md"]
        out.append({
            "q": f"Is {t['title']} currently blocked, and what is the latest known state?",
            "gold": gold, "title": t["title"], "category": "contradiction",
            "answer_key": c["answer_key"],
        })
        if "q_alt" in c:
            out.append({
                "q": c["q_alt"], "gold": gold, "title": t["title"],
                "category": "contradiction", "answer_key": c["answer_key"],
            })

    return out


def category_mix(rows: list[dict] | None = None) -> dict[str, float]:
    """Fraction of behavior_cases() rows in each category, rounded to 3 places.

    Exists so the category balance is visible (printed by `--manifest` and
    asserted in tests) rather than only implied by counting entries by hand -
    the mistake that let fact questions creep up to ~48% of the set before
    this function existed.
    """
    rows = behavior_cases() if rows is None else rows
    n = len(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return {cat: round(counts.get(cat, 0) / n, 3) for cat in BEHAVIOR_CATEGORIES} if n else {}


def manifest(files: dict[str, str], sets: dict[str, list[dict]]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode())
        h.update(files[rel].encode())
    for name in sorted(sets):
        h.update(name.encode())
        h.update(json.dumps(sets[name], sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="Directory to write the synthetic vault into")
    ap.add_argument("--notes", type=int, default=300, help="Total notes (default 300)")
    ap.add_argument("--seed", type=int, default=20260726,
                    help="Fixed by default so everyone measures the same corpus")
    ap.add_argument("--manifest", action="store_true",
                    help="Print the corpus hash and exit, to confirm two people match")
    args = ap.parse_args(argv[1:])

    files, sets = build(args.notes, args.seed), cases()
    sets["behavior"] = behavior_cases()

    if args.manifest or not args.out:
        print(f"corpus  {len(files)} notes")
        print("cases   " + ", ".join(f"{k} {len(v)}" for k, v in sorted(sets.items())))
        mix = category_mix(sets["behavior"])
        print("behavior mix   " + ", ".join(f"{cat} {pct*100:.1f}%" for cat, pct in mix.items()))
        print(f"sha256  {manifest(files, sets)}")
        if not args.out:
            print("\nPass --out <dir> to write it.")
        return 0

    out = Path(args.out).expanduser()
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    cdir = out / "_cases"
    cdir.mkdir(parents=True, exist_ok=True)
    for name, rows in sets.items():
        (cdir / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    print(f"Wrote {len(files)} notes and {len(sets)} case sets to {out}")
    print(f"sha256 {manifest(files, sets)}")
    print(f"\nOBSIDIAN_VAULT_PATH={out} uv run python scripts/eval/retrieval_eval.py \\\n"
          f"    --cases {cdir}/paraphrase.jsonl --mode lexical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
