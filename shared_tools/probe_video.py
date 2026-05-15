#!/usr/bin/env python3
"""
probe_video.py — ffprobe wrapper that returns video metadata as JSON.

Usage:
    python tools/probe_video.py --input video.mp4
    python tools/probe_video.py --input video.mp4 --output .tmp/meta.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def probe_video(input_path: str) -> dict:
    """Run ffprobe on input_path and return a structured metadata dict."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[probe_video] ffprobe error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(result.stdout)
    streams = raw.get("streams", [])
    fmt = raw.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    # Parse fps from "30000/1001" or "30/1" style strings
    fps = None
    if video_stream:
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = r_frame_rate.split("/")
            fps = round(int(num) / int(den), 3)
        except (ValueError, ZeroDivisionError):
            fps = None

    metadata = {
        "source_file": input_path,
        "duration": float(fmt.get("duration", 0)),
        "size_bytes": int(fmt.get("size", 0)),
        "format_name": fmt.get("format_name", ""),
        "has_video": video_stream is not None,
        "has_audio": audio_stream is not None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "fps": fps,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "is_portrait": (
            (video_stream.get("height", 0) > video_stream.get("width", 0))
            if video_stream else False
        ),
    }
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Probe video metadata via ffprobe.")
    parser.add_argument("--input", "-i", required=True, help="Path to input video file")
    parser.add_argument("--output", "-o", help="Optional path to write JSON output")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"[probe_video] File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    metadata = probe_video(args.input)

    output_json = json.dumps(metadata, indent=2)
    print(output_json)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json)
        print(f"[probe_video] Metadata written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
