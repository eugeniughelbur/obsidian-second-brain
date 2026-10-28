"""Behavioral tests for source discovery and log-backed ingestion recovery.

These exercise the real helper, not an LLM's extraction or consolidation quality.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import ingest_batch as batch


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "Sources").mkdir()
    (tmp_path / "raw").mkdir()
    return tmp_path


def source(vault, name="note.md", content=b"A source.\r\n"):
    path = vault / "Sources" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def capture(vault, path, name="capture.md"):
    raw = vault / "raw" / name
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("---\ntype: source\nsource_path: " + json.dumps(batch.identity(vault, path))
                   + "\nsource_file_hash: " + batch.digest(path)
                   + "\ncontent_hash: abcdef0123456789\ncapture_scope: full-local\n"
                   "ai-first: true\n---\n\nA retained source.\n", encoding="utf-8")
    return raw.relative_to(vault).as_posix()


def finish(vault, path, raw, source_hash=None, **kwargs):
    return batch.complete(vault, {"source_path": batch.identity(vault, path),
                                 "source_file_hash": source_hash or batch.digest(path),
                                 "raw_path": raw, **kwargs})


def next_batch(vault, **kwargs):
    return batch.plan(vault, vault / "Sources", allow=["Sources"], **kwargs)


@pytest.mark.parametrize("suffix,kind", batch.FORMATS.items())
def test_supported_formats_are_discovered_and_hashed_as_bytes(vault, suffix, kind):
    data = b"\xef\xbb\xbf\x00\xffbinary\r\n"
    path = source(vault, "sample" + suffix.upper(), data)
    result = next_batch(vault)
    assert result["batch"] == [{"source_path": "Sources/" + path.name, "format": kind,
                                "source_file_hash": hashlib.sha256(data).hexdigest(),
                                "raw_path": None}]
    assert path.read_bytes() == data
    assert not (vault / "log.md").exists()


def test_discovery_orders_and_prunes_without_reading_bodies(vault, monkeypatch):
    for name in ("z.txt", "A.pdf", "a.md", "nested/b.mp3", "x.xlsx", ".hidden.md",
                 "Templates/t.md", "raw/generated.md", "Private/secret.md", "Skip/a.md"):
        source(vault, name)
    (vault / ".vault-config.json").write_text(json.dumps({
        "exclude-dirs": ["Skip"], "exclude-paths": ["Sources/Private"],
        "exclude-link-scan": ["Sources/z.txt"],
    }), encoding="utf-8-sig")
    monkeypatch.setattr(batch, "digest", lambda _: pytest.fail("Discovery hashed a file"))
    result = batch.discover(vault, vault / "Sources")
    assert [e["source_path"] for e in result["candidates"]] == [
        "Sources/a.md", "Sources/A.pdf", "Sources/nested/b.mp3", "Sources/z.txt"]
    assert len(result["excluded"]) == 6


def test_office_documents_are_discovered_like_single_source_ingest(vault):
    # Single-source ingest converts these to PDF; folder discovery must not drop them.
    for name in ("report.docx", "legacy.DOC", "notes.odt"):
        source(vault, name)
    result = batch.discover(vault, vault / "Sources")
    assert result["candidates"] == [
        {"source_path": "Sources/legacy.DOC", "format": "document"},
        {"source_path": "Sources/notes.odt", "format": "document"},
        {"source_path": "Sources/report.docx", "format": "document"},
    ]
    assert result["excluded"] == []


def test_permissions_are_applied_before_hashing(vault, monkeypatch):
    source(vault, "Private/a.md")
    public = source(vault, "public.txt")
    original = batch.digest
    read = []

    def track(path):
        read.append(path)
        return original(path)

    monkeypatch.setattr(batch, "digest", track)
    denied = batch.plan(vault, vault / "Sources")
    assert denied["batch"] == [] and len(denied["blocked"]) == 2
    result = next_batch(vault, block=["Sources/Private"])
    assert read == [public]
    assert result["blocked"][0]["source_path"] == "Sources/Private/a.md"


def test_batches_skip_finished_sources_and_preserve_originals(vault):
    before = {source(vault, f"{i}.md"): b"A source.\r\n" for i in range(3)}
    assert len(next_batch(vault, limit=2)["batch"]) == 2
    first = next(iter(before))
    finish(vault, first, capture(vault, first))
    result = next_batch(vault, limit=2)
    assert result["skipped"][0]["source_path"] == "Sources/0.md"
    assert len(result["batch"]) == result["remaining"] == 2
    assert batch.receipts(vault)["Sources/0.md"]["raw_path"] == "raw/capture.md"
    assert all(path.read_bytes() == value for path, value in before.items())
    assert set(p.name for p in vault.iterdir()) == {"Sources", "raw", "log.md"}


def test_interruption_after_capture_reuses_it_on_an_ordinary_rerun(vault):
    path = source(vault, "recording.wav", b"\x00\xffaudio")
    raw = capture(vault, path)
    result = next_batch(vault)
    assert result["batch"][0]["raw_path"] == raw
    assert not (vault / "log.md").exists()
    finish(vault, path, raw)
    assert next_batch(vault)["batch"] == []
    assert len(list((vault / "raw").glob("*.md"))) == 1


def test_capture_without_completion_is_not_skipped(vault):
    path = source(vault)
    raw = capture(vault, path)
    (vault / "log.md").write_text("**10:00** - ingest | note - 1 created\n", encoding="utf-8")
    result = next_batch(vault)
    assert result["batch"][0]["raw_path"] == raw
    assert result["skipped"] == []


def test_unpublished_capture_is_not_reused_until_atomic_publish(vault):
    path = source(vault)
    temporary = capture(vault, path, "capture.tmp")
    assert next_batch(vault)["batch"][0]["raw_path"] is None
    with pytest.raises(ValueError, match="existing source capture"):
        finish(vault, path, temporary)
    (vault / temporary).rename(vault / "raw/capture.md")
    assert next_batch(vault)["batch"][0]["raw_path"] == "raw/capture.md"
    finish(vault, path, "raw/capture.md")
    assert next_batch(vault)["skipped"]


def test_changed_version_is_selected_and_older_captures_are_immutable(vault):
    path = source(vault)
    raw = capture(vault, path, "old.md")
    old_bytes = (vault / raw).read_bytes()
    finish(vault, path, raw)
    path.write_bytes(b"Changed source.")
    assert next_batch(vault)["batch"][0]["raw_path"] is None
    new_raw = capture(vault, path, "new.md")
    finish(vault, path, new_raw)
    assert (vault / raw).read_bytes() == old_bytes
    assert next_batch(vault)["batch"] == []


@pytest.mark.parametrize("unresolved", [
    {"error": "Transcription unavailable"},
    {"pending": ["wiki/concepts/X.md: rewrite declined"]},
    {"status": "pending_approval"},
])
def test_unresolved_work_cannot_be_logged_as_completion(vault, unresolved):
    path = source(vault)
    raw = capture(vault, path)
    with pytest.raises(ValueError, match="Completion requires only"):
        finish(vault, path, raw, **unresolved)
    result = next_batch(vault)
    assert result["batch"][0]["raw_path"] == raw
    assert result["skipped"] == []
    assert not (vault / "log.md").exists()


def test_missing_capture_and_mid_ingest_edit_prevent_false_completion(vault):
    path = source(vault)
    source_hash = batch.digest(path)
    with pytest.raises(ValueError, match="existing source capture"):
        finish(vault, path, "raw/missing.md")
    raw = capture(vault, path)
    path.write_bytes(b"Human edit while ingest runs.")
    with pytest.raises(ValueError, match="Source changed"):
        finish(vault, path, raw, source_hash)
    assert not (vault / "log.md").exists()
    assert next_batch(vault)["batch"]


def test_deleted_capture_makes_completed_source_eligible_again(vault):
    path = source(vault)
    raw = capture(vault, path)
    finish(vault, path, raw)
    (vault / raw).unlink()
    assert next_batch(vault)["batch"][0]["raw_path"] is None


def test_logs_are_append_only_and_daily_receipts_survive_new_sessions(vault):
    (vault / "Logs").mkdir()
    (vault / "log.md").write_bytes(b"Daily log pointer.\r\n")
    path = source(vault)
    raw = capture(vault, path)
    finish(vault, path, raw)
    log = next((vault / "Logs").glob("*.md"))
    before = log.read_bytes()
    path.write_bytes(b"A new version.")
    finish(vault, path, capture(vault, path, "new.md"))
    assert log.read_bytes().startswith(before)
    assert (vault / "log.md").read_bytes() == b"Daily log pointer.\r\n"
    assert "## For future agent" in log.read_text(encoding="utf-8")
    assert next_batch(vault)["skipped"]


def test_torn_append_is_not_a_completion_record(vault):
    path = source(vault)
    raw = capture(vault, path)
    with (vault / "log.md").open("a", encoding="utf-8") as stream:
        stream.write(batch.MARKER + '{"source_path":"Sources/note.md"')
    assert not batch.receipts(vault)
    assert next_batch(vault)["batch"][0]["raw_path"] == raw
    finish(vault, path, raw)
    assert next_batch(vault)["skipped"]


def test_invalid_receipts_and_exclusions_fail_visibly(vault):
    source(vault)
    (vault / "log.md").write_text(batch.MARKER + '{"v":1} -->\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid ingest-complete"):
        next_batch(vault)
    (vault / "log.md").unlink()
    (vault / ".vault-config.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        next_batch(vault)


def test_overlap_and_invalid_batch_sizes_are_rejected(vault):
    source(vault)
    with pytest.raises(ValueError, match="overlap"):
        next_batch(vault, outputs=["Sources/derived"])
    with pytest.raises(ValueError, match="positive"):
        next_batch(vault, limit=0)


def test_external_collections_use_absolute_identity_without_first_brain(vault, tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-external")
    external.mkdir()
    path = external / "photo.png"
    path.write_bytes(b"image bytes")
    result = batch.plan(vault, external, allow=[external])
    assert result["batch"][0]["source_path"] == path.resolve().as_posix()


def test_linked_sources_are_not_followed(vault, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "secret.md").write_bytes(b"secret")
    try:
        (vault / "Sources" / "link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit creating directory symlinks")
    assert batch.discover(vault, vault / "Sources")["candidates"] == []


def test_cli_reports_json_and_uses_stdin_for_completion(vault):
    path = source(vault)
    script = Path(batch.__file__)
    command = [sys.executable, str(script), "--vault", str(vault)]
    result = subprocess.run([*command, "plan", "Sources", "--allow", "Sources"],
                            capture_output=True, text=True, check=True)
    item = json.loads(result.stdout)["batch"][0]
    outcome = {key: item[key] for key in ("source_path", "source_file_hash")}
    outcome["raw_path"] = capture(vault, path)
    result = subprocess.run([*command, "complete"], input=json.dumps(outcome),
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["raw_path"] == outcome["raw_path"]
    result = subprocess.run([*command, "plan", "Sources", "--allow", "Sources"],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["skipped"]


def test_custom_raw_route_is_used_for_recovery(vault):
    path = source(vault)
    raw = capture(vault, path)
    custom = vault / "Evidence"
    (vault / "raw").rename(custom)
    raw = "Evidence/" + Path(raw).name
    batch.complete(vault, {"source_path": "Sources/note.md",
                           "source_file_hash": batch.digest(path), "raw_path": raw},
                   raw_root="Evidence")
    assert next_batch(vault, raw_root="Evidence")["skipped"]


def test_completion_adds_only_one_hidden_line_to_existing_log(vault):
    path = source(vault)
    (vault / "log.md").write_bytes(b"An existing ingestion summary.\r\n")
    before = (vault / "log.md").read_bytes()
    finish(vault, path, capture(vault, path))
    addition = (vault / "log.md").read_bytes()[len(before):].decode("utf-8")
    assert len(addition.splitlines()) == 2  # separator plus one comment
    event = json.loads(addition.strip()[len(batch.MARKER):-4])
    assert set(event) == {"source_path", "source_file_hash", "raw_path", "timestamp"}
    assert len(addition) < 350


def test_reverting_to_an_older_version_is_not_mistaken_for_current_completion(vault):
    original = b"An original version."
    path = source(vault, content=original)
    raw = capture(vault, path, "old.md")
    finish(vault, path, raw)
    path.write_bytes(b"A newer version.")
    finish(vault, path, capture(vault, path, "new.md"))
    path.write_bytes(original)
    assert next_batch(vault)["batch"][0]["raw_path"] == raw
    assert next_batch(vault)["skipped"] == []


def test_bad_raw_metadata_never_leaves_a_partially_loaded_capture_index(vault):
    for name in ("a.md", "b.md"):
        path = source(vault, name)
        capture(vault, path, name)
    (vault / "raw" / "0-bad.md").write_text("---\ntype: [\n---\n", encoding="utf-8")
    result = next_batch(vault)
    assert result["batch"] == []
    assert len(result["failed"]) == 2


def test_unreadable_subtree_is_reported_instead_of_silently_omitted(vault, monkeypatch):
    def unreadable_walk(*args, onerror, **kwargs):
        onerror(PermissionError("Unreadable source subtree"))

    monkeypatch.setattr(batch.os, "walk", unreadable_walk)
    with pytest.raises(PermissionError, match="Unreadable source subtree"):
        batch.discover(vault, vault / "Sources")
