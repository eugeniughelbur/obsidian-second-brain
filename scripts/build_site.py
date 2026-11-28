# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer working on agent memory), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Generate the GitHub Pages site from commands/, which is the only source of truth.

GitHub Pages has been live and building for this repo for some time, serving the
README from the repo root. Meanwhile `commands/` holds 47 files that each carry a
one-line `description`, a `category`, and `triggers_en` / `triggers_de` /
`triggers_es` / `triggers_pt` / `triggers_zh` arrays. Those trigger arrays are, literally, the
sentences a person would type when they want the thing - written by hand, in five
languages, and until now visible only to the dispatcher adapters.

So this generates one page per command plus an index. Content, hosting and build
tooling all already existed and were wired to nothing.

Generated, never hand-edited, for the same reason the adapters are: a docs page
maintained separately from the command it documents is a page that will disagree
with it. `--check` fails when the tree on disk differs from what this would
produce, so CI catches a stale site the way it catches a stale conformance board.

Self-contained by construction: inline CSS, no fonts, no scripts from anywhere,
no build step beyond running this file. Light and dark both handled.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS = REPO_ROOT / "commands"
REPO_URL = "https://github.com/eugeniughelbur/obsidian-second-brain"
SITE_URL = "https://eugeniughelbur.github.io/obsidian-second-brain/"
AUTHOR = {"@type": "Person", "name": "Eugeniu Ghelbur", "url": "https://github.com/eugeniughelbur"}
# Bing Webmaster Tools ownership token. Bing reads it from BingSiteAuth.xml at the
# site root to confirm the maintainer owns the site. It is public by design: it
# proves control of the site, it grants no access to anything.
BING_SITE_AUTH = "C497F8E66AA32D3CDE6D809D49978D58"

# Questions people ask AI assistants about this problem, each answered in a
# short block that an answer engine can quote whole: the direct answer first,
# one concrete number, one link to where the claim lives. Same claims as the
# README; written as answers rather than as feature names. `{n}` is the live
# command count, so the page cannot drift from commands/.
FAQ = [
    ("How do I give Claude Code long-term memory across sessions?",
     "Install obsidian-second-brain and point it at an Obsidian vault. A session-start "
     "hook loads the vault's operating manual, and {n} commands read and write plain "
     "markdown notes, so the next session starts with your projects, people and "
     "decisions. No vector database is required; local semantic search is optional.",
     f"{REPO_URL}#install"),
    ("Does it work with Codex, Gemini CLI or Grok Bot, not only Claude?",
     "Yes. One set of command files compiles to 8 platforms: Claude Code, OpenAI Codex "
     "CLI, Google Gemini CLI, OpenCode, Google Antigravity, Nous Research Hermes, Pi and "
     "Grok Bot. The notes stay plain markdown, so any agent that can read files can use "
     "the same vault.",
     f"{REPO_URL}#does-this-work-with-codex-cli-gemini-cli-or-opencode"),
    ("How do my AI agents share what each other did?",
     "The /crew command gives Claude Code, Codex, Cursor and Grok Bot one shared "
     "logbook. After every job an agent writes one line: time, agent, area, outcome and "
     "evidence. Before the next answer, each agent's hooks show it the lines the others "
     "added. It works in any plain folder, with or without Obsidian.",
     f"{REPO_URL}#crew-one-logbook-for-all-your-agents"),
    ("How is this different from Karpathy's LLM wiki pattern?",
     "It builds on it. In the LLM wiki pattern an agent maintains a markdown wiki. Here "
     "every new source rewrites the existing pages it touches instead of only appending, "
     "contradictions are reconciled, and 4 scheduled agents run a morning brief, a "
     "nightly consolidation, a weekly review and a vault health check.",
     f"{REPO_URL}#how-this-extends-karpathys-llm-wiki"),
    ("Can Grok read my Obsidian notes?",
     "Yes, through Grok Bot. GROK-BOT.md holds one starter prompt to paste into a Grok "
     "Bot chat, with the folder layout and the core note rules, so Grok can save and "
     "answer from the same notes. The full skill adds {n} commands, a search index and "
     "checks on every note, and you keep the same notes when you move up.",
     f"{REPO_URL}/blob/main/GROK-BOT.md"),
    ("How do I turn my ChatGPT conversations into Obsidian notes?",
     "Export each chat to a Markdown file with any exporter that writes Markdown, into "
     "a folder outside the vault. Then run /obsidian-ingest on one file or on the whole "
     "folder in batches. AI-CHATS.md walks through the 2 steps and the 3 exporter "
     "settings to change first. It works for Claude.ai and Gemini chats too.",
     f"{REPO_URL}/blob/main/AI-CHATS.md"),
    ("Is it free, and do I need API keys?",
     "It is free and open source under the MIT license, and your notes stay on your "
     "machine. The vault commands need no API keys, and /research falls back to free "
     "sources such as Wikipedia, Hacker News and arXiv. A few research commands, such as "
     "the X and YouTube readers, need their own keys and say so when one is missing.",
     f"{REPO_URL}#do-i-need-api-keys-to-use-this"),
]

