# SteamGridDB Art Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SteamGridDB as the primary game-art source (ahead of the existing libretro-thumbnails exact-match fallback), with the API key configured once on the server device and shared to every connected device — no per-user key setup.

**Architecture:** A new generic `server_settings` key-value table (SQLite) stores the shared API key server-side, exposed via a new authenticated `GET`/`PUT /settings/steamgriddb-key` API route pair. Every device's Electron main process fetches the key from the server (cached in-memory for the process's lifetime) and uses it to call the `steamgriddb` npm package before falling back to the existing libretro-thumbnails lookup. Onboarding (`Setup.tsx`, host path only) and settings (`ServerStatusButton.tsx`, editable on the server / read-only on clients) round out the UI.

**Tech Stack:** Python (FastAPI, SQLite/sqlite3, pytest), TypeScript (Electron main process, React renderer), `steamgriddb` npm package (v2.2.1).

## Global Constraints

- Full spec: `docs/superpowers/specs/2026-07-06-steamgriddb-art-source-design.md` — read it before starting if anything below is unclear.
- No restart required for the key to take effect server-side (store-backed, not part of the restart-requiring `Config`/`.toml` file).
- A device's own in-memory cache of the key only refreshes on that device's next app restart — this is intentional, not a bug to fix.
- No enforcement that only the server device can `PUT` the key — the API trusts any authenticated device, matching this project's existing PIN-only trust model. The UI is what restricts the *edit* control to the server device.
- No JS test framework exists in this project — Electron/React tasks are verified manually (steps say exactly what to click/observe); Python tasks use real pytest + real SQLite, no mocks (project-wide rule, see `CLAUDE.md`).
- `art:getConsoleIcon` (RetroArch system logos) is out of scope — do not touch it.
- Every task that touches an "architecture file" (per this repo's pre-commit hook: `server/api.py`, `server/config.py`, `server/store.py`, `server/mdns.py`, `server/sync_client.py`, `gui/electron/main.ts`, `gui/electron/preload.ts`, `requirements.txt`, `gui/package.json`) will trigger a warning unless `CLAUDE.md` is updated in the same commit — Task 7 handles all doc updates in one place; commit it together with the last code task, or the hook will complain (harmless — you can commit anyway with `--no-verify` if doing it in strict task order, but preferred is to fold Task 7's relevant lines into whichever commit touches those files).

---

### Task 1: Store — `server_settings` table + `SettingsMixin`

**Files:**
- Modify: `server/store/schema.py` (bump `_SCHEMA_VERSION`, add migration, add to fresh-db `_SCHEMA`)
- Create: `server/store/settings.py`
- Modify: `server/store/__init__.py` (mix in `SettingsMixin`)
- Test: `tests/test_server_settings.py`

**Interfaces:**
- Produces: `Store.get_setting(key: str) -> Optional[str]`, `Store.set_setting(key: str, value: str) -> None` — consumed by Task 2's API routes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_settings.py`:

```python
"""Generic server-wide settings key-value store (issue #322)."""
from __future__ import annotations

import tempfile

from server.store import Store


def test_get_setting_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        assert store.get_setting("steamgriddb_api_key") is None


def test_set_then_get_setting_roundtrips():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.set_setting("steamgriddb_api_key", "abc123")
        assert store.get_setting("steamgriddb_api_key") == "abc123"


def test_set_setting_overwrites_existing_value():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.set_setting("steamgriddb_api_key", "first")
        store.set_setting("steamgriddb_api_key", "second")
        assert store.get_setting("steamgriddb_api_key") == "second"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_server_settings.py -v`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'get_setting'`

- [ ] **Step 3: Add the schema migration + fresh-db table**

In `server/store/schema.py`, change:

```python
_SCHEMA_VERSION = 13
```

to:

```python
_SCHEMA_VERSION = 14
```

Then find the end of the `_SCHEMA` string (the `console_saves` table, immediately before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS console_saves (
    console_key      TEXT PRIMARY KEY,
    device_id        TEXT NOT NULL,
    hash             TEXT NOT NULL,
    pushed_at        TEXT NOT NULL,
    size             INTEGER NOT NULL
);
"""
```

