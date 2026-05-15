# Anime Commentary — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the `anime-commentary` repo with all client wrappers (Claude Code, edge-tts, Supabase), channel YAML loader, database schema, and a CLI shell — providing the foundation that subsequent plans (overview pipeline, moment pipeline, publish, review UI, observability) build on.

**Architecture:** Click-based Python CLI orchestrator + thin client wrappers per external service. Channel configs are pure YAML loaded via pydantic models. State store schema defined in SQL (Supabase Postgres-compatible) but local dev runs without a live DB. Vendored helper tools from `~/agentic coding projects/shorts maker/tools/` are copied in for later use.

**Tech Stack:** Python 3.12+, Click, pydantic v2, supabase-py, edge-tts, PyYAML, pytest, pytest-mock.

**Reference:** Design spec at `docs/superpowers/specs/2026-05-15-anime-commentary-pipeline-design.md`.

---

## File Structure

Files created in this plan, each with a single clear responsibility:

```
anime-commentary/
├── pyproject.toml                       # project metadata, deps
├── requirements.txt                     # pinned runtime deps
├── requirements-dev.txt                 # dev/test deps
├── .gitignore
├── .env.example
├── README.md
├── docs/schema.sql                      # Supabase Postgres schema
├── main.py                              # Click CLI entrypoint (stubs only)
├── tools/
│   ├── __init__.py
│   ├── channel_config.py                # pydantic models + loader
│   ├── llm_client.py                    # Claude Code headless wrapper
│   ├── tts_client.py                    # edge-tts wrapper
│   └── supabase_client.py               # Supabase wrapper functions
├── shared_tools/                        # vendored from shorts maker
│   ├── __init__.py
│   ├── generate_script.py               # copied as-is for now
│   ├── generate_voiceover.py            # copied; will be replaced w/ edge-tts in Plan 2
│   ├── burn_captions.py                 # copied as-is
│   ├── assemble_generated_short.py      # copied as-is
│   └── transcribe_video.py              # copied as-is
├── channels/
│   └── reactions.yaml                   # first channel config
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── channel_minimal.yaml
    │   └── channel_invalid.yaml
    └── unit/
        ├── __init__.py
        ├── test_channel_config.py
        ├── test_llm_client.py
        ├── test_tts_client.py
        ├── test_supabase_client.py
        └── test_main_cli.py
```

---

## Task 1: Project scaffolding (deps, .gitignore, .env.example, README)

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "anime-commentary"
version = "0.1.0"
description = "Automated anime commentary shorts pipeline"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "pyyaml>=6.0",
    "pydantic>=2.6",
    "httpx>=0.27",
    "supabase>=2.4",
    "edge-tts>=6.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "pytest-cov>=4.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tools", "shared_tools"]
```

- [ ] **Step 2: Create `requirements.txt` mirroring runtime deps**

```
click>=8.1
pyyaml>=6.0
pydantic>=2.6
httpx>=0.27
supabase>=2.4
edge-tts>=6.1
python-dotenv>=1.0
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
pytest-cov>=4.1
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/
.env
*.egg-info/
dist/
build/
.tmp/
data/
.coverage
htmlcov/
.DS_Store
```

- [ ] **Step 5: Create `.env.example`**

```
# Supabase project
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Claude Code (long-lived OAuth token from `claude setup-token`)
CLAUDE_CODE_OAUTH_TOKEN=

# Discord webhook for alerts
DISCORD_WEBHOOK_URL=

# YouTube OAuth (per channel)
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YT_REFRESH_TOKEN_REACTIONS=
```

- [ ] **Step 6: Create `README.md`**

```markdown
# anime-commentary

Automated short-form anime commentary pipeline. See `docs/superpowers/specs/` for the design.

## Quickstart (development)

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # fill in values
python main.py --help
pytest
\`\`\`

## Status

Foundation phase. Subsequent plans add the actual pipeline.
```

- [ ] **Step 7: Verify deps install cleanly**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
Expected: clean install, no errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .gitignore .env.example README.md
git commit -m "feat: project scaffolding with deps and env template"
```

---

## Task 2: Database schema SQL

**Files:**
- Create: `docs/schema.sql`

- [ ] **Step 1: Create `docs/schema.sql` matching design spec §7**

```sql
-- anime-commentary database schema (Supabase Postgres)
-- See docs/superpowers/specs/2026-05-15-anime-commentary-pipeline-design.md §7

CREATE TABLE IF NOT EXISTS episodes (
  id             BIGSERIAL PRIMARY KEY,
  anilist_id     INT NOT NULL,
  title          TEXT NOT NULL,
  episode_num    INT NOT NULL,
  aired_at       TIMESTAMPTZ,
  detected_at    TIMESTAMPTZ DEFAULT NOW(),
  file_url       TEXT,
  transcript_url TEXT,
  summary_text   TEXT,
  summary_source TEXT,
  status         TEXT NOT NULL,
  metadata       JSONB,
  UNIQUE (anilist_id, episode_num)
);

