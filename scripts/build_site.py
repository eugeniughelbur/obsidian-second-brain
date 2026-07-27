"""Generate the GitHub Pages site from commands/, which is the only source of truth.

GitHub Pages has been live and building for this repo for some time, serving the
README from the repo root. Meanwhile `commands/` holds 46 files that each carry a
one-line `description`, a `category`, and `triggers_en` / `triggers_es` /
`triggers_pt` / `triggers_zh` arrays. Those trigger arrays are, literally, the
sentences a person would type when they want the thing - written by hand, in four
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
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS = REPO_ROOT / "commands"
REPO_URL = "https://github.com/eugeniughelbur/obsidian-second-brain"

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


def page(title: str, description: str, body: str, depth: int = 0) -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<style>{CSS}</style>
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
        f"you. These {len(cmds)} commands give it long-term memory across "
        "sessions, kept as plain markdown in your own Obsidian vault. Every one works "
        "by plain language, in English, Spanish, Portuguese or Simplified Chinese.</p>",
        '<input type="search" id="q" placeholder="Filter commands..." '
        'aria-label="Filter commands">',
    ]
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


def build(out: Path, cmds: list[dict]) -> dict[str, str]:
    """Return the whole site as {relative path: contents}, writing nothing."""
    files = {
        # GitHub Pages runs Jekyll by default, which would try to process these
        # and skip anything it thinks is a draft. This turns that off.
        ".nojekyll": "",
        # Title and description are written in the words people actually search
        # with ("persistent memory", "across sessions"), not the words the project
        # uses for itself ("cross-CLI skill", "46 commands"). Repos with a fraction
        # of the stars outrank this one on those queries purely by saying the
        # problem out loud. Same claims either way; only the ordering changed.
        "index.html": page(
            "Persistent memory for Claude Code, in your Obsidian vault "
            "- obsidian-second-brain",
            "Give Claude Code and six other CLI agents long-term memory across "
            "sessions, stored as plain markdown in your own Obsidian vault. Stop "
            "re-explaining your projects, decisions and people every time. 46 "
            "commands, with plain-language triggers in English, Spanish, Portuguese "
            "and Simplified Chinese.",
            render_index(cmds),
        ),
    }
    for c in cmds:
        files[f"commands/{c['name']}.html"] = page(
            f"/{c['name']} - obsidian-second-brain",
            c["description"],
            render_command(c),
            depth=1,
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
