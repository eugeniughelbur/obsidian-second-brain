---
description: Generate a visual canvas map of your vault - see the shape of your second brain and how knowledge connects
category: meta
triggers_en: ["visualize vault", "vault map", "canvas of vault", "show me the vault shape"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-visualize $ARGUMENTS`:

The optional argument is a scope: a project name, entity name, topic, or "full" for the entire vault. Default: full vault.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Read `index.md` for the full vault catalog

3. Build the graph:
   - If scoped to a topic/project/entity: start from that note, follow all outgoing `[[wikilinks]]` 2 levels deep
   - If full vault: read all notes, map all links between them

4. Generate a JSON Canvas file (`.canvas`) compatible with Obsidian's native canvas viewer:

   Structure:
   ```json
   {
     "nodes": [
       {"id": "1", "type": "file", "file": "wiki/entities/Eric Siu.md", "x": 0, "y": 0, "width": 250, "height": 60},
       {"id": "2", "type": "file", "file": "wiki/projects/Centralized API Gateway.md", "x": 300, "y": 0, "width": 250, "height": 60}
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
   - **Edge thickness** = number of connections between two nodes (thicker = stronger relationship)
   - **Orphan nodes** placed at the edges with a red border (easy to spot)

5. Save to vault root as `atlas.canvas` (or `atlas-{topic}.canvas` if scoped)

6. Also generate a text summary with centrality ranking:
   - Total nodes and edges
   - **Hub nodes (centrality)** - top 5 by degree centrality, with the raw link count and a one-line "everything flows through this because..." note. A hub qualifies if its degree is at least 3x the median, or it sits in the top 1% of the vault - whichever surfaces fewer.
   - **Bridge nodes** - nodes that, if removed, would split a cluster. Rank by betweenness (approximate: count the shortest paths each node sits on between the top-10 hubs). These are the load-bearing connectors; surface the top 3 with the two clusters each one joins.
   - **Orphan nodes** - no connections, listed by type. Flag any that are >30 days old (stale orphans are higher-priority cleanup targets than fresh ones).
   - **Clusters** - groups of tightly connected notes, named by their hub. Note any cluster with <3 cross-cluster edges (those are silos).
   - **Centrality skew** - if one node holds >25% of total edges, call it out as a single point of failure for navigation.

7. Append to the operation log: if `Logs/` exists write `**HH:MM** - visualize | Canvas generated - X nodes, Y edges, Z orphans` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] visualize | Canvas generated — X nodes, Y edges, Z orphans` to `log.md`

The user can open the `.canvas` file in Obsidian to visually explore their vault's knowledge graph.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
