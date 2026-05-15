#!/usr/bin/env python3
"""
burn_captions.py — Generate ASS subtitle file from word timestamps and burn into video.

Groups ~4 words per subtitle event. For generated shorts, runs Whisper on the
voiceover audio first to get word timestamps.

Usage:
    # From existing transcript (clip mode)
    python tools/burn_captions.py --input vertical.mp4 --transcript transcript.json --output captioned.mp4

    # From voiceover audio (generate mode — Whisper will run on the audio)
    python tools/burn_captions.py --input assembled.mp4 --voiceover voiceover.mp3 --output captioned.mp4
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

WORDS_PER_EVENT = 4

ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,80,80,160,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def seconds_to_ass_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def words_to_ass(words: list[dict]) -> str:
    """Group words into events and generate ASS subtitle content."""
    if not words:
        return ASS_HEADER

    events = []
    for i in range(0, len(words), WORDS_PER_EVENT):
        group = words[i:i + WORDS_PER_EVENT]
        text = " ".join(w["word"].strip() for w in group)
        start = group[0]["start"]
        end = group[-1]["end"]
        # Small padding so last word doesn't disappear instantly
        end = max(end, start + 0.5)
        t_start = seconds_to_ass_time(start)
        t_end = seconds_to_ass_time(end)
        # Bold + slightly yellow highlight color for readability
        styled_text = f"{{\\b1}}{text}"
        events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{styled_text}")

    return ASS_HEADER + "\n".join(events) + "\n"


def transcribe_audio_for_words(audio_path: str) -> list[dict]:
    """Run faster-whisper on audio file and return word-level timestamps."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[burn_captions] faster-whisper not installed. Run: pip install faster-whisper --break-system-packages", file=sys.stderr)
        sys.exit(1)

    model = None
    device = "cpu"
    try:
        model = WhisperModel("base", device="cuda", compute_type="float16")
        device = "cuda"
    except Exception:
        pass
    if model is None:
        model = WhisperModel("base", device="cpu", compute_type="int8")

    print(f"[burn_captions] Transcribing voiceover on {device} for word timestamps...", file=sys.stderr)
    try:
        segs, _ = model.transcribe(audio_path, word_timestamps=True)
    except RuntimeError as e:
        if "cuda" in str(e).lower() or "cublas" in str(e).lower():
            print(f"[burn_captions] CUDA error, retrying on CPU: {e}", file=sys.stderr)
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segs, _ = model.transcribe(audio_path, word_timestamps=True)
        else:
            raise

    words = []
    for seg in segs:
        for w in (seg.words or []):
            words.append({
                "word": w.word.strip(),
                "start": round(w.start, 3),
                "end": round(w.end, 3),
            })
    return words


def burn_captions(
    input_video: str,
    output_video: str,
    words: list[dict],
) -> None:
    """Write ASS file and burn subtitles into video via FFmpeg."""
    Path(output_video).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".ass", mode="w", delete=False) as f:
        ass_path = f.name
        f.write(words_to_ass(words))

    print(f"[burn_captions] Burning {len(words)} words → {output_video}", file=sys.stderr)
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", f"subtitles={ass_path}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_video,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[burn_captions] FFmpeg error:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
    finally:
        Path(ass_path).unlink(missing_ok=True)

    print(f"[burn_captions] Done: {output_video}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Burn captions into video from word timestamps.")
    parser.add_argument("--input", "-i", required=True, help="Input video path")
    parser.add_argument("--output", "-o", required=True, help="Output video path")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--transcript", "-t", help="Transcript JSON with word timestamps (clip mode)")
    source.add_argument("--voiceover", "-v", help="Voiceover audio file — Whisper will transcribe it (generate mode)")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"[burn_captions] Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.transcript:
        transcript = json.loads(Path(args.transcript).read_text())
        words = transcript.get("words", [])
        if not words:
            print("[burn_captions] No word timestamps in transcript.", file=sys.stderr)
            sys.exit(1)
    else:
        if not Path(args.voiceover).exists():
            print(f"[burn_captions] Voiceover not found: {args.voiceover}", file=sys.stderr)
            sys.exit(1)
        words = transcribe_audio_for_words(args.voiceover)

    burn_captions(args.input, args.output, words)


if __name__ == "__main__":
    main()
