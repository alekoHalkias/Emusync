"""`mod` command group — manual list/sync for the communal Switch mod pool (#444)."""
from __future__ import annotations

import click

from cli.common import _client, _fmt_time
from cli.root import cli
from cli.run_switch import _local_switch_mods, _sync_switch_mods
from cli.sync import _fmt_size


def _title_id_for(client, slug: str) -> str:
    game = client.get_game(slug)
    if not game:
        click.echo(f"'{slug}' is not a managed game.", err=True)
        raise SystemExit(1)
    if (game.get("console") or "") != "Switch":
        click.echo(f"'{slug}' isn't a Switch game — mods only apply to Switch.", err=True)
        raise SystemExit(1)
    title_id = game.get("switch_title_id") or ""
    if not title_id:
        click.echo(
            f"'{slug}' has no known Switch title ID yet — launch it once via 'emusync run' "
            f"so its save/mod folder can be discovered first.",
            err=True,
        )
        raise SystemExit(1)
    return title_id


@cli.group()
def mod() -> None:
    """Manage the communal Switch mod pool (Eden's load/<title-id>/ folder)."""


@mod.command("list")
@click.argument("slug")
def mod_list(slug: str) -> None:
    """List local + pooled mods for a Switch game, newest pool entry first."""
    client = _client()
    title_id = _title_id_for(client, slug)
    local = _local_switch_mods(title_id)
    try:
        pool = client.list_switch_mods(title_id)
    except Exception as e:
        click.echo(f"Failed to fetch the mod pool: {e}", err=True)
        raise SystemExit(1)
    pool_names = {m["mod_name"] for m in pool}

    if not local and not pool:
        click.echo(f"No mods found locally or in the pool for '{slug}'.")
        return

    click.echo(f"Mods for '{slug}':\n")
    click.echo(f"  {'Name':<40} {'Local':<7} {'Pool':<7} {'Size':<10} Pushed by / at")
    click.echo("  " + "-" * 100)
    for name in sorted(set(local) | pool_names):
        pool_entry = next((m for m in pool if m["mod_name"] == name), None)
        size = _fmt_size(pool_entry["size"]) if pool_entry else "?"
        by_at = f"{(pool_entry.get('pushed_by') or '')[:12]} / {_fmt_time(pool_entry.get('pushed_at'))}" if pool_entry else ""
        click.echo(f"  {name:<40} {'yes' if name in local else '':<7} {'yes' if name in pool_names else '':<7} {size:<10} {by_at}")


@mod.command("sync")
@click.argument("slug")
def mod_sync(slug: str) -> None:
    """Push local-only mods to the pool and pull pool-only mods locally.

    Name-only comparison — a mod that already exists by name on both sides is
    never re-transferred (mod folders can be gigabytes).
    """
    client = _client()
    title_id = _title_id_for(client, slug)
    pushed, pulled = _sync_switch_mods(client, title_id)
    if not pushed and not pulled:
        click.echo("Already in sync — nothing to push or pull.")
        return
    if pushed:
        click.echo(f"Pushed: {', '.join(pushed)}")
    if pulled:
        click.echo(f"Pulled: {', '.join(pulled)}")
