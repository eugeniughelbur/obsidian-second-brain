# Folder map

Where each note type lives. Every skill resolves destinations through this table. The vault's own `AGENTS.md` can override a row in its `## Folder map` section; when it does, the vault wins. Never invent a folder that is neither here nor in `AGENTS.md` - ask instead.

This layout follows the three layers of Karpathy's LLM Wiki pattern: `raw/` is the immutable source layer, `wiki/` is the LLM-maintained layer, and `AGENTS.md` is the schema.

## Layout

```
<vault>/
  AGENTS.md            schema: how this vault is organised and maintained (canonical)
  CLAUDE.md            symlink to AGENTS.md (Claude Code reads CLAUDE.md, Codex reads AGENTS.md)
  index.md             content catalog, read first when answering a question
  log.md               pointer to Logs/ (explains the format)
  Logs/YYYY-MM-DD.md   append-only operation log, one file per day
  raw/                 immutable captures, never edited after writing
    articles/            web pages, pasted text
    videos/              YouTube transcripts
    documents/           PDFs and other files (a note pointing at the original)
    images/              image descriptions
    sessions/            conversation excerpts saved from agent sessions
  wiki/                LLM-maintained knowledge
    entities/            people, companies, tools (told apart by `type:`)
    concepts/            ideas, frameworks, methods
    sources/             one summary page per processed source (`type: research`)
    projects/            projects
    decisions/           decisions and open conflicts (`type: decision` / `type: conflict`)
    synthesis/           cross-source patterns and comparisons (`type: synthesis`)
    sessions/            what a working session produced (`type: devlog`)
    reviews/             daily / weekly / monthly reviews (`type: review`)
```

## Note type to folder

| Note type | Folder |
|---|---|
| Person / company / tool | `wiki/entities/` |
| Idea / concept / framework | `wiki/concepts/` |
| Summary of an external source | `wiki/sources/` |
| Raw capture of a source | `raw/<kind>/` |
| Project | `wiki/projects/` |
| Decision, conflict | `wiki/decisions/` |
| Synthesis | `wiki/synthesis/` |
| Session log | `wiki/sessions/` |
| Review | `wiki/reviews/` |

## File names

- Use the title as the file name, in the vault language. Korean titles are fine: `wiki/concepts/지식 관리.md`.
- Normalize to Unicode NFC before writing. macOS can hand over decomposed (NFD) Hangul, which produces a second file that looks identical.
- Characters not allowed in a file name (`/ \ : * ? " < > |`, `#`, `^`, `[`, `]`) become a space or are dropped.
- Dated notes: `YYYY-MM-DD - Title.md` (sources, sessions, raw captures). Reviews: `YYYY-MM-DD - Daily Review.md`, `YYYY-Www - Weekly Review.md`, `YYYY-MM - Monthly Review.md`.
- Put the other-language name in `aliases:` (for example the English name of a Korean entity) so search and links find it either way.
<!-- author-credit -->

---

From [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain), created by Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator). Questions or consulting: [LinkedIn](https://www.linkedin.com/in/eugeniu-ghelbur/) or [e.ghelbur@gmail.com](mailto:e.ghelbur@gmail.com). More: [The AI Operator](https://theaioperator.io/?utm_source=github&utm_medium=file-credit) | [X](https://x.com/eugeniu_ghelbur) | [GitHub](https://github.com/eugeniughelbur). MIT license.
