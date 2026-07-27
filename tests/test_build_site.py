"""The docs site is generated from commands/, and must not be able to drift.

A page documenting a command, maintained separately from that command, is a page
that will eventually contradict it. Every one of these 46 pages is derived from
frontmatter that already existed, so the only real failure mode is the tree on
disk falling behind the tree the generator would produce - which is what
`--check` and the CI step exist to catch.

Also pinned here: the site stays self-contained. GitHub Pages will happily serve
a page that pulls a font or a script from a CDN, and nothing would fail; it would
just quietly send every visitor's IP to a third party.
"""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_site  # noqa: E402


def test_the_committed_site_matches_the_generator():
    """The CI fence, run locally. Regenerate with build_site.py if this fails."""
    r = subprocess.run([sys.executable, "scripts/build_site.py", "--check"],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout


def test_every_command_gets_a_page():
    cmds = build_site.load_commands()
    expected = len(list((REPO_ROOT / "commands").glob("*.md")))
    assert len(cmds) == expected, (
        f"{expected - len(cmds)} command(s) have no description in frontmatter, so "
        "they were silently dropped from the site"
    )
    for c in cmds:
        assert (DOCS / "commands" / f"{c['name']}.html").is_file(), (
            f"/{c['name']} exists as a command but has no page"
        )


def test_every_command_has_every_published_trigger_language():
    missing = []
    for command in build_site.load_commands():
        for code, _label in build_site.LANGS:
            if not command["triggers"].get(code):
                missing.append(f"{command['name']}: triggers_{code}")
    assert not missing, "published trigger languages are incomplete:\n  " + "\n  ".join(missing)


def test_the_generator_refuses_to_write_an_empty_site(tmp_path, monkeypatch):
    """A parser change that quietly matches nothing must fail, not publish a husk."""
    monkeypatch.setattr(build_site, "load_commands", lambda: [])
    rc = build_site.main(["build_site.py", "--out", str(tmp_path)])
    assert rc == 1
    assert not list(tmp_path.iterdir()), "it wrote files despite having no commands"


# --- self-containment -------------------------------------------------------

RESOURCE_RE = re.compile(r'(?:src|href)\s*=\s*"([^"]+)"')
ALLOWED_EXTERNAL_PREFIX = "https://github.com/eugeniughelbur/obsidian-second-brain"


@pytest.mark.parametrize("path", sorted(DOCS.rglob("*.html")), ids=lambda p: p.name)
def test_pages_load_nothing_from_a_third_party(path):
    bad = []
    for ref in RESOURCE_RE.findall(path.read_text(encoding="utf-8")):
        if ref.startswith(("http://", "https://")) and not ref.startswith(ALLOWED_EXTERNAL_PREFIX):
            bad.append(ref)
    assert not bad, (
        f"{path.name} references {bad}. A CDN font or script on a docs page sends "
        "every visitor's IP to a third party for no benefit; everything here is "
        "small enough to inline."
    )


class _Balance(HTMLParser):
    VOID = {"meta", "link", "br", "img", "input", "hr", "source"}

    def __init__(self):
        super().__init__()
        self.stack, self.mismatched = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.mismatched.append(tag)


@pytest.mark.parametrize("path", sorted(DOCS.rglob("*.html")), ids=lambda p: p.name)
def test_pages_are_well_formed(path):
    p = _Balance()
    p.feed(path.read_text(encoding="utf-8"))
    assert not p.stack and not p.mismatched, (
        f"{path.name}: unclosed {p.stack}, mismatched {p.mismatched}"
    )


@pytest.mark.parametrize("path", sorted(DOCS.rglob("*.html")), ids=lambda p: p.name)
def test_every_page_has_a_title_and_description(path):
    text = path.read_text(encoding="utf-8")
    assert re.search(r"<title>[^<]{10,}</title>", text), f"{path.name} has no useful title"
    assert re.search(r'<meta name="description" content="[^"]{20,}"', text), (
        f"{path.name} has no meta description, which is the line a search result shows"
    )


def test_jekyll_is_disabled():
    """Pages runs Jekyll by default and would reprocess the generated HTML."""
    assert (DOCS / ".nojekyll").exists()


def test_index_links_resolve():
    index = (DOCS / "index.html").read_text(encoding="utf-8")
    links = re.findall(r'href="(commands/[^"]+)"', index)
    assert len(links) >= 40, f"index lists only {len(links)} commands"
    missing = [x for x in links if not (DOCS / x).is_file()]
    assert not missing, f"index links to pages that do not exist: {missing}"
