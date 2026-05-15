# Overview Pipeline Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a local anime episode file ingested via CLI, drive an end-to-end pipeline that produces a rendered ~45-60s overview commentary short (vertical 9:16 MP4) in `data/output/` and Supabase Storage, with state tracked in Supabase Postgres.

**Architecture:** A state-machine-driven orchestrator advances rows through statuses (`detected → downloaded → transcribed → script_ready → voice_ready → rendered`). Each transition is one idempotent stage: a Python module reading the row's current state, doing the work (transcribe / generate script via Claude / synthesize via edge-tts / assemble via FFmpeg), persisting the artifact (upload to Supabase Storage), and updating the row. Auto-acquisition (ani-cli) and crowd-summary fallback are deferred to Plan 3.

**Tech Stack:** Python 3.12+, FFmpeg (subprocess), whisper.cpp (subprocess, small.en model), httpx (AniList GraphQL), Click, pytest. Reuses `tools/llm_client.py`, `tools/tts_client.py`, `tools/supabase_client.py`, `tools/channel_config.py` from Plan 1. Reuses `shared_tools/burn_captions.py` for ASS subtitle burning.

**Reference:** Design spec at `docs/superpowers/specs/2026-05-15-anime-commentary-pipeline-design.md` §5 (data flow) and §6 (state machine).

---

## State Machine (per-shorts row)

```
detected
  → downloaded         (file_url set in episodes row; status of shorts row "detected")
    → transcribed      (transcript_url set on episodes row)
      → script_ready   (script_text set on shorts row)
        → voice_ready  (audio_url set on shorts row)
          → rendered   (video_url set on shorts row)

Failure terminal states (per shorts row):
  transcription_failed, script_failed, tts_failed, render_failed
```

Plan 2 covers `detected → rendered`. Confidence gate + publish flow (`rendered → auto_publish_queued → published`) is Plan 4.

---

## Task 1: Supabase client helpers

Closes a follow-up flagged in Plan 1's final review: the orchestrator needs `get_short`, `update_short`, `get_episode`, and `append_job_log`.

**Files:**
- Modify: `tools/supabase_client.py`
- Modify: `tests/unit/test_supabase_client.py`

- [ ] **Step 1: Write failing tests for the new helpers**

Add to `tests/unit/test_supabase_client.py`:

```python
def test_get_short_returns_row():
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": 7, "status": "rendered", "platform": "youtube"
    }
    row = sb.get_short(client, 7)
    assert row["id"] == 7
    client.table.assert_called_once_with("shorts")


def test_update_short_without_status_change():
    client = MagicMock()
    sb.update_short(client, 7, video_url="output/7.mp4", duration_sec=47.3)
    update_kwargs = client.table.return_value.update.call_args[0][0]
    assert "status" not in update_kwargs
    assert update_kwargs["video_url"] == "output/7.mp4"
    assert update_kwargs["duration_sec"] == 47.3


def test_get_episode_returns_row():
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": 1, "title": "Frieren", "episode_num": 12, "status": "downloaded"
    }
    row = sb.get_episode(client, 1)
    assert row["title"] == "Frieren"


def test_append_job_log_inserts_job_row():
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [{"id": 99}]
    out = sb.append_job_log(client, kind="render", status="ok", payload={"short_id": 7}, log="rendered in 4.2s")
    assert out["id"] == 99
    client.table.assert_called_once_with("jobs")
    insert_kwargs = client.table.return_value.insert.call_args[0][0]
    assert insert_kwargs["kind"] == "render"
    assert insert_kwargs["status"] == "ok"
    assert insert_kwargs["log"] == "rendered in 4.2s"
```

- [ ] **Step 2: Run tests — expect failures**

Run: `pytest tests/unit/test_supabase_client.py::test_get_short_returns_row -v`
Expected: FAIL — `AttributeError: module 'tools.supabase_client' has no attribute 'get_short'`

- [ ] **Step 3: Add the helpers to `tools/supabase_client.py`**

Append to the file:

```python
def get_short(client: Client, short_id: int) -> dict[str, Any]:
    res = client.table("shorts").select("*").eq("id", short_id).single().execute()
    return res.data


def update_short(client: Client, short_id: int, **fields: Any) -> dict[str, Any]:
    """Update fields on a short row WITHOUT changing status. Use update_short_status to change status."""
    res = client.table("shorts").update(fields).eq("id", short_id).execute()
    return res.data[0] if res.data else {}


def get_episode(client: Client, episode_id: int) -> dict[str, Any]:
    res = client.table("episodes").select("*").eq("id", episode_id).single().execute()
    return res.data


def append_job_log(client: Client, kind: str, status: str,
                   payload: dict[str, Any] | None = None,
                   log: str = "") -> dict[str, Any]:
    """Insert a row in the jobs table for observability."""
    row = {"kind": kind, "status": status, "log": log}
    if payload is not None:
        row["payload"] = payload
    res = client.table("jobs").insert(row).execute()
    return res.data[0]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_supabase_client.py -v`
Expected: all 10 tests PASS (6 original + 4 new).

- [ ] **Step 5: Commit**

```bash
git add tools/supabase_client.py tests/unit/test_supabase_client.py
git commit -m "feat(supabase): add get_short, update_short, get_episode, append_job_log"
```

---

## Task 2: Slug-uniqueness check in channel_config

Closes another Plan 1 follow-up: two YAMLs with the same `slug:` would silently load both, breaking per-channel routing.

**Files:**
- Modify: `tools/channel_config.py`
- Modify: `tests/unit/test_channel_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_channel_config.py`:

```python
def test_discover_channels_raises_on_duplicate_slugs(tmp_path, fixture_dir):
    src = (fixture_dir / "channel_minimal.yaml").read_text()
    (tmp_path / "a.yaml").write_text(src)              # slug=minimal
    (tmp_path / "b.yaml").write_text(src)              # also slug=minimal
    with pytest.raises(ChannelConfigError, match="duplicate slug"):
        discover_channels(tmp_path)
```

- [ ] **Step 2: Run test — expect failure**

Run: `pytest tests/unit/test_channel_config.py::test_discover_channels_raises_on_duplicate_slugs -v`
Expected: FAIL — `DID NOT RAISE`

- [ ] **Step 3: Add the check to `discover_channels`**

Modify the function body:

```python
def discover_channels(directory: str | Path) -> list[ChannelConfig]:
    """Load all .yaml channel files under `directory`. Skips files ending .yaml.disabled."""
    d = Path(directory)
    if not d.is_dir():
        return []
    out: list[ChannelConfig] = []
    seen_slugs: dict[str, Path] = {}
    for f in sorted(d.glob("*.yaml")):
        cfg = load_channel(f)
        if cfg.slug in seen_slugs:
            raise ChannelConfigError(
                f"duplicate slug '{cfg.slug}' in {f} (already loaded from {seen_slugs[cfg.slug]})"
            )
        seen_slugs[cfg.slug] = f
        out.append(cfg)
    return out
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/unit/test_channel_config.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/channel_config.py tests/unit/test_channel_config.py
git commit -m "feat(channel_config): raise on duplicate channel slug"
```

---

## Task 3: Refactor `load_dotenv()` out of `shared_tools/*` module scope

Closes Plan 1 follow-up I-3. Importing any vendored shared tool currently invokes `load_dotenv()` as a side effect, which can re-inject env vars stripped by tests' `isolate_env` autouse fixture.

**Files (all modify):**
- `shared_tools/generate_script.py`
- `shared_tools/generate_voiceover.py`
- `shared_tools/burn_captions.py`
- `shared_tools/transcribe_video.py`

- [ ] **Step 1: Identify the affected lines**

Run: `cd "/home/sh4d0w/agentic coding projects/anime-commentary" && grep -n 'load_dotenv' shared_tools/*.py`

Expected: 4 lines, one per file, all at module scope.

- [ ] **Step 2: Move each `load_dotenv()` invocation**

For each of the 4 files, find the line:

```python
load_dotenv()
```

Replace with a guarded version that only runs when the module is executed as a script:

```python
# (delete the bare `load_dotenv()` line)
# Add at the BOTTOM of the file, inside `if __name__ == "__main__":`
```

