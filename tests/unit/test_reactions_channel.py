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
