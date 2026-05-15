import json
import subprocess
import pytest
from unittest.mock import patch
from tools import llm_client
from tools.llm_client import ClaudeError


def _ok_completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_chat_returns_result_field():
    payload = json.dumps({"result": "hello world", "duration_ms": 123})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        out = llm_client.chat("test prompt")
        assert out == "hello world"
        args, kwargs = run.call_args
        cmd = args[0]
        assert cmd[0] == "claude"
        assert "-p" in cmd and "test prompt" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--model" in cmd and "sonnet" in cmd


def test_chat_passes_system_prompt():
    payload = json.dumps({"result": "yes"})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        llm_client.chat("p", system="you are X")
        cmd = run.call_args[0][0]
        assert "--system-prompt" in cmd
        assert "you are X" in cmd


def test_chat_overrides_model():
    payload = json.dumps({"result": "ok"})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)) as run:
        llm_client.chat("p", model="opus")
        cmd = run.call_args[0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"


def test_chat_wraps_nonzero_exit_in_claude_error():
    err = subprocess.CalledProcessError(returncode=2, cmd=["claude"], stderr="boom")
    with patch("tools.llm_client.subprocess.run", side_effect=err):
        with pytest.raises(ClaudeError, match="exited 2"):
            llm_client.chat("p")


def test_chat_wraps_timeout_in_claude_error():
    err = subprocess.TimeoutExpired(cmd="claude", timeout=1)
    with patch("tools.llm_client.subprocess.run", side_effect=err):
        with pytest.raises(ClaudeError, match="timed out"):
            llm_client.chat("p", timeout=1)


def test_chat_wraps_bad_json_in_claude_error():
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed("not-json")):
        with pytest.raises(ClaudeError, match="could not parse"):
            llm_client.chat("p")


def test_chat_raises_when_result_field_missing():
    payload = json.dumps({"duration_ms": 42, "error": "oops"})
    with patch("tools.llm_client.subprocess.run", return_value=_ok_completed(payload)):
        with pytest.raises(ClaudeError, match="missing 'result'"):
            llm_client.chat("p")
