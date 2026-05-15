# Anime Commentary Pipeline — Design Spec

**Date:** 2026-05-15
**Status:** Approved — ready for implementation planning
**Author/Operator:** sh4d0w (shivamlfs123@gmail.com)

---

## 1. Overview

Automated pipeline that produces short-form anime commentary videos (YouTube Shorts), driven by AniList airing data, scripted by Claude, voiced by edge-tts, rendered by FFmpeg, and published to YouTube. Goal: a low-touch system that produces ~10-20 shorts/day with ~30 min/day of human review, with zero recurring infrastructure cost.

This is the operator's third shorts-related project, after `shorts maker/` (generic short-form pipeline, Feb 2026) and `anime to shorts/` (episode-chunking experiment using n8n, Mar 2026). This project explicitly builds on top of the WAT framework defined at `~/agentic coding projects/CLAUDE.md` and vendors specific tools from `shorts maker/`.

## 2. Goals & Non-Goals

### Goals (MVP)

- Detect newly-aired anime episodes within ~1 hour of release.
- For each tracked episode, produce **1 overview recap short** + **2 moment shorts** automatically.
- Auto-acquire episode files via `ani-cli` with a provider-chain fallback.
- Apply per-platform confidence gating: TikTok-style "loose" thresholds vs YouTube-style "strict" thresholds (configurable per channel; YouTube only at MVP).
- Surface shorts that fail confidence checks to a human review queue (Streamlit Community Cloud).
- Cost ceiling: $0/month. All services use free tiers or the operator's existing Claude Code subscription.
- Architecture supports N channels (each = one YAML config) but launches with one (`reactions.yaml`).

### Non-Goals (deferred to v1.5+)

- TikTok publishing (defer until YouTube channel is monetized or until we accept browser-automation fragility / paid uploader).
- In-UI script editing & re-render from the review queue (avoid ElevenLabs/TTS waste on day-one iteration; introduce after seeing real reject rates).
- Word-error-rate (WER) confidence check between script and rendered audio (drop at MVP since whisper API is paid; reintroduce later with whisper.cpp if reject rates indicate need).
- Local Whisper API transcription as primary path (use embedded subs first, whisper.cpp small.en in CI as fallback).
- Multi-channel launch at day one (architecturally supported, but launch one channel only).
- Automated comment replies, community management.
- Distributed tracing, Prometheus, Sentry.

## 3. Existing Assets to Reuse

### From `~/agentic coding projects/shorts maker/`

Vendored (copied, not symlinked — GH Actions clones only this repo):

| Script | What it does | Vendor as |
|---|---|---|
| `tools/generate_script.py` | LLM prompt → structured script JSON | `shared_tools/generate_script.py` |
| `tools/generate_voiceover.py` | TTS → MP3 (current: ElevenLabs; needs adaptation for edge-tts) | `shared_tools/generate_voiceover.py` |
| `tools/burn_captions.py` | ASS subtitles from word timestamps + FFmpeg burn | `shared_tools/burn_captions.py` |
| `tools/assemble_generated_short.py` | FFmpeg normalize + concat + audio mix | `shared_tools/assemble_generated_short.py` |
| `tools/transcribe_video.py` | Whisper API wrapper (needs whisper.cpp fallback added) | `shared_tools/transcribe_video.py` |

### From `~/agentic coding projects/anime to shorts/`

| Script | Reuse |
|---|---|
| `tools/create_shorts.py` | Logic for `_has_subtitle_stream` (embedded subs detection) and 9:16 conversion with blurred BG via FFmpeg |
| `tools/upload_youtube.py` | Direct copy (it works; just rebind to per-channel credentials) |

### NOT reusing

- `anime to shorts/tools/download_anime.py` — broken (JSON parse error); replaced by ani-cli wrapper.
- `anime to shorts/workflows/*.json` (n8n) — n8n architecture abandoned for GitHub Actions.

## 4. Architecture

### Deployment

