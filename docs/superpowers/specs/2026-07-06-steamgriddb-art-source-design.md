# SteamGridDB as a primary art source (issue #322)

## Problem

Game art (`art:get` in `gui/electron/art.ts`) only works for the small subset of
games whose stored `name` field happens to be a byte-for-byte match against a
libretro-thumbnails filename — including the exact parenthetical region tag
(e.g. `Sonic The Hedgehog (World).png`). There is no fuzzy matching, no
directory listing, no fallback. Confirmed against the real
`libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis` repo: filenames are
No-Intro-style titles with a required region suffix that EmuSync's freely
editable game names rarely carry verbatim. This is why art shows for only a
handful of Genesis games rather than being console-specific in the code.

## Goal

Add SteamGridDB (fuzzy title search, much more forgiving) as the primary art
source, falling back to the existing libretro-thumbnails exact-match lookup
when SteamGridDB has nothing.

## Key constraint: no per-user API key setup

SteamGridDB requires a Bearer-token API key on every endpoint. There is no
OAuth or programmatic flow for a third-party app to obtain a key on a user's
behalf — confirmed against Steam ROM Manager, RomM, and SteamTinkerLaunch,
which all require the user to manually visit
`steamgriddb.com/profile/preferences/api` and paste the key into the app.

Given that, the key is configured **once, on the server device**, and shared
to every device that connects to it — stored server-side and fetched by each
device's own Electron process, rather than requiring every device's user to
independently obtain and paste in a key.

(Note: Steam ROM Manager itself actually ships a single hardcoded API key
baked into its public repo, shared across every install of that app. EmuSync
is not doing that here — each EmuSync *deployment* gets its own key, entered
once by whoever sets up the server, which is a meaningfully different trust
model from one key shared across every install of the software worldwide.)

## Design

### 1. Storage — new SQLite table

Schema version bump to 14, with a migration:

```sql
CREATE TABLE server_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
)
```

A generic single-column key-value table, not a purpose-built
`steamgriddb_api_key` column — so a future single server-wide setting doesn't
need its own migration. `server/store/` gains a small mixin (or an addition to
an existing one) with:

```python
def get_setting(self, key: str) -> Optional[str]: ...
def set_setting(self, key: str, value: str) -> None: ...
```

### 2. Server API — new route pair

New `server/api/settings.py` router (or folded into an existing small one —
implementer's call at plan time), registered like the other routers in
`server/api/__init__.py`:

- `GET /settings/steamgriddb-key` → `{"api_key": "..." | null}` — any
  authenticated device (server or client) can read it.
- `PUT /settings/steamgriddb-key` → body `{"api_key": "..."}` → persists via
  `set_setting`, returns `{"ok": true}`.

No enforcement that only the server device can call `PUT` — matches this
project's existing PIN-only trust model (nothing else enforces per-device
permissions either). The UI is what restricts the *set* control to the server
device (see section 4); the API itself just requires valid auth.

No restart required to take effect — this is live server state (store-backed),
not part of the `Config` dataclass / `.toml` file that currently requires a
restart to reload (that restart requirement is specific to `server_pin`'s
existing change flow and is not being touched here).

### 3. Electron side — reading/writing via the server API

`gui/electron/art.ts` and the settings UI call the new routes directly via
`fetch`, using the same `loadServerCfg()` (host/port/authHeaders) pattern
`gui/electron/sync.ts` already uses for every other server call. No Python/CLI
change needed — Electron never routes through the CLI's `SyncClient`.

New IPC channels (mirroring existing naming conventions):

- `steamgriddb:getKey()` → `Promise<string | null>` — GETs the route above.
  Used by: `art:get` (to decide whether to try SteamGridDB), and both the
  server's editable settings field and a joining device's read-only display.
- `steamgriddb:setKey(key: string)` → `Promise<{ ok: boolean; error?: string }>`
  — PUTs the route above. Used by: the server device's settings field, and
  Setup's onboarding paste-back step.
- `steamgriddb:openKeyPage()` → `Promise<void>` — `shell.openExternal("https://www.steamgriddb.com/profile/preferences/api")`.
  Used by: Setup's onboarding "Yes" button, and a "Get a key" link/button next
  to the server's settings field.

