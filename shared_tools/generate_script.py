#!/usr/bin/env python3
"""
generate_script.py — Generate a structured short-form video script via Gemini CLI.

Usage:
    python tools/generate_script.py --prompt "5 tips for better sleep" --duration 45
    python tools/generate_script.py --prompt "5 tips for better sleep" --dry-run
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """\
You are an expert short-form video scriptwriter for YouTube Shorts, TikTok, and Instagram Reels.

Structure every script as:
1. HOOK (0-3s): One sentence that immediately grabs attention
2. SCENES (3-5 scenes): Each has voiceover + visual instructions
3. CTA (last 3s): Simple call-to-action

Rules:
- Total voiceover fits within the requested duration (~2.5 words per second)
- Each scene voiceover_text is 1-2 sentences
- visual_description: describe stock footage (no text on screen, no faces required)
- search_keywords: 2-3 short keywords for stock footage search
- duration_seconds: estimated voiceover duration for the scene

Return ONLY a valid JSON object, no markdown fences:
{
  "title": "Video title",
  "total_duration": 45,
  "hook": "Opening hook sentence",
  "scenes": [
    {
      "scene_id": 1,
      "voiceover_text": "...",
      "visual_description": "...",
      "search_keywords": ["keyword1", "keyword2"],
      "duration_seconds": 8
    }
  ],
  "cta": "Call to action text"
}"""


def call_gemini(prompt: str) -> str:
    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"[generate_script] Gemini CLI error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def extract_json(text: str) -> dict:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        print(f"[generate_script] No JSON in response:\n{text}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"[generate_script] JSON parse error: {e}\nRaw:\n{text}", file=sys.stderr)
        sys.exit(1)


def generate_script(prompt: str, duration: int = 45, dry_run: bool = False) -> dict:
    if dry_run:
        print("[generate_script] DRY RUN — returning mock script.", file=sys.stderr)
        return {
            "title": f"Mock: {prompt}",
            "total_duration": duration,
            "hook": f"Did you know about {prompt}? Here's what nobody tells you.",
            "scenes": [
                {
                    "scene_id": 1,
                    "voiceover_text": "This is scene one of the mock script.",
                    "visual_description": "Person looking at camera with neutral background",
                    "search_keywords": ["person talking", "lifestyle"],
                    "duration_seconds": 10,
                },
                {
                    "scene_id": 2,
                    "voiceover_text": "This is scene two. Keep it engaging.",
                    "visual_description": "Close-up of hands doing something relevant",
                    "search_keywords": ["hands", "activity"],
                    "duration_seconds": 10,
                },
                {
                    "scene_id": 3,
                    "voiceover_text": "This is the final scene before the CTA.",
                    "visual_description": "Wide shot outdoor natural lighting",
                    "search_keywords": ["outdoor", "nature"],
                    "duration_seconds": 10,
                },
            ],
            "cta": "Follow for more tips like this!",
        }

    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Write a short-form video script about: {prompt}\n"
        f"Target total duration: {duration} seconds."
    )

    print(f"[generate_script] Generating script via Gemini for '{prompt}' ({duration}s)...", file=sys.stderr)
    raw = call_gemini(full_prompt)
    result = extract_json(raw)
    print(f"[generate_script] Script generated: {len(result.get('scenes', []))} scenes.", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate short-form video script via Gemini.")
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--duration", "-d", type=int, default=45)
    parser.add_argument("--output", "-o")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = generate_script(args.prompt, duration=args.duration, dry_run=args.dry_run)
    output_json = json.dumps(result, indent=2)
    print(output_json)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json)
        print(f"[generate_script] Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
