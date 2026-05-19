"""Tests for emusync.store — Store class covering all public methods."""
import time
import pytest

from emusync.store import GameDevice, Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "data"))


# ── Devices ────────────────────────────────────────────────────────────────


class TestDevices:
    def test_register_and_retrieve_by_token(self, store):
        device = store.register_device("dev-1", "Desktop", "token-abc")
        assert device.id == "dev-1"
        assert device.name == "Desktop"
        assert device.token == "token-abc"

        fetched = store.device_by_token("token-abc")
        assert fetched is not None
        assert fetched.id == "dev-1"

    def test_device_by_token_missing_returns_none(self, store):
        assert store.device_by_token("nonexistent-token") is None

    def test_list_devices_empty(self, store):
        assert store.list_devices() == []

    def test_list_devices_returns_all(self, store):
        store.register_device("dev-1", "Desktop", "t1")
        store.register_device("dev-2", "SteamDeck", "t2")
        devices = store.list_devices()
        assert len(devices) == 2
        ids = {d.id for d in devices}
        assert ids == {"dev-1", "dev-2"}

    def test_register_device_replace_on_conflict(self, store):
        store.register_device("dev-1", "Old Name", "t1")
        store.register_device("dev-1", "New Name", "t2")
        device = store.device_by_token("t2")
        assert device is not None
        assert device.name == "New Name"

    def test_device_created_at_is_populated(self, store):
        device = store.register_device("dev-1", "Desktop", "t1")
        assert device.created_at > 0


# ── Games ──────────────────────────────────────────────────────────────────


class TestGames:
    def test_add_and_get_game(self, store):
        game = store.add_game("zelda", "The Legend of Zelda")
        assert game.slug == "zelda"
        assert game.name == "The Legend of Zelda"

        fetched = store.get_game("zelda")
        assert fetched is not None
        assert fetched.slug == "zelda"

    def test_get_game_missing_returns_none(self, store):
        assert store.get_game("nonexistent") is None

    def test_add_game_ignore_duplicate(self, store):
        store.add_game("zelda", "Zelda")
        store.add_game("zelda", "Different Name")
        game = store.get_game("zelda")
        assert game.name == "Zelda"

    def test_list_games_empty(self, store):
        assert store.list_games() == []

    def test_list_games_returns_all(self, store):
        store.add_game("zelda", "Zelda")
        store.add_game("mario", "Mario")
        games = store.list_games()
        assert len(games) == 2
        slugs = {g.slug for g in games}
        assert slugs == {"zelda", "mario"}

    def test_update_game_name(self, store):
        store.add_game("zelda", "Zelda")
        store.update_game_name("zelda", "Zelda: BOTW")
        game = store.get_game("zelda")
        assert game.name == "Zelda: BOTW"

    def test_remove_game(self, store):
        store.add_game("zelda", "Zelda")
        store.remove_game("zelda")
        assert store.get_game("zelda") is None

    def test_remove_game_cascades_to_saves(self, store):
        store.register_device("dev-1", "Desktop", "t1")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"save-data")
        store.remove_game("zelda")
        data, meta = store.pull_save("zelda")
        assert data is None
        assert meta is None

    def test_remove_game_cascades_to_locks(self, store):
        store.register_device("dev-1", "Desktop", "t1")
        store.add_game("zelda", "Zelda")
        store.acquire_lock("zelda", "dev-1")
        store.remove_game("zelda")
        assert store.get_lock("zelda") is None

    def test_remove_game_cascades_to_game_devices(self, store):
        store.register_device("dev-1", "Desktop", "t1")
        store.add_game("zelda", "Zelda")
        gd = GameDevice(game_slug="zelda", device_id="dev-1", rom_path="/rom", save_path="/save")
        store.set_game_device(gd)
        store.remove_game("zelda")
        assert store.get_game_device("zelda", "dev-1") is None


# ── Game-device config ─────────────────────────────────────────────────────


class TestGameDevice:
    def test_set_and_get_game_device(self, store):
        gd = GameDevice(
            game_slug="zelda", device_id="dev-1",
            rom_path="/roms/zelda.rom", save_path="/saves/zelda.sav",
            launch_command="retroarch -L ...",
        )
        store.set_game_device(gd)
        fetched = store.get_game_device("zelda", "dev-1")
        assert fetched is not None
        assert fetched.rom_path == "/roms/zelda.rom"
        assert fetched.save_path == "/saves/zelda.sav"
        assert fetched.launch_command == "retroarch -L ..."

    def test_get_game_device_missing_returns_none(self, store):
        assert store.get_game_device("zelda", "dev-1") is None

    def test_set_game_device_updates_on_conflict(self, store):
        gd1 = GameDevice(game_slug="zelda", device_id="dev-1", rom_path="/old", save_path="/old")
        store.set_game_device(gd1)
        gd2 = GameDevice(game_slug="zelda", device_id="dev-1", rom_path="/new", save_path="/new")
        store.set_game_device(gd2)
        fetched = store.get_game_device("zelda", "dev-1")
        assert fetched.rom_path == "/new"

    def test_game_devices_are_isolated_by_device(self, store):
        gd1 = GameDevice(game_slug="zelda", device_id="dev-1", rom_path="/dev1-rom", save_path="")
        gd2 = GameDevice(game_slug="zelda", device_id="dev-2", rom_path="/dev2-rom", save_path="")
        store.set_game_device(gd1)
        store.set_game_device(gd2)
        assert store.get_game_device("zelda", "dev-1").rom_path == "/dev1-rom"
        assert store.get_game_device("zelda", "dev-2").rom_path == "/dev2-rom"