Concretely, in each file find the existing `if __name__ == "__main__":` block (every vendored tool has one — they're CLI entrypoints) and add `load_dotenv()` as the **first** statement inside it. The bare top-level `load_dotenv()` line is deleted.

Example (`shared_tools/generate_script.py`):

```python
# BEFORE: at module top
from dotenv import load_dotenv
load_dotenv()

# AFTER: keep the import; remove the bare call; add inside the __main__ block:
if __name__ == "__main__":
    load_dotenv()
    # ... rest of CLI code unchanged
```

Apply the same change in the other 3 files. Do NOT remove the `from dotenv import load_dotenv` import — it's still needed inside `__main__`.

- [ ] **Step 3: Verify side effect gone**

Run: `cd "/home/sh4d0w/agentic coding projects/anime-commentary" && python -c "import os; os.environ.pop('OPENAI_API_KEY', None); import shared_tools.generate_script; assert 'OPENAI_API_KEY' not in os.environ, 'load_dotenv still firing at import time'; print('OK')"`

Expected: `OK`. If it fails (env var got re-injected), check that the file you edited still doesn't have a top-level `load_dotenv()`.

- [ ] **Step 4: Confirm full test suite still passes**

Run: `pytest -m "not slow" 2>&1 | tail -3`
Expected: `39 passed` (or current count) — no regressions.

- [ ] **Step 5: Commit**

```bash
git add shared_tools/
git commit -m "fix(shared_tools): scope load_dotenv() to __main__ blocks only"
```

---

## Task 4: State machine module

Centralizes status constants and valid transitions. Used by every pipeline stage.

**Files:**
- Create: `tools/state_machine.py`
- Create: `tests/unit/test_state_machine.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_state_machine.py`:

```python
import pytest
from tools.state_machine import (
    EPISODE_STATES,
    SHORT_STATES,
    advance_short,
    advance_episode,
    InvalidTransition,
)


def test_short_states_include_pipeline_steps():
    for s in ("detected", "transcribed", "script_ready", "voice_ready", "rendered"):
        assert s in SHORT_STATES


def test_episode_states_include_acquisition_steps():
    for s in ("detected", "downloaded", "transcribed"):
        assert s in EPISODE_STATES


def test_advance_short_legal_transition():
    assert advance_short("detected", "transcribed") == "transcribed"


def test_advance_short_illegal_transition_raises():
    with pytest.raises(InvalidTransition):
        advance_short("rendered", "detected")  # going backwards


def test_advance_short_to_failure_state_always_allowed():
    assert advance_short("script_ready", "script_failed") == "script_failed"
    assert advance_short("voice_ready", "tts_failed") == "tts_failed"


def test_advance_episode_legal_transition():
    assert advance_episode("downloaded", "transcribed") == "transcribed"


def test_advance_episode_unknown_target_raises():
    with pytest.raises(InvalidTransition):
        advance_episode("downloaded", "bogus_state")
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_state_machine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/state_machine.py`**

```python
"""Pipeline state machine — status constants and legal transitions.

Each status update goes through `advance_short()` / `advance_episode()` to enforce
forward-only progress (except to failure terminals, which are always allowed).
"""
from __future__ import annotations


class InvalidTransition(ValueError):
    """Raised when a status transition is not allowed."""


# Episode-level states (set on episodes.status)
EPISODE_STATES: tuple[str, ...] = (
    "detected",
    "downloaded",
    "transcribed",
    "acquisition_failed",
    "transcription_failed",
)

_EPISODE_LEGAL_NEXT: dict[str, set[str]] = {
    "detected":   {"downloaded", "acquisition_failed"},
    "downloaded": {"transcribed", "transcription_failed"},
    "transcribed": set(),  # terminal-ish for episode; shorts take over
}

# Short-level states (set on shorts.status)
SHORT_STATES: tuple[str, ...] = (
    "detected",
    "transcribed",
    "script_ready",
    "voice_ready",
    "rendered",
    "auto_publish_queued",
    "review_queued",
    "publishing",
    "published",
    "script_failed",
    "tts_failed",
    "render_failed",
    "confidence_check_failed",
    "publish_failed",
    "rejected",
    "abandoned",
)

_SHORT_LEGAL_NEXT: dict[str, set[str]] = {
    "detected":            {"transcribed"},
    "transcribed":         {"script_ready", "script_failed"},
    "script_ready":        {"voice_ready", "tts_failed"},
    "voice_ready":         {"rendered", "render_failed"},
    "rendered":            {"auto_publish_queued", "review_queued", "confidence_check_failed"},
    "review_queued":       {"auto_publish_queued", "rejected"},
    "auto_publish_queued": {"publishing"},
    "publishing":          {"published", "publish_failed"},
}

# Failure states are always reachable from any non-terminal state
_FAILURE_STATES: set[str] = {
    "script_failed", "tts_failed", "render_failed",
    "confidence_check_failed", "publish_failed",
    "rejected", "abandoned",
}


def advance_short(current: str, target: str) -> str:
    """Return `target` if the transition is legal; else raise InvalidTransition."""
    if target not in SHORT_STATES:
        raise InvalidTransition(f"unknown short state: {target!r}")
    if target in _FAILURE_STATES:
        return target
    legal = _SHORT_LEGAL_NEXT.get(current, set())
    if target not in legal:
        raise InvalidTransition(f"shorts: {current!r} -> {target!r} not allowed")
    return target


def advance_episode(current: str, target: str) -> str:
    """Return `target` if the transition is legal; else raise InvalidTransition."""
    if target not in EPISODE_STATES:
        raise InvalidTransition(f"unknown episode state: {target!r}")
    legal = _EPISODE_LEGAL_NEXT.get(current, set())
    if target not in legal:
        raise InvalidTransition(f"episodes: {current!r} -> {target!r} not allowed")
    return target
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_state_machine.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/state_machine.py tests/unit/test_state_machine.py
git commit -m "feat: state machine for episode + short status transitions"
```

---

## Task 5: AniList GraphQL client (metadata + visuals)

Fetches anime metadata (title, episode count, season, cover/banner images, etc.) by AniList media ID. Used in Task 6 to download visuals and in Plan 3 for polling.

**Files:**
- Create: `tools/anilist_client.py`
- Create: `tests/unit/test_anilist_client.py`
- Create: `tests/fixtures/anilist_media_sample.json`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/anilist_media_sample.json`:

```json
{
  "data": {
    "Media": {
      "id": 154587,
      "title": {
        "romaji": "Sousou no Frieren",
        "english": "Frieren: Beyond Journey's End"
      },
      "coverImage": {
        "extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/frieren.jpg",
        "color": "#5670e4"
      },
      "bannerImage": "https://s4.anilist.co/file/anilistcdn/media/anime/banner/154587.jpg",
      "episodes": 28,
      "season": "FALL",
      "seasonYear": 2023,
      "genres": ["Adventure", "Drama", "Fantasy"],
      "averageScore": 91,
      "description": "Frieren the Elf...",
      "studios": {
        "nodes": [{"name": "MADHOUSE"}]
      },
      "nextAiringEpisode": null
    }
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_anilist_client.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from tools import anilist_client


def _load_sample(fixture_dir):
    return json.loads((fixture_dir / "anilist_media_sample.json").read_text())


def test_fetch_media_returns_parsed_payload(fixture_dir):
    sample = _load_sample(fixture_dir)
    mock_response = MagicMock()
    mock_response.json.return_value = sample
    mock_response.raise_for_status = MagicMock()
    with patch("tools.anilist_client.httpx.post", return_value=mock_response) as post:
        media = anilist_client.fetch_media(154587)
    assert media["id"] == 154587
    assert media["title"]["english"] == "Frieren: Beyond Journey's End"
    assert media["bannerImage"].endswith("154587.jpg")
    # Verify the request shape
    args, kwargs = post.call_args
    assert kwargs["json"]["variables"] == {"id": 154587}
    assert "query" in kwargs["json"]


def test_fetch_media_raises_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("503")
    with patch("tools.anilist_client.httpx.post", return_value=mock_response):
        with pytest.raises(Exception, match="503"):
            anilist_client.fetch_media(1)


def test_fetch_media_raises_on_null_media():
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"Media": None}}
    mock_response.raise_for_status = MagicMock()
    with patch("tools.anilist_client.httpx.post", return_value=mock_response):
        with pytest.raises(anilist_client.AniListError, match="not found"):
            anilist_client.fetch_media(999999999)
```

- [ ] **Step 3: Run tests — expect failure**

Run: `pytest tests/unit/test_anilist_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `tools/anilist_client.py`**

```python
"""AniList GraphQL client.

Used to fetch anime metadata + key visuals. No auth required; rate-limited
to 90 req/min unauthenticated (we stay well under).
"""
from __future__ import annotations
import httpx
from typing import Any

ANILIST_API = "https://graphql.anilist.co"
DEFAULT_TIMEOUT = 30.0


class AniListError(RuntimeError):
    """Raised when AniList returns no data or an unexpected response."""


_MEDIA_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    id
    title { romaji english native }
    coverImage { extraLarge color }
    bannerImage
    episodes
    season
    seasonYear
    genres
    averageScore
    description(asHtml: false)
    studios(isMain: true) { nodes { name } }
    nextAiringEpisode { episode airingAt }
  }
}
"""


def fetch_media(anilist_id: int, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Fetch full media metadata by AniList ID. Returns the Media dict.

    Raises AniListError if the media is not found, or httpx errors on HTTP failure.
    """
    response = httpx.post(
        ANILIST_API,
        json={"query": _MEDIA_QUERY, "variables": {"id": anilist_id}},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    media = body.get("data", {}).get("Media")
    if media is None:
        raise AniListError(f"AniList media id={anilist_id} not found")
    return media
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `pytest tests/unit/test_anilist_client.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/anilist_client.py tests/unit/test_anilist_client.py tests/fixtures/anilist_media_sample.json
git commit -m "feat: AniList GraphQL client (fetch_media by id)"
```

---

## Task 6: extract_subs — embedded subs first, whisper.cpp fallback

Extracts a word-level transcript from an episode file. Prefers embedded subtitle streams (often present in ani-cli/torrent rips); falls back to `whisper.cpp` small.en if no usable embedded subs.

**Files:**
- Create: `tools/extract_subs.py`
- Create: `tests/unit/test_extract_subs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_extract_subs.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tools import extract_subs


def test_has_subtitle_stream_true_when_ffprobe_returns_indices():
    fake_proc = MagicMock(stdout="0\n1\n", returncode=0)
    with patch("tools.extract_subs.subprocess.run", return_value=fake_proc):
        assert extract_subs.has_subtitle_stream("any.mp4") is True


def test_has_subtitle_stream_false_when_empty():
    fake_proc = MagicMock(stdout="\n", returncode=0)
    with patch("tools.extract_subs.subprocess.run", return_value=fake_proc):
        assert extract_subs.has_subtitle_stream("any.mp4") is False


def test_extract_embedded_subs_returns_segments(tmp_path):
    """Embedded-sub path writes srt via ffmpeg, then parses to {start, end, text}."""
    srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n2\n00:00:04,000 --> 00:00:05,500\nGoodbye\n"
    fake_proc = MagicMock(returncode=0)

    def fake_run(cmd, **kwargs):
        # ffmpeg call writes the srt to the path in cmd
        out_path = cmd[-1]
        Path(out_path).write_text(srt_content)
        return fake_proc

    with patch("tools.extract_subs.subprocess.run", side_effect=fake_run):
        segments = extract_subs.extract_embedded_subs(str(tmp_path / "vid.mp4"))

    assert len(segments) == 2
    assert segments[0] == {"start": 1.0, "end": 3.0, "text": "Hello world"}
    assert segments[1] == {"start": 4.0, "end": 5.5, "text": "Goodbye"}


def test_extract_with_whisper_cpp_parses_json(tmp_path):
    """When no embedded subs, fall through to whisper.cpp which emits JSON."""
    whisper_json = {
        "transcription": [
            {"offsets": {"from": 500, "to": 1500}, "text": "first line"},
            {"offsets": {"from": 1600, "to": 3000}, "text": "second line"},
        ]
    }

    fake_proc = MagicMock(returncode=0)

    def fake_run(cmd, **kwargs):
        # whisper.cpp writes <output_prefix>.json
        # The cmd has -of <prefix>; grab it
        of_idx = cmd.index("-of")
        prefix = cmd[of_idx + 1]
        Path(prefix + ".json").write_text(json.dumps(whisper_json))
        return fake_proc

    with patch("tools.extract_subs.subprocess.run", side_effect=fake_run):
        segments = extract_subs.extract_with_whisper_cpp(
            str(tmp_path / "audio.wav"),
            model_path="dummy-model.bin",
        )

    assert len(segments) == 2
    assert segments[0] == {"start": 0.5, "end": 1.5, "text": "first line"}
    assert segments[1] == {"start": 1.6, "end": 3.0, "text": "second line"}


def test_extract_transcript_prefers_embedded_when_present(tmp_path):
    """Integration: extract_transcript() picks embedded path if has_subtitle_stream True."""
    fake_segments = [{"start": 0, "end": 1, "text": "hi"}]
    with patch("tools.extract_subs.has_subtitle_stream", return_value=True), \
         patch("tools.extract_subs.extract_embedded_subs", return_value=fake_segments) as emb, \
         patch("tools.extract_subs.extract_with_whisper_cpp") as wcpp:
        result = extract_subs.extract_transcript(str(tmp_path / "vid.mp4"))
    assert result == fake_segments
    emb.assert_called_once()
    wcpp.assert_not_called()


def test_extract_transcript_falls_back_to_whisper_when_no_subs(tmp_path, monkeypatch):
    fake_segments = [{"start": 0, "end": 1, "text": "hi"}]
    monkeypatch.setenv("WHISPER_CPP_MODEL", "model.bin")
    with patch("tools.extract_subs.has_subtitle_stream", return_value=False), \
         patch("tools.extract_subs._extract_audio_track") as extract_audio, \
         patch("tools.extract_subs.extract_with_whisper_cpp", return_value=fake_segments) as wcpp:
        extract_audio.return_value = str(tmp_path / "audio.wav")
        result = extract_subs.extract_transcript(str(tmp_path / "vid.mp4"))
    assert result == fake_segments
    wcpp.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_extract_subs.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/extract_subs.py`**

```python
"""Transcript extraction.

Strategy:
1. Use ffprobe to detect embedded subtitle streams. If present, extract one to SRT
   via ffmpeg and parse it.
2. Otherwise, extract audio via ffmpeg → WAV 16kHz mono and run whisper.cpp small.en
   for word-level transcription.

The returned shape is a list of {"start": float, "end": float, "text": str} segments.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


SrtPattern = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*\n"
    r"(.*?)(?=\n\n|\Z)",
    re.DOTALL,
)


def has_subtitle_stream(video_path: str) -> bool:
    """Return True if ffprobe finds at least one subtitle stream."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=15,
    )
    return bool(result.stdout.strip())


