import pytest
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


@pytest.mark.slow
def test_real_synthesis_produces_valid_mp3(tmp_path):
    """Hits real edge-tts; needs network. Skipped in fast CI."""
    out = tmp_path / "real.mp3"
    tts_client.synthesize("Hello world.", str(out))
    assert out.exists()
    assert out.stat().st_size > 1000
    head = out.read_bytes()[:4]
    # Accept ID3v2 tag or any MPEG audio frame sync (11-bit pattern 0xFFE).
    is_mpeg_frame = head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    assert head.startswith(b"ID3") or is_mpeg_frame
