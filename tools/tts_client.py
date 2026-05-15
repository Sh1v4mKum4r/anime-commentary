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
