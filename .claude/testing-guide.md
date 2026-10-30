# EmuSync Testing Guide

## Test Philosophy
- No mocks, real SQLite only. Use `tmp_path` for filesystem operations.
- Unit tests for pure functions (detect.py helpers, store methods).
- Integration tests for API routes (client fixture, real FastAPI app).
- CLI-level tests that need sockets use the `live_server` fixture.

## Fixtures (conftest.py)
- `client`: fresh Store + FastAPI app + AsyncClient (default PIN="test-master-pin")
- `make_client`: factory for custom data_dir or blank PIN
- `live_server`: real uvicorn server on free port, blank PIN

## Patterns

### Unit tests (pure functions, filesystem helpers)
```python
from cli.detect import _some_helper
def test_some_helper(tmp_path):
    (tmp_path / "sub/file.txt").write_text("data")
    assert _some_helper(str(tmp_path)) == expected
```
Use `tmp_path` for file/directory setup. Use `monkeypatch` to replace environment-dependent calls (Path.home, subprocess, os.path.exists).

### Integration tests (API routes)
```python
@pytest.mark.asyncio
async def test_route(client):
    r = await client.post("/route", json={"key": "val"}, headers=AUTH)
    assert r.status_code == 200
```

### CLI tests needing real sockets
```python
def test_cli_command(live_server):
    # Uses real HTTP client against live_server["host"]:live_server["port"]
```

## Test File Naming
`test_<module>_<feature>.py` — mirrors the module under test. One file per logical area.

## Reuse Strategy
Extend existing test files when the test touches code already covered there. Create new files only when the coverage area is distinct (e.g., scanner logic gets its own file since no existing test covers detect.py scanning).

## Console rows (#629)
Console/extra-folder API cases go in `test_devices.py` after the #539 tests and drive `PUT /games/{slug}/device` -> `GET /devices/{id}/consoles` via `_seed_console`. Migration cases build a minimal old-shaped table and call `schema._migrate(conn, from_version=N)` (see `test_v9_to_v10_migration`). GUI has no JS test runner: `make lint` plus a manual run.

## Electron main / renderer-only changes
No JS test runner and no main-process harness exist. Such changes are verified by both `tsc` projects, `make lint`, and a written manual script in the plan's Testing section (real files in a temp folder, a dev server, no mocks). Put server-visible behavior in a Python integration test whenever the logic can live server-side.
