# Ecosystem

`obsidian-second-brain` is the core. Domain-specific forks extend the pattern.

This page lists known forks that take the vault-rewrite architecture (the AI-first rule, the wikilink graph, the rewrite-vs-append principle from Karpathy's LLM Wiki) and apply it to a specific domain - academic research, legal practice, finance, medicine, anything.

Each fork stays independent. The relationship is contractual, not custodial: upstream owns the core primitives (vault management, AI-first rule, the rewrite engine, the multi-platform adapter layer, the generic research toolkit), and forks own everything domain-specific (source routers, controlled-vocab schemas, domain-specific backends, specialized note types).

## Why this pattern

A vault skill is only as useful as the domain knowledge it carries. PubMed routing belongs in an academic fork, not in core. Case-law lookup belongs in a legal fork, not in core. The alternative - absorbing every domain into the upstream repo - leads to a single monolithic skill that nobody can maintain and that fails the AI-first rule (because the upstream maintainer cannot meaningfully reason about controlled vocabularies they do not use).

Instead, upstream ships the **primitives** that forks plug into:

- Vault management, AI-first rule enforcement, the rewrite engine
- Multi-platform adapter layer (Claude Code / Codex CLI / Gemini CLI / OpenCode)
- The generic research toolkit shape (Phase 1 vault scan, Phase 2/3 external research, Phase 4 synthesis)
- A pluggable **Backend protocol** for Phase 3 (in progress, per [Discussion #38](https://github.com/eugeniughelbur/obsidian-second-brain/discussions/38)) so any domain can add its own research backends without forking the engine

Forks contribute back the generic primitives that came out of their domain work. Anything that survives the "would a non-domain user benefit from this?" test is PR-eligible.

## Known forks

| Fork | Domain | Maintainer | Status |
|---|---|---|---|
| [`SHzzzAyys/scholarbrain`](https://github.com/SHzzzAyys/scholarbrain) | Academic research (PubMed, arXiv, Semantic Scholar) | [@SHzzzAyys](https://github.com/SHzzzAyys) | Active. Paper-card controlled vocab, DeepSeek backend, language-aware gap prompts. First proof case of the ecosystem pattern. |

## How to be added

If you have built a domain-specific fork that meaningfully extends the pattern, open a discussion in [this repo's Discussions tab](https://github.com/eugeniughelbur/obsidian-second-brain/discussions) and link to:

1. Your fork's repository
2. A short description of the domain it serves
3. Anything you plan to contribute back upstream (if applicable)

We do not gatekeep on stars, downloads, or audience size. We gatekeep on whether the fork actually uses the architecture in a way that other people can learn from.

## What does NOT belong on this list

- Personal forks that just rename things or change theme colors
- Forks that have not actually shipped a domain-specific feature beyond a README
- Forks that violate the AI-first rule in their own vault writes (defeats the point)
- Anything that just resells the upstream functionality under a new name without genuine domain work

The list is curated. If a fork stops being maintained or drifts away from the pattern, we remove it.