CREATE TABLE IF NOT EXISTS shorts (
  id            BIGSERIAL PRIMARY KEY,
  episode_id    BIGINT REFERENCES episodes(id) ON DELETE CASCADE,
  channel_slug  TEXT NOT NULL,
  kind          TEXT NOT NULL,
  moment_idx    INT,
  status        TEXT NOT NULL,
  script_text   TEXT,
  audio_url     TEXT,
  video_url     TEXT,
  duration_sec  NUMERIC,
  confidence    JSONB,
  platform      TEXT NOT NULL,
  external_url  TEXT,
  error_log     TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  published_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS jobs (
  id         BIGSERIAL PRIMARY KEY,
  kind       TEXT NOT NULL,
  status     TEXT NOT NULL,
  payload    JSONB,
  log        TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS metrics (
  id            BIGSERIAL PRIMARY KEY,
  short_id      BIGINT REFERENCES shorts(id) ON DELETE CASCADE,
  polled_at     TIMESTAMPTZ DEFAULT NOW(),
  views         INT,
  likes         INT,
  retention_pct NUMERIC
);

CREATE INDEX IF NOT EXISTS shorts_status_idx ON shorts (status);
CREATE INDEX IF NOT EXISTS shorts_channel_platform_idx ON shorts (channel_slug, platform);
CREATE INDEX IF NOT EXISTS episodes_status_idx ON episodes (status);
```

- [ ] **Step 2: Verify SQL parses (syntax check via sqlite for lightweight check — types differ but structure validates)**

Run: `python -c "import re; sql = open('docs/schema.sql').read(); assert sql.count('CREATE TABLE') == 4, 'expected 4 tables'; assert sql.count('CREATE INDEX') == 3, 'expected 3 indexes'; print('schema looks structurally OK')"`
Expected: `schema looks structurally OK`

- [ ] **Step 3: Commit**

```bash
git add docs/schema.sql
git commit -m "feat: add Supabase Postgres schema"
```

---

## Task 3: Vendor shared tools from shorts maker

**Files:**
- Create: `shared_tools/__init__.py`
- Create: `shared_tools/generate_script.py` (copy)
- Create: `shared_tools/generate_voiceover.py` (copy — replaced in Plan 2)
- Create: `shared_tools/burn_captions.py` (copy)
- Create: `shared_tools/assemble_generated_short.py` (copy)
- Create: `shared_tools/transcribe_video.py` (copy)

- [ ] **Step 1: Create `shared_tools/__init__.py`**

```python
"""Vendored tools from ../shorts maker/tools/. Edited in-place; sync back manually when improving."""
```

- [ ] **Step 2: Copy each script from shorts maker**

Run:
```bash
cp "../shorts maker/tools/generate_script.py" shared_tools/generate_script.py
cp "../shorts maker/tools/generate_voiceover.py" shared_tools/generate_voiceover.py
cp "../shorts maker/tools/burn_captions.py" shared_tools/burn_captions.py
cp "../shorts maker/tools/assemble_generated_short.py" shared_tools/assemble_generated_short.py
cp "../shorts maker/tools/transcribe_video.py" shared_tools/transcribe_video.py
```

Expected: 5 files copied. If any source is missing, log and skip — Plan 2 will write fresh versions.

- [ ] **Step 3: Verify each file parses (syntax-only check)**

Run: `python -m py_compile shared_tools/*.py && echo "syntax OK"`
Expected: `syntax OK`

Note: this only checks Python syntax — vendored scripts may still fail at runtime due to missing third-party deps (e.g. `openai`). That's acceptable; later plans rewrite or replace them. Step 4's test only asserts file presence.

- [ ] **Step 4: Add smoke test `tests/unit/test_vendored_tools_present.py`**

```python
from pathlib import Path

VENDORED = [
    "generate_script.py",
    "generate_voiceover.py",
    "burn_captions.py",
    "assemble_generated_short.py",
    "transcribe_video.py",
]

def test_all_vendored_tools_present():
    root = Path(__file__).resolve().parents[2] / "shared_tools"
    for name in VENDORED:
        f = root / name
        assert f.exists(), f"missing vendored tool: {name}"
        assert f.stat().st_size > 0, f"vendored tool is empty: {name}"
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/unit/test_vendored_tools_present.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shared_tools/ tests/unit/test_vendored_tools_present.py
git commit -m "feat: vendor shared tools from shorts maker"
```

---

## Task 4: Channel config loader (pydantic models + YAML loader)

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/channel_config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/channel_minimal.yaml`
- Create: `tests/fixtures/channel_invalid.yaml`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_channel_config.py`

- [ ] **Step 1: Create `tools/__init__.py`**

```python
"""Anime-commentary pipeline tools."""
```

- [ ] **Step 2: Create `tests/__init__.py` and `tests/unit/__init__.py`**

```python
# tests/__init__.py
```

```python
# tests/unit/__init__.py
```

- [ ] **Step 3: Create `tests/conftest.py` for shared fixtures**

```python
import os
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixture_dir():
    return FIXTURES

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Strip env vars that would leak into tests."""
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
```

- [ ] **Step 4: Write the failing test `tests/unit/test_channel_config.py`**

```python
import pytest
from pathlib import Path
from tools.channel_config import (
    load_channel,
    discover_channels,
    ChannelConfig,
    ChannelConfigError,
)

def test_load_valid_minimal(fixture_dir):
    cfg = load_channel(fixture_dir / "channel_minimal.yaml")
    assert isinstance(cfg, ChannelConfig)
    assert cfg.slug == "minimal"
    assert cfg.platforms.youtube.enabled is True
    assert cfg.anime.mode == "auto"
    assert cfg.anime.top_n == 8

def test_persona_defaults_filled(fixture_dir):
    cfg = load_channel(fixture_dir / "channel_minimal.yaml")
    assert cfg.persona.spoiler_policy == "warn"  # default value

def test_load_invalid_raises(fixture_dir):
    with pytest.raises(ChannelConfigError):
        load_channel(fixture_dir / "channel_invalid.yaml")

def test_discover_channels(tmp_path, fixture_dir):
    # Copy minimal twice with different slugs
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    src = (fixture_dir / "channel_minimal.yaml").read_text()
    a.write_text(src.replace("slug: minimal", "slug: alpha"))
    b.write_text(src.replace("slug: minimal", "slug: beta"))
    (tmp_path / "skipped.yaml.disabled").write_text("x: 1")

    found = discover_channels(tmp_path)
    slugs = sorted(c.slug for c in found)
    assert slugs == ["alpha", "beta"]

def test_unknown_keys_warn_not_fail(fixture_dir, tmp_path, caplog):
    import logging
    src = (fixture_dir / "channel_minimal.yaml").read_text()
    src += "\nextra_unknown_field: yes\n"
    p = tmp_path / "extra.yaml"
    p.write_text(src)
    with caplog.at_level(logging.WARNING, logger="tools.channel_config"):
        cfg = load_channel(p)
    assert cfg.slug == "minimal"
    assert any("extra_unknown_field" in r.message for r in caplog.records)


def test_permission_error_wrapped_as_config_error(tmp_path):
    src = tmp_path / "unreadable.yaml"
    src.write_text("slug: x")
    src.chmod(0o000)
    try:
        with pytest.raises(ChannelConfigError):
            load_channel(src)
    finally:
        src.chmod(0o644)  # restore so tmp_path cleanup works
```

- [ ] **Step 5: Create fixture YAMLs**

`tests/fixtures/channel_minimal.yaml`:

```yaml
slug: minimal
display_name: "Minimal Channel"

anime:
  mode: auto
  top_n: 8
  exclude_genres: []

persona:
  voice: "neutral commentator"
  style: "informative"
  hot_takes: false

tts:
  provider: edge-tts
  voice_id: en-US-GuyNeural
  speed: 1.0

output_mix:
  overview_per_episode: 1
  moments_per_episode: 2
  max_total_per_day: 10

schedule:
  publish_times_utc: ["08:00"]
  immediate_publish: false

platforms:
  youtube:
    enabled: true
    auth_secret: YT_REFRESH_TOKEN_MINIMAL
    default_action: review_queued
    auto_publish_if_all_pass:
      - hook_score >= 7
    title_template: "{anime} EP{ep}"
    description_template: "Short on {anime}"
    tags: [anime]
    privacy: public
```

`tests/fixtures/channel_invalid.yaml`:

```yaml
slug: missing_platforms
display_name: "Missing platforms"
anime:
  mode: auto
  top_n: 8
persona:
  voice: "x"
  style: "y"
tts:
  provider: edge-tts
  voice_id: en-US-GuyNeural
output_mix:
  overview_per_episode: 1
  moments_per_episode: 2
schedule:
  publish_times_utc: ["08:00"]
# platforms intentionally omitted to trigger validation error
```

- [ ] **Step 6: Run the test to confirm it fails (module not implemented yet)**

Run: `pytest tests/unit/test_channel_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.channel_config'`

- [ ] **Step 7: Implement `tools/channel_config.py`**

```python
"""Channel YAML schema, loader, and discovery."""
from __future__ import annotations
from pathlib import Path
from typing import Literal
import logging
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)


class ChannelConfigError(Exception):
    """Raised when a channel YAML fails to load or validate."""


class AnimeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["auto", "curated"] = "auto"
    top_n: int = 8
    curated_ids: list[int] = Field(default_factory=list)
    exclude_genres: list[str] = Field(default_factory=list)


class PersonaConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    voice: str
    style: str
    hot_takes: bool = False
    spoiler_policy: Literal["warn", "reveal", "avoid"] = "warn"


class TTSConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: Literal["edge-tts"] = "edge-tts"
    voice_id: str
    speed: float = 1.0


class OutputMixConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    overview_per_episode: int = 1
    moments_per_episode: int = 2
    max_total_per_day: int = 12


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    publish_times_utc: list[str] = Field(default_factory=lambda: ["08:00"])
    immediate_publish: bool = False


class YoutubePlatformConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    auth_secret: str | None = None
    default_action: Literal["auto_publish", "review_queued"] = "review_queued"
    auto_publish_if_all_pass: list[str] = Field(default_factory=list)
    rejecting_checks: list[str] = Field(default_factory=list)
    title_template: str = "{anime} EP{ep}"
    description_template: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: Literal["public", "unlisted", "private"] = "public"


class TiktokPlatformConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    auth_secret: str | None = None
    default_action: Literal["auto_publish", "review_queued"] = "auto_publish"
    rejecting_checks: list[str] = Field(default_factory=list)


class PlatformsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    youtube: YoutubePlatformConfig = Field(default_factory=YoutubePlatformConfig)
    tiktok: TiktokPlatformConfig = Field(default_factory=TiktokPlatformConfig)


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slug: str
    display_name: str
    anime: AnimeConfig
    persona: PersonaConfig
    tts: TTSConfig
    output_mix: OutputMixConfig
    schedule: ScheduleConfig
    platforms: PlatformsConfig


def load_channel(path: str | Path) -> ChannelConfig:
    """Load a single channel YAML into a ChannelConfig. Raises ChannelConfigError on failure."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise ChannelConfigError(f"could not read {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ChannelConfigError(f"{p} did not parse to a dict")
    # Warn on unknown top-level keys (forward-compat) rather than fail.
    known = set(ChannelConfig.model_fields.keys())
    for k in raw.keys():
        if k not in known:
            log.warning("unknown top-level key %r in %s — ignored", k, p)
    try:
        return ChannelConfig.model_validate(raw)
    except ValidationError as e:
        raise ChannelConfigError(f"validation failed for {p}: {e}") from e


def discover_channels(directory: str | Path) -> list[ChannelConfig]:
    """Load all .yaml channel files under `directory`. Skips files ending .yaml.disabled."""
    d = Path(directory)
    if not d.is_dir():
        return []
    out: list[ChannelConfig] = []
    for f in sorted(d.glob("*.yaml")):
        out.append(load_channel(f))
    return out
```

- [ ] **Step 8: Run the test — expect PASS**

Run: `pytest tests/unit/test_channel_config.py -v`
Expected: 5 tests PASS

- [ ] **Step 9: Commit**

```bash
git add tools/__init__.py tools/channel_config.py tests/__init__.py tests/conftest.py tests/fixtures/ tests/unit/__init__.py tests/unit/test_channel_config.py
git commit -m "feat: channel YAML schema and loader with pydantic"
```

---

## Task 5: First channel config file (`channels/reactions.yaml`)

**Files:**
- Create: `channels/reactions.yaml`
- Create: `tests/unit/test_reactions_channel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reactions_channel.py
from pathlib import Path
from tools.channel_config import load_channel

REACTIONS = Path(__file__).resolve().parents[2] / "channels" / "reactions.yaml"

def test_reactions_channel_loads():
    cfg = load_channel(REACTIONS)
    assert cfg.slug == "reactions"
    assert cfg.tts.voice_id == "en-US-GuyNeural"
    assert cfg.platforms.youtube.enabled is True
    assert cfg.platforms.tiktok.enabled is False
    assert "hook_score >= 7" in cfg.platforms.youtube.auto_publish_if_all_pass
    assert cfg.anime.exclude_genres == ["Hentai", "Ecchi"]
    assert cfg.output_mix.max_total_per_day == 12
```

- [ ] **Step 2: Run the test — expect failure (file missing)**

Run: `pytest tests/unit/test_reactions_channel.py -v`
Expected: FAIL — file not found

- [ ] **Step 3: Create `channels/reactions.yaml` matching design spec §9**

```yaml
slug: reactions
display_name: "Anime Reactions"

anime:
  mode: auto
  top_n: 8
  curated_ids: []
  exclude_genres: [Hentai, Ecchi]

persona:
  voice: "excited fan who's been watching since 2018"
  style: "energetic but informed, no clickbait, no fake reactions"
  hot_takes: true
  spoiler_policy: warn

tts:
  provider: edge-tts
  voice_id: en-US-GuyNeural
  speed: 1.05

output_mix:
  overview_per_episode: 1
  moments_per_episode: 2
  max_total_per_day: 12

schedule:
  publish_times_utc: ["02:00", "08:00", "14:00", "20:00"]
  immediate_publish: false

platforms:
  youtube:
    enabled: true
    auth_secret: YT_REFRESH_TOKEN_REACTIONS
    default_action: review_queued
    auto_publish_if_all_pass:
      - hook_score >= 7
      - coherence_score >= 7
      - sensitive_flag == clean
    title_template: "{anime} EP{ep} — {hook_summary}"
    description_template: |
      Quick take on {anime} episode {ep}.
      #anime #shorts #{anime_slug}
    tags: [anime, shorts, reaction]
    privacy: public

  tiktok:
    enabled: false
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `pytest tests/unit/test_reactions_channel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add channels/reactions.yaml tests/unit/test_reactions_channel.py
git commit -m "feat: first channel config (reactions)"
```

---

## Task 6: Supabase client wrapper

**Files:**
- Create: `tools/supabase_client.py`
- Create: `tests/unit/test_supabase_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_supabase_client.py
import pytest
from unittest.mock import MagicMock, patch
from tools import supabase_client as sb


def make_mock_client():
    client = MagicMock()
    # Set up chainable `client.table(...).insert(...).execute()` returning data.
    return client


def test_get_client_raises_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(KeyError):
        sb.get_client()


def test_get_client_uses_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")
    with patch("tools.supabase_client.create_client") as create:
        create.return_value = MagicMock()
        client = sb.get_client()
        create.assert_called_once_with("https://example.supabase.co", "fake-key")
        assert client is create.return_value


def test_insert_episode_returns_first_row():
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": 1, "title": "Frieren", "episode_num": 12, "status": "detected"}
    ]
    out = sb.insert_episode(client, {"anilist_id": 999, "title": "Frieren",
                                      "episode_num": 12, "status": "detected"})
    assert out["id"] == 1
    client.table.assert_called_once_with("episodes")


def test_get_episodes_by_status():
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": 1, "status": "detected"},
        {"id": 2, "status": "detected"},
    ]
    rows = sb.get_episodes_by_status(client, "detected")
    assert len(rows) == 2
    client.table.assert_called_once_with("episodes")


def test_update_episode_status_sets_field():
    client = MagicMock()
    sb.update_episode_status(client, 1, "downloaded", file_url="episodes/1.mp4")
    client.table.return_value.update.assert_called_once()
    update_kwargs = client.table.return_value.update.call_args[0][0]
    assert update_kwargs["status"] == "downloaded"
    assert update_kwargs["file_url"] == "episodes/1.mp4"


def test_signed_url_returns_url():
    client = MagicMock()
    client.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://signed.example/abc"
    }
    url = sb.signed_url(client, "episodes", "1.mp4", 3600)
    assert url == "https://signed.example/abc"
```

- [ ] **Step 2: Run the test — expect failure (module missing)**

Run: `pytest tests/unit/test_supabase_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/supabase_client.py`**

```python
"""Thin Supabase wrappers for episode/short state and storage."""
from __future__ import annotations
import os
from typing import Any
from supabase import create_client, Client


def get_client() -> Client:
    """Return a Supabase client built from SUPABASE_URL and SUPABASE_KEY env vars."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def insert_episode(client: Client, data: dict[str, Any]) -> dict[str, Any]:
    res = client.table("episodes").insert(data).execute()
    return res.data[0]


def get_episodes_by_status(client: Client, status: str) -> list[dict[str, Any]]:
    res = client.table("episodes").select("*").eq("status", status).execute()
    return res.data


def update_episode_status(client: Client, episode_id: int, status: str, **fields: Any) -> dict[str, Any]:
    fields["status"] = status
    res = client.table("episodes").update(fields).eq("id", episode_id).execute()
    return res.data[0] if res.data else {}


def insert_short(client: Client, data: dict[str, Any]) -> dict[str, Any]:
    res = client.table("shorts").insert(data).execute()
    return res.data[0]


def get_shorts_by_status(client: Client, status: str) -> list[dict[str, Any]]:
    res = client.table("shorts").select("*").eq("status", status).execute()
    return res.data


def update_short_status(client: Client, short_id: int, status: str, **fields: Any) -> dict[str, Any]:
    fields["status"] = status
    res = client.table("shorts").update(fields).eq("id", short_id).execute()
    return res.data[0] if res.data else {}


def upload_file(client: Client, bucket: str, dest_path: str, src_file_path: str) -> str:
    """Upload local file to a Supabase Storage bucket. Returns the dest_path."""
    with open(src_file_path, "rb") as f:
        client.storage.from_(bucket).upload(dest_path, f)
    return dest_path


def signed_url(client: Client, bucket: str, path: str, ttl_seconds: int = 3600) -> str:
    res = client.storage.from_(bucket).create_signed_url(path, ttl_seconds)
    return res["signedURL"]
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `pytest tests/unit/test_supabase_client.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/supabase_client.py tests/unit/test_supabase_client.py
git commit -m "feat: supabase client wrappers for episode/short state and storage"
```

---

## Task 7: LLM client — Claude Code headless wrapper

**Files:**
- Create: `tools/llm_client.py`
- Create: `tests/unit/test_llm_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_client.py
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from tools import llm_client
from tools.llm_client import ClaudeError


def _ok_completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_chat_returns_result_field():
    payload = json.dumps({"result": "hello world", "duration_ms": 123})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        out = llm_client.chat("test prompt")
        assert out == "hello world"
        args, kwargs = run.call_args
        cmd = args[0]
        assert cmd[0] == "claude"
        assert "-p" in cmd and "test prompt" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--model" in cmd and "sonnet" in cmd


def test_chat_passes_system_prompt():
    payload = json.dumps({"result": "yes"})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        llm_client.chat("p", system="you are X")
        cmd = run.call_args[0][0]
        assert "--system-prompt" in cmd
        assert "you are X" in cmd


def test_chat_overrides_model():
    payload = json.dumps({"result": "ok"})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        llm_client.chat("p", model="opus")
        cmd = run.call_args[0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"


def test_chat_wraps_nonzero_exit_in_claude_error():
    err = subprocess.CalledProcessError(returncode=2, cmd=["claude"], stderr="boom")
    with patch("tools.llm_client.subprocess.run", side_effect=err):
        with pytest.raises(ClaudeError, match="exited 2"):
            llm_client.chat("p")


def test_chat_wraps_timeout_in_claude_error():
    err = subprocess.TimeoutExpired(cmd="claude", timeout=1)
    with patch("tools.llm_client.subprocess.run", side_effect=err):
        with pytest.raises(ClaudeError, match="timed out"):
            llm_client.chat("p", timeout=1)


def test_chat_wraps_bad_json_in_claude_error():
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed("not-json")):
        with pytest.raises(ClaudeError, match="could not parse"):
            llm_client.chat("p")
```

- [ ] **Step 2: Run the test — expect failure**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/llm_client.py`**

```python
"""Claude Code headless-mode LLM client.

Authenticates via CLAUDE_CODE_OAUTH_TOKEN env var. Calls `claude -p ... --output-format json`
and returns the `result` string from the JSON payload.
"""
from __future__ import annotations
import json
import subprocess
from typing import Optional


class ClaudeError(RuntimeError):
    """Raised when the claude CLI fails or returns malformed output."""


def chat(prompt: str, system: Optional[str] = None, model: str = "sonnet",
         timeout: int = 120) -> str:
    """Send a single-turn prompt to Claude Code in headless mode.

    Args:
        prompt: User prompt text.
        system: Optional system prompt.
        model: Claude model alias (`sonnet`, `opus`, `haiku`, or full id).
        timeout: Subprocess timeout in seconds.

    Returns:
        The `result` field from Claude's JSON output.

    Raises:
        ClaudeError: on non-zero exit, timeout, or malformed JSON.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--system-prompt", system]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                check=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        raise ClaudeError(f"claude exited {e.returncode}: {e.stderr}") from e
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude timed out after {timeout}s") from e

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"could not parse claude output: {result.stdout[:200]}") from e

    if "result" not in payload:
        raise ClaudeError(f"claude payload missing 'result' field: {payload!r}")
    return payload["result"]
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/llm_client.py tests/unit/test_llm_client.py
git commit -m "feat: Claude Code headless-mode LLM client"
```

---

## Task 8: TTS client — edge-tts wrapper

**Files:**
- Create: `tools/tts_client.py`
- Create: `tests/unit/test_tts_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tts_client.py
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from tools import tts_client


def test_synthesize_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError, match="text must not be empty"):
        tts_client.synthesize("   ", str(tmp_path / "out.mp3"))


def test_synthesize_calls_edge_tts_with_rate(tmp_path):
    out = tmp_path / "out.mp3"

    fake_comm = MagicMock()
    fake_comm.save = AsyncMock()

    with patch("tools.tts_client.edge_tts.Communicate", return_value=fake_comm) as Comm:
        tts_client.synthesize("hello world", str(out), voice="en-US-AriaNeural", speed=1.10)

    # Communicate(text=..., voice=..., rate=...)
    kwargs = Comm.call_args.kwargs
    assert kwargs["text"] == "hello world"
    assert kwargs["voice"] == "en-US-AriaNeural"
    assert kwargs["rate"] == "+10%"
    fake_comm.save.assert_awaited_once_with(str(out))


def test_synthesize_negative_speed_rate(tmp_path):
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock()
    with patch("tools.tts_client.edge_tts.Communicate", return_value=fake_comm) as Comm:
        tts_client.synthesize("x", str(tmp_path / "o.mp3"), speed=0.90)
    assert Comm.call_args.kwargs["rate"] == "-10%"


def test_synthesize_creates_parent_dir(tmp_path):
    nested = tmp_path / "a" / "b" / "out.mp3"
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock()
    with patch("tools.tts_client.edge_tts.Communicate", return_value=fake_comm):
        tts_client.synthesize("x", str(nested))
    assert nested.parent.exists()


def test_default_voice_constant():
    assert tts_client.DEFAULT_VOICE == "en-US-GuyNeural"
```

- [ ] **Step 2: Run the test — expect failure**

Run: `pytest tests/unit/test_tts_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/tts_client.py`**

```python
"""edge-tts (Microsoft Cognitive Services) TTS wrapper.

Provides a synchronous `synthesize()` API that writes an MP3 file to disk.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
import edge_tts


DEFAULT_VOICE = "en-US-GuyNeural"


async def _synthesize_async(text: str, voice: str, output_path: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(output_path)


def _speed_to_rate(speed: float) -> str:
    """Convert speed multiplier to edge-tts rate string (e.g. 1.05 -> '+5%')."""
    pct = int(round((speed - 1.0) * 100))
    return f"{'+' if pct >= 0 else ''}{pct}%"


def synthesize(text: str, output_path: str, voice: str = DEFAULT_VOICE,
               speed: float = 1.0) -> str:
    """Synthesize `text` to an MP3 at `output_path`. Returns the path."""
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    rate = _speed_to_rate(speed)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_synthesize_async(text, voice, output_path, rate))
    return output_path


def list_voices() -> list[dict]:
    """Return all available edge-tts voices (synchronous wrapper)."""
    return asyncio.run(edge_tts.list_voices())
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `pytest tests/unit/test_tts_client.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Add a marked-slow real-synthesis integration test**

Add to `tests/unit/test_tts_client.py`:

```python
@pytest.mark.slow
def test_real_synthesis_produces_valid_mp3(tmp_path):
    """Hits real edge-tts; needs network. Skipped in fast CI."""
    out = tmp_path / "real.mp3"
    tts_client.synthesize("Hello world.", str(out))
    assert out.exists()
    assert out.stat().st_size > 1000  # ~1KB minimum for a short MP3
    # MP3 magic bytes: ID3 or 0xFF 0xFB
    head = out.read_bytes()[:4]
    # Accept ID3v2 tag or any MPEG audio frame sync (11-bit pattern 0xFFE).
    is_mpeg_frame = head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    assert head.startswith(b"ID3") or is_mpeg_frame
```

- [ ] **Step 6: Run the slow test once locally to verify real synthesis works**

Run: `pytest tests/unit/test_tts_client.py::test_real_synthesis_produces_valid_mp3 -v -m slow`
Expected: PASS (requires network)

- [ ] **Step 7: Commit**

```bash
git add tools/tts_client.py tests/unit/test_tts_client.py
git commit -m "feat: edge-tts TTS client wrapper"
```

---

## Task 9: CLI scaffold with stub subcommands

**Files:**
- Create: `main.py`
- Create: `tests/unit/test_main_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_main_cli.py
from click.testing import CliRunner
from main import cli


def test_cli_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("init", "poll", "review", "publish"):
        assert sub in result.output


def test_init_creates_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    for d in ("data/episodes", "data/audio", "data/output", "data/transcripts", ".tmp"):
        assert (tmp_path / d).is_dir()


def test_init_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0


def test_poll_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["poll"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output.lower()


def test_review_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["review"])
    assert result.exit_code == 0


def test_publish_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["publish"])
    assert result.exit_code == 0


def test_channels_lists_loaded_channels(tmp_path, monkeypatch):
    # Point CHANNELS_DIR at a tmp dir containing reactions.yaml
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    monkeypatch.setenv("CHANNELS_DIR", str(repo_root / "channels"))
    runner = CliRunner()
    result = runner.invoke(cli, ["channels"])
    assert result.exit_code == 0
    assert "reactions" in result.output
```

- [ ] **Step 2: Run the test — expect failure**

Run: `pytest tests/unit/test_main_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implement `main.py`**

```python
"""anime-commentary CLI entrypoint.

Subcommands are stubs in this foundation plan. Subsequent plans wire them up.
"""
from __future__ import annotations
import os
from pathlib import Path
import click

from tools.channel_config import discover_channels, ChannelConfigError


DEFAULT_CHANNELS_DIR = Path(__file__).resolve().parent / "channels"


@click.group()
def cli() -> None:
    """Anime Commentary pipeline."""


@cli.command()
def init() -> None:
    """Create local data directories used by the pipeline."""
    for d in ("data/episodes", "data/audio", "data/output", "data/transcripts", ".tmp"):
        Path(d).mkdir(parents=True, exist_ok=True)
        click.echo(f"created {d}")


@cli.command()
def poll() -> None:
    """Run the hourly pipeline traversal. (not yet implemented — see Plan 2)"""
    click.echo("poll: not yet implemented")


@cli.command()
def review() -> None:
    """Walk pending shorts in the review queue. (not yet implemented — see Plan 5)"""
    click.echo("review: not yet implemented")


@cli.command()
def publish() -> None:
    """Publish approved shorts. (not yet implemented — see Plan 4)"""
    click.echo("publish: not yet implemented")


@cli.command()
def channels() -> None:
    """List loaded channel configs."""
    channels_dir = Path(os.environ.get("CHANNELS_DIR", str(DEFAULT_CHANNELS_DIR)))
    try:
        configs = discover_channels(channels_dir)
    except ChannelConfigError as e:
        raise click.ClickException(str(e))
    if not configs:
        click.echo(f"no channel configs found in {channels_dir}")
        return
    for c in configs:
        platforms = []
        if c.platforms.youtube.enabled:
            platforms.append("youtube")
        if c.platforms.tiktok.enabled:
            platforms.append("tiktok")
        click.echo(f"{c.slug}  ({c.display_name})  platforms={','.join(platforms) or '-'}")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `pytest tests/unit/test_main_cli.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Run the full test suite to confirm everything green**

Run: `pytest -v -m "not slow"`
Expected: all tests PASS

- [ ] **Step 6: Verify CLI works end-to-end manually**

Run:
```bash
python main.py --help
python main.py channels
python main.py init
ls data/
```

Expected:
- `--help` lists `init`, `poll`, `review`, `publish`, `channels`
- `channels` prints `reactions  (Anime Reactions)  platforms=youtube`
- `init` creates the four `data/` subdirs and `.tmp/`
- `ls data/` shows `episodes  audio  output  transcripts`

- [ ] **Step 7: Commit**

```bash
git add main.py tests/unit/test_main_cli.py
git commit -m "feat: CLI scaffold with stub subcommands"
```

---

## Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v -m "not slow" --cov=tools --cov=main --cov-report=term-missing`
Expected: all tests PASS; coverage on `tools/` and `main` ≥ 85%.

- [ ] **Step 2: Verify project structure**

Run: `find . -type f -name "*.py" -o -name "*.yaml" -o -name "*.sql" -o -name "*.toml" -o -name "*.md" | grep -v ".venv" | grep -v ".tmp" | sort`

Expected file listing should include:
- pyproject.toml, requirements.txt, requirements-dev.txt
- main.py
- tools/__init__.py, tools/channel_config.py, tools/llm_client.py, tools/tts_client.py, tools/supabase_client.py
- shared_tools/__init__.py + 5 vendored .py files
- channels/reactions.yaml
- docs/schema.sql
- docs/superpowers/specs/2026-05-15-anime-commentary-pipeline-design.md
- docs/superpowers/plans/2026-05-15-foundation.md (this file)
- tests/conftest.py, tests/fixtures/*.yaml, tests/unit/test_*.py

- [ ] **Step 3: Confirm git log shows discrete commits**

Run: `git log --oneline`
Expected: ~9 commits, one per task.

---

## What this plan delivers

After completion, the repo has:

- All client wrappers functioning with full unit-test coverage (Claude Code, edge-tts, Supabase).
- Channel YAML schema with pydantic validation; `reactions.yaml` loads cleanly.
- Database schema captured as SQL; ready to apply to a Supabase project (Plan 6 task).
- CLI scaffold (`main.py`) with `init`, `channels` (working) and `poll`/`review`/`publish` (stubs).
- Vendored helper tools from `shorts maker` ready to be used or replaced in later plans.
- Test suite passing under `pytest -m "not slow"`.

## What this plan does NOT deliver (see follow-up plans)

- Episode polling, downloading, transcription, scripting, voicing, rendering — **Plan 2**.
- Moment detection and moment-short rendering — **Plan 3**.
- Confidence gate and YouTube upload — **Plan 4**.
- Streamlit review UI — **Plan 5**.
- GitHub Actions workflows, metrics polling, Discord alerts — **Plan 6**.