CATEGORIES = [
    ("vault", "Vault management",
     "Capture, retrieve and maintain the notes themselves."),
    ("thinking", "Thinking tools",
     "Turn what is already in the vault into a decision, a plan or an argument."),
    ("research", "Research toolkit",
     "Pull the outside world in, with sources and recency preserved."),
    ("meta", "Meta",
     "Set up, extend and inspect the skill itself."),
]

LANGS = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Espanol"),
    ("pt", "Portugues"),
    ("zh", "简体中文"),
]

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def parse_command(path: Path) -> dict | None:
    """Frontmatter only. Command bodies are instructions addressed to an agent
    ("Execute /obsidian-find $ARGUMENTS"), not prose a reader wants, so putting
    them on a docs page would make the page worse, not longer."""
    m = FM_RE.match(path.read_text(encoding="utf-8-sig"))
    if not m:
        return None
    fm = m.group(1)

    def scalar(key: str) -> str:
        mm = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        return mm.group(1).strip().strip("\"'") if mm else ""

    def array(key: str) -> list[str]:
        mm = re.search(rf"^{key}:\s*\[(.*?)\]", fm, re.M | re.S)
        if not mm:
            return []
        return [x.strip().strip("\"'") for x in mm.group(1).split(",") if x.strip()]

    return {
        "name": path.stem,
        "description": scalar("description"),
        "category": scalar("category"),
        "triggers": {code: array(f"triggers_{code}") for code, _ in LANGS},
    }


def load_commands() -> list[dict]:
    out = []
    for f in sorted(COMMANDS.glob("*.md")):
        c = parse_command(f)
        if c and c["description"]:
            out.append(c)
    return out


CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--dim:#5c5c5c;--line:#e3e3e3;--accent:#4c2889;--card:#fafafa}
@media(prefers-color-scheme:dark){:root{--bg:#121212;--fg:#e8e8e8;--dim:#9a9a9a;--line:#2c2c2c;--accent:#b191e8;--card:#1a1a1a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:52rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
a{color:var(--accent)}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 .5rem}
h2{font-size:1.15rem;margin:2.5rem 0 .25rem;padding-top:1.25rem;border-top:1px solid var(--line)}
h2:first-of-type{border-top:0;padding-top:0}
.lede{color:var(--dim);font-size:1.05rem;margin:0 0 2rem}
.note{color:var(--dim);font-size:.9rem;margin:.25rem 0 1.25rem}
.cmd{display:block;padding:.7rem .9rem;margin:.4rem 0;border:1px solid var(--line);
 border-radius:8px;background:var(--card);text-decoration:none;color:inherit}
.cmd:hover{border-color:var(--accent)}
.cmd code{color:var(--accent);font-weight:600}
.cmd span{display:block;color:var(--dim);font-size:.9rem;margin-top:.15rem}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}
input[type=search]{width:100%;padding:.7rem .9rem;font-size:1rem;border-radius:8px;
 border:1px solid var(--line);background:var(--card);color:var(--fg);margin-bottom:1.5rem}
