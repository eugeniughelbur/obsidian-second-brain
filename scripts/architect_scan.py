#!/usr/bin/env python3
"""Scan a codebase and emit a JSON architecture manifest for /obsidian-architect.

Deterministic only: this walks a repo and reports its stack, entry points,
proposed modules, external dependencies, and git metadata. It does NOT write
anything and does NOT call an LLM - the calling Claude turns this JSON into
AI-first architecture notes (the "why", descriptions, personas, diagram).

Stdlib only, so it runs with no install.

Usage:
  python scripts/architect_scan.py --path ~/code/myproject
  python scripts/architect_scan.py --path . --max-modules 12
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Directories never worth scanning as source.
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".next", ".nuxt",
    ".idea", ".vscode", "vendor", "coverage", ".turbo", ".cache", "out",
    "site-packages", ".gradle", "bin", "obj",
}
# Directory names that are support, not core modules.
SUPPORT_DIRS = {"tests", "test", "docs", "doc", "examples", "example", "scripts",
                "fixtures", "__tests__", "spec", "specs", ".github"}

# Extension -> language label.
LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".java": "Java",
    ".kt": "Kotlin", ".swift": "Swift", ".c": "C", ".h": "C", ".cpp": "C++",
    ".cc": "C++", ".cs": "C#", ".php": "PHP", ".sh": "Shell", ".bash": "Shell",
    ".sql": "SQL", ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
    ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown", ".lua": "Lua",
}
SOURCE_EXTS = {e for e in LANG if e not in (".md",)}


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        parts = set(p.relative_to(root).parts)
        if parts & SKIP_DIRS:
            continue
        yield p


def detect_languages(root: Path) -> list[dict]:
    counts: Counter = Counter()
    for p in _iter_files(root):
        lang = LANG.get(p.suffix.lower())
        if lang:
            counts[lang] += 1
    total = sum(counts.values()) or 1
    return [
        {"language": lang, "files": n, "pct": round(100 * n / total, 1)}
        for lang, n in counts.most_common()
    ]


def detect_manifests(root: Path) -> dict:
    """Find the primary manifest and pull name + a few dependencies."""
    info: dict = {"name": root.name, "kind": None, "dependencies": [], "entry_points": []}

    pkg = root / "package.json"
    pyproject = root / "pyproject.toml"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            info["kind"] = "node"
            info["name"] = data.get("name") or info["name"]
            info["dependencies"] = sorted(data.get("dependencies", {}).keys())[:25]
            info["entry_points"] = sorted(data.get("scripts", {}).keys())[:15]
        except (json.JSONDecodeError, OSError):
            pass
    elif pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
            info["kind"] = "python"
            m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                info["name"] = m.group(1)
            # crude dependency capture from [project] dependencies = [ ... ]
            dep_block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
            if dep_block:
                deps = re.findall(r'["\']([A-Za-z0-9_.\-]+)', dep_block.group(1))
                info["dependencies"] = deps[:25]
            info["entry_points"] = re.findall(r"(?m)^\s*([A-Za-z0-9_\-]+)\s*=\s*[\"'][^\"']+:[^\"']+[\"']", text)[:15]
        except OSError:
            pass
    else:
        for fn, kind in (("go.mod", "go"), ("Cargo.toml", "rust"),
                         ("requirements.txt", "python"), ("Gemfile", "ruby"),
                         ("pom.xml", "java"), ("build.gradle", "gradle")):
            if (root / fn).is_file():
                info["kind"] = kind
                break
    # extra signals
    info["has_dockerfile"] = (root / "Dockerfile").is_file()
    info["has_makefile"] = (root / "Makefile").is_file()
    info["has_ci"] = (root / ".github" / "workflows").is_dir()
    return info


def _source_roots(root: Path) -> list[Path]:
    """Where modules live: src/lib/app if present, else the repo root."""
    for name in ("src", "lib", "app", "apps", "packages"):
        d = root / name
        if d.is_dir():
            return [d]
    return [root]


def propose_modules(root: Path, max_modules: int) -> list[dict]:
    """Top-level source directories that look like real modules."""
    modules = []
    for base in _source_roots(root):
        for child in sorted(base.iterdir() if base.is_dir() else []):
            if not child.is_dir():
                continue
            name = child.name
            if name in SKIP_DIRS or name.startswith("."):
                continue
            n_source = sum(
                1 for p in _iter_files(child) if p.suffix.lower() in SOURCE_EXTS
            )
            if n_source == 0:
                continue
            modules.append({
                "name": name,
                "path": str(child.relative_to(root)),
                "source_files": n_source,
                "role_hint": "support" if name.lower() in SUPPORT_DIRS else "core",
            })
    modules.sort(key=lambda m: (m["role_hint"] != "core", -m["source_files"]))
    return modules[:max_modules]


def git_info(root: Path) -> dict:
    def _git(*args):
        try:
            out = subprocess.run(["git", "-C", str(root), *args],
                                 capture_output=True, text=True, check=False)
            return out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            return ""
    commit = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    return {"commit": commit, "dirty": dirty} if commit else {}


def scan(root: Path, max_modules: int) -> dict:
    manifests = detect_manifests(root)
    return {
        "root": str(root),
        "name": manifests["name"],
        "kind": manifests["kind"],
        "languages": detect_languages(root),
        "modules": propose_modules(root, max_modules),
        "dependencies": manifests["dependencies"],
        "entry_points": manifests["entry_points"],
        "signals": {
            "dockerfile": manifests["has_dockerfile"],
            "makefile": manifests["has_makefile"],
            "ci": manifests["has_ci"],
        },
        "git": git_info(root),
        "note": ("Deterministic scan only. Synthesize the architecture notes "
                 "(descriptions, rationale, personas, diagram) from this manifest."),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Scan a codebase into an architecture manifest.")
    ap.add_argument("--path", default=".", help="repo root to scan (default: cwd)")
    ap.add_argument("--max-modules", type=int, default=12, help="cap on proposed modules")
    args = ap.parse_args(argv[1:])

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1
    print(json.dumps(scan(root, args.max_modules), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