- **GitHub Actions on a public repo** (free unlimited Linux minutes; secrets encrypted regardless of repo visibility).
- All scheduled work runs in workflow YAMLs under `.github/workflows/`.

### State and Storage

- **Supabase free tier** for state (Postgres, 500MB) and binary storage (1GB).
- Tables: `episodes`, `shorts`, `jobs`, `metrics`.
- Storage buckets: `episodes/` (downloaded source files), `audio/` (TTS output), `output/` (rendered shorts), `transcripts/`.

### Review UI

- **Streamlit Community Cloud** (free), deployed directly from this repo.
- Reads/writes Supabase. Auth: Streamlit Cloud's Google OAuth gate, locked to operator's email.

### LLM Integration

- **Claude Code in headless mode** via `claude -p "..." --output-format json`.
- Authenticated in CI via `CLAUDE_CODE_OAUTH_TOKEN` (long-lived OAuth token generated locally with `claude setup-token`, stored as GitHub Secret).
- Billed against operator's Claude subscription — zero additional cost.
- All LLM calls funnel through `tools/llm_client.py` (single abstraction; can swap to API later).

### Other Free Services

| Component | Service | Auth |
|---|---|---|
| Anime metadata | AniList GraphQL API | None |
| TTS | edge-tts (Microsoft Cognitive Services) | None |
| Episode acquisition | ani-cli (multi-provider scrape) | None |
| Visual assets | AniList key art + MangaDex API (manga panels) | None |
| Publishing | YouTube Data API v3 | OAuth refresh token per channel, stored as GH Secret |
| Notifications | Discord webhook (reused from `anime to shorts`) | None |
| Transcription | Embedded subs first; whisper.cpp small.en fallback in CI | None |

### Project Layout

```
anime-commentary/                       # public GitHub repo
├── README.md
├── pyproject.toml
├── main.py                             # Click CLI: poll, render, review, publish, init
├── orchestrator.py                     # State machine driver
├── channels/
│   ├── reactions.yaml                  # MVP channel
│   ├── analysis.yaml.disabled          # future channel template
│   ├── news.yaml.disabled              # future
│   └── rankings.yaml.disabled          # future
├── tools/                              # NEW anime-specific scripts
│   ├── poll_anilist.py
│   ├── download_episode.py             # ani-cli wrapper with provider chain
│   ├── extract_subs.py                 # embedded subs OR whisper.cpp fallback
│   ├── fetch_episode_summary.py        # Reddit/MAL crowd-summaries (fallback path)
│   ├── fetch_anime_visuals.py          # AniList key art, MangaDex panels
│   ├── detect_moments.py               # transcript → LLM → moment timestamps
│   ├── confidence_check.py             # post-render gate
│   ├── llm_client.py                   # Claude Code headless wrapper
│   ├── tts_client.py                   # edge-tts wrapper
│   ├── supabase_client.py              # state/storage helpers
│   └── upload_youtube.py
├── shared_tools/                       # vendored from shorts maker
│   ├── generate_script.py
│   ├── generate_voiceover.py
│   ├── burn_captions.py
│   ├── assemble_generated_short.py
│   └── transcribe_video.py
├── workflows/                          # WAT SOPs (markdown for Claude+human)
│   ├── overview_recap.md
│   ├── moment_short.md
│   └── publish_flow.md
├── .github/workflows/                  # GH Actions YAMLs
│   ├── poll.yml                        # hourly cron: full pipeline traversal
│   ├── publish.yml                     # every 15min: publish approved
│   ├── metrics.yml                     # every 6h: pull analytics
│   └── test.yml                        # on push: pytest
├── review_ui/                          # Streamlit Cloud app
│   ├── app.py
│   └── requirements.txt
├── docs/
│   └── superpowers/specs/              # THIS file
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
└── .env.example
```

## 5. Components & Data Flow

### Unified pipeline (single traversal)