def _srt_time_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _parse_srt(text: str) -> list[dict]:
    segments: list[dict] = []
    for m in SrtPattern.finditer(text):
        start = _srt_time_to_sec(m.group(2), m.group(3), m.group(4), m.group(5))
        end = _srt_time_to_sec(m.group(6), m.group(7), m.group(8), m.group(9))
        line = m.group(10).strip().replace("\n", " ")
        segments.append({"start": start, "end": end, "text": line})
    return segments


def extract_embedded_subs(video_path: str, stream_index: int = 0) -> list[dict]:
    """Extract the first embedded subtitle stream to SRT and parse."""
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
        srt_path = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", video_path,
             "-map", f"0:s:{stream_index}",
             "-c:s", "srt",
             srt_path],
            check=True, timeout=120,
        )
        return _parse_srt(Path(srt_path).read_text(encoding="utf-8", errors="replace"))
    finally:
        Path(srt_path).unlink(missing_ok=True)


def _extract_audio_track(video_path: str, output_wav: str) -> str:
    """Extract audio as 16kHz mono WAV (whisper.cpp's preferred format)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", video_path,
         "-vn", "-ac", "1", "-ar", "16000", "-f", "wav",
         output_wav],
        check=True, timeout=300,
    )
    return output_wav


def extract_with_whisper_cpp(audio_wav_path: str, model_path: str,
                             whisper_bin: str = "whisper-cli") -> list[dict]:
    """Run whisper.cpp on a WAV; parse its JSON output to {start, end, text}."""
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as f:
        prefix = f.name
    try:
        subprocess.run(
            [whisper_bin,
             "-m", model_path,
             "-f", audio_wav_path,
             "-oj",  # output JSON
             "-of", prefix],
            check=True, timeout=900,
        )
        data = json.loads(Path(prefix + ".json").read_text())
        segments: list[dict] = []
        for entry in data.get("transcription", []):
            start_ms = entry["offsets"]["from"]
            end_ms = entry["offsets"]["to"]
            segments.append({
                "start": start_ms / 1000.0,
                "end": end_ms / 1000.0,
                "text": entry["text"].strip(),
            })
        return segments
    finally:
        Path(prefix + ".json").unlink(missing_ok=True)


def extract_transcript(video_path: str, model_path: str | None = None) -> list[dict]:
    """Return list of {start, end, text} for a video, preferring embedded subs."""
    if has_subtitle_stream(video_path):
        return extract_embedded_subs(video_path)
    model = model_path or os.environ.get("WHISPER_CPP_MODEL")
    if not model:
        raise RuntimeError(
            "no embedded subtitles and WHISPER_CPP_MODEL env var not set"
        )
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        _extract_audio_track(video_path, wav_path)
        return extract_with_whisper_cpp(wav_path, model)
    finally:
        Path(wav_path).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_extract_subs.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/extract_subs.py tests/unit/test_extract_subs.py
git commit -m "feat: extract_subs (embedded SRT + whisper.cpp fallback)"
```

---

## Task 7: fetch_anime_visuals — download AniList key art

Downloads cover image + banner from AniList to local cache. Returns list of file paths suitable for the visual assembler.

**Files:**
- Create: `tools/fetch_anime_visuals.py`
- Create: `tests/unit/test_fetch_anime_visuals.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_fetch_anime_visuals.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tools import fetch_anime_visuals


def test_fetch_visuals_downloads_cover_and_banner(tmp_path, fixture_dir):
    media = {
        "id": 154587,
        "title": {"romaji": "Sousou no Frieren"},
        "coverImage": {"extraLarge": "https://example/cover.jpg", "color": "#5670e4"},
        "bannerImage": "https://example/banner.jpg",
    }

    fake_resp_cover = MagicMock()
    fake_resp_cover.content = b"COVER_BYTES"
    fake_resp_cover.raise_for_status = MagicMock()

    fake_resp_banner = MagicMock()
    fake_resp_banner.content = b"BANNER_BYTES"
    fake_resp_banner.raise_for_status = MagicMock()

    with patch("tools.fetch_anime_visuals.httpx.get",
               side_effect=[fake_resp_cover, fake_resp_banner]):
        paths = fetch_anime_visuals.fetch_visuals(media, cache_dir=str(tmp_path))

    assert len(paths) == 2
    assert all(Path(p).exists() for p in paths)
    assert Path(paths[0]).read_bytes() == b"COVER_BYTES"
    assert Path(paths[1]).read_bytes() == b"BANNER_BYTES"


def test_fetch_visuals_skips_missing_banner(tmp_path):
    media = {
        "id": 1,
        "title": {"romaji": "x"},
        "coverImage": {"extraLarge": "https://example/cover.jpg"},
        "bannerImage": None,
    }
    fake_resp = MagicMock()
    fake_resp.content = b"COVER_BYTES"
    fake_resp.raise_for_status = MagicMock()
    with patch("tools.fetch_anime_visuals.httpx.get", return_value=fake_resp):
        paths = fetch_anime_visuals.fetch_visuals(media, cache_dir=str(tmp_path))
    assert len(paths) == 1


def test_fetch_visuals_uses_cache_dir(tmp_path):
    """File names should include the AniList ID so different anime don't collide."""
    media = {
        "id": 12345,
        "title": {"romaji": "x"},
        "coverImage": {"extraLarge": "https://example/cover.jpg"},
        "bannerImage": "https://example/banner.jpg",
    }
    fake_resp = MagicMock()
    fake_resp.content = b"x"
    fake_resp.raise_for_status = MagicMock()
    with patch("tools.fetch_anime_visuals.httpx.get", return_value=fake_resp):
        paths = fetch_anime_visuals.fetch_visuals(media, cache_dir=str(tmp_path))
    for p in paths:
        assert "12345" in Path(p).name
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_fetch_anime_visuals.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/fetch_anime_visuals.py`**

```python
"""Download AniList key visuals (cover, banner) to local cache.

These images feed the visual assembler for overview shorts. Format-safe (JPEG/PNG
content-type respected by AniList CDN).
"""
from __future__ import annotations
import httpx
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT = 30.0


