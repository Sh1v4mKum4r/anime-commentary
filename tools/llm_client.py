"""Claude Code headless-mode LLM client.

Authenticates via CLAUDE_CODE_OAUTH_TOKEN env var. Calls `claude -p ... --output-format json`
and returns the `result` string from the JSON payload.
"""
from __future__ import annotations
import json
import subprocess
from typing import Optional


class ClaudeError(RuntimeError):
    """Raised when the claude CLI fails or returns malformed output."""


def chat(prompt: str, system: Optional[str] = None, model: str = "sonnet",
         timeout: int = 120) -> str:
    """Send a single-turn prompt to Claude Code in headless mode.

    Args:
        prompt: User prompt text.
        system: Optional system prompt.
        model: Claude model alias (`sonnet`, `opus`, `haiku`, or full id).
        timeout: Subprocess timeout in seconds.

    Returns:
        The `result` field from Claude's JSON output.

    Raises:
        ClaudeError: on non-zero exit, timeout, or malformed JSON.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--system-prompt", system]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                check=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        raise ClaudeError(f"claude exited {e.returncode}: {e.stderr}") from e
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude timed out after {timeout}s") from e

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"could not parse claude output: {result.stdout[:200]}") from e

    if "result" not in payload:
        raise ClaudeError(f"claude payload missing 'result' field: {payload!r}")
    return payload["result"]