# ── Saves ──────────────────────────────────────────────────────────────────


class TestSaves:
    def test_push_and_pull_save(self, store):
        data = b"save-file-bytes"
        meta = store.push_save("zelda", "dev-1", data)
        assert meta.game_slug == "zelda"
        assert meta.device_id == "dev-1"
        assert meta.size == len(data)
        assert len(meta.sha256) == 64

        pulled_data, pulled_meta = store.pull_save("zelda")
        assert pulled_data == data
        assert pulled_meta.sha256 == meta.sha256

    def test_pull_save_missing_returns_none(self, store):
        data, meta = store.pull_save("nonexistent")
        assert data is None
        assert meta is None

    def test_get_save_meta_missing_returns_none(self, store):
        assert store.get_save_meta("nonexistent") is None

    def test_push_save_sha256_is_correct(self, store):
        import hashlib
        data = b"hello world"
        meta = store.push_save("zelda", "dev-1", data)
        expected = hashlib.sha256(data).hexdigest()
        assert meta.sha256 == expected

    def test_pull_save_returns_latest(self, store):
        store.push_save("zelda", "dev-1", b"version-1")
        store.push_save("zelda", "dev-1", b"version-2")
        data, meta = store.pull_save("zelda")
        assert data == b"version-2"

    def test_get_save_meta_returns_latest(self, store):
        import hashlib
        store.push_save("zelda", "dev-1", b"v1")
        store.push_save("zelda", "dev-1", b"v2")
        meta = store.get_save_meta("zelda")
        assert meta.sha256 == hashlib.sha256(b"v2").hexdigest()

    def test_saves_are_isolated_by_game(self, store):
        store.push_save("zelda", "dev-1", b"zelda-save")
        store.push_save("mario", "dev-1", b"mario-save")
        zelda_data, _ = store.pull_save("zelda")
        mario_data, _ = store.pull_save("mario")
        assert zelda_data == b"zelda-save"
        assert mario_data == b"mario-save"


# ── Locks ──────────────────────────────────────────────────────────────────


class TestLocks:
    def test_acquire_and_get_lock(self, store):
        store.acquire_lock("zelda", "dev-1")
        lock = store.get_lock("zelda")
        assert lock is not None
        assert lock.device_id == "dev-1"
        assert lock.game_slug == "zelda"

    def test_get_lock_missing_returns_none(self, store):
        assert store.get_lock("zelda") is None

    def test_same_device_can_reacquire_lock(self, store):
        store.acquire_lock("zelda", "dev-1")
        store.acquire_lock("zelda", "dev-1")  # should not raise
        lock = store.get_lock("zelda")
        assert lock.device_id == "dev-1"

    def test_different_device_cannot_acquire_held_lock(self, store):
        store.acquire_lock("zelda", "dev-1")
        with pytest.raises(ValueError, match="Locked by device"):
            store.acquire_lock("zelda", "dev-2")

    def test_release_lock(self, store):
        store.acquire_lock("zelda", "dev-1")
        store.release_lock("zelda", "dev-1")
        assert store.get_lock("zelda") is None

    def test_release_nonexistent_lock_is_noop(self, store):
        store.release_lock("zelda", "dev-1")  # should not raise

    def test_locks_are_isolated_by_game(self, store):
        store.acquire_lock("zelda", "dev-1")
        store.acquire_lock("mario", "dev-2")
        assert store.get_lock("zelda").device_id == "dev-1"
        assert store.get_lock("mario").device_id == "dev-2"

    def test_stale_lock_is_removed_on_reacquire(self, store):
        from emusync.store import LOCK_EXPIRE_SECONDS
        # Insert a stale lock directly
        stale_time = int(time.time()) - LOCK_EXPIRE_SECONDS - 1
        store.conn.execute(
            "INSERT INTO locks (game_slug, device_id, acquired_at) VALUES (?, ?, ?)",
            ("zelda", "dev-1", stale_time),
        )
        store.conn.commit()
        # dev-2 should now be able to acquire the lock
        store.acquire_lock("zelda", "dev-2")
        lock = store.get_lock("zelda")
        assert lock.device_id == "dev-2"