def _download(url: str, dest_path: Path, timeout: float = DEFAULT_TIMEOUT) -> Path:
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(resp.content)
    return dest_path


def fetch_visuals(media: dict[str, Any], cache_dir: str = ".tmp/visuals") -> list[str]:
    """Download cover + banner images for an AniList Media dict.

    Args:
        media: AniList Media dict (from anilist_client.fetch_media).
        cache_dir: directory to write images into.

    Returns:
        List of local file paths in canonical order: [cover, banner] (banner may be omitted).
    """
    out: list[str] = []
    anilist_id = media["id"]
    cache = Path(cache_dir)

    cover_url = media.get("coverImage", {}).get("extraLarge")
    if cover_url:
        suffix = Path(cover_url).suffix or ".jpg"
        cover_path = cache / f"{anilist_id}_cover{suffix}"
        _download(cover_url, cover_path)
        out.append(str(cover_path))

    banner_url = media.get("bannerImage")
    if banner_url:
        suffix = Path(banner_url).suffix or ".jpg"
        banner_path = cache / f"{anilist_id}_banner{suffix}"
        _download(banner_url, banner_path)
        out.append(str(banner_path))

    return out
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_fetch_anime_visuals.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_anime_visuals.py tests/unit/test_fetch_anime_visuals.py
git commit -m "feat: fetch_anime_visuals (AniList key art downloader)"
```

---

## Task 8: script_generator — Claude → overview commentary

Given an episode transcript (or summary) + channel persona, calls Claude to produce a structured commentary script targeting 45-60 seconds of voiced narration.

**Files:**
- Create: `tools/script_generator.py`
- Create: `tests/unit/test_script_generator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_script_generator.py`:

```python
import json
from unittest.mock import patch, MagicMock
import pytest
from tools import script_generator
from tools.channel_config import load_channel


def test_build_prompt_includes_persona_and_transcript(fixture_dir):
    cfg = load_channel(fixture_dir / "channel_minimal.yaml")
    media = {"title": {"english": "Frieren"}, "episodes": 28}
    segments = [{"start": 0, "end": 2, "text": "hello"}, {"start": 2, "end": 4, "text": "world"}]
    prompt = script_generator.build_prompt(cfg, media, episode_num=12, transcript=segments)
    # Persona is included
    assert cfg.persona.voice in prompt
    assert cfg.persona.style in prompt
    # Anime context included
    assert "Frieren" in prompt
    assert "12" in prompt
    # Transcript content included
    assert "hello world" in prompt or "hello" in prompt


def test_generate_overview_script_returns_parsed_json():
    # build_prompt is mocked, so the channel arg is never inspected.
    cfg = MagicMock()
    fake_claude_output = json.dumps({
        "hook": "Frieren ep 12 just aired and the time skip was insane.",
        "body": "Here's everything that happened in 60 seconds.",
        "outro": "If you missed it, link's below.",
        "estimated_duration_sec": 52,
    })
    with patch("tools.script_generator.llm_client.chat", return_value=fake_claude_output), \
         patch("tools.script_generator.build_prompt", return_value="PROMPT"):
        result = script_generator.generate_overview_script(cfg, media={}, episode_num=12, transcript=[])
    assert result["hook"].startswith("Frieren ep 12")
    assert result["estimated_duration_sec"] == 52


def test_generate_overview_script_rejects_malformed_claude_output():
    cfg = MagicMock()
    with patch("tools.script_generator.llm_client.chat", return_value="not json"), \
         patch("tools.script_generator.build_prompt", return_value="PROMPT"):
        with pytest.raises(script_generator.ScriptGenerationError, match="parse"):
            script_generator.generate_overview_script(cfg, {}, 1, [])


def test_full_text_concatenates_hook_body_outro():
    script = {"hook": "Hook line.", "body": "Body line.", "outro": "Outro line."}
    assert script_generator.full_text(script) == "Hook line. Body line. Outro line."
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_script_generator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/script_generator.py`**

```python
"""Overview commentary script generator.

Given an anime episode's transcript (or summary) and a channel persona, asks Claude
to produce a structured script (hook + body + outro) for 45-60 seconds of voiced narration.
"""
from __future__ import annotations
import json
from typing import Any

from tools import llm_client
from tools.channel_config import ChannelConfig


class ScriptGenerationError(RuntimeError):
    """Raised when Claude returns content that doesn't parse as expected."""


_SYSTEM_PROMPT = """You are an expert anime commentary writer producing short-form video scripts.

Output STRICT JSON only — no markdown, no preamble, no trailing commentary. The JSON must have exactly these keys:
  - "hook": the first ~3 seconds (10-15 words) — must grab attention immediately
  - "body": the main commentary (~35-45 seconds, 90-130 words)
  - "outro": closing line (~5 seconds, 10-15 words) — usually a CTA or teaser
  - "estimated_duration_sec": your honest estimate of voiced duration in seconds (target 45-60)

Write in the operator's voice. NO fake reactions. NO clickbait. NO spoilers without warning.
Plain prose only — no stage directions, no bracketed notes, no emoji.
"""


def build_prompt(channel: ChannelConfig, media: dict[str, Any], episode_num: int,
                 transcript: list[dict]) -> str:
    """Build the user-facing prompt sent to Claude."""
    title = (media.get("title") or {}).get("english") or (media.get("title") or {}).get("romaji") or "Unknown"
    transcript_text = " ".join(seg.get("text", "") for seg in transcript).strip()
    if len(transcript_text) > 8000:
        transcript_text = transcript_text[:8000] + "... [truncated]"

    persona = channel.persona
    return f"""Channel persona:
  voice: {persona.voice}
  style: {persona.style}
  hot_takes allowed: {persona.hot_takes}
  spoiler policy: {persona.spoiler_policy}

Anime: {title}
Episode: {episode_num}
Total episodes in series: {media.get('episodes', '?')}

Transcript of episode {episode_num}:
\"\"\"
{transcript_text}
\"\"\"

Produce a 45-60 second overview commentary script in the structured JSON format described in the system prompt."""


