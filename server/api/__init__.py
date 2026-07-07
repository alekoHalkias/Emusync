"""EmuSync HTTP API.

Split into per-domain APIRouter modules (issue #224). `_core` owns the FastAPI
`app`, shared state, `_auth`, and `init()`; the routers below contribute the
routes. Public surface is unchanged: `from server import api` still exposes
`api.app` and `api.init`.
"""
from __future__ import annotations

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

__all__ = ["app", "init"]