and add the new table right before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS console_saves (
    console_key      TEXT PRIMARY KEY,
    device_id        TEXT NOT NULL,
    hash             TEXT NOT NULL,
    pushed_at        TEXT NOT NULL,
    size             INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS server_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""
```

Then find the last migration block in `_migrate()`:

```python
    if from_version < 13:
        # Console-scoped shared save: one memory card per console (PS2), shared
        # across every game on that console, reconciled around any launch (#295).
        _try(conn, """CREATE TABLE IF NOT EXISTS console_saves (
            console_key      TEXT PRIMARY KEY,
            device_id        TEXT NOT NULL,
            hash             TEXT NOT NULL,
            pushed_at        TEXT NOT NULL,
            size             INTEGER NOT NULL
        )""")
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
```

and add a new block right after it, before the `PRAGMA user_version` line:

```python
    if from_version < 13:
        # Console-scoped shared save: one memory card per console (PS2), shared
        # across every game on that console, reconciled around any launch (#295).
        _try(conn, """CREATE TABLE IF NOT EXISTS console_saves (
            console_key      TEXT PRIMARY KEY,
            device_id        TEXT NOT NULL,
            hash             TEXT NOT NULL,
            pushed_at        TEXT NOT NULL,
            size             INTEGER NOT NULL
        )""")
    if from_version < 14:
        # Generic single-value server-wide settings (issue #322) — currently
        # used for the shared SteamGridDB API key (entered once on the server
        # device, fetched by every connected device), but kept generic so a
        # future single server-wide setting doesn't need its own migration.
        _try(conn, """CREATE TABLE IF NOT EXISTS server_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )""")
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
```

- [ ] **Step 4: Create the mixin**

Create `server/store/settings.py`:

```python
"""Generic single-value server-wide settings (issue #322).

A small key-value table for server-wide settings that aren't per-game,
per-device, or per-console — currently just the shared SteamGridDB API key,
entered once on the server device and fetched by every connected device
(SteamGridDB has no OAuth/programmatic flow for a per-user key). Kept
generic so a future single server-wide setting doesn't need its own
migration.
"""
from __future__ import annotations

from typing import Optional


class SettingsMixin:
    """Operates on `self._conn`; mixed into Store."""

    def get_setting(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM server_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO server_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()
```

- [ ] **Step 5: Mix it into `Store`**

In `server/store/__init__.py`, add the import:

```python
from server.store.locks import LOCK_TTL_HOURS, LockMixin
```

becomes (add the new import alphabetically after `models` imports, before `transfers`):

```python
from server.store.locks import LOCK_TTL_HOURS, LockMixin
from server.store.models import (
    Console,
    Device,
    Game,
    GameDevice,
    Lock,
    RomPullRequest,
    RomTransfer,
    SaveMeta,
)
from server.store.settings import SettingsMixin
from server.store.transfers import TransferMixin
```

And add `SettingsMixin` to the `Store` class bases:

```python
class Store(
    DeviceMixin,
    ConsoleMixin,
    GameMixin,
    GameDeviceMixin,
    SaveStateMixin,
    LockMixin,
    EventMixin,
    TransferMixin,
    ConsoleDefMixin,
    ConflictMixin,
    SettingsMixin,
    StoreBase,
):
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_server_settings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the full suite to check for regressions**

Run: `make test`
Expected: all tests pass (previous count + 3 new ones)

- [ ] **Step 8: Commit**

```bash
git add server/store/schema.py server/store/settings.py server/store/__init__.py tests/test_server_settings.py
git commit -m "Add server_settings table for the shared SteamGridDB key (#322)"
```

---

### Task 2: API — `GET`/`PUT /settings/steamgriddb-key`

**Files:**
- Create: `server/api/settings.py`
- Modify: `server/api/__init__.py` (register the router)
- Test: `tests/test_settings_api.py`

**Interfaces:**
- Consumes: `Store.get_setting`/`set_setting` from Task 1.
- Produces: the two HTTP routes, consumed by Task 3's Electron code.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_api.py`:

```python
"""GET/PUT /settings/steamgriddb-key (issue #322)."""
from __future__ import annotations

import pytest

from tests.conftest import AUTH


@pytest.mark.asyncio
async def test_get_steamgriddb_key_defaults_to_none(client):
    r = await client.get("/settings/steamgriddb-key", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"api_key": None}


@pytest.mark.asyncio
async def test_set_then_get_steamgriddb_key_roundtrips(client):
    r = await client.put("/settings/steamgriddb-key", json={"api_key": "sgdb-test-key"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await client.get("/settings/steamgriddb-key", headers=AUTH)
    assert r.json() == {"api_key": "sgdb-test-key"}


@pytest.mark.asyncio
async def test_get_steamgriddb_key_requires_auth(client):
    r = await client.get("/settings/steamgriddb-key")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_set_steamgriddb_key_requires_auth(client):
    r = await client.put("/settings/steamgriddb-key", json={"api_key": "x"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_settings_api.py -v`
Expected: FAIL — 404 Not Found on all four (route doesn't exist yet)

- [ ] **Step 3: Create the router**

Create `server/api/settings.py`:

```python
"""Server-wide settings (issue #322) — currently just the shared SteamGridDB
API key. Entered once on the server device (see gui's Setup.tsx onboarding
step and ServerStatusButton's settings panel) and fetched by every device's
Electron process, since SteamGridDB has no OAuth/programmatic flow for a
per-user key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ._core import _auth, _get_store

router = APIRouter()

_STEAMGRIDDB_KEY = "steamgriddb_api_key"


class SteamGridDbKey(BaseModel):
    api_key: str = ""


@router.get("/settings/steamgriddb-key")
def get_steamgriddb_key(device_id: str = Depends(_auth)) -> dict:
    return {"api_key": _get_store().get_setting(_STEAMGRIDDB_KEY)}


@router.put("/settings/steamgriddb-key")
def set_steamgriddb_key(req: SteamGridDbKey, device_id: str = Depends(_auth)) -> dict:
    _get_store().set_setting(_STEAMGRIDDB_KEY, req.api_key)
    return {"ok": True}
```

- [ ] **Step 4: Register the router**

In `server/api/__init__.py`, change:

```python
from ._core import app, init
from . import devices, games, transfers, blobs, locks, defs, conflicts

# Order is not load-bearing across routers (no same-depth literal/param
# collisions exist between them); the one collision — /games/overview vs
# /games/{slug} — is resolved within games.py by declaration order.
app.include_router(devices.router)
app.include_router(games.router)
app.include_router(transfers.router)
app.include_router(blobs.router)
app.include_router(locks.router)
app.include_router(defs.router)
app.include_router(conflicts.router)
```

to:

```python
from ._core import app, init
from . import devices, games, transfers, blobs, locks, defs, conflicts, settings

# Order is not load-bearing across routers (no same-depth literal/param
# collisions exist between them); the one collision — /games/overview vs
# /games/{slug} — is resolved within games.py by declaration order.
app.include_router(devices.router)
app.include_router(games.router)
app.include_router(transfers.router)
app.include_router(blobs.router)
app.include_router(locks.router)
app.include_router(defs.router)
app.include_router(conflicts.router)
app.include_router(settings.router)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_settings_api.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Run the full suite to check for regressions**

Run: `make test`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add server/api/settings.py server/api/__init__.py tests/test_settings_api.py
git commit -m "Add GET/PUT /settings/steamgriddb-key API route (#322)"
```

---

### Task 3: Electron — `steamgriddb.ts` IPC module

**Files:**
- Create: `gui/electron/steamgriddb.ts`
- Modify: `gui/electron/main.ts` (register the new IPC)
- Modify: `gui/electron/preload.ts` (expose the bridge)
- Modify: `gui/renderer/src/emusync.d.ts` (add the types)

**Interfaces:**
- Consumes: `loadServerCfg()` from `gui/electron/config-store.ts` (existing, `{ host, port, authHeaders }`).
- Produces: `getSteamGridDbKey(): Promise<string | null>` (a plain exported function, imported directly by Task 4's `art.ts` — same process, no IPC round-trip needed for that internal use), plus the three IPC channels `steamgriddb:getKey`, `steamgriddb:setKey`, `steamgriddb:openKeyPage` consumed by Task 5 (`Setup.tsx`) and Task 6 (`ServerStatusButton.tsx`) via `window.emusync.steamgriddb.*`.

- [ ] **Step 1: Create the module**

Create `gui/electron/steamgriddb.ts`:

```typescript
// SteamGridDB shared-key handling (issue #322) — the key is entered once on
// the server device and shared to every device via the EmuSync server, since
// SteamGridDB has no OAuth/programmatic flow for a third-party app to obtain
// a per-user key (confirmed: every integration — Steam ROM Manager, RomM,
// SteamTinkerLaunch — requires manually pasting a key obtained from
// steamgriddb.com/profile/preferences/api).
import { ipcMain, shell } from "electron";
import { loadServerCfg } from "./config-store";

const STEAMGRIDDB_KEY_URL = "https://www.steamgriddb.com/profile/preferences/api";

// Cached for this process's lifetime — art:get calls this on every cache miss,
// and the key rarely changes, so there's no need to hit the server every
// time. A key changed on the server takes effect here on next app restart.
let cachedKey: string | null | undefined; // undefined = not yet fetched this run

export async function getSteamGridDbKey(): Promise<string | null> {
  if (cachedKey !== undefined) return cachedKey;
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/settings/steamgriddb-key`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) { cachedKey = null; return null; }
    const body = await res.json() as { api_key: string | null };
    cachedKey = body.api_key || null;
    return cachedKey;
  } catch {
    cachedKey = null;
    return null;
  }
}

export function registerSteamGridDbIpc(): void {
  ipcMain.handle("steamgriddb:getKey", (): Promise<string | null> => getSteamGridDbKey());

  ipcMain.handle("steamgriddb:setKey", async (_event, key: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/settings/steamgriddb-key`, {
        method: "PUT",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, error: (body as any).detail ?? res.statusText };
      }
      cachedKey = key || null; // refresh this process's own cache immediately
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Failed to save key" };
    }
  });

  ipcMain.handle("steamgriddb:openKeyPage", async (): Promise<void> => {
    await shell.openExternal(STEAMGRIDDB_KEY_URL);
  });
}
```

- [ ] **Step 2: Register it in `main.ts`**

In `gui/electron/main.ts`, change:

```typescript
import { registerEmulatorIpc } from "./emulator/ipc";
import { registerArtIpc } from "./art";

// Register all IPC handlers up front (renderer can only call them once a window
// has loaded, which happens after app.whenReady below).
registerConfigIpc();
registerServerIpc();
registerGameIpc();
registerFilesIpc();
registerSyncIpc();
registerEmulatorIpc();
registerArtIpc();
```

to:

```typescript
import { registerEmulatorIpc } from "./emulator/ipc";
import { registerArtIpc } from "./art";
import { registerSteamGridDbIpc } from "./steamgriddb";

// Register all IPC handlers up front (renderer can only call them once a window
// has loaded, which happens after app.whenReady below).
registerConfigIpc();
registerServerIpc();
registerGameIpc();
registerFilesIpc();
registerSyncIpc();
registerEmulatorIpc();
registerArtIpc();
registerSteamGridDbIpc();
```

- [ ] **Step 3: Expose it in `preload.ts`**

In `gui/electron/preload.ts`, change:

```typescript
  art: {
    get: (slug: string, gameName: string, consoleKey: string): Promise<string | null> =>
      ipcRenderer.invoke("art:get", slug, gameName, consoleKey),
    getConsoleIcon: (consoleKey: string): Promise<string | null> =>
      ipcRenderer.invoke("art:getConsoleIcon", consoleKey),
  },
```

to:

```typescript
  art: {
    get: (slug: string, gameName: string, consoleKey: string): Promise<string | null> =>
      ipcRenderer.invoke("art:get", slug, gameName, consoleKey),
    getConsoleIcon: (consoleKey: string): Promise<string | null> =>
      ipcRenderer.invoke("art:getConsoleIcon", consoleKey),
  },
  steamgriddb: {
    getKey: (): Promise<string | null> => ipcRenderer.invoke("steamgriddb:getKey"),
    setKey: (key: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke("steamgriddb:setKey", key),
    openKeyPage: (): Promise<void> => ipcRenderer.invoke("steamgriddb:openKeyPage"),
  },
```

- [ ] **Step 4: Add the types in `emusync.d.ts`**

In `gui/renderer/src/emusync.d.ts`, change:

```typescript
  art: {
    get: (slug: string, gameName: string, consoleKey: string) => Promise<string | null>;
    getConsoleIcon: (consoleKey: string) => Promise<string | null>;
  };
  daemon: {
```

to:

```typescript
  art: {
    get: (slug: string, gameName: string, consoleKey: string) => Promise<string | null>;
    getConsoleIcon: (consoleKey: string) => Promise<string | null>;
  };
  steamgriddb: {
    getKey: () => Promise<string | null>;
    setKey: (key: string) => Promise<{ ok: boolean; error?: string }>;
    openKeyPage: () => Promise<void>;
  };
  daemon: {
```

- [ ] **Step 5: Typecheck**

Run: `cd gui && npx tsc --noEmit -p tsconfig.node.json`
Expected: no output (clean)

- [ ] **Step 6: Commit**

```bash
git add gui/electron/steamgriddb.ts gui/electron/main.ts gui/electron/preload.ts gui/renderer/src/emusync.d.ts
git commit -m "Add steamgriddb:getKey/setKey/openKeyPage IPC (#322)"
```

---

### Task 4: Electron — wire SteamGridDB into `art:get`

**Files:**
- Modify: `gui/package.json` (add the `steamgriddb` dependency)
- Modify: `gui/electron/art.ts`

**Interfaces:**
- Consumes: `getSteamGridDbKey()` from Task 3's `gui/electron/steamgriddb.ts`.

- [ ] **Step 1: Add the dependency**

In `gui/package.json`, change:

```json
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "smol-toml": "^1.3.1"
  },
```

to:

```json
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "smol-toml": "^1.3.1",
    "steamgriddb": "^2.2.1"
  },
```

Run: `cd gui && npm install`
Expected: `steamgriddb` added to `node_modules` and `gui/package-lock.json` updated

- [ ] **Step 2: Wire it into `art:get`**

In `gui/electron/art.ts`, change the imports:

```typescript
import { ipcMain } from "electron";
import { createWriteStream, existsSync, mkdirSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import https from "https";
```

to:

```typescript
import { ipcMain } from "electron";
import { createWriteStream, existsSync, mkdirSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import https from "https";
import SGDB from "steamgriddb";
import { getSteamGridDbKey } from "./steamgriddb";
```

Then add a new function after `buildThumbnailUrl` (right before the `download` function):

```typescript
async function fetchFromSteamGridDb(gameName: string, dest: string): Promise<boolean> {
  const key = await getSteamGridDbKey();
  if (!key) return false;
  try {
    const client = new SGDB({ key });
    const games = await client.searchGame(gameName);
    if (!games.length) return false;
    const grids = await client.getGrids({ id: games[0].id, type: "game", dimensions: ["600x900"] });
    if (!grids.length) return false;
    await download(String(grids[0].url), dest);
    return existsSync(dest);
  } catch {
    return false;
  }
}
```

Then change the `art:get` handler:

```typescript
  ipcMain.handle(
    "art:get",
    async (_event, slug: string, gameName: string, consoleKey: string): Promise<string | null> => {
      try {
        mkdirSync(ART_DIR, { recursive: true });
        const dest = join(ART_DIR, `${slug}.png`);
        if (existsSync(dest)) return toDataUrl(dest);

        const url = buildThumbnailUrl(consoleKey, gameName);
        if (!url) return null;

        await download(url, dest);
        return existsSync(dest) ? toDataUrl(dest) : null;
      } catch {
        return null;
      }
    },
  );
```

to:

```typescript
  ipcMain.handle(
    "art:get",
    async (_event, slug: string, gameName: string, consoleKey: string): Promise<string | null> => {
      try {
        mkdirSync(ART_DIR, { recursive: true });
        const dest = join(ART_DIR, `${slug}.png`);
        if (existsSync(dest)) return toDataUrl(dest);

        // SteamGridDB's fuzzy title search finds far more games than the
        // exact-filename libretro-thumbnails lookup below; try it first when
        // a shared key is configured (issue #322).
        if (await fetchFromSteamGridDb(gameName, dest)) return toDataUrl(dest);

        const url = buildThumbnailUrl(consoleKey, gameName);
        if (!url) return null;

        await download(url, dest);
        return existsSync(dest) ? toDataUrl(dest) : null;
      } catch {
        return null;
      }
    },
  );
```

- [ ] **Step 3: Typecheck**

Run: `cd gui && npx tsc --noEmit -p tsconfig.node.json`
Expected: no output (clean)

- [ ] **Step 4: Manual verification**

This step needs a real SteamGridDB API key (get one free at
`steamgriddb.com/profile/preferences/api`, linked via Steam login) since there's
no automated test coverage for Electron code in this project:

1. Run `make dev-gui`.
2. In the running app, use `window.emusync.steamgriddb.setKey("<your real key>")`
   from the renderer devtools console (Ctrl+Shift+I), or wait for Task 6's UI.
3. Delete any cached art for a test game: `rm ~/.emusync/art/<slug>.png`.
4. Reload the game grid and confirm art now loads for a game that previously
   showed the placeholder (e.g. a Genesis game whose name doesn't carry the
   exact libretro region tag).
5. Confirm a game with NO SteamGridDB match at all still falls through to the
   libretro-thumbnails lookup (or placeholder) without erroring — check the
   `make dev-gui` terminal for `[scan]`-style errors; there should be none.

- [ ] **Step 5: Commit**

```bash
git add gui/package.json gui/package-lock.json gui/electron/art.ts
git commit -m "Try SteamGridDB before libretro-thumbnails in art:get (#322)"
```

---

### Task 5: Onboarding — `Setup.tsx` art-prompt step

**Files:**
- Modify: `gui/renderer/src/components/Setup.tsx`

**Interfaces:**
- Consumes: `window.emusync.steamgriddb.openKeyPage()` / `.setKey(key)` from Task 3.

- [ ] **Step 1: Add the new steps to the `Step` type**

Change:

```typescript
type Step =
  | "choose"
  | "server-starting"
  | "server-ready"
  | "join-scanning"
  | "join-select"
  | "join-pin"
  | "join-name";
```

to:

```typescript
type Step =
  | "choose"
  | "server-starting"
  | "server-ready"
  | "art-prompt"
  | "art-key-paste"
  | "join-scanning"
  | "join-select"
  | "join-pin"
  | "join-name";
```

- [ ] **Step 2: Add state for the key-paste step**

Change:

```typescript
  const [busy, setBusy] = useState(false);
  const [deviceName, setDeviceName] = useState("");
```

to:

```typescript
  const [busy, setBusy] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [artKey, setArtKey] = useState("");
  const [artKeyError, setArtKeyError] = useState("");
  const [artKeyBusy, setArtKeyBusy] = useState(false);
```

- [ ] **Step 3: Redirect the server-ready "Continue" button**

Change:

```tsx
        {step === "server-ready" && (
          <>
            <h1>Server is running!</h1>
            <p style={{ marginBottom: 16 }}>
              Your EmuSync server is ready. Other devices on your network can now connect.
            </p>
            <p style={{ marginBottom: 24, fontSize: 13, color: "var(--text-muted, #888)" }}>
              To require a PIN, open the server settings from the top-right button after continuing.
              If no PIN is set, any device on your LAN can connect.
            </p>
            <button className="btn btn-primary" onClick={onDone} style={{ width: "100%" }}>
              Continue to game list
            </button>
          </>
        )}
```

to:

```tsx
        {step === "server-ready" && (
          <>
            <h1>Server is running!</h1>
            <p style={{ marginBottom: 16 }}>
              Your EmuSync server is ready. Other devices on your network can now connect.
            </p>
            <p style={{ marginBottom: 24, fontSize: 13, color: "var(--text-muted, #888)" }}>
              To require a PIN, open the server settings from the top-right button after continuing.
              If no PIN is set, any device on your LAN can connect.
            </p>
            <button className="btn btn-primary" onClick={() => setStep("art-prompt")} style={{ width: "100%" }}>
              Continue
            </button>
          </>
        )}

        {step === "art-prompt" && (
          <>
            <h1>Game art</h1>
            <p style={{ marginBottom: 24 }}>
              Would you like to use SteamGridDB to fetch box art for your games?
              This is configured once here and shared with every device that
              connects to this server.
            </p>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" style={{ flex: 1 }} onClick={onDone}>
                Skip for now
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={async () => {
                  await window.emusync.steamgriddb.openKeyPage();
                  setStep("art-key-paste");
                }}
              >
                Yes
              </button>
            </div>
          </>
        )}

        {step === "art-key-paste" && (
          <>
            <h1>Paste your SteamGridDB API key</h1>
            <p style={{ marginBottom: 16 }}>
              Log in with Steam on the page that just opened, then copy your
              API key from the "API" tab and paste it below.
            </p>
            <div className="input-group" style={{ marginBottom: 16 }}>
              <label>API key</label>
              <input
                type="text"
                value={artKey}
                onChange={(e) => { setArtKey(e.target.value); setArtKeyError(""); }}
                placeholder="Paste your key here"
                className={artKeyError ? "error" : ""}
                autoFocus
              />
              {artKeyError && <span className="error-msg">{artKeyError}</span>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" onClick={onDone} disabled={artKeyBusy}>
                Skip
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={artKeyBusy || !artKey.trim()}
                onClick={async () => {
                  setArtKeyBusy(true);
                  setArtKeyError("");
                  const result = await window.emusync.steamgriddb.setKey(artKey.trim());
                  setArtKeyBusy(false);
                  if (result.ok) {
                    onDone();
                  } else {
                    setArtKeyError(result.error || "Failed to save key.");
                  }
                }}
              >
                {artKeyBusy ? <><span className="spinner" /> Saving…</> : "Save"}
              </button>
            </div>
          </>
        )}
```

Note: the join path's `doConnect()` function is untouched — it still calls
`onDone()` directly, so joining devices never see this prompt (per the
approved design).

- [ ] **Step 4: Typecheck**

Run: `cd gui && npx tsc --noEmit -p tsconfig.web.json`
Expected: no output (clean)

- [ ] **Step 5: Manual verification**

1. Move or rename `~/.emusync/emusync.toml` temporarily (so Setup shows again) — e.g. `mv ~/.emusync/emusync.toml ~/.emusync/emusync.toml.bak`.
2. Run `make dev-gui`, choose "Set up this as the server".
3. Confirm after "Server is running!" → Continue, you land on the new "Game art" prompt.
4. Click "Skip for now" — confirm it goes straight to the game list (no key saved).
5. Restore the backup: `mv ~/.emusync/emusync.toml.bak ~/.emusync/emusync.toml`, repeat steps 1-3, this time click "Yes" — confirm your browser opens to `steamgriddb.com/profile/preferences/api` and the app advances to the paste step.
6. Paste a real key (or a throwaway string for this check) and click Save — confirm it advances to the game list without error.
7. Confirm the *join* path (second device / manual host+port entry) never shows this prompt at all.

- [ ] **Step 6: Commit**

```bash
git add gui/renderer/src/components/Setup.tsx
git commit -m "Add SteamGridDB art-prompt onboarding step (server path only) (#322)"
```

---

### Task 6: Settings — `ServerStatusButton.tsx` key field

**Files:**
- Modify: `gui/renderer/src/components/ServerStatusButton.tsx`

**Interfaces:**
- Consumes: `window.emusync.steamgriddb.getKey()` / `.setKey(key)` / `.openKeyPage()` from Task 3.

- [ ] **Step 1: Add state**

Change:

```typescript
  // Connect-to-server form
  const [pairHost, setPairHost] = useState("");
```

to:

```typescript
  // SteamGridDB art key (issue #322)
  const [artKey, setArtKey] = useState("");
  const [artKeyInput, setArtKeyInput] = useState("");
  const [artKeyBusy, setArtKeyBusy] = useState(false);
  const [artKeySaved, setArtKeySaved] = useState(false);

  // Connect-to-server form
  const [pairHost, setPairHost] = useState("");
```

- [ ] **Step 2: Fetch the current key when the panel opens**

Change:

```typescript
  useEffect(() => {
    if (!open) return;
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      setPairHost((cfg.server_host as string) || "localhost");
      setPairPort(String((cfg.server_port as number) || 8765));
      setDeviceName((cfg.device_name as string) || "");
      setPinInput((cfg.server_pin as string) || "");
    });
  }, [open]);
```

to:

```typescript
  useEffect(() => {
    if (!open) return;
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      setPairHost((cfg.server_host as string) || "localhost");
      setPairPort(String((cfg.server_port as number) || 8765));
      setDeviceName((cfg.device_name as string) || "");
      setPinInput((cfg.server_pin as string) || "");
    });
    window.emusync.steamgriddb.getKey().then((key) => {
      setArtKey(key || "");
      setArtKeyInput(key || "");
    });
  }, [open]);
```

- [ ] **Step 3: Add the save handler**

Change:

```typescript
  async function saveDeviceName(): Promise<void> {
    const cfg = (await window.emusync.config.load()) ?? {};
    await window.emusync.config.save({ ...cfg, device_name: deviceName });
    setDeviceNameSaved(true);
    setTimeout(() => setDeviceNameSaved(false), 2000);
  }
```

to:

```typescript
  async function saveDeviceName(): Promise<void> {
    const cfg = (await window.emusync.config.load()) ?? {};
    await window.emusync.config.save({ ...cfg, device_name: deviceName });
    setDeviceNameSaved(true);
    setTimeout(() => setDeviceNameSaved(false), 2000);
  }

  async function saveArtKey(): Promise<void> {
    setArtKeyBusy(true);
    const result = await window.emusync.steamgriddb.setKey(artKeyInput.trim());
    setArtKeyBusy(false);
    if (result.ok) {
      setArtKey(artKeyInput.trim());
      setArtKeySaved(true);
      setTimeout(() => setArtKeySaved(false), 2000);
    }
  }
```

- [ ] **Step 4: Add the UI section**

Change:

```tsx
            {/* Paired devices — folded in from the old standalone modal (#262) */}
            <DevicesPanel />
```

to:

```tsx
            {/* SteamGridDB art key (issue #322) — set on the server device,
                shared to every device that connects; joining devices see a
                read-only view. */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginBottom: 20 }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 12 }}>
                SteamGridDB art
              </div>
              {isServer ? (
                <>
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
                    <div className="input-group" style={{ flex: 1, marginBottom: 0 }}>
                      <label>API key <span style={{ opacity: 0.6, fontWeight: 400 }}>(optional)</span></label>
                      <input
                        type="text"
                        value={artKeyInput}
                        onChange={(e) => setArtKeyInput(e.target.value)}
                        placeholder="Paste your SteamGridDB API key"
                      />
                    </div>
                    <button className="btn btn-ghost" onClick={saveArtKey} disabled={artKeyBusy} style={{ flexShrink: 0 }}>
                      {artKeySaved ? "Saved" : artKeyBusy ? <span className="spinner" /> : "Save"}
                    </button>
                  </div>
                  <button className="btn btn-ghost" onClick={() => window.emusync.steamgriddb.openKeyPage()} style={{ fontSize: 12 }}>
                    Get a key from SteamGridDB →
                  </button>
                </>
              ) : (
                <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {artKey ? "Configured on the server." : "Not configured on the server."}
                </p>
              )}
            </div>

            {/* Paired devices — folded in from the old standalone modal (#262) */}
            <DevicesPanel />
```

- [ ] **Step 5: Typecheck**

Run: `cd gui && npx tsc --noEmit -p tsconfig.web.json`
Expected: no output (clean)

- [ ] **Step 6: Manual verification**

1. Run `make dev-gui` on the server device, open the server-status panel
   (top-right button) — confirm an editable "SteamGridDB art" section appears
   with a "Get a key" link and a Save button; save a key and confirm the
   Save button briefly shows "Saved".
2. On a joining/client device (or by temporarily setting `is_server: false`
   in `~/.emusync/emusync.toml` for a quick local check), open the same
   panel — confirm it shows the read-only "Configured on the server." /
   "Not configured on the server." text instead of an input.

- [ ] **Step 7: Commit**

```bash
git add gui/renderer/src/components/ServerStatusButton.tsx
git commit -m "Add SteamGridDB key field to server settings panel (#322)"
```

---

### Task 7: Documentation — `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the IPC bridge list**

Find:

```
window.emusync.daemon.start()              // spawn emusync sync-daemon (client devices only; no-op on server or if already running)
window.emusync.daemon.stop()               // kill the sync daemon if running
```

Add right after it:

```
window.emusync.steamgriddb.getKey()        // fetches the shared SteamGridDB API key from the server (GET /settings/steamgriddb-key); cached in-memory for this process's lifetime
window.emusync.steamgriddb.setKey(key)     // PUTs a new shared key to the server; any device can call this, but only the server device's UI exposes an edit control (issue #322)
window.emusync.steamgriddb.openKeyPage()   // opens steamgriddb.com/profile/preferences/api in the system browser
```

- [ ] **Step 2: Update the schema-versioning gotcha**

Find:

```
**DB schema versioning — use `PRAGMA user_version`, not try/except** — `server/store/schema.py` tracks the schema version in `PRAGMA user_version` (currently `_SCHEMA_VERSION = 13`).
```

Change `_SCHEMA_VERSION = 13` to `_SCHEMA_VERSION = 14` in that sentence.

- [ ] **Step 3: Add a key-files table entry**

Find the `server/api/` row in the Key files table and add, at the end of its
cell (before the closing `|`):

```
; `settings.py` = the shared SteamGridDB API key (`GET`/`PUT /settings/steamgriddb-key`), a generic `server_settings` key-value store — entered once on the server device, fetched by every connected device's Electron process so art fetching doesn't need a per-user key (issue #322)
```

Find the `server/store/` row and add, at the end of its cell:

```
; `settings.py` (`SettingsMixin`) backs the above with a generic `server_settings(key, value)` table (schema v14)
```

Find the `gui/electron/` row's module list and add `steamgriddb.ts` to it,
right after the `art.ts` mention:

```
`steamgriddb.ts` (`getSteamGridDbKey()` + `steamgriddb:getKey`/`setKey`/`openKeyPage` IPC — fetches/sets the shared key via the server API, and opens the browser to `steamgriddb.com/profile/preferences/api`; `art.ts`'s `art:get` tries SteamGridDB first when a key is configured, falling back to the existing libretro-thumbnails exact-match lookup, issue #322)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the SteamGridDB shared-key feature (#322)"
```

---

## Self-Review Notes

- **Spec coverage:** storage (Task 1), API (Task 2), Electron key-fetch/IPC (Task 3), art.ts provider order (Task 4), onboarding host-only (Task 5), settings editable/read-only (Task 6), docs (Task 7) — all spec sections have a task.
- **Type consistency checked:** `getSteamGridDbKey(): Promise<string | null>` (Task 3) is the exact signature Task 4 imports and calls; `steamgriddb:setKey` returns `{ ok: boolean; error?: string }` consistently across `steamgriddb.ts`, `preload.ts`, `emusync.d.ts`, `Setup.tsx`, and `ServerStatusButton.tsx`.
- **No restart required** is implemented correctly: Task 2's routes mutate the SQLite-backed store directly, with no interaction with `Config`/`.toml` or the server process restart path used by `server:change-pin`.