def generate_overview_script(channel: ChannelConfig, media: dict[str, Any],
                             episode_num: int, transcript: list[dict]) -> dict[str, Any]:
    """Call Claude and parse the returned script JSON."""
    prompt = build_prompt(channel, media, episode_num, transcript)
    raw = llm_client.chat(prompt, system=_SYSTEM_PROMPT, model="sonnet", timeout=90)
    # Sometimes models wrap JSON in markdown fences; strip them.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
    try:
        script = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScriptGenerationError(f"could not parse Claude output as JSON: {raw[:200]!r}") from e
    for required in ("hook", "body", "outro"):
        if required not in script:
            raise ScriptGenerationError(f"script missing required field: {required!r}")
    return script


def full_text(script: dict[str, Any]) -> str:
    """Concatenate hook + body + outro for TTS feeding."""
    parts = [script.get("hook", ""), script.get("body", ""), script.get("outro", "")]
    return " ".join(p.strip() for p in parts if p.strip())
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_script_generator.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/script_generator.py tests/unit/test_script_generator.py
git commit -m "feat: script_generator (Claude → overview commentary JSON)"
```

---

## Task 9: voice_renderer — TTS + Supabase upload

Wraps `tts_client.synthesize` to produce an MP3 from a script's `full_text`, stores it locally in `data/audio/`, and uploads to the Supabase Storage `audio` bucket.

**Files:**
- Create: `tools/voice_renderer.py`
- Create: `tests/unit/test_voice_renderer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_voice_renderer.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tools import voice_renderer
from tools.channel_config import load_channel


def test_render_voice_calls_tts_with_channel_voice(tmp_path, fixture_dir):
    cfg = load_channel(fixture_dir / "channel_minimal.yaml")
    script = {"hook": "h.", "body": "b.", "outro": "o."}

    def fake_synth(text, output_path, voice, speed, timeout):
        Path(output_path).write_bytes(b"FAKE_MP3")
        return output_path

    with patch("tools.voice_renderer.tts_client.synthesize", side_effect=fake_synth) as synth:
        out = voice_renderer.render_voice(cfg, script, output_dir=str(tmp_path))

    assert Path(out["local_path"]).exists()
    call_kwargs = synth.call_args.kwargs
    assert call_kwargs["voice"] == cfg.tts.voice_id
    assert call_kwargs["speed"] == cfg.tts.speed


def test_upload_voice_calls_supabase(tmp_path):
    src = tmp_path / "out.mp3"
    src.write_bytes(b"x")
    client = MagicMock()
    out = voice_renderer.upload_voice(client, str(src), short_id=42)
    # Path in storage: audio/42.mp3
    assert out["storage_path"] == "audio/42.mp3"
    client.storage.from_.assert_called_once_with("audio")


def test_render_voice_rejects_empty_script(tmp_path, fixture_dir):
    cfg = load_channel(fixture_dir / "channel_minimal.yaml")
    script = {"hook": "", "body": "", "outro": ""}
    with pytest.raises(ValueError, match="empty"):
        voice_renderer.render_voice(cfg, script, output_dir=str(tmp_path))
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_voice_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/voice_renderer.py`**

```python
"""Voice rendering: feed a script to TTS, save MP3 locally, upload to Supabase."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from tools import tts_client, supabase_client, script_generator
from tools.channel_config import ChannelConfig


def render_voice(channel: ChannelConfig, script: dict[str, Any],
                 output_dir: str = "data/audio") -> dict[str, Any]:
    """Synthesize the script's full text to an MP3 in `output_dir`. Returns metadata."""
    full = script_generator.full_text(script)
    if not full.strip():
        raise ValueError("cannot render voice for an empty script")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # Stable filename per (script hook hash) so re-runs don't duplicate.
    import hashlib
    digest = hashlib.sha256(full.encode("utf-8")).hexdigest()[:12]
    out_path = Path(output_dir) / f"voice_{digest}.mp3"
    tts_client.synthesize(
        text=full,
        output_path=str(out_path),
        voice=channel.tts.voice_id,
        speed=channel.tts.speed,
        timeout=120.0,
    )
    return {"local_path": str(out_path), "duration_text_words": len(full.split())}


def upload_voice(client, local_path: str, short_id: int, bucket: str = "audio") -> dict[str, Any]:
    """Upload a local voice MP3 to Supabase Storage under `audio/<short_id>.mp3`."""
    dest = f"audio/{short_id}.mp3"
    # Note bucket is just "audio"; the path inside is "audio/<id>.mp3" to match design
    supabase_client.upload_file(client, bucket, dest, local_path)
    return {"storage_path": dest, "bucket": bucket}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_voice_renderer.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/voice_renderer.py tests/unit/test_voice_renderer.py
git commit -m "feat: voice_renderer (TTS + Supabase upload)"
```

---

## Task 10: visual_assembler — FFmpeg vertical 9:16 with Ken Burns + captions

Stitches a list of (image, duration) clips with a voice MP3 and optional caption SRT into a vertical 1080x1920 MP4. Uses FFmpeg subprocess; produces the output expected by Supabase Storage upload.

**Files:**
- Create: `tools/visual_assembler.py`
- Create: `tests/unit/test_visual_assembler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_visual_assembler.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tools import visual_assembler


def test_compute_image_durations_evenly_divides(tmp_path):
    """If we have 3 images and 30s of audio, each gets 10s."""
    durations = visual_assembler.compute_image_durations(num_images=3, total_audio_sec=30.0)
    assert durations == [10.0, 10.0, 10.0]


def test_compute_image_durations_handles_one_image():
    durations = visual_assembler.compute_image_durations(num_images=1, total_audio_sec=47.5)
    assert durations == [47.5]


def test_compute_image_durations_rejects_zero():
    with pytest.raises(ValueError, match="at least 1"):
        visual_assembler.compute_image_durations(num_images=0, total_audio_sec=30.0)


