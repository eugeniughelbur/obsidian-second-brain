"""Instruction contracts for the optional human source layer.

These tests check the agent playbooks and shared specifications, not actual
filesystem initialization or LLM ingestion. Live acceptance belongs in the
PR's validation notes. Prose assertions guard documented obligations and may
need updating when those instructions are reworded; they are not behavior tests.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_init_uses_agent_directory_creation_and_shared_routing():
    command = read("commands/obsidian-init.md")
    assert command.index("ensure `First-Brain/` exists") < command.index("Generate a complete")
    assert "creating it if absent with filesystem tools" in command
    assert "Create missing destination directories with filesystem tools" in command
    assert "references/folder-map.md" in command
    assert "even if `wiki/` was absent" in command


def test_init_preserves_sources_manual_review_and_existing_layout_choice():
    command = read("commands/obsidian-init.md")
    assert "Preserve the current layout when the variant is declined" in command
    assert "Do not move, rename, edit, or ingest" in command
    assert "stop on a file named `First-Brain` or an unsafe linked path" in command
    assert "ask before overwriting" in command
    assert "sensitive-content rules" in command
    assert "never route generated outputs under the source folder" in command


def test_init_covers_ancillary_routing_and_preserves_existing_bases():
    command = read("commands/obsidian-init.md")
    for destination in (
        "entities", "concepts/synthesis", "projects", "meetings",
        "decisions/conflicts", "tasks/recurring obligations", "daily notes",
        "work logs", "reviews", "agenda", "boards",
    ):
        assert destination in command
    assert "variant's wiki-style routes" in command
    assert "Honor approved custom Folder Map destinations" in command
    assert "Skip any base file that already exists" in command


def test_schema_and_template_distinguish_human_sources_from_agent_outputs():
    schema = read("references/vault-schema.md")
    variant = schema.split("## First-Brain wiki-style variant", 1)[1].split(
        "## Obsidian-Style", 1)[0]
    for folder in ("First-Brain/", "raw/", "wiki/", "boards/", "Logs/", "Bases/"):
        assert folder in variant
    assert "commands/obsidian-init.md" in variant
    assert "not a hard filesystem sandbox" in variant
    template = read("references/claude-md-template.md")
    assert "## First Brain Protection" in template
    assert "all current and future descendants" in template
    assert "instruction-based, not a filesystem sandbox" in template
    assert "Scope Section 0 and Frontmatter Requirements to agent-generated notes" in template


def test_ingest_retains_hash_approval_provenance_and_source_boundary():
    command = read("commands/obsidian-ingest.md")
    assert "source_path" in command
    assert "same hash follows the existing re-read rule" in command
    assert "first 16 hex characters of the SHA-256" in command
    assert "wait for a yes before writing" in command
    assert "Do not propose or apply a rewrite to `First-Brain/`" in command
    assert "Pass these restrictions to every subagent" in command
    assert "sensitive-content permissions before reading or capturing" in command
    assert "source_path:" in read("references/ai-first-rules.md")


def test_protection_covers_all_vault_writing_commands():
    schema = read("references/vault-schema.md")
    paragraph = next(p for p in schema.split("\n\n") if "Every vault-writing command" in p)
    for marker in (
        "must honor", "First Brain Protection", "_CLAUDE.md",
        "/obsidian-reconcile", "/obsidian-synthesize", "/obsidian-health",
        "background agents", "subagents",
    ):
        assert marker in paragraph
    template = read("references/claude-md-template.md")
    protection = template.split("## First Brain Protection", 1)[1].split("```", 1)[0]
    assert "Every vault-writing command" in protection
    assert "must honor" in protection