```
poll.yml (cron: 0 * * * *)
  ↓
poll_anilist.py             → episodes(status=detected)
  ↓
download_episode.py         → ani-cli (provider chain)
                              episode file uploaded to Supabase Storage
                              ├ all providers fail → status=acquisition_failed
                              │   Pipeline A falls back to crowd-summary; Pipeline B skipped
                              └ success            → status=downloaded
  ↓
extract_subs.py             → embedded subs (preferred) OR whisper.cpp small.en
                              → status=transcribed
  ↓
  ┌─────────────────────────┬───────────────────────────────┐
  │ Track A: overview        │ Track B: moments (×N per ep) │
  ↓                          ↓
generate_script.py         detect_moments.py → clip_video → generate_script.py
(commentary from full        (per-moment 20-30s reaction)
 transcript, 45-60s)
  ↓                          ↓
generate_voiceover.py       generate_voiceover.py + burn_captions.py
(edge-tts)                  (edge-tts; subs from word timing)
  ↓                          ↓
fetch_anime_visuals.py     (uses clip + commentary mixed over clip audio at low vol)
(safe visuals: key art,
 promo, manga)
  ↓                          ↓
assemble_generated_short    assemble (vertical 9:16, original audio ducked under voice)
  ↓                          ↓
  └────► status=rendered ◄───┘
              ↓
        confidence_check.py     (per-platform thresholds from channel YAML)
              ↓
       ┌──────┴──────────┐
   auto_publish_queued  review_queued
              ↓                  ↓
       publish.yml (15min)   Streamlit review → approve → auto_publish_queued
              ↓
        status=published
```

Each pipeline stage is idempotent: it picks up rows in the prior status and advances them. A crashed run is re-tried by the next hourly poll.

### `download_episode.py` provider chain

```python
PROVIDERS = ["allanime", "gogoanime", "9anime"]  # ani-cli's known scrape sources

for provider in PROVIDERS:
    result = run_ani_cli(provider, anime_title, episode_num, quality="720p")
    if result.success:
        upload_to_supabase(result.file_path, f"episodes/{episode_id}.mp4")
        return result
mark_failed(episode_id, "all_providers_failed")
```

### `llm_client.py` (Claude Code headless wrapper)

```python
import subprocess, json, os

def chat(prompt: str, system: str | None = None, model: str = "sonnet") -> str:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--system-prompt", system]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True,
                            env={**os.environ})
    return json.loads(result.stdout)["result"]
```

### GH Actions install of dependencies

```yaml
# .github/workflows/poll.yml fragment
- uses: actions/setup-python@v5
  with: { python-version: '3.12' }
- uses: actions/setup-node@v4
  with: { node-version: 20 }

- name: System deps
  run: sudo apt-get update && sudo apt-get install -y ffmpeg curl sed grep gawk

- name: Install ani-cli
  run: |
    curl -fsSL https://raw.githubusercontent.com/pystardust/ani-cli/master/ani-cli -o /usr/local/bin/ani-cli
    sudo chmod +x /usr/local/bin/ani-cli

- name: Install Claude Code
  run: npm install -g @anthropic-ai/claude-code

- name: Configure Claude auth
  run: echo "CLAUDE_CODE_OAUTH_TOKEN=${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}" >> $GITHUB_ENV

- name: Install Python deps
  run: pip install -r requirements.txt

- name: Run poll
  env:
    SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
    SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
  run: python main.py poll
```

## 6. State Machine (one row per `shorts.id`)

```
detected
  → downloaded
    → transcribed
      → script_ready
        → voice_ready
          → rendered
            → [confidence_check]
              ├ pass strict → auto_publish_queued
              └ fail        → review_queued
                                ↓ [human approves]
                              auto_publish_queued
            → publishing
              → published
                
Failure terminal states:
  acquisition_failed | transcription_failed | script_failed |
  tts_failed         | render_failed         | confidence_check_failed |
  publish_failed     | rejected              | abandoned
```

**Idempotency rule:** every stage transitions `status` only on success. A crashed workflow re-runs and picks up wherever it left off.

## 7. Database Schema (Supabase Postgres)

