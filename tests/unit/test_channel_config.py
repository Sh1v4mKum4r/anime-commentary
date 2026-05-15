import logging
import pytest
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
