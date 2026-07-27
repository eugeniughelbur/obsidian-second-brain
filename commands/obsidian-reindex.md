---
description: Refresh the vault's semantic search index and report coverage before and after
category: meta
triggers_en: ["reindex vault", "rebuild semantic index", "refresh semantic search", "update vault embeddings"]
triggers_es: ["reindexa el vault", "reconstruye el índice semántico", "actualiza la búsqueda semántica", "actualiza los embeddings del vault"]
triggers_pt: ["reindexe o vault", "reconstrua o índice semântico", "atualize a busca semântica", "atualize os embeddings do vault"]
triggers_zh: ["重建知识库索引", "刷新语义搜索", "更新笔记向量", "重新索引我的知识库"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-reindex`:

The semantic index is incremental. An existing, current index is cheap to refresh because only new and changed notes are embedded again.

1. Read `_CLAUDE.md` first to find the vault path. Resolve it to an absolute path and substitute it for `VAULT_PATH` below. The skill root was given at session start as **Skill root**; substitute its absolute path for `SKILL_ROOT`.

2. Measure coverage before changing the index:
   ```bash
   uv run --directory "SKILL_ROOT" python -c 'import json, sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "integrations" / "obsidian-mcp-server")); from vault_ops import index_coverage; print(json.dumps(index_coverage(Path(sys.argv[2]).expanduser().resolve())))' "SKILL_ROOT" "VAULT_PATH"
   ```
   Report `indexed`, `scanned`, `missing`, and `pct_missing`. If `index` is false, say that no readable semantic index exists yet instead of presenting `0/0` as coverage.

3. Tell the user that the build is incremental, then run it from the skill root:
   ```bash
   uv run --directory "SKILL_ROOT" python scripts/eval/semantic_search.py --path "VAULT_PATH" --build
   ```
   Preserve the command's exit status and capture its stderr. If it exits nonzero, stop and show the actionable backend error. Do not claim the index was refreshed and do not report an after-state as success. The common failure is Ollama not running or the configured embedding model not being pulled; use the runtime and model named by the command's own output rather than assuming the defaults.

4. On success, run the coverage command from step 2 again.

5. Report the result:
   - Coverage before and after as `indexed/scanned`, with missing count and percentage
   - The builder's `new` count from its `[semantic] indexed ...` summary as notes newly embedded or refreshed
   - Cached, excluded, degraded, and dropped counts when nonzero
   - Every degraded or dropped path printed by the builder, because those notes are not fully searchable by meaning

If coverage did not improve, say so plainly and use the builder output to distinguish a current index from failed or excluded notes. This command updates only `.obsidian-semantic-index.json`; it does not modify Markdown notes.

---

**Anti-fabrication:** Report coverage and build counts exactly as the tools emit them. Never infer a successful refresh from an unchanged file or a zero exit status alone when the builder reports dropped notes.