ul.say{list-style:none;padding:0}
ul.say li{padding:.45rem .8rem;margin:.3rem 0;border-left:3px solid var(--line);
 background:var(--card);border-radius:0 6px 6px 0}
.lang{color:var(--dim);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;
 margin:1.25rem 0 .25rem}
footer{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--line);
 color:var(--dim);font-size:.9rem}
table{width:100%;border-collapse:collapse}
.scroll{overflow-x:auto}
"""


def _ld(data: dict) -> str:
    """Structured data (schema.org JSON-LD) that search and answer engines read
    to know what a page is about. Inert: the browser never executes it. `</` is
    escaped so a description can never close the tag early."""
    payload = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{payload}\n</script>\n'


def page(title: str, description: str, body: str, depth: int = 0,
         path: str = "index.html", structured: list[dict] | None = None) -> str:
    up = "../" * depth
    url = SITE_URL + ("" if path == "index.html" else path)
    ld = "".join(_ld(d) for d in structured or [])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="obsidian-second-brain">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{url}">
{ld}<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<footer>
<a href="{up}index.html">All commands</a> &middot;
<a href="{REPO_URL}">Source on GitHub</a>
</footer>
</div>
</body>
</html>
"""


def render_index(cmds: list[dict]) -> str:
    by_cat: dict[str, list[dict]] = {}
    for c in cmds:
        by_cat.setdefault(c["category"], []).append(c)

    parts = [
        "<h1>obsidian-second-brain</h1>",
        f'<p class="lede">Your AI agent starts every session knowing nothing about '
        f"you. These {len(cmds)} commands give Claude, Grok Bot, and other agents long-term memory across "
        "sessions, kept as plain markdown in your Obsidian vault. Every one works "
        "by plain language, in English, German, Spanish, Portuguese or Simplified Chinese.</p>",
        '<input type="search" id="q" placeholder="Filter commands..." '
        'aria-label="Filter commands">',
    ]
    faq = ["<h2>Common questions</h2>"]
    for q, a, link in FAQ:
        faq.append(f"<h3>{html.escape(q)}</h3>")
        faq.append(f'<p>{html.escape(a.format(n=len(cmds)))} <a href="{link}">Details</a></p>')
    for key, heading, blurb in CATEGORIES:
        group = by_cat.get(key, [])
        if not group:
            continue
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        parts.append(f'<p class="note">{html.escape(blurb)}</p>')
        for c in group:
            trig = " ".join(t for arr in c["triggers"].values() for t in arr)
            parts.append(
                f'<a class="cmd" href="commands/{c["name"]}.html" '
                f'data-s="{html.escape((c["name"] + " " + c["description"] + " " + trig).lower())}">'
                f'<code>/{html.escape(c["name"])}</code>'
                f'<span>{html.escape(c["description"])}</span></a>'
            )
    parts.extend(faq)
    # The only script on the site, and it degrades to a full list without it.
    parts.append("""<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{const v=q.value.toLowerCase().trim();
document.querySelectorAll('.cmd').forEach(el=>{
el.style.display=!v||el.dataset.s.includes(v)?'':'none';});});
</script>""")
    return "\n".join(parts)


def render_command(c: dict) -> str:
    parts = [
        f'<h1><code>/{html.escape(c["name"])}</code></h1>',
        f'<p class="lede">{html.escape(c["description"])}</p>',
        "<p>Type the command, or just say what you want. The skill matches on "
        "meaning, so the phrases below are examples of the shape, not a list you "
        "have to memorise.</p>",
    ]
    for code, label in LANGS:
        trig = c["triggers"].get(code) or []
        if not trig:
            continue
        parts.append(f'<p class="lang">{html.escape(label)}</p>')
        parts.append('<ul class="say">')
        parts.extend(f"<li>{html.escape(t)}</li>" for t in trig)
        parts.append("</ul>")
    parts.append(
        f'<p class="note"><a href="{REPO_URL}/blob/main/commands/{c["name"]}.md">'
        "Read what this command actually does</a> - the command file is the "
        "instruction set the agent follows, and it is plain markdown.</p>"
    )
    return "\n".join(parts)


