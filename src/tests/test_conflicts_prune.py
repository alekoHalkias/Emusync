import tempfile
from datetime import datetime, timedelta, timezone

from server.store import Store


def _ts(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_old_dismissed_conflicts_pruned_from_both_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("d1", "PC")
        store.add_game("g", "Game")
        db = store._conn

        def seed(table, key_col, key, cid, status, days):
            db.execute(
                f"INSERT INTO {table} (id, {key_col}, winner_device_id, loser_device_id, "
                "winner_hash, loser_hash, resolved_at, status) VALUES (?, ?, 'd1', 'd1', 'w', 'l', ?, ?)",
                (cid, key, _ts(days), status),
            )

        for table, col, key in (("save_conflicts", "game_slug", "g"), ("console_save_conflicts", "console_key", "PS2")):
            seed(table, col, key, f"{table}-old-dismissed", "dismissed", 200)
            seed(table, col, key, f"{table}-new-dismissed", "dismissed", 5)
            seed(table, col, key, f"{table}-old-open", "open", 200)
        db.commit()

        # dismissing triggers the prune: once via the per-game table, once via the console one
        assert store.dismiss_conflict("save_conflicts-old-open")
        left = {r["id"] for r in db.execute("SELECT id FROM save_conflicts UNION ALL SELECT id FROM console_save_conflicts")}
        assert left == {
            "save_conflicts-new-dismissed",
            "console_save_conflicts-new-dismissed",
            "console_save_conflicts-old-open",
        }
        assert store.dismiss_conflict("console_save_conflicts-old-open")
        assert not db.execute("SELECT 1 FROM console_save_conflicts WHERE id = 'console_save_conflicts-old-open'").fetchone()