```sql
CREATE TABLE episodes (
  id             BIGSERIAL PRIMARY KEY,
  anilist_id     INT NOT NULL,
  title          TEXT NOT NULL,
  episode_num    INT NOT NULL,
  aired_at       TIMESTAMPTZ,
  detected_at    TIMESTAMPTZ DEFAULT NOW(),
  file_url       TEXT,                         -- supabase storage path
  transcript_url TEXT,
  summary_text   TEXT,                         -- only populated when transcript path failed
  summary_source TEXT,                         -- 'reddit' | 'mal' | 'mixed' | NULL when transcript used
  status         TEXT NOT NULL,                -- episode-level status
  metadata       JSONB,                        -- key visuals, AniList payload
  UNIQUE (anilist_id, episode_num)
);

CREATE TABLE shorts (
  id            BIGSERIAL PRIMARY KEY,
  episode_id    BIGINT REFERENCES episodes(id) ON DELETE CASCADE,
  channel_slug  TEXT NOT NULL,                 -- maps to channels/<slug>.yaml
  kind          TEXT NOT NULL,                 -- 'overview' | 'moment'
  moment_idx    INT,                           -- NULL for overview
  status        TEXT NOT NULL,
  script_text   TEXT,
  audio_url     TEXT,
  video_url     TEXT,
  duration_sec  NUMERIC,
  confidence    JSONB,                         -- all check results
  platform      TEXT NOT NULL,                 -- 'youtube' | 'tiktok'
  external_url  TEXT,                          -- published URL
  error_log     TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  published_at  TIMESTAMPTZ
);

CREATE TABLE jobs (
  id         BIGSERIAL PRIMARY KEY,
  kind       TEXT NOT NULL,
  status     TEXT NOT NULL,
  payload    JSONB,
  log        TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at   TIMESTAMPTZ
);

CREATE TABLE metrics (
  id            BIGSERIAL PRIMARY KEY,
  short_id      BIGINT REFERENCES shorts(id) ON DELETE CASCADE,
  polled_at     TIMESTAMPTZ DEFAULT NOW(),
  views         INT,
  likes         INT,
  retention_pct NUMERIC
);

CREATE INDEX ON shorts (status);
CREATE INDEX ON shorts (channel_slug, platform);
CREATE INDEX ON episodes (status);
```

### Storage retention

- Episode source files: auto-delete 7 days after the last child `shorts.published_at` (Supabase Edge Function or cron-driven cleanup in `poll.yml`).
- Audio/output assets: keep indefinitely (small) until parent short is `abandoned`.

## 8. Workflow Trigger Graph

| Workflow | Trigger | Responsibility |
|---|---|---|
| `poll.yml` | `cron: '0 * * * *'` (hourly) | Full pipeline: poll AniList → download → transcribe → script → voice → render → confidence_check |
| `publish.yml` | `cron: '*/15 * * * *'` | Read `auto_publish_queued` rows, upload to YouTube, mark `published` |
| `metrics.yml` | `cron: '0 */6 * * *'` (every 6h) | Pull view/retention numbers per published short, write to `metrics` |
| `test.yml` | `push` to any branch | pytest (unit + fast integration) |
| `e2e.yml` | `pull_request` to main | Slow E2E test with fixture episode |

`render.yml` was considered as a separate workflow but folded into `poll.yml` — same workflow walks the state machine forward, simpler.

`ingest_episode.yml` was removed when ani-cli auto-acquisition replaced the watch-folder mechanism.

## 9. Channel YAML Spec