`art:get` fetches the key once and keeps it in memory for the Electron main
process's lifetime (module-level variable, lazily populated on first use) —
boxart fetches are infrequent and already disk-cached per game once
successful, so there's no need for TTL/refresh logic. A key changed on the
server takes effect for a given device on that device's next app restart.

### 4. Onboarding (`Setup.tsx`)

A new step `"art-prompt"`, inserted right before `onDone()` fires, but **only
on the host-a-server path** (the `server-ready` screen's "Continue to game
list" button) — not on the join path at all, since joining devices inherit
whatever the server has.

- Screen: "Would you like to use SteamGridDB to fetch game art for your
  library?" — **Yes** / **Skip for now** buttons.
- **Yes** → `steamgriddb:openKeyPage()` opens the system browser, then
  advances to `"art-key-paste"`: a text input + **Save** (calls
  `steamgriddb:setKey`, then `onDone()`) and a **Skip** escape hatch (calls
  `onDone()` without saving).
- **Skip** (from the first screen) → `onDone()` immediately, no key set.

Setup.tsx only ever runs once per device (only shown when `config.load()`
returns `null` — confirmed in `App.tsx`), so there's no "don't ask again"
flag to track separately; the prompt is inherently one-time.

### 5. Settings (`ServerStatusButton.tsx`)

- On the server device (`cfg.is_server === true`): an editable field — load
  current value via `steamgriddb:getKey()` on panel open, a "Get a key"
  button (`steamgriddb:openKeyPage()`), a text input, and a Save button
  (`steamgriddb:setKey()`), following the existing PIN field's UI
  conventions in this same component (plain text input, not password-masked,
  for consistency).
- On a joining device (`cfg.is_server === false`): the same field rendered
  **read-only** — fetched via `steamgriddb:getKey()`, no edit control, just a
  masked-or-plain display confirming whether a key is configured server-side.

### 6. `art:get` provider order

Inside the existing `art:get` handler in `art.ts`:

1. Check local disk cache (`~/.emusync/art/<slug>.png`) — unchanged, first
   thing, as today.
2. If no cache: fetch the shared key (`steamgriddb:getKey()` internally, or
   the in-memory cache from section 3). If a key is present, call the
   `steamgriddb` npm package: `searchGame(gameName)` → take the first
   result's `id` → `getGrids({ id, type: "game", dimensions: ["600x900"] })`
   → download the first grid's URL into the cache path.
3. If SteamGridDB has no key configured, no search results, or the request
   errors (network, rate limit) — fall through to the existing
   `buildThumbnailUrl` + libretro-thumbnails exact-match download, unchanged.
4. If both fail, return `null` (existing placeholder behavior, unchanged).

`art:getConsoleIcon` (RetroArch system logos, a different asset entirely) is
untouched — out of scope.

### New dependency

`steamgriddb` npm package added to `gui/package.json`, matching how Steam ROM
Manager itself calls the API (typed client over `searchGame`/`getGrids`).

## Testing

No JS test framework exists in this project (confirmed in earlier work on the
Ctrl+= zoom fix — Electron main-process code has no automated test coverage
anywhere). Verification here will be:

- Python side: standard `make test` regression run (unaffected by this
  change, but must still pass) plus a new store-level test for
  `get_setting`/`set_setting` and the new API route pair, following the
  existing pattern in `tests/test_console_memcard.py` (a small, focused
  Python test file is realistic here since the storage + API route are
  ordinary Python/FastAPI code, unlike the Electron side).
- Electron side: manual verification in dev mode — onboarding flow, settings
  panel (both server and joining-device views), and an actual art fetch
  against a real SteamGridDB key.

## Out of scope

- Automatic/OAuth key retrieval (confirmed not possible via SteamGridDB's
  API).
- Per-user (rather than per-server-deployment) keys.
- Any change to `art:getConsoleIcon`.
- Negative-caching a failed art lookup (if SteamGridDB and libretro-thumbnails
  both miss, the next attempt just retries — matches existing behavior, not a
  regression).
