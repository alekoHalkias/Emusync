"""Background save/state watcher (issue #242).

Pushes a game's save (and state) when it changes on disk, *regardless of how the
emulator was launched* — closing the gap where a save written by a plain
RetroArch-direct session (outside `emusync run`) stayed invisible until the next
wrapped launch wrote to the same folder (limitation noted in #210).

Implementation is dependency-free polling: the number of watched files is tiny
(one save/state per local game), so a periodic stat/hash sweep is simpler and more
portable than an inotify/watchdog dependency. It is **opt-in** via the
`watch_saves` config flag and runs as a background thread inside `sync-daemon`
(and the server's embedded daemon).

Safety:
- A file must be *settled* (unmodified for `SETTLE_SECONDS`) before it's pushed, so
  a half-written save mid-flush is never uploaded.
- Saves go through the same truncation guard as `emusync run`
  (`_save_is_safe_to_push`), so a 0-byte/shrunk save can't clobber the server copy.
- A game currently locked by *another* device is skipped — that device is the one
  actively playing, so we don't push this device's stale copy over it.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from cli.run import _save_is_safe_to_push

logger = logging.getLogger("emusync.watch")

POLL_INTERVAL_SECONDS = 10
# How long a file must be unmodified before we consider it settled (not mid-write).
SETTLE_SECONDS = 5
# How often to re-read this device's game list (configs change as games are added).
REFRESH_SECONDS = 60


def _file_sig(path: Path) -> Optional[tuple[float, int]]:
    """(mtime, size) for a file, or None if it doesn't exist / isn't readable."""
    try:
        st = path.stat()
        return st.st_mtime, st.st_size
    except OSError:
        return None


def _hash_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _state_token(path: Path) -> tuple[Optional[str], float]:
    """A cheap change-detection token for a state target + its newest mtime.

    States are usually a folder of slots; aggregate (count, total size, newest
    mtime) rather than hashing potentially-large archives. `.bak` files are
    ignored so a pull's retained backup doesn't trip the watcher. Returns
    (None, 0.0) if the target doesn't exist.
    """
    if path.is_dir():
        count = 0
        total = 0
        newest = 0.0
        for f in path.rglob("*"):
            if not f.is_file() or f.name.endswith(".bak"):
                continue
            sig = _file_sig(f)
            if sig is None:
                continue
            mtime, size = sig
            count += 1
            total += size
            newest = max(newest, mtime)
        if count == 0:
            return None, 0.0
        return f"{count}:{total}:{newest}", newest
    sig = _file_sig(path)
    if sig is None:
        return None, 0.0
    mtime, size = sig
    return f"file:{size}:{mtime}", mtime


class SaveWatcher:
    """Holds per-target push state so the same content isn't pushed twice."""

    def __init__(self, client, device_id: str, log=None, settle_seconds: float = SETTLE_SECONDS):
        self.client = client
        self.device_id = device_id
        self.log = log or (lambda m: logger.info(m))
        self.settle_seconds = settle_seconds
        # (slug, kind) -> last pushed signature (save hash / state token)
        self._last_pushed: dict[tuple[str, str], str] = {}

    # ── helpers ────────────────────────────────────────────────────────────────

    def _locked_by_other(self, slug: str) -> bool:
        """True if another device holds the lock (or we can't tell — be safe)."""
        try:
            lock = self.client.get_lock(slug)
        except Exception:
            logger.debug("watcher: lock check failed for %s", slug, exc_info=True)
            return True
        return bool(lock.get("locked")) and lock.get("device_id") != self.device_id

    def _save_meta(self, slug: str) -> Optional[dict]:
        try:
            return self.client.get_save_meta(slug)
        except Exception:
            logger.debug("watcher: save meta failed for %s", slug, exc_info=True)
            return None

    # ── per-target checks ──────────────────────────────────────────────────────

    def check_save(self, slug: str, name: str, save_path: str, now: Optional[float] = None) -> bool:
        """Push the save if it changed, is settled, safe, and not locked elsewhere.
        Returns True iff a push happened."""
        now = time.time() if now is None else now
        p = Path(save_path)
        sig = _file_sig(p)
        if sig is None:
            return False
        mtime, size = sig
        if now - mtime < self.settle_seconds:
            return False  # still being written — wait for it to settle
        h = _hash_file(p)
        if h is None:
            return False
        key = (slug, "save")
        if self._last_pushed.get(key) == h:
            return False  # nothing new since we last pushed
        if self._locked_by_other(slug):
            return False
        meta = self._save_meta(slug)
        if meta and meta.get("hash") == h:
            self._last_pushed[key] = h  # already current on the server
            return False
        server_size = meta.get("size") if meta else None
        if not _save_is_safe_to_push(size, server_size):
            logger.warning("watcher: refusing to push unsafe save for '%s' (%d bytes)", slug, size)
            return False
        self.client.push_save(slug, str(p))
        self._last_pushed[key] = h
        self.log(f"auto-synced save: {name}")
        return True

    def check_state(self, slug: str, name: str, state_path: str, now: Optional[float] = None) -> bool:
        """Push the state if it changed, is settled, and not locked elsewhere.
        Returns True iff a push happened. No truncation guard (states vary in size);
        the server dedupes identical content."""
        now = time.time() if now is None else now
        token, mtime = _state_token(Path(state_path))
        if token is None:
            return False
        if now - mtime < self.settle_seconds:
            return False
        key = (slug, "state")
        if self._last_pushed.get(key) == token:
            return False
        if self._locked_by_other(slug):
            return False
        self.client.push_state(slug, str(state_path))
        self._last_pushed[key] = token
        self.log(f"auto-synced state: {name}")
        return True


def _build_targets(client) -> Optional[list[tuple[str, str, str, str]]]:
    """(slug, name, kind, path) for every local game with a save/state path, or
    None if the game list couldn't be fetched this cycle."""
    try:
        games = client.list_my_game_devices()
    except Exception:
        logger.debug("watcher: could not refresh game list", exc_info=True)
        return None
    targets: list[tuple[str, str, str, str]] = []
    for g in games:
        slug = g["slug"]
        name = g.get("name", slug)
        if g.get("save_path"):
            targets.append((slug, name, "save", g["save_path"]))
        if g.get("state_path"):
            targets.append((slug, name, "state", g["state_path"]))
    return targets


def run_save_watcher(client, cfg, log=None, shutdown_event=None,
                     poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    """Poll local saves/states and push changes until `shutdown_event` is set."""
    log = log or (lambda m: logger.info(m))
    watcher = SaveWatcher(client, cfg.device_id, log)
    targets: list[tuple[str, str, str, str]] = []
    last_refresh = 0.0

    def _stopping() -> bool:
        return shutdown_event is not None and shutdown_event.is_set()

    log("Save watcher active — auto-syncing saves/states changed outside EmuSync.")
    while not _stopping():
        now = time.time()
        if now - last_refresh >= REFRESH_SECONDS or not targets:
            refreshed = _build_targets(client)
            if refreshed is not None:
                targets = refreshed
            last_refresh = now
        for slug, name, kind, path in targets:
            if _stopping():
                return
            try:
                if kind == "save":
                    watcher.check_save(slug, name, path)
                else:
                    watcher.check_state(slug, name, path)
            except Exception:
                logger.debug("watcher: error handling %s/%s", slug, kind, exc_info=True)
        # Sleep in small slices so a shutdown is acted on promptly.
        end = time.time() + poll_interval
        while time.time() < end:
            if _stopping():
                return
            time.sleep(0.25)