def test_assemble_calls_ffmpeg_with_expected_filter(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    img1 = tmp_path / "cover.jpg"
    img1.write_bytes(b"x")
    out = tmp_path / "final.mp4"

    fake_proc = MagicMock(returncode=0)
    with patch("tools.visual_assembler.subprocess.run", return_value=fake_proc) as run, \
         patch("tools.visual_assembler.probe_audio_duration", return_value=10.0):
        visual_assembler.assemble(
            audio_path=str(audio),
            image_paths=[str(img1)],
            output_path=str(out),
        )
    cmd = run.call_args[0][0]
    assert "ffmpeg" in cmd
    assert str(out) in cmd
    # Vertical resolution baked in
    joined = " ".join(cmd)
    assert "1080:1920" in joined or "1080x1920" in joined


def test_assemble_burns_captions_when_provided(tmp_path):
    audio = tmp_path / "v.mp3"
    audio.write_bytes(b"x")
    img = tmp_path / "i.jpg"
    img.write_bytes(b"x")
    caption = tmp_path / "c.srt"
    caption.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    out = tmp_path / "o.mp4"

    fake_proc = MagicMock(returncode=0)
    with patch("tools.visual_assembler.subprocess.run", return_value=fake_proc) as run, \
         patch("tools.visual_assembler.probe_audio_duration", return_value=5.0):
        visual_assembler.assemble(
            audio_path=str(audio),
            image_paths=[str(img)],
            output_path=str(out),
            caption_path=str(caption),
        )
    cmd = " ".join(run.call_args[0][0])
    assert "subtitles=" in cmd
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_visual_assembler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/visual_assembler.py`**

```python
"""Compose vertical 9:16 MP4 from images + voice + optional captions.

Filter graph (FFmpeg):
  1. Each image is looped for its share of the total audio duration.
  2. Each image is scaled to fit a 1080×1920 canvas with a blurred-copy background
     (so the cover/banner aspect ratios don't distort).
  3. A subtle slow zoom ("Ken Burns") is applied.
  4. Clips are concatenated.
  5. Voice MP3 is muxed as audio track.
  6. Optional captions burned in via `subtitles=` filter.

Output: H.264 video, AAC audio, `+faststart` for upload compatibility.
"""
from __future__ import annotations
import subprocess
from pathlib import Path


def probe_audio_duration(path: str) -> float:
    """Return audio duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         path],
        capture_output=True, text=True, check=True, timeout=15,
    )
    return float(result.stdout.strip())


def compute_image_durations(num_images: int, total_audio_sec: float) -> list[float]:
    """Split total audio duration evenly across the images."""
    if num_images < 1:
        raise ValueError("need at least 1 image")
    each = total_audio_sec / num_images
    return [each] * num_images


def _build_filter_complex(image_paths: list[str], durations: list[float],
                          caption_path: str | None) -> str:
    """Construct the FFmpeg filter_complex string."""
    parts: list[str] = []
    for i, dur in enumerate(durations):
        # For each input image: scale and pad with a blurred copy as background,
        # then apply a slow zoom (zoompan).
        parts.append(
            f"[{i}:v]"
            f"loop=loop=-1:size=1:start=0,trim=duration={dur},"
            f"split[fg{i}][bg{i}];"
            f"[bg{i}]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,boxblur=20:5[bg_blur{i}];"
            f"[fg{i}]scale=1080:-1:force_original_aspect_ratio=decrease[fg_sc{i}];"
            f"[bg_blur{i}][fg_sc{i}]overlay=(W-w)/2:(H-h)/2,"
            f"zoompan=z='min(zoom+0.0005,1.10)':d={int(dur * 30)}:s=1080x1920,"
            f"setsar=1[v{i}]"
        )
    # Concatenate all video streams
    concat_inputs = "".join(f"[v{i}]" for i in range(len(durations)))
    parts.append(f"{concat_inputs}concat=n={len(durations)}:v=1:a=0[vout]")

    if caption_path:
        # Escape colons in path for FFmpeg filter syntax
        escaped = caption_path.replace(":", "\\:").replace("'", "\\'")
        parts.append(f"[vout]subtitles='{escaped}':force_style='Fontsize=24'[vfinal]")
        return ";".join(parts)
    parts.append("[vout]copy[vfinal]")
    return ";".join(parts)


def assemble(audio_path: str, image_paths: list[str], output_path: str,
             caption_path: str | None = None, timeout: float = 600.0) -> str:
    """Compose vertical MP4 from images + voice + optional captions.

    Returns the output path on success; raises CalledProcessError on FFmpeg failure.
    """
    duration = probe_audio_duration(audio_path)
    durations = compute_image_durations(len(image_paths), duration)

    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    # Input each image as a video stream of correct duration
    for img, dur in zip(image_paths, durations):
        cmd += ["-loop", "1", "-t", f"{dur}", "-i", img]
    # Audio input (always last so input indexes 0..N-1 are the images)
    cmd += ["-i", audio_path]

    filter_complex = _build_filter_complex(image_paths, durations, caption_path)
    audio_input_idx = len(image_paths)
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-map", f"{audio_input_idx}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-s", "1080x1920",
        "-r", "30",
        output_path,
    ]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, timeout=timeout)
    return output_path
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_visual_assembler.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/visual_assembler.py tests/unit/test_visual_assembler.py
git commit -m "feat: visual_assembler (FFmpeg vertical 9:16 compose)"
```

---

## Task 11: orchestrator — state-machine driver

The brain of the pipeline. Walks the `shorts` table forward through statuses, dispatching each transition to the right stage.

**Files:**
- Create: `tools/orchestrator.py`
- Create: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_orchestrator.py`:

```python
from unittest.mock import patch, MagicMock
import pytest
from tools import orchestrator  # noqa: F401


def test_advance_one_short_handles_detected_to_transcribed():
    """A 'detected' short with an episode in 'transcribed' state advances to 'transcribed'."""
    client = MagicMock()
    short = {"id": 7, "episode_id": 1, "status": "detected", "kind": "overview"}
    episode = {"id": 1, "status": "transcribed", "transcript_url": "transcripts/1.json"}

    with patch("tools.orchestrator.supabase_client.get_episode", return_value=episode), \
         patch("tools.orchestrator.supabase_client.update_short_status") as upd:
        new_status = orchestrator.advance_one_short(client, short, channel=MagicMock())
    assert new_status == "transcribed"
    upd.assert_called_once()
    call = upd.call_args
    assert call.args[1] == 7              # short_id
    assert call.args[2] == "transcribed"  # new status


def test_advance_one_short_skips_when_episode_not_ready():
    """If episode is still 'downloaded' (not transcribed), don't advance the short."""
    client = MagicMock()
    short = {"id": 7, "episode_id": 1, "status": "detected", "kind": "overview"}
    episode = {"id": 1, "status": "downloaded"}
    with patch("tools.orchestrator.supabase_client.get_episode", return_value=episode):
        new_status = orchestrator.advance_one_short(client, short, channel=MagicMock())
    assert new_status == "detected"  # unchanged


def test_advance_one_short_transcribed_to_script_ready():
    client = MagicMock()
    short = {"id": 7, "episode_id": 1, "status": "transcribed", "kind": "overview"}
    episode = {"id": 1, "status": "transcribed", "transcript_url": "/local/tr.json", "anilist_id": 154587}

    fake_script = {"hook": "h", "body": "b", "outro": "o"}
    with patch("tools.orchestrator.supabase_client.get_episode", return_value=episode), \
         patch("tools.orchestrator._load_transcript_local", return_value=[]), \
         patch("tools.orchestrator.anilist_client.fetch_media", return_value={"id": 154587, "title": {}, "episodes": 28}), \
         patch("tools.orchestrator.script_generator.generate_overview_script", return_value=fake_script), \
         patch("tools.orchestrator.supabase_client.update_short_status") as upd:
        new_status = orchestrator.advance_one_short(client, short, channel=MagicMock())
    assert new_status == "script_ready"
    # script_text should be passed along
    update_fields = upd.call_args.kwargs
    assert update_fields["script_text"] == "h b o" or "hook" in update_fields.get("script_text", "")


def test_advance_one_short_wraps_stage_failure_in_failed_status():
    client = MagicMock()
    short = {"id": 7, "episode_id": 1, "status": "transcribed", "kind": "overview"}
    episode = {"id": 1, "status": "transcribed", "anilist_id": 1}
    with patch("tools.orchestrator.supabase_client.get_episode", return_value=episode), \
         patch("tools.orchestrator._load_transcript_local", return_value=[]), \
         patch("tools.orchestrator.anilist_client.fetch_media", return_value={"id": 1, "title": {}}), \
         patch("tools.orchestrator.script_generator.generate_overview_script", side_effect=RuntimeError("claude died")), \
         patch("tools.orchestrator.supabase_client.update_short_status") as upd:
        new_status = orchestrator.advance_one_short(client, short, channel=MagicMock())
    assert new_status == "script_failed"
    # Verify error_log was populated
    update_fields = upd.call_args.kwargs
    assert "claude died" in update_fields.get("error_log", "")


def test_run_poll_cycle_advances_each_pending_short():
    """run_poll_cycle pulls 'detected', 'transcribed', 'script_ready', 'voice_ready' rows."""
    client = MagicMock()
    detected = [{"id": 1, "status": "detected", "episode_id": 10, "kind": "overview", "channel_slug": "reactions"}]
    with patch("tools.orchestrator.supabase_client.get_shorts_by_status", side_effect=[
        detected, [], [], [],
    ]):
        with patch("tools.orchestrator.advance_one_short", return_value="transcribed") as adv:
            orchestrator.run_poll_cycle(client, channels=[MagicMock(slug="reactions")])
    adv.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/orchestrator.py`**

```python
"""Pipeline orchestrator: walks shorts rows through the state machine.

Each transition is one idempotent stage. The orchestrator picks up shorts
in pending states and advances them by calling the right module:
  detected → transcribed     (waits for episode.status == 'transcribed')
  transcribed → script_ready (script_generator.generate_overview_script)
  script_ready → voice_ready (voice_renderer.render_voice + upload)
  voice_ready → rendered     (visual_assembler.assemble + upload)
"""
from __future__ import annotations
import json
import traceback
from pathlib import Path
from typing import Any

from tools import (
    supabase_client,
    anilist_client,
    script_generator,
    voice_renderer,
    visual_assembler,
    fetch_anime_visuals,
)
from tools.channel_config import ChannelConfig


PENDING_STATUSES = ("detected", "transcribed", "script_ready", "voice_ready")


def _load_transcript_local(transcript_url: str) -> list[dict]:
    """Read a transcript JSON from local disk. Assumes Plan 3 syncs from storage."""
    return json.loads(Path(transcript_url).read_text())


def _channel_for(slug: str, channels: list[ChannelConfig]) -> ChannelConfig | None:
    for c in channels:
        if c.slug == slug:
            return c
    return None


def advance_one_short(client, short: dict[str, Any], channel: ChannelConfig) -> str:
    """Advance a single short by one state. Returns the new status."""
    status = short["status"]
    short_id = short["id"]

    if status == "detected":
        episode = supabase_client.get_episode(client, short["episode_id"])
        if episode["status"] != "transcribed":
            return status  # not ready
        supabase_client.update_short_status(client, short_id, "transcribed")
        return "transcribed"

    if status == "transcribed":
        try:
            episode = supabase_client.get_episode(client, short["episode_id"])
            transcript = _load_transcript_local(episode["transcript_url"])
            media = anilist_client.fetch_media(episode["anilist_id"])
            script = script_generator.generate_overview_script(
                channel, media, episode["episode_num"], transcript,
            )
            full = script_generator.full_text(script)
            supabase_client.update_short_status(
                client, short_id, "script_ready",
                script_text=full,
            )
            return "script_ready"
        except Exception as e:
            supabase_client.update_short_status(
                client, short_id, "script_failed",
                error_log=f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}",
            )
            return "script_failed"

    if status == "script_ready":
        try:
            script = {"hook": "", "body": short["script_text"], "outro": ""}
            voice_info = voice_renderer.render_voice(channel, script)
            uploaded = voice_renderer.upload_voice(client, voice_info["local_path"], short_id)
            supabase_client.update_short_status(
                client, short_id, "voice_ready",
                audio_url=uploaded["storage_path"],
            )
            return "voice_ready"
        except Exception as e:
            supabase_client.update_short_status(
                client, short_id, "tts_failed",
                error_log=f"{type(e).__name__}: {e}",
            )
            return "tts_failed"

    if status == "voice_ready":
        try:
            episode = supabase_client.get_episode(client, short["episode_id"])
            media = anilist_client.fetch_media(episode["anilist_id"])
            image_paths = fetch_anime_visuals.fetch_visuals(media)
            # Audio MP3 is at data/audio/voice_<digest>.mp3 — find via script_text hash
            import hashlib
            digest = hashlib.sha256(short["script_text"].encode("utf-8")).hexdigest()[:12]
            audio_local = f"data/audio/voice_{digest}.mp3"
            output_local = f"data/output/short_{short_id}.mp4"
            visual_assembler.assemble(
                audio_path=audio_local,
                image_paths=image_paths,
                output_path=output_local,
            )
            # Upload final video to Supabase bucket "output"
            supabase_client.upload_file(client, "output", f"output/{short_id}.mp4", output_local)
            supabase_client.update_short_status(
                client, short_id, "rendered",
                video_url=f"output/{short_id}.mp4",
            )
            return "rendered"
        except Exception as e:
            supabase_client.update_short_status(
                client, short_id, "render_failed",
                error_log=f"{type(e).__name__}: {e}",
            )
            return "render_failed"

    return status  # unknown — leave alone


