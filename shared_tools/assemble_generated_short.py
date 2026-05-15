#!/usr/bin/env python3
"""
assemble_generated_short.py — Assemble stock clips + voiceover into a final short video.

Pipeline:
  1. Normalize each clip: scale to 1080x1920, silent audio if missing, fps=30, libx264
  2. Write ffmpeg concat list
  3. Concat + mix with voiceover audio

Usage:
    python tools/assemble_generated_short.py \
        --clips .tmp/stock/scene_01.mp4 .tmp/stock/scene_02.mp4 \
        --voiceover .tmp/audio/vo.mp3 \
        --script script.json \
        --output .tmp/output/final.mp4
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_video import probe_video


def has_audio_stream(video_path: str) -> bool:
    """Return True if the video file has an audio stream."""
    try:
        meta = probe_video(video_path)
        return meta.get("has_audio", False)
    except Exception:
        return False


def normalize_clip(
    input_path: str,
    output_path: str,
    target_duration: float | None = None,
) -> None:
    """
    Normalize a clip to 1080x1920, 30fps, libx264, with audio (silent if none).
    Optionally trim to target_duration seconds.
    """
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"

    duration_args = []
    if target_duration:
        duration_args = ["-t", str(target_duration)]

    if has_audio_stream(input_path):
        audio_filter = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    else:
        # Add silent audio track
        audio_filter = [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-shortest",
        ]

    # Build command differently if we need to add silent audio (extra -i)
    if has_audio_stream(input_path):
        cmd = (
            ["ffmpeg", "-y", "-i", input_path]
            + duration_args
            + [
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-profile:v", "high",
                "-level", "4.2",
            ]
            + audio_filter
            + ["-movflags", "+faststart", output_path]
        )
    else:
        cmd = (
            ["ffmpeg", "-y", "-i", input_path]
            + ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            + duration_args
            + [
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-profile:v", "high",
                "-level", "4.2",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]
        )

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[assemble] Normalize error for {input_path}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def concat_clips(clip_paths: list[str], output_path: str) -> None:
    """Concatenate normalized clips using ffmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(
        suffix=".txt", mode="w", delete=False, dir=Path(output_path).parent
    ) as f:
        list_path = f.name
        for p in clip_paths:
            # Escape single quotes in paths
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(list_path).unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"[assemble] Concat error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def mix_voiceover(
    video_path: str,
    voiceover_path: str,
    output_path: str,
    bg_volume: float = 0.15,
) -> None:
    """
    Mix video's ambient audio with voiceover. Voiceover drives duration.
    bg_volume: multiplier for background audio (0.15 = 15% of original)
    """
    filter_complex = (
        f"[0:a]volume={bg_volume}[bg];"
        f"[bg][1:a]amix=inputs=2:duration=first:dropout_transition=2"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", voiceover_path,
        "-filter_complex", filter_complex,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[assemble] Audio mix error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def assemble(
    clip_paths: list[str],
    voiceover_path: str,
    output_path: str,
    script: dict | None = None,
) -> None:
    """Full assembly pipeline."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Extract per-scene durations from script if available
    scene_durations = []
    if script:
        for scene in script.get("scenes", []):
            scene_durations.append(scene.get("duration_seconds"))

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Normalize each clip
        normalized = []
        for i, clip_path in enumerate(clip_paths):
            norm_path = str(Path(tmpdir) / f"norm_{i:02d}.mp4")
            target_dur = scene_durations[i] if i < len(scene_durations) else None
            print(
                f"[assemble] Normalizing clip {i + 1}/{len(clip_paths)}: {clip_path}",
                file=sys.stderr,
            )
            normalize_clip(clip_path, norm_path, target_duration=target_dur)
            normalized.append(norm_path)

        # Step 2: Concatenate
        concat_path = str(Path(tmpdir) / "concat.mp4")
        print(f"[assemble] Concatenating {len(normalized)} clips...", file=sys.stderr)
        concat_clips(normalized, concat_path)

        # Step 3: Mix voiceover
        print(f"[assemble] Mixing voiceover: {voiceover_path}", file=sys.stderr)
        mix_voiceover(concat_path, voiceover_path, output_path)

    print(f"[assemble] Done: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Assemble stock clips + voiceover into a short.")
    parser.add_argument("--clips", "-c", nargs="+", required=True, help="Stock clip paths (in order)")
    parser.add_argument("--voiceover", "-v", required=True, help="Voiceover MP3 path")
    parser.add_argument("--output", "-o", required=True, help="Final output video path")
    parser.add_argument("--script", "-s", help="Optional script JSON (for per-scene duration trimming)")
    args = parser.parse_args()

    missing = [p for p in args.clips if not Path(p).exists()]
    if missing:
        print(f"[assemble] Missing clip(s): {missing}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.voiceover).exists():
        print(f"[assemble] Voiceover not found: {args.voiceover}", file=sys.stderr)
        sys.exit(1)

    script = None
    if args.script:
        script = json.loads(Path(args.script).read_text())

    assemble(args.clips, args.voiceover, args.output, script=script)


if __name__ == "__main__":
    main()
