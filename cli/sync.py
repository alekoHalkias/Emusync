"""`sync` command group — lock and save status, plus save/state history & rollback."""
from __future__ import annotations

import click

from cli.common import _client, _fmt_time
from cli.root import cli


def _fmt_size(n) -> str:
    """Human-readable byte size for history listings."""
    try:
        size = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"


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
            push_str = _fmt_time(meta["pushed_at"]) if meta else "never"
        except Exception:
            push_str = "?"
        click.echo(f"{slug:<30}  {lock_str:<22}  {push_str}")


@sync.command("history")
@click.argument("slug")
@click.option("--state", "is_state", is_flag=True, help="Show state history instead of save history.")
def sync_history(slug: str, is_state: bool) -> None:
    """List retained save (or --state) versions for a game, newest first."""
    client = _client()
    kind = "state" if is_state else "save"
    try:
        history = client.list_state_history(slug) if is_state else client.list_save_history(slug)
    except Exception as e:
        click.echo(f"Failed to fetch {kind} history: {e}", err=True)
        raise SystemExit(1)
    if not history:
        click.echo(f"No {kind} history for '{slug}'.")
        return
    click.echo(f"{kind.capitalize()} history for '{slug}' (newest first):\n")
    click.echo(f"  {'#':<3} {'When':<38} {'Size':<10} {'From device':<24} Version ID")
    click.echo("  " + "-" * 100)
    for i, v in enumerate(history, 1):
        current = " (current)" if i == 1 else ""
        click.echo(
            f"  {i:<3} {_fmt_time(v.get('pushed_at')):<38} {_fmt_size(v.get('size')):<10} "
            f"{(v.get('device_id') or '')[:22]:<24} {v.get('id', '')}{current}"
        )
    click.echo(f"\nRestore one with:  emusync sync restore {slug} <version-id>" + (" --state" if is_state else ""))


@sync.command("restore")
@click.argument("slug")
@click.argument("version_id")
@click.option("--state", "is_state", is_flag=True, help="Restore a state version instead of a save.")
def sync_restore(slug: str, version_id: str, is_state: bool) -> None:
    """Roll a game's save (or --state) back to a previous version.

    The chosen version becomes current on the server; if this device has the game
    configured locally it is also written to disk (the replaced file is kept as .bak).
    """
    client = _client()
    kind = "state" if is_state else "save"
    try:
        if is_state:
            client.restore_state(slug, version_id)
        else:
            client.restore_save(slug, version_id)
    except Exception as e:
        click.echo(f"Failed to restore {kind}: {e}", err=True)
        raise SystemExit(1)
    click.echo(f"Restored {kind} version on the server.")

    # If this device has the game configured, pull the restored version to disk too.
    try:
        gd = client.get_game_device(slug)
    except Exception:
        gd = None
    target = (gd.state_path if is_state else gd.save_path) if gd else ""
    if not target:
        click.echo("This device has no local path for the game — restored on the server only. "
                   "It will land here on the next launch/sync.")
        return
    try:
        if is_state:
            pulled, _ = client.pull_state(slug, target)
        else:
            pulled, _ = client.pull_save(slug, target)
        if pulled:
            click.echo(f"Wrote restored {kind} to {target} (previous file kept as .bak).")
    except Exception as e:
        click.echo(f"Restored on server, but failed to write locally: {e}", err=True)