```yaml
# channels/reactions.yaml
slug: reactions
display_name: "Anime Reactions"

anime:
  mode: auto                # 'auto' = top N airing | 'curated' = explicit list
  top_n: 8                  # only used if mode=auto
  curated_ids: []           # AniList media IDs if mode=curated
  exclude_genres: [Hentai, Ecchi]

persona:
  voice: "excited fan who's been watching since 2018"
  style: "energetic but informed, no clickbait, no fake reactions"
  hot_takes: true
  spoiler_policy: warn      # warn | reveal | avoid

tts:
  provider: edge-tts
  voice_id: en-US-GuyNeural
  speed: 1.05

output_mix:
  overview_per_episode: 1
  moments_per_episode: 2
  max_total_per_day: 12     # global safety cap

schedule:
  publish_times_utc: ["02:00", "08:00", "14:00", "20:00"]
  immediate_publish: false  # bypass schedule = publish ASAP

platforms:
  youtube:
    enabled: true
    auth_secret: YT_REFRESH_TOKEN_REACTIONS   # GH Secret name
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
    enabled: false          # MVP: deferred
```

### Channel YAML validation

`tools/channel_config.py` loads + validates each YAML on startup. Required fields enforced. Unknown keys logged as warnings (forward-compat). Invalid configs fail the workflow loudly with a Discord alert.

### Adding a future channel

1. `cp channels/reactions.yaml channels/analysis.yaml`
2. Edit persona, anime mode, voice, output mix
3. Create separate YouTube channel + OAuth → `YT_REFRESH_TOKEN_ANALYSIS` in GH Secrets
4. Push. Pipeline auto-discovers on next `poll.yml` run.

## 10. Confidence Check Spec

`tools/confidence_check.py` runs all checks; returns dict of `(check_name, passed, score, evidence)`; written to `shorts.confidence` JSONB.

### Technical sanity checks (deterministic; FFprobe + librosa)

| Check | Definition | Notes |
|---|---|---|
| `duration` | 20s ≤ video ≤ 90s | Hard fail outside range |
| `audio_silence_pct` | % of audio under -40dB | Detects TTS that died mid-call |
| `av_sync` | abs(audio_len - video_len) < 1s | Detects FFmpeg assemble drift |
| `no_black_frames` | First/last 0.5s isn't pure black | Catches concat glitches |
| `filesize_sane` | 1MB ≤ filesize ≤ 100MB | Floor/ceiling sanity |
| `captions_present` | ASS subs baked in (if expected) | Per-channel config |

### Content quality checks (LLM via Claude)

| Check | Method |
|---|---|
| `hook_score` | LLM rates first 3s of script (1-10). Sonnet, single call. |
| `coherence_score` | LLM rates whole script (1-10). |
| `sensitive_flag` | LLM detects profanity / unwarned spoilers / inflammatory takes. Returns `clean` / `flagged`. |
| `name_spelling` | String match against AniList canonical character/anime names. |

### Expression syntax in channel YAML

The strings under `auto_publish_if_all_pass` and `rejecting_checks` are simple expressions parsed by a small DSL in `tools/confidence_check.py`. Supported operators: `>=`, `<=`, `>`, `<`, `==`, `!=`. LHS must be a known check name; RHS is a literal (number or unquoted symbol like `clean`). No nesting, no boolean combinators (use a list — implicit AND). Implementation uses the `operator` module, never `eval()`.

Examples:
- `hook_score >= 7`
- `audio_silence_pct (max=0.05)` — alternate shorthand: `check_name (param=value)` for parametric checks

### Per-platform threshold logic

```python
def evaluate(short, channel_config):
    platform_cfg = channel_config["platforms"][short.platform]
    checks = run_all_checks(short)

    if platform_cfg["default_action"] == "auto_publish":
        # TikTok-style: publish unless a rejecting check fails
        for c in platform_cfg.get("rejecting_checks", []):
            if not check_passes(c, checks):
                return "review_queued"
        return "auto_publish_queued"

    else:  # default_action == "review_queued" (YouTube)
        all_pass = all(check_passes(c, checks)
                       for c in platform_cfg.get("auto_publish_if_all_pass", []))
        return "auto_publish_queued" if all_pass else "review_queued"
```

### WER check (deferred)

A whisper-cpp transcribe of the rendered output, compared via `jiwer.wer` to the original script, is in the design but **dropped for MVP** to save runner minutes. Reintroduced if observed reject rates indicate scripts aren't faithfully voiced.

