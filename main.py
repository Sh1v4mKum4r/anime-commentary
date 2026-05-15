"""anime-commentary CLI entrypoint.

Subcommands are stubs in this foundation plan. Subsequent plans wire them up.
"""
from __future__ import annotations
import os
from pathlib import Path
import click

from tools.channel_config import discover_channels, ChannelConfigError


DEFAULT_CHANNELS_DIR = Path(__file__).resolve().parent / "channels"


@click.group()
def cli() -> None:
    """Anime Commentary pipeline."""


@cli.command()
def init() -> None:
    """Create local data directories used by the pipeline."""
    for d in ("data/episodes", "data/audio", "data/output", "data/transcripts", ".tmp"):
        Path(d).mkdir(parents=True, exist_ok=True)
        click.echo(f"created {d}")


@cli.command()
def poll() -> None:
    """Run the hourly pipeline traversal. (not yet implemented — see Plan 2)"""
    click.echo("poll: not yet implemented")


@cli.command()
def review() -> None:
    """Walk pending shorts in the review queue. (not yet implemented — see Plan 5)"""
    click.echo("review: not yet implemented")


@cli.command()
def publish() -> None:
    """Publish approved shorts. (not yet implemented — see Plan 4)"""
    click.echo("publish: not yet implemented")


@cli.command()
def channels() -> None:
    """List loaded channel configs."""
    channels_dir = Path(os.environ.get("CHANNELS_DIR", str(DEFAULT_CHANNELS_DIR)))
    try:
        configs = discover_channels(channels_dir)
    except ChannelConfigError as e:
        raise click.ClickException(str(e))
    if not configs:
        click.echo(f"no channel configs found in {channels_dir}")
        return
    for c in configs:
        platforms = []
        if c.platforms.youtube.enabled:
            platforms.append("youtube")
        if c.platforms.tiktok.enabled:
            platforms.append("tiktok")
        click.echo(f"{c.slug}  ({c.display_name})  platforms={','.join(platforms) or '-'}")


if __name__ == "__main__":
    cli()
