#!/usr/bin/env python3
"""
generate_voiceover.py — Generate TTS voiceover via ElevenLabs API.

ALWAYS shows character count + estimated cost and prompts for confirmation
before making the API call (unless --no-confirm is passed).

Usage:
    python tools/generate_voiceover.py --text "Hello world" --output .tmp/audio/vo.mp3
    python tools/generate_voiceover.py --script script.json --output .tmp/audio/vo.mp3
    python tools/generate_voiceover.py --list-voices
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
# eleven_turbo_v2 is fast + high quality; ~$0.18 per 1000 chars
COST_PER_1000_CHARS = 0.18
MODEL_ID = "eleven_turbo_v2"


def list_voices() -> None:
    """Print all available ElevenLabs voices."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key or api_key == "...":
        print("[generate_voiceover] ELEVENLABS_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    resp = requests.get(
        f"{ELEVENLABS_BASE}/voices",
        headers={"xi-api-key": api_key},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[generate_voiceover] API error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    voices = resp.json().get("voices", [])
    print(f"\n{'Voice ID':<32} {'Name'}")
    print("-" * 60)
    for v in voices:
        print(f"{v['voice_id']:<32} {v['name']}")
    print()


def generate_voiceover(
    text: str,
    output_path: str,
    voice_id: str | None = None,
    confirm: bool = True,
) -> None:
    """Call ElevenLabs TTS API and save MP3 to output_path."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key or api_key == "...":
        print("[generate_voiceover] ELEVENLABS_API_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    if voice_id is None:
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    char_count = len(text)
    estimated_cost = (char_count / 1000) * COST_PER_1000_CHARS

    print(f"\n[generate_voiceover] Voice ID : {voice_id}")
    print(f"[generate_voiceover] Model    : {MODEL_ID}")
    print(f"[generate_voiceover] Chars    : {char_count:,}")
    print(f"[generate_voiceover] Est. cost: ~${estimated_cost:.4f} USD\n")

    if confirm:
        answer = input("Proceed with ElevenLabs TTS? [y/N] ").strip().lower()
        if answer != "y":
            print("[generate_voiceover] Aborted.", file=sys.stderr)
            sys.exit(0)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    print(f"[generate_voiceover] Generating TTS...", file=sys.stderr)
    resp = requests.post(url, json=payload, headers=headers, timeout=60)

    if resp.status_code != 200:
        print(f"[generate_voiceover] API error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    Path(output_path).write_bytes(resp.content)
    print(f"[generate_voiceover] Saved to {output_path} ({len(resp.content) / 1024:.1f} KB)")


def script_to_voiceover_text(script: dict) -> str:
    """Concatenate hook + all scene voiceover_text + CTA from a script JSON."""
    parts = []
    if hook := script.get("hook"):
        parts.append(hook)
    for scene in script.get("scenes", []):
        if vt := scene.get("voiceover_text"):
            parts.append(vt)
    if cta := script.get("cta"):
        parts.append(cta)
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate voiceover via ElevenLabs TTS.")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", "-t", help="Raw text to synthesize")
    mode.add_argument("--script", "-s", help="Script JSON file (hook + scenes + CTA)")
    mode.add_argument("--list-voices", action="store_true", help="List available voices and exit")

    parser.add_argument("--output", "-o", help="Output MP3 path")
    parser.add_argument("--voice-id", help="ElevenLabs voice ID (overrides .env)")
    parser.add_argument("--no-confirm", action="store_true", help="Skip cost confirmation prompt")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return

    if not args.output:
        print("[generate_voiceover] --output is required unless using --list-voices", file=sys.stderr)
        sys.exit(1)

    if args.text:
        text = args.text
    elif args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"[generate_voiceover] Script not found: {args.script}", file=sys.stderr)
            sys.exit(1)
        script = json.loads(script_path.read_text())
        text = script_to_voiceover_text(script)
    else:
        print("[generate_voiceover] Provide --text or --script.", file=sys.stderr)
        sys.exit(1)

    generate_voiceover(
        text,
        args.output,
        voice_id=args.voice_id,
        confirm=not args.no_confirm,
    )


if __name__ == "__main__":
    main()