## 11. Review UI Spec (Streamlit Community Cloud)

Single Streamlit app deployed from `review_ui/app.py`. Four tabs:

### Tab 1 — Queue

- Filters: Channel, Platform, Status (`review_queued` by default), Age
- Two-pane: short list (left) + selected short detail (right)
- Detail pane shows:
  - Embedded video player (signed Supabase URL, 1h expiry, rotates on refresh)
  - Script text
  - Confidence breakdown (✅/⚠/❌ per check)
  - Buttons: **Approve & Publish** | **Reject (with reason)**
- Approve → write `status='auto_publish_queued'` → picked up by next `publish.yml` (≤15 min latency)
- Reject → prompts reason → write `status='rejected'` + reason → never reattempted

### Tab 2 — Recently Published

- Last 50 published shorts
- Columns: title, channel, platform, published_at, views, retention_pct, link
- Sortable; lets operator spot underperforming hooks and iterate prompts

### Tab 3 — System Health

- Last successful poll/download/publish (each with timestamp)
- Stuck jobs (no status change >2h)
- Failed-state counts by status
- YouTube daily quota consumed
- Last 20 errors from `jobs.log`

### Tab 4 — Channel Configs

- Read-only view of each channel YAML
- Editing happens via git commit; redirects operator to GitHub web edit URL

### Auth

- Streamlit Cloud Google OAuth gate, allowlist: `shivamlfs123@gmail.com`

### Out of MVP scope

- In-UI script editing & re-render (TTS cost discipline). Add after seeing reject patterns.
- Comment-reply tools.
- Analytics graphs beyond simple lists.

## 12. Testing Strategy

```
tests/
├── unit/
│   ├── test_channel_config.py    # YAML schema, defaults, validation
│   ├── test_state_machine.py     # legal status transitions
│   ├── test_confidence_check.py  # threshold logic
│   └── test_templates.py         # script + title template substitution
├── integration/
│   ├── test_anilist_poller.py    # read-only against real AniList
│   ├── test_ani_cli_download.py  # downloads a known short clip
│   ├── test_edge_tts.py          # synthesizes one line, asserts valid MP3
│   └── test_youtube_upload.py    # uploads to test channel as private
├── e2e/
│   └── test_full_pipeline.py     # fixture episode → rendered MP4 → confidence
└── fixtures/                     # 30s sample clip, JSON transcript, etc.
```

### CI Strategy

- `test.yml` runs on every push: `pytest -m "not slow"` (target <2 min)
- `e2e.yml` runs only on PRs to main: full E2E with fixture (keeps free-minute budget intact)
- Coverage target: pure logic >90%; subprocess wrappers ≥1 happy-path test
- LLM calls: mocked in unit tests; golden-output eval suite in `tests/eval/` (not gated in CI)

## 13. Failure Handling

### Retry policy per stage

