"""ROM transfers (push side) and ROM pull requests (pull side)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from server.store.models import RomPullRequest, RomTransfer


class TransferMixin:
    """Operates on `self._conn`; mixed into Store."""

    # ── rom_transfers ─────────────────────────────────────────────────────────

    def create_rom_transfer(
        self,
        id: str,
        slug: str,
        from_device_id: str,
        to_device_id: str,
        destination_path: str,
        staged_file: str,
    ) -> RomTransfer:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO rom_transfers
               (id, slug, from_device_id, to_device_id, destination_path, staged_file, status, queued_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (id, slug, from_device_id, to_device_id, destination_path, staged_file, now),
        )
        self._conn.commit()
        return RomTransfer(
            id=id, slug=slug, from_device_id=from_device_id, to_device_id=to_device_id,
            destination_path=destination_path, staged_file=staged_file,
            status="pending", queued_at=now,
        )

    def get_rom_transfer(self, transfer_id: str) -> Optional[RomTransfer]:
        row = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      staged_file, status, queued_at, completed_at
               FROM rom_transfers WHERE id = ?""",
            (transfer_id,),
        ).fetchone()
        return RomTransfer(**dict(row)) if row else None

    def list_pending_transfers_for_device(self, device_id: str) -> list[RomTransfer]:
        rows = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      staged_file, status, queued_at, completed_at
               FROM rom_transfers WHERE to_device_id = ? AND status = 'pending'
               ORDER BY queued_at""",
            (device_id,),
        ).fetchall()
        return [RomTransfer(**dict(r)) for r in rows]

    def update_transfer_status(self, transfer_id: str, status: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat() if status in ("completed", "failed") else None
        self._conn.execute(
            "UPDATE rom_transfers SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, transfer_id),
        )
        self._conn.commit()

    # ── rom pull requests ─────────────────────────────────────────────────────

    def create_pull_request(
        self,
        id: str,
        slug: str,
        from_device_id: str,
        to_device_id: str,
        destination_path: str,
    ) -> RomPullRequest:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO rom_pull_requests
               (id, slug, from_device_id, to_device_id, destination_path, status, requested_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (id, slug, from_device_id, to_device_id, destination_path, now),
        )
        self._conn.commit()
        return RomPullRequest(
            id=id, slug=slug, from_device_id=from_device_id, to_device_id=to_device_id,
            destination_path=destination_path, status="pending", requested_at=now,
        )

    def get_pull_request(self, pull_request_id: str) -> Optional[RomPullRequest]:
        row = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      status, requested_at, fulfilled_at
               FROM rom_pull_requests WHERE id = ?""",
            (pull_request_id,),
        ).fetchone()
        return RomPullRequest(**dict(row)) if row else None

    def list_pending_pull_requests_for_device(self, device_id: str) -> list[RomPullRequest]:
        """Return pending pull requests where this device is the source (from_device_id)."""
        rows = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      status, requested_at, fulfilled_at
               FROM rom_pull_requests WHERE from_device_id = ? AND status = 'pending'
               ORDER BY requested_at""",
            (device_id,),
        ).fetchall()
        return [RomPullRequest(**dict(r)) for r in rows]

    def update_pull_request_status(self, pull_request_id: str, status: str) -> None:
        fulfilled_at = datetime.now(timezone.utc).isoformat() if status in ("fulfilled", "failed") else None
        self._conn.execute(
            "UPDATE rom_pull_requests SET status = ?, fulfilled_at = ? WHERE id = ?",
            (status, fulfilled_at, pull_request_id),
        )
        self._conn.commit()