def render_sitemap(paths: list[str]) -> str:
    """No <lastmod>: it would change on every build and break --check, and
    crawlers re-read a small sitemap anyway."""
    urls = "".join(
        f"<url><loc>{html.escape(SITE_URL + ('' if p == 'index.html' else p))}</loc></url>\n"
        for p in paths
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}</urlset>\n")


def build(out: Path, cmds: list[dict]) -> dict[str, str]:
    """Return the whole site as {relative path: contents}, writing nothing."""
    index_description = (
        "Persistent memory for Claude Code, Codex, Grok Bot and other agents, stored "
        "as plain markdown in your Obsidian vault. Crew adds one shared logbook, so "
        f"your agents know what each other did. {len(cmds)} commands."
    )
    structured = [
        {
            "@context": "https://schema.org",
            "@type": "SoftwareSourceCode",
            "name": "obsidian-second-brain",
            "description": index_description,
            "url": SITE_URL,
            "codeRepository": REPO_URL,
            "license": "https://opensource.org/licenses/MIT",
            "programmingLanguage": ["Python", "Shell"],
            "author": AUTHOR,
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a.format(n=len(cmds))}}
                for q, a, _ in FAQ
            ],
        },
    ]
    files = {
        # GitHub Pages runs Jekyll by default, which would try to process these
        # and skip anything it thinks is a draft. This turns that off.
        ".nojekyll": "",
        # Title and description are written in the words people actually search
        # with ("persistent memory", "across sessions"), not the words the project
        # uses for itself ("cross-CLI skill", "48 commands"). Repos with a fraction
        # of the stars outrank this one on those queries purely by saying the
        # problem out loud. Same claims either way; only the ordering changed.
        "index.html": page(
            "AI second brain for Obsidian - persistent memory for "
            "Claude Code, Codex and Grok Bot",
            index_description,
            render_index(cmds),
            structured=structured,
        ),
    }
    for c in cmds:
        rel = f"commands/{c['name']}.html"
        files[rel] = page(
            f"/{c['name']} - obsidian-second-brain",
            c["description"],
            render_command(c),
            depth=1,
            path=rel,
        )
    # The repo's llms.txt, served from the site too, where tools that read the
    # convention look for it. Copied, not rewritten, so the two never disagree.
    files["llms.txt"] = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
    # Bing feeds ChatGPT search and Copilot, so the site is registered there.
    files["BingSiteAuth.xml"] = (
        '<?xml version="1.0"?>\n<users>\n'
        f"\t<user>{BING_SITE_AUTH}</user>\n</users>\n"
    )
    files["sitemap.xml"] = render_sitemap(
        [p for p in files if p.endswith(".html")]
    )
    return files


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build the GitHub Pages site from commands/")
    ap.add_argument("--out", default=str(REPO_ROOT / "docs"), help="Output directory")
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 if the tree on disk differs from what this would write")
    args = ap.parse_args(argv[1:])

    out = Path(args.out)
    cmds = load_commands()
    if not cmds:
        print("No commands parsed; refusing to write an empty site.", file=sys.stderr)
        return 1
    files = build(out, cmds)

    if args.check:
        stale = []
        for rel, content in files.items():
            p = out / rel
            if not p.exists() or p.read_text(encoding="utf-8") != content:
                stale.append(rel)
        if stale:
            print(f"Site is stale ({len(stale)} file(s)). Regenerate:\n"
                  f"  uv run python scripts/build_site.py\n  " + "\n  ".join(stale[:10]),
                  file=sys.stderr)
            return 1
        print(f"Site is current: {len(files)} files from {len(cmds)} commands")
        return 0

    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {out} from {len(cmds)} commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
