"""A JSON transcript that uses `segments[].text` must be read, not discarded.

`_parse_json_transcript` only accepted the Podcast Index spelling of the
per-segment string, `body`. Whisper-derived exports spell the same field
`text`, and several hosts ship those: flightcast (the host behind SOLVED with
Mark Manson, where this was found), Deepgram, AssemblyAI. On those feeds the
transcript tag resolved, the file downloaded, and the parser then returned None
and let the caller fall through to a show-notes-only summary. The user gets a
much thinner note with an empty Notable Quotes section, and nothing in the
output says a full transcript was in hand and dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def test_whisper_style_text_segments_are_read():
    from research.lib.podcast import _parse_json_transcript

    # Shape as served by flightcast, extra Whisper fields included verbatim.
    body = json.dumps(
        {
            "segments": [
                {"start": 0.0, "end": 3.2, "text": "So a lot of people", "avg_logprob": -0.2},
                {"start": 3.2, "end": 6.1, "text": "don't know this.", "avg_logprob": -0.3},
            ]
        }
    )
    assert _parse_json_transcript(body) == "So a lot of people don't know this."


def test_podcast_index_body_segments_still_win():
    from research.lib.podcast import _parse_json_transcript

    body = json.dumps({"segments": [{"body": "first"}, {"body": "second"}]})
    assert _parse_json_transcript(body) == "first second"


def test_segments_with_neither_field_still_return_none():
    from research.lib.podcast import _parse_json_transcript

    body = json.dumps({"segments": [{"start": 0.0, "end": 1.0}]})
    assert _parse_json_transcript(body) is None


def test_empty_strings_do_not_count_as_a_transcript():
    from research.lib.podcast import _parse_json_transcript

    body = json.dumps({"segments": [{"text": ""}, {"text": "   "}]})
    assert _parse_json_transcript(body) is None
