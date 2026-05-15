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
  episode_id    BIGINT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
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
  short_id      BIGINT NOT NULL REFERENCES shorts(id) ON DELETE CASCADE,
  polled_at     TIMESTAMPTZ DEFAULT NOW(),
  views         INT,
  likes         INT,
  retention_pct NUMERIC
);

CREATE INDEX IF NOT EXISTS shorts_status_created_idx ON shorts (status, created_at);
CREATE INDEX IF NOT EXISTS shorts_channel_platform_idx ON shorts (channel_slug, platform);
CREATE INDEX IF NOT EXISTS episodes_status_idx ON episodes (status);
