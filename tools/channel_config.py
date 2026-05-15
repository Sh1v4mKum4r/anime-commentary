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
    except (FileNotFoundError, yaml.YAMLError) as e:
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
