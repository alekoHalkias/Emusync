"""`sync` command group — lock and save status."""
from __future__ import annotations

import click

from cli.common import _client
from cli.root import cli


@cli.group()
def sync() -> None:
    """Sync status and utilities."""


@sync.command("status")
def sync_status() -> None:
    """Show lock and save status for all games."""
    client = _client()
    games = client.list_games()
    if not games:
        click.echo("No games managed.")
        return

    click.echo(f"{'Game':<30}  {'Lock':<22}  Last Push")
    click.echo("-" * 80)
    for g in games:
        slug = g["slug"]
        try:
            lock_info = client.get_lock(slug)
            lock_str = lock_info["device_id"][:20] if lock_info.get("locked") else "free"
        except Exception:
            lock_str = "?"
        try:
            meta = client.get_save_meta(slug)
            push_str = meta["pushed_at"][:19] if meta else "never"
        except Exception:
            push_str = "?"
        click.echo(f"{slug:<30}  {lock_str:<22}  {push_str}")
