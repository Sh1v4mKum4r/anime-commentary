from click.testing import CliRunner
from main import cli


def test_cli_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("init", "poll", "review", "publish"):
        assert sub in result.output


def test_init_creates_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    for d in ("data/episodes", "data/audio", "data/output", "data/transcripts", ".tmp"):
        assert (tmp_path / d).is_dir()


def test_init_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0


def test_poll_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["poll"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output.lower()


def test_review_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["review"])
    assert result.exit_code == 0


def test_publish_stub_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["publish"])
    assert result.exit_code == 0


def test_channels_lists_loaded_channels(tmp_path, monkeypatch):
    # Point CHANNELS_DIR at a tmp dir containing reactions.yaml
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    monkeypatch.setenv("CHANNELS_DIR", str(repo_root / "channels"))
    runner = CliRunner()
    result = runner.invoke(cli, ["channels"])
    assert result.exit_code == 0
    assert "reactions" in result.output