def run_poll_cycle(client, channels: list[ChannelConfig]) -> dict[str, int]:
    """Walk every pending short forward by at most one state. Returns counts per status."""
    counts: dict[str, int] = {}
    for status in PENDING_STATUSES:
        rows = supabase_client.get_shorts_by_status(client, status)
        for short in rows:
            chan = _channel_for(short["channel_slug"], channels)
            if chan is None:
                continue
            new = advance_one_short(client, short, chan)
            counts[new] = counts.get(new, 0) + 1
    return counts
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_orchestrator.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: orchestrator (state-machine driver)"
```

---

## Task 12: main.py — wire `poll` and add `ingest-episode` command

Two CLI commands the operator actually invokes:
- `ingest-episode --file ... --title ... --episode-num ... --anilist-id ...` — creates the episode row, copies file into `data/episodes/`, runs `extract_subs.extract_transcript()`, creates one overview `shorts` row.
- `poll` — calls `orchestrator.run_poll_cycle()` for all loaded channels.

**Files:**
- Modify: `main.py`
- Modify: `tests/unit/test_main_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_main_cli.py`:

```python
def test_ingest_episode_creates_episode_and_short_rows(tmp_path, monkeypatch):
    """Smoke: ingest-episode invokes the right helpers with the right args."""
    monkeypatch.chdir(tmp_path)
    # Create the source file
    src = tmp_path / "ep12.mp4"
    src.write_bytes(b"FAKEMP4")

    from unittest.mock import patch, MagicMock
    fake_client = MagicMock()
    fake_episode_row = {"id": 1, "status": "downloaded", "anilist_id": 154587, "title": "Frieren", "episode_num": 12}
    fake_short_row = {"id": 7, "status": "detected"}

    with patch("main.supabase_client.get_client", return_value=fake_client), \
         patch("main.supabase_client.insert_episode", return_value=fake_episode_row), \
         patch("main.supabase_client.insert_short", return_value=fake_short_row), \
         patch("main.supabase_client.upload_file"), \
         patch("main.supabase_client.update_episode_status"), \
         patch("main.extract_subs.extract_transcript", return_value=[{"start": 0, "end": 1, "text": "hi"}]):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ingest-episode",
            "--file", str(src),
            "--title", "Frieren",
            "--episode-num", "12",
            "--anilist-id", "154587",
            "--channel", "reactions",
        ])
    assert result.exit_code == 0, result.output
    assert "ingested" in result.output.lower() or "ep12" in result.output


def test_poll_command_invokes_orchestrator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Point to the real channels dir so reactions.yaml loads
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    monkeypatch.setenv("CHANNELS_DIR", str(repo_root / "channels"))
    from unittest.mock import patch, MagicMock
    fake_client = MagicMock()
    with patch("main.supabase_client.get_client", return_value=fake_client), \
         patch("main.orchestrator.run_poll_cycle", return_value={"transcribed": 1}) as run_poll:
        runner = CliRunner()
        result = runner.invoke(cli, ["poll"])
    assert result.exit_code == 0
    run_poll.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/unit/test_main_cli.py::test_ingest_episode_creates_episode_and_short_rows -v`
Expected: FAIL — `No such command 'ingest-episode'`

- [ ] **Step 3: Update `main.py`**

Edit `main.py` — add imports near the top:

```python
from tools import supabase_client, orchestrator, extract_subs
from tools.channel_config import load_channel
```

Replace the existing `poll` stub command with:

```python
@cli.command()
def poll() -> None:
    """Run one pipeline traversal: advance every pending short by one state."""
    client = supabase_client.get_client()
    channels_dir = Path(os.environ.get("CHANNELS_DIR", str(DEFAULT_CHANNELS_DIR)))
    from tools.channel_config import discover_channels
    channels = discover_channels(channels_dir)
    counts = orchestrator.run_poll_cycle(client, channels)
    for status, n in counts.items():
        click.echo(f"  {n} shorts now in '{status}'")
    if not counts:
        click.echo("  (no pending shorts)")
```

Add a new `ingest-episode` command:

```python
@cli.command("ingest-episode")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--title", required=True)
@click.option("--episode-num", required=True, type=int)
@click.option("--anilist-id", required=True, type=int)
@click.option("--channel", required=True, help="channel slug — must match a YAML in channels/")
def ingest_episode(file_path: str, title: str, episode_num: int, anilist_id: int,
                   channel: str) -> None:
    """Ingest a local episode file and create one overview short row in 'detected'."""
    import shutil
    client = supabase_client.get_client()
    # 1. Copy file to data/episodes/
    Path("data/episodes").mkdir(parents=True, exist_ok=True)
    dest = Path(f"data/episodes/{anilist_id}_ep{episode_num}.mp4")
    shutil.copyfile(file_path, dest)
    click.echo(f"copied {file_path} -> {dest}")

    # 2. Create episode row (status=downloaded since file is in place)
    episode_row = supabase_client.insert_episode(client, {
        "anilist_id": anilist_id,
        "title": title,
        "episode_num": episode_num,
        "status": "downloaded",
        "file_url": str(dest),
    })
    click.echo(f"created episode row #{episode_row['id']}")

    # 3. Run transcript extraction
    segments = extract_subs.extract_transcript(str(dest))
    transcript_path = Path(f"data/transcripts/{episode_row['id']}.json")
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    transcript_path.write_text(json.dumps(segments))
    supabase_client.update_episode_status(
        client, episode_row["id"], "transcribed",
        transcript_url=str(transcript_path),
    )
    click.echo(f"transcribed {len(segments)} segments -> {transcript_path}")

    # 4. Create one overview short row
    short_row = supabase_client.insert_short(client, {
        "episode_id": episode_row["id"],
        "channel_slug": channel,
        "kind": "overview",
        "status": "detected",
        "platform": "youtube",
    })
    click.echo(f"ingested ep{episode_num} (short row #{short_row['id']})")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_main_cli.py -v`
Expected: all 9 tests PASS (7 original + 2 new).

- [ ] **Step 5: Verify CLI smoke**

Run: `python main.py --help`
Expected: now lists `ingest-episode` alongside `init`, `poll`, etc.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/unit/test_main_cli.py
git commit -m "feat(cli): ingest-episode command + wire poll to orchestrator"
```

---

## Task 13: End-to-end integration test

Validates the whole pipeline against a fixture episode file. Uses heavy mocking for external services (Supabase, AniList, Claude, edge-tts) but runs the real FFmpeg path.

