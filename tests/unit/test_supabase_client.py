import pytest
from unittest.mock import MagicMock, patch
from tools import supabase_client as sb


def test_get_client_raises_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(KeyError):
        sb.get_client()


def test_get_client_uses_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")
    with patch("tools.supabase_client.create_client") as create:
        create.return_value = MagicMock()
        client = sb.get_client()
        create.assert_called_once_with("https://example.supabase.co", "fake-key")
        assert client is create.return_value


def test_insert_episode_returns_first_row():
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": 1, "title": "Frieren", "episode_num": 12, "status": "detected"}
    ]
    out = sb.insert_episode(client, {"anilist_id": 999, "title": "Frieren",
                                      "episode_num": 12, "status": "detected"})
    assert out["id"] == 1
    client.table.assert_called_once_with("episodes")


def test_get_episodes_by_status():
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": 1, "status": "detected"},
        {"id": 2, "status": "detected"},
    ]
    rows = sb.get_episodes_by_status(client, "detected")
    assert len(rows) == 2
    client.table.assert_called_once_with("episodes")


def test_update_episode_status_sets_field():
    client = MagicMock()
    sb.update_episode_status(client, 1, "downloaded", file_url="episodes/1.mp4")
    client.table.return_value.update.assert_called_once()
    update_kwargs = client.table.return_value.update.call_args[0][0]
    assert update_kwargs["status"] == "downloaded"
    assert update_kwargs["file_url"] == "episodes/1.mp4"


def test_signed_url_returns_url():
    client = MagicMock()
    client.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://signed.example/abc"
    }
    url = sb.signed_url(client, "episodes", "1.mp4", 3600)
    assert url == "https://signed.example/abc"
