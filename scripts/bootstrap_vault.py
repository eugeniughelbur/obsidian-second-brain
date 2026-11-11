#!/usr/bin/env python3
"""Create (or adopt) an LLM Wiki vault and register it with Claude Code / Codex.

Usage:
    python3 bootstrap_vault.py --path ~/Documents/MyVault --name "홍길동" \
        --company "ACME" --role "CTO" --language ko --hosts claude,codex

What it does:
1. Creates the folder layout from references/folder-map.md (raw/, wiki/..., Logs/).
   Existing folders and files are never overwritten, so pointing it at an
   existing vault only adds what is missing.
2. Writes <vault>/.osb/profile.json (owner, company, role, language) that
   obsidian-init reads to fill AGENTS.md.
3. Writes the owner's entity note (and the company's) in wiki/entities/.
4. Writes .obsidian/app.json (attachments to raw/images) when .obsidian/ is absent.
5. Registers the vault with the toolkit config and the chosen hosts via
   host_config.py: Claude settings.json, Codex config.toml (writable_roots and
   network_access) and the validator hook for both.

AGENTS.md and index.md are NOT written here: run the obsidian-init skill inside
the vault afterwards. That step is the agent's, because it reads the vault.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_config  # noqa: E402

FOLDERS = [
    "raw/articles", "raw/videos", "raw/documents", "raw/images", "raw/sessions",
    "wiki/entities", "wiki/concepts", "wiki/sources", "wiki/projects",
    "wiki/decisions", "wiki/synthesis", "wiki/sessions", "wiki/reviews",
    "Logs", ".osb",
]

OBSIDIAN_APP = {
    "attachmentFolderPath": "raw/images",
    "newLinkFormat": "shortest",
    "useMarkdownLinks": False,
}


def safe_name(text: str) -> str:
    text = unicodedata.normalize("NFC", text).strip()
    text = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", text)
    return re.sub(r"\s+", " ", text).strip() or "TBD"


def write_new(path: Path, content: str) -> bool:
    """Write only when the file does not exist. Returns True when written."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def owner_note(name: str, company: str, role: str, language: str, today: str) -> str:
    company_link = f'"[[{safe_name(company)}]]"' if company else "TBD"
    if language == "ko":
        preamble = (f"이 볼트의 소유자 {name}의 인물 노트. 볼트가 '나', '내 프로젝트'라고 말할 때 "
                    f"가리키는 사람이다. 소속과 직책은 설치 시 입력한 값({today} 기준)이다.")
        body = (f"## 기본 정보\n\n- 이름: {name}\n- 회사: "
                f"{('[[' + safe_name(company) + ']]') if company else 'TBD'}\n- 직책: {role or 'TBD'} "
                f"(as of {today[:7]}, 설치 입력)\n\n## 관심사와 현재 초점\n\nTBD\n")
    else:
        preamble = (f"Person note for {name}, the owner of this vault. When the vault says "
                    f"'I' or 'my project', it means this person. Company and role are the "
                    f"values entered at install time ({today}).")
        body = (f"## Basics\n\n- Name: {name}\n- Company: "
                f"{('[[' + safe_name(company) + ']]') if company else 'TBD'}\n- Role: {role or 'TBD'} "
                f"(as of {today[:7]}, install input)\n\n## Interests and current focus\n\nTBD\n")
    return (
        "---\n"
        "type: person\n"
        f"date: {today}\n"
        f"updated: {today}\n"
        "tags: [person, owner]\n"
        f"company: {company_link}\n"
        f'role: "{role or "TBD"}"\n'
        "relationship: self\n"
        "ai-first: true\n"
        "---\n\n"
        f"# {name}\n\n## For future agent\n\n{preamble}\n\n{body}"
    )


def company_note(company: str, owner: str, language: str, today: str) -> str:
    if language == "ko":
        preamble = f"볼트 소유자 [[{safe_name(owner)}]]가 일하는 회사 {company}의 노트. 설치 시 입력한 값이다({today})."
        body = "## 개요\n\nTBD\n"
    else:
        preamble = f"Company note for {company}, where the vault owner [[{safe_name(owner)}]] works. Entered at install time ({today})."
        body = "## Overview\n\nTBD\n"
    return (
        "---\n"
        "type: company\n"
        f"date: {today}\n"
        f"updated: {today}\n"
        "tags: [company]\n"
        f'people: ["[[{safe_name(owner)}]]"]\n'
        "ai-first: true\n"
        "---\n\n"
        f"# {company}\n\n## For future agent\n\n{preamble}\n\n{body}"
    )


def bootstrap(vault: Path, name: str, company: str, role: str, language: str) -> list[str]:
    today = date.today().isoformat()
    created: list[str] = []
    vault.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        p = vault / folder
        if not p.exists():
            p.mkdir(parents=True)
            created.append(folder + "/")

    profile = vault / ".osb" / "profile.json"
    data = json.loads(profile.read_text(encoding="utf-8")) if profile.exists() else {}
    data.update({"owner": name, "company": company, "role": role, "language": language,
                 "vault_path": str(vault)})
    data.setdefault("created", today)
    profile.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created.append(".osb/profile.json")

    if write_new(vault / "wiki" / "entities" / f"{safe_name(name)}.md",
                 owner_note(name, company, role, language, today)):
        created.append(f"wiki/entities/{safe_name(name)}.md")
    if company and write_new(vault / "wiki" / "entities" / f"{safe_name(company)}.md",
                             company_note(company, name, language, today)):
        created.append(f"wiki/entities/{safe_name(company)}.md")

    if not (vault / ".obsidian").exists():
        write_new(vault / ".obsidian" / "app.json", json.dumps(OBSIDIAN_APP, indent=2) + "\n")
        created.append(".obsidian/app.json")
    return created


def main() -> int:
    ap = argparse.ArgumentParser(description="Create or adopt an LLM Wiki vault.")
    ap.add_argument("--path", required=True, help="vault folder (created if missing)")
    ap.add_argument("--name", required=True, help="owner's name")
    ap.add_argument("--company", default="", help="company name")
    ap.add_argument("--role", default="", help="job title / role")
    ap.add_argument("--language", default="ko", choices=["ko", "en"], help="note language")
    ap.add_argument("--hosts", default="", help="comma list of hosts to configure: claude,codex")
    ap.add_argument("--no-hooks", action="store_true", help="skip the validator hook")
    args = ap.parse_args()

    vault = Path(args.path).expanduser().resolve()
    if vault.exists() and not vault.is_dir():
        print(f"error: {vault} exists and is not a folder", file=sys.stderr)
        return 2
    name = unicodedata.normalize("NFC", args.name.strip())
    if not name:
        print("error: --name is required", file=sys.stderr)
        return 2
    created = bootstrap(vault, name, args.company.strip(), args.role.strip(), args.language)
    print(f"vault: {vault}")
    print("created: " + (", ".join(created) if created else "nothing new"))

    hosts = {h.strip() for h in args.hosts.split(",") if h.strip()}
    if host_config.write_env(vault, args.language):
        print("updated: toolkit config (~/.config/obsidian-second-brain/.env)")
    if "claude" in hosts and host_config.configure_claude(vault, hooks=not args.no_hooks):
        print("updated: ~/.claude/settings.json")
    if "codex" in hosts:
        for path in host_config.configure_codex(vault, hooks=not args.no_hooks):
            print(f"updated: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