**Files:**
- Create: `tests/fixtures/sample_30s_clip.mp4` (generated by ffmpeg in Step 1)
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_overview_pipeline.py`

- [ ] **Step 1: Generate the test fixture clip**

Run (one-time setup):

```bash
cd "/home/sh4d0w/agentic coding projects/anime-commentary" && ffmpeg -f lavfi -i "testsrc=duration=30:size=1280x720:rate=15" -f lavfi -i "sine=frequency=440:duration=30" -c:v libx264 -preset ultrafast -c:a aac -shortest tests/fixtures/sample_30s_clip.mp4
```

Expected: creates a ~500KB MP4 of test pattern + 440Hz tone, 30 seconds.

- [ ] **Step 2: Create the E2E test module**

`tests/e2e/__init__.py`:

```python
```

`tests/e2e/test_overview_pipeline.py`:

```python
"""End-to-end pipeline integration test.

Real components: FFmpeg (extract_subs, visual_assembler), state machine, channel loader.
Mocked: Supabase (in-memory fake), AniList (returns sample fixture), Claude (returns canned script), edge-tts (writes 5s of silence).
"""
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from tools import orchestrator
from tools.channel_config import load_channel


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CLIP = REPO_ROOT / "tests" / "fixtures" / "sample_30s_clip.mp4"


class FakeSupabase:
    """Minimal in-memory shim of the supabase_client API for E2E."""
    def __init__(self):
        self.episodes: dict[int, dict] = {}
        self.shorts: dict[int, dict] = {}
        self.uploads: dict[str, bytes] = {}
        self._next_id = 1

    def _id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i


@pytest.fixture
def fake_supabase():
    return FakeSupabase()


@pytest.mark.slow
def test_overview_pipeline_end_to_end(tmp_path, monkeypatch, fake_supabase):
    """Drive a clip from detected → rendered, verify a real MP4 lands in data/output/."""
    monkeypatch.chdir(tmp_path)
    # Copy the sample clip into a working data dir
    eps_dir = tmp_path / "data" / "episodes"
    eps_dir.mkdir(parents=True)
    src = eps_dir / "ep12.mp4"
    shutil.copyfile(SAMPLE_CLIP, src)

    # Build episode + short rows in the fake DB
    episode_row = {"id": 1, "anilist_id": 154587, "title": "Frieren", "episode_num": 12,
                   "status": "transcribed", "transcript_url": str(tmp_path / "tr.json"),
                   "file_url": str(src)}
    (tmp_path / "tr.json").write_text(json.dumps([
        {"start": 0, "end": 15, "text": "Frieren battles a demon, and time skips dramatically."},
    ]))
    short_row = {"id": 1, "episode_id": 1, "status": "transcribed", "kind": "overview",
                 "channel_slug": "reactions", "script_text": "", "platform": "youtube"}
    fake_supabase.episodes[1] = episode_row
    fake_supabase.shorts[1] = short_row

    channel = load_channel(REPO_ROOT / "channels" / "reactions.yaml")

    def fake_get_episode(client, eid): return fake_supabase.episodes[eid]
    def fake_update_short_status(client, sid, status, **fields):
        fake_supabase.shorts[sid]["status"] = status
        fake_supabase.shorts[sid].update(fields)
    def fake_upload_file(client, bucket, dest, src_local):
        fake_supabase.uploads[dest] = Path(src_local).read_bytes()

    # Fake AniList returns minimal media
    fake_media = {
        "id": 154587,
        "title": {"english": "Frieren", "romaji": "Sousou no Frieren"},
        "coverImage": {"extraLarge": "https://example/cover.jpg"},
        "bannerImage": None,
        "episodes": 28,
    }

    # Fake Claude returns a valid script
    fake_script = json.dumps({
        "hook": "Frieren ep 12 just aired.",
        "body": "Time skipped dramatically and the demon was defeated in under a minute.",
        "outro": "More takes coming tomorrow.",
        "estimated_duration_sec": 12,
    })

    # Fake fetch_visuals returns one local image path (use the sample clip's first frame extracted)
    cover_img = tmp_path / "cover.jpg"
    # Generate a real test image using ffmpeg (1 frame from the sample clip)
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(SAMPLE_CLIP), "-frames:v", "1", str(cover_img),
    ], check=True, timeout=30)

    # Fake edge-tts writes a real (silent) audio file via ffmpeg
    def fake_synth(text, output_path, voice, speed, timeout):
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=cl=mono:r=16000",
            "-t", "10", "-c:a", "libmp3lame", output_path,
        ], check=True, timeout=30)
        return output_path

    with patch("tools.orchestrator.supabase_client.get_episode", side_effect=fake_get_episode), \
         patch("tools.orchestrator.supabase_client.update_short_status", side_effect=fake_update_short_status), \
         patch("tools.orchestrator.supabase_client.upload_file", side_effect=fake_upload_file), \
         patch("tools.orchestrator.anilist_client.fetch_media", return_value=fake_media), \
         patch("tools.orchestrator.script_generator.llm_client.chat", return_value=fake_script), \
         patch("tools.orchestrator.fetch_anime_visuals.fetch_visuals", return_value=[str(cover_img)]), \
         patch("tools.orchestrator.voice_renderer.tts_client.synthesize", side_effect=fake_synth):
        # Run the orchestrator three times to walk: transcribed → script_ready → voice_ready → rendered
        for _ in range(3):
            orchestrator.advance_one_short(MagicMock(), fake_supabase.shorts[1], channel)

    # Assertions
    assert fake_supabase.shorts[1]["status"] == "rendered", \
        f"expected rendered, got {fake_supabase.shorts[1]['status']} (error_log: {fake_supabase.shorts[1].get('error_log')})"
    final_path = Path("data/output/short_1.mp4")
    assert final_path.exists(), "rendered MP4 not on disk"
    assert final_path.stat().st_size > 50_000, "rendered MP4 suspiciously small"
    # Confirm it's a valid MP4 (ffprobe parses it)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(final_path)],
        capture_output=True, text=True, check=True,
    )
    streams = result.stdout.strip().split("\n")
    assert "video" in streams and "audio" in streams
```

- [ ] **Step 3: Run the E2E test (slow)**

Run: `cd "/home/sh4d0w/agentic coding projects/anime-commentary" && pytest tests/e2e/test_overview_pipeline.py -v -m slow`
Expected: PASS (takes 30-60 seconds — runs real FFmpeg).

- [ ] **Step 4: Run the fast suite to confirm no regressions**

Run: `pytest -v -m "not slow" 2>&1 | tail -3`
Expected: every prior test still passes (was 39 → with Plan 2 tests: ~70+).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/ tests/fixtures/sample_30s_clip.mp4
git commit -m "test(e2e): overview pipeline end-to-end with real FFmpeg"
```

---

## Final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v -m "not slow" --cov=tools --cov=main --cov-report=term-missing`
Expected: all tests PASS; coverage on `tools/` ≥ 85%.

- [ ] **Step 2: Run the slow suite once**

Run: `pytest -v -m slow`
Expected: TTS real synthesis + E2E pipeline both pass.

- [ ] **Step 3: Manual smoke test with the fixture clip**

Run (you'll need to set SUPABASE_URL/KEY in `.env` or skip if no Supabase project yet):

```bash
python main.py ingest-episode --file tests/fixtures/sample_30s_clip.mp4 --title "Test Anime" --episode-num 1 --anilist-id 154587 --channel reactions
python main.py poll
python main.py poll
python main.py poll
```

Expected: After three `poll` invocations, `data/output/short_<id>.mp4` exists and is a valid MP4.

- [ ] **Step 4: Confirm git log shows discrete commits**

Run: `git log --oneline main..HEAD`
Expected: 13+ commits, one per task.

---

## What this plan delivers

After completion, you have a working overview-track pipeline:

- Given a local episode MP4, `ingest-episode` creates DB rows and extracts a transcript.
- `poll` advances rows through the state machine: transcript → script (via Claude) → voice (via edge-tts) → final vertical MP4 (via FFmpeg).
- A rendered overview short lands in `data/output/` AND `output/<short_id>.mp4` in Supabase Storage.
- The full pipeline is covered by ~30+ unit tests and a real-FFmpeg E2E test.

## What this plan does NOT deliver (deferred plans)

- **Plan 3:** ani-cli auto-acquisition, AniList polling for currently-airing episodes, crowd-summary fallback when downloads fail.
- **Plan 4:** Moment shorts (clipping highlights from the episode), confidence gate, YouTube upload.
- **Plan 5:** Streamlit review UI (currently rendered shorts have no review path).
- **Plan 6:** GitHub Actions workflows, Discord alerts, metrics polling.

## Items to track for Plan 3+

- The orchestrator's `_load_transcript_local` reads the transcript from the path stored in `episodes.transcript_url`. Plan 6 (GH Actions) will need to either keep the transcript on Supabase Storage and download it, or share state via the DB only. For now we rely on the file being on local disk.
- `voice_renderer.render_voice` writes to `data/audio/` by name-hash; if two shorts have identical scripts they share the same MP3. Fine for MVP; revisit if needed.
- The visual assembler runs FFmpeg with `-preset veryfast`. CI minutes are cheaper with `ultrafast` if quality suffers, or we can move to GPU encoding later.
- Plan 2's `ingest-episode` is the temporary entry-point; Plan 3 replaces it with the AniList-driven auto-acquisition flow.