| Stage | Retry policy | Terminal state |
|---|---|---|
| `poll_anilist` | 3× exp backoff (30s, 2m, 5m) | Skip cycle; Discord low-pri |
| `download_episode` | Provider chain: 3 providers × 2 retries each | `acquisition_failed` |
| `extract_subs` | Embedded → whisper.cpp fallback (no further retry) | `transcription_failed` |
| `generate_script` | 3× exp backoff (10s, 30s, 1m) | `script_failed`; Discord high-pri |
| `generate_voiceover` | 3× exp backoff (5s, 15s, 30s) | `tts_failed` |
| `assemble` (FFmpeg) | **No retry** (deterministic — re-run won't help) | `render_failed`; quarantined |
| `confidence_check` | 2× retry on LLM-side checks only | `confidence_check_failed` (falls through to review queue — safest default) |
| `upload_youtube` | 3× exp backoff (5m, 15m, 1h) | `publish_failed`; surfaced in Streamlit Health |

### Terminal-state semantics

- **`*_failed` states** (e.g. `render_failed`, `publish_failed`) are **retriable**. They land in DB with `error_log` populated; surfaced in Streamlit Health tab; manual retry from UI sets status back one stage and re-queues.
- **`rejected`** is **final** — a human explicitly rejected this short in the review UI. Never reattempted; not retriable. To produce a different short for the same episode, the operator triggers a fresh render via a new row.
- **`abandoned`** is **final** — operator gave up on a `*_failed` row that's not worth fixing.

### Acquisition-failed fallback (Pipeline A only)

If `download_episode` exhausts all providers, Pipeline A (overview short) falls back to a **crowd-summary** path:
- `fetch_episode_summary.py` scrapes Reddit r/anime episode discussion + MAL episode page
- Waits up to 4 hours for sufficient crowd-summary content
- Script is generated from summary instead of transcript
- Visuals remain safe (key art, promo)

Pipeline B (moment shorts) is **skipped** for that episode — no episode file means no clips.

## 14. Observability

### Logs

- Every tool logs structured JSON to stdout: `{ts, tool, stage, episode_id, short_id, level, msg}`
- GH Actions captures stdout in workflow run UI (free, searchable)
- Each job's concatenated stdout also written to `jobs.log` for long-term retention

### Metrics

- `metrics.yml` polls YouTube Analytics API every 6h per published short → `metrics` table
- Tracks: views, likes, retention_pct, watch_time
- Streamlit "Recently Published" tab: sortable leaderboard; auto-flags low-retention shorts for prompt iteration

### Alerts (Discord webhook)

Reuses operator's existing Discord webhook (already in `anime to shorts/run.sh`).

| Event | Priority |
|---|---|
| `acquisition_failed` single episode | low (silent count) |
| `render_failed` / `publish_failed` | high (full @here ping) |
| Pipeline hasn't completed E2E in 24h | high (system health) |
| Daily summary 23:00 UTC | info (shorts produced/published/views) |

### Out of MVP scope

- Distributed tracing
- Prometheus/Grafana
- Sentry-style error tracking
- Per-stage performance histograms (GH Actions UI suffices)
- Automated A/B testing of prompts

## 15. Setup Checklist

Operator-actionable, in order. Most are one-time terminal commands; the few unavoidable web steps are flagged.

```bash
# 1. Create GitHub repo (operator does this on github.com - PUBLIC visibility)
#    Repo name: anime-commentary

# 2. Clone locally and scaffold from this spec
git clone git@github.com:<user>/anime-commentary.git
cd anime-commentary

# 3. (Web step) Create Supabase project at supabase.com
#    Free tier. Note SUPABASE_URL and SUPABASE_KEY (service role).
#    Run schema migrations from docs/schema.sql

# 4. Generate Claude Code OAuth token
claude setup-token
# Copy token shown.

# 5. (Web step) Create YouTube channel + Google Cloud project for OAuth
#    Get client_secrets.json; run a one-time local OAuth flow:
python tools/upload_youtube.py --bootstrap-oauth
# Outputs a refresh_token. Save it.

# 6. Add all secrets to GitHub repo (web step on github.com → Settings → Secrets):
#    CLAUDE_CODE_OAUTH_TOKEN
#    SUPABASE_URL
#    SUPABASE_KEY
#    YT_REFRESH_TOKEN_REACTIONS
#    YT_CLIENT_ID
#    YT_CLIENT_SECRET
#    DISCORD_WEBHOOK_URL

# 7. (Web step) Deploy Streamlit Cloud app from this repo's review_ui/ dir
#    Configure same Supabase env vars.
#    Bookmark the URL.

# 8. Push. First poll.yml runs on next hourly cron.

# 9. Run first manual poll for immediate feedback:
gh workflow run poll.yml
```

## 16. Open Questions / Residual Risks

1. **Legal exposure (ani-cli).** Auto-scraped episodes from grey-area sources is the riskiest element. Mitigation: confidence_check's `sensitive_flag` is the only gate; consider periodic legal review. Accepted by operator with eyes open.
2. **Datacenter IP blocks on ani-cli providers.** GitHub Actions runner IPs may be blocked by some streaming sites. Will discover during integration testing. Mitigation: 3+ provider fallbacks; can route through Cloudflare WARP if needed.
3. **YouTube Content ID strikes.** Even safe-visual overview shorts could trip Content ID on background music or accidentally-used clips. Mitigation: only use royalty-free BGM (YouTube Audio Library); confidence_check warns on detection of any embedded audio with copyright fingerprint.
4. **ani-cli scraper drift.** Providers change selectors monthly. Mitigation: pin ani-cli version per workflow; monthly manual bump; Discord alert when all providers fail simultaneously.
5. **Claude usage in CI.** Claude Code subscription limits are not explicitly documented for headless usage at this scale. ~120 calls/day at MVP. If we hit limits, swap `LLM_PROVIDER` env var to API key path.
6. **Supabase free-tier limits.** 500MB DB + 1GB storage. Auto-cleanup of episode source files after 7 days is mandatory to avoid blowing the cap.
7. **Streamlit Cloud reliability.** Free tier has periodic outages. Acceptable for a review UI (worst case: review work backs up).

## 17. Cost Summary

| Cost Center | Service | Cost |
|---|---|---|
| Compute | GitHub Actions (public repo, Linux) | $0 (unlimited) |
| LLM | Claude Code subscription (already paid) | $0 marginal |
| TTS | edge-tts | $0 |
| Database + storage | Supabase free tier | $0 (within limits) |
| Review UI hosting | Streamlit Community Cloud | $0 |
| Episode acquisition | ani-cli (free tool, grey-area sources) | $0 |
| Transcription | Embedded subs + whisper.cpp | $0 |
| Anime metadata | AniList API | $0 |
| Visuals | AniList + MangaDex API | $0 |
| Notifications | Discord webhook | $0 |
| Publishing | YouTube Data API v3 | $0 (within 10k daily quota) |
| **Total recurring** | | **$0/month** |

Hidden cost: operator time. Realistic budget:

- Weeks 1-3 (build): ~15-30 hrs total
- Weeks 4-8 (iterate prompts based on retention): ~5 hrs/week
- Months 3-6 (stabilize): ~3 hrs/week
- Month 6+ (steady-state, if working): ~30 min/day

## 18. Decisions Log

Captures the reasoning behind non-obvious choices, for handoff/audit.

| Decision | Why |
|---|---|
| GitHub Actions over local cron | l3l0uch unavailable; operator wanted always-on without paying for VPS; public repo gives free unlimited minutes |
| Supabase over SQLite-on-Actions | GH Actions runners are stateless — SQLite would need sync between runs, which is fragile |
| Claude Code headless over Anthropic API | Operator has subscription, no API credits; subscription covers headless mode at our scale |
| edge-tts over ElevenLabs | $0 vs $5+/mo; quality acceptable for commentary; can upgrade later |
| ani-cli over fixing `download_anime.py` | Existing script was crashing; ani-cli is actively maintained |
| Embedded subs over Whisper API | $0 vs paid; ani-cli rips usually include subs; whisper.cpp covers fallback |
| Hybrid clip source (safe visuals for overview, real clips for moments) | Aligns with platform asymmetry: YT-bound overviews use safe assets; TikTok-bound moments use real clips |
| TikTok deferred from MVP | No clean free API; browser-automation is fragile; revisit after YouTube monetization |
| Drop WER check at MVP | Whisper API costs money; whisper.cpp in CI burns runner minutes; reintroduce only if reject rates indicate need |
| Approve/reject only in UI (no in-UI edit) | Avoids ElevenLabs/TTS waste on day-one iteration |
| Multi-channel architecture, single-channel launch | YT Partner Program is per-channel; launching 4 channels = 4 cold starts; learn on one first |
| Public repo | Required for unlimited GH Actions minutes; secrets stay encrypted regardless |

---

**End of design spec. Next step: writing-plans skill to produce an implementation plan.**
