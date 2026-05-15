from pathlib import Path

VENDORED = [
    "generate_script.py",
    "generate_voiceover.py",
    "burn_captions.py",
    "assemble_generated_short.py",
    "transcribe_video.py",
]

def test_all_vendored_tools_present():
    root = Path(__file__).resolve().parents[2] / "shared_tools"
    for name in VENDORED:
        f = root / name
        assert f.exists(), f"missing vendored tool: {name}"
        assert f.stat().st_size > 0, f"vendored tool is empty: {name}"
