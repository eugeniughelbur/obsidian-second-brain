---
description: Generate a visual canvas map of your vault - see the shape of your second brain and how knowledge connects
category: meta
triggers_en: ["visualize vault", "vault map", "canvas of vault", "show me the vault shape"]
triggers_es: ["visualiza el vault", "mapa del vault", "canvas del vault", "muéstrame la forma de mi vault"]
triggers_pt: ["visualize o vault", "mapa do vault", "canvas do vault", "mostre a forma do vault"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-visualize $ARGUMENTS`:

The optional argument is a scope: an EXACT note title or alias (a project, an entity), or "full" for the entire vault. Default: full vault. A free-form topic phrase will not match - resolve it to a real note title first (e.g. via /obsidian-find).

1. Read `_CLAUDE.md` first if it exists in the vault root

2. Build the graph deterministically with the scanner instead of reading every note into context (a full-vault read is O(read-everything) and burns the budget). Run from the skill root (its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`):
   ```bash
   uv run --directory "SKILL_ROOT" scripts/link_graph.py --path "<vault>" [--scope "<topic/project/entity>"]
   ```
   It returns JSON with `nodes` (path, title, `type`, folder, in/out/`degree`), `edges` (resolved `[[wikilink]]` pairs), and `stats` (`node_count`, `edge_count`, `orphan_count`, `dangling_link_count`, `top_hubs`, `orphans`). Pass `--scope` with an exact note title/alias (the script keeps that note plus its 2-hop neighborhood); omit it for the full vault. If the result has `node_count: 0`, the scope did not resolve to a note - find the real title and rerun. Use this JSON as the graph - only open individual notes if you need a label the scan did not provide.

3. Generate a JSON Canvas file (`.canvas`) compatible with Obsidian's native canvas viewer:

   Structure:
   ```json
   {
     "nodes": [
       {"id": "1", "type": "file", "file": "wiki/entities/Ada Lovelace.md", "x": 0, "y": 0, "width": 250, "height": 60},
       {"id": "2", "type": "file", "file": "wiki/projects/Tide Gateway.md", "x": 300, "y": 0, "width": 250, "height": 60}
     ],
     "edges": [
       {"id": "e1", "fromNode": "1", "toNode": "2"}
     ]
   }
   ```

   Layout rules:
   - **Hub nodes** (most links) go in the center, larger
   - **Cluster by type**: entities on the left, projects top-right, concepts bottom-right, daily notes bottom
   - **Color by type**: entities = blue, projects = green, concepts = purple, daily = gray, sources = orange
   - **Edge labels** = when two nodes connect through multiple links, record the count in the edge `label` (JSON Canvas edges have no thickness property)
   - **Orphan nodes** placed at the edges with a red border (easy to spot)

4. Save to vault root as `atlas.canvas` (or `atlas-{topic}.canvas` if scoped)

5. Also generate a text summary with centrality ranking (use the scanner's `stats` and per-node `degree`/`in`/`out` directly - do not recompute by hand):
   - Total nodes and edges (`stats.node_count`, `stats.edge_count`), plus the `dangling_link_count` (wanted notes - links to unwritten notes).
   - **Hub nodes (centrality)** - top 5 from `stats.top_hubs` (already ranked by degree), each with its link count and a one-line "everything flows through this because..." note. A hub qualifies if its degree is at least 3x the median, or it sits in the top 1% of the vault - whichever surfaces fewer.
   - **Bridge nodes** - nodes that, if removed, would split a cluster. Rank by betweenness (approximate: count the shortest paths each node sits on between the top-10 hubs). These are the load-bearing connectors; surface the top 3 with the two clusters each one joins.
   - **Orphan nodes** - no connections, listed by type. Flag any that are >30 days old (stale orphans are higher-priority cleanup targets than fresh ones).
   - **Clusters** - groups of tightly connected notes, named by their hub. Note any cluster with <3 cross-cluster edges (those are silos).
   - **Centrality skew** - if one node holds >25% of total edges, call it out as a single point of failure for navigation.

6. Append to the operation log: if `Logs/` exists write `**HH:MM** - visualize | Canvas generated - X nodes, Y edges, Z orphans` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] visualize | Canvas generated - X nodes, Y edges, Z orphans` to `log.md`

The user can open the `.canvas` file in Obsidian to visually explore their vault's knowledge graph.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
