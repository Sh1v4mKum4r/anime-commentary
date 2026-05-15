import os
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixture_dir():
    return FIXTURES

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Strip env vars that would leak into tests."""
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
