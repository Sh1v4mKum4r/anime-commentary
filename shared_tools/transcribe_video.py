#!/usr/bin/env python3
"""
transcribe_video.py — Extract audio and transcribe using faster-whisper (local, no API key).

faster-whisper uses CTranslate2 backend — much faster and lighter than openai-whisper.
Runs on GPU (CUDA) if available, falls back to CPU.

Model sizes: tiny, base, small, medium, large-v2 (default: base)

Usage:
    python tools/transcribe_video.py --input video.mp4 --output .tmp/transcripts/out.json
    python tools/transcribe_video.py --input video.mp4 --output out.json --model small
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

DEFAULT_MODEL = "base"


def extract_audio(input_path: str, output_wav: str) -> None:
    """Extract mono 16kHz WAV from video."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        output_wav,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[transcribe] ffmpeg error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def transcribe_with_faster_whisper(wav_path: str, model_name: str) -> dict:
    """Run faster-whisper on WAV, return segments + words."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[transcribe] faster-whisper not installed. Run:", file=sys.stderr)
        print("  pip install faster-whisper --break-system-packages", file=sys.stderr)
        sys.exit(1)

    # Try CUDA first, fall back to CPU on any failure
    model = None
    device = "cpu"
    try:
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
        device = "cuda"
    except Exception:
        pass

    if model is None:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        device = "cpu"

    print(f"[transcribe] Loaded faster-whisper '{model_name}' on {device}", file=sys.stderr)
    print(f"[transcribe] Transcribing {wav_path}...", file=sys.stderr)

    try:
        segs, info = model.transcribe(wav_path, word_timestamps=True)
    except RuntimeError as e:
        if "cuda" in str(e).lower() or "cublas" in str(e).lower():
            print(f"[transcribe] CUDA runtime error, retrying on CPU: {e}", file=sys.stderr)
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segs, info = model.transcribe(wav_path, word_timestamps=True)
        else:
            raise

    segments = []
    words = []
    seg_id = 0
    for seg in segs:
        segments.append({
            "id": seg_id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        for w in (seg.words or []):
            words.append({
                "word": w.word.strip(),
                "start": round(w.start, 3),
                "end": round(w.end, 3),
            })
        seg_id += 1

    return {
        "language": info.language,
        "segments": segments,
        "words": words,
    }


def transcribe_video(input_path: str, output_path: str, model_name: str = DEFAULT_MODEL) -> dict:
    """Full pipeline: extract audio → faster-whisper → save JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = str(Path(tmpdir) / "audio.wav")
        print(f"[transcribe] Extracting audio from {input_path}...", file=sys.stderr)
        extract_audio(input_path, wav_path)
        size_mb = Path(wav_path).stat().st_size / 1024 / 1024
        print(f"[transcribe] Audio: {size_mb:.1f} MB", file=sys.stderr)
        transcribed = transcribe_with_faster_whisper(wav_path, model_name)

    from probe_video import probe_video
    try:
        duration = probe_video(input_path)["duration"]
    except Exception:
        duration = 0.0

    output = {
        "source_file": input_path,
        "duration": duration,
        "language": transcribed["language"],
        "segments": transcribed["segments"],
        "words": transcribed["words"],
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, indent=2))
    print(f"[transcribe] Done — {len(output['segments'])} segments, {len(output['words'])} words → {output_path}", file=sys.stderr)
    return output


def main():
    parser = argparse.ArgumentParser(description="Transcribe video via faster-whisper (local).")
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        choices=["tiny", "base", "small", "medium", "large-v2"])
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"[transcribe] Not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    transcribe_video(args.input, args.output, model_name=args.model)


if __name__ == "__main__":
    main()
