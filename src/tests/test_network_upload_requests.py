"""Network-drive upload requests between devices (#660): request validation,
share_id in network-source, upload_to_network, daemon and CLI fulfilment.
Real SQLite and real uvicorn (live_server); the share is a tmp_path folder."""
from __future__ import annotations

import os

from click.testing import CliRunner

import server.config as cfg_module
from cli import netrom
from cli.rom import fulfill_network_upload
from cli.transfer import _handle_network_upload
from server.sync_client import GameDeviceConfig, SyncClient
from tests.test_manual_transfer_cli import _device_client, _write_cfg

SHARE_ID = "share-uuid-1"


def _owner(live_server, tmp_path, *, marker=SHARE_ID, registered=SHARE_ID, rom_name="g.gba"):
    """Device A holds g.gba locally; its GBA console points at a tmp share folder."""
    a = _device_client(live_server, "dev-a", "DeviceA")
    a.add_game("Metroid", "GBA")
    local = tmp_path / "local" / "GBA"
    share = tmp_path / "share" / "GBA"
    local.mkdir(parents=True)
    share.mkdir(parents=True)
    rom = local / rom_name
    rom.write_bytes(b"ROM" * 100)
    if marker is not None:
        (share / netrom.SHARE_MARKER).write_text(marker)
    a.set_game_device("metroid", GameDeviceConfig(
        rom_path=str(rom), launch_command=f"emu {rom}", rom_source="local",
        device_network_folder=str(share), device_local_folder=str(local), save_path="/s/g.srm",
    ))
    row = next(c for c in a.get_device_consoles("dev-a") if c["console_name"] == "GBA")
    body = {k: row[k] for k in ("device_game_folder", "device_save_folder", "device_state_folder",
                                "device_emulator", "device_network_folder", "device_local_folder")}
    body["network_share_id"] = registered
    a._client.put(a._url(f"/devices/dev-a/consoles/{row['id']}"), json=body, timeout=10).raise_for_status()
    return a, rom, share


def _request(live_server):
    b = _device_client(live_server, "dev-b", "DeviceB")
    return b, b.create_pull_request("metroid", "dev-a", "", kind="network-upload")


def test_request_lifecycle_and_dedupe(live_server, tmp_path):
    a, _, _ = _owner(live_server, tmp_path)
    b, res = _request(live_server)
    assert res["status"] == "pending"
    assert b.create_pull_request("metroid", "dev-a", "", kind="network-upload")["pull_request_id"] == res["pull_request_id"]
    pending = a.list_pending_pull_requests()
    assert [(p["id"], p["kind"]) for p in pending] == [(res["pull_request_id"], "network-upload")]
    out = b._client.get(b._url("/rom-pull-requests/outgoing")).json()
    assert out[0]["status"] == "pending" and out[0]["slug"] == "metroid"


def test_request_rejected_without_local_rom(live_server, tmp_path):
    _device_client(live_server, "dev-a", "DeviceA").add_game("Metroid", "GBA")
    b = _device_client(live_server, "dev-b", "DeviceB")
    r = b._client.post(b._url("/games/metroid/rom-pull-request"),
                       json={"from_device_id": "dev-a", "kind": "network-upload"})
    assert r.status_code == 400


def test_request_rejected_when_already_on_network(live_server, tmp_path):
    a, _, _ = _owner(live_server, tmp_path)
    netrom.upload_to_network(a, "dev-a", "metroid")
    b = _device_client(live_server, "dev-b", "DeviceB")
    r = b._client.post(b._url("/games/metroid/rom-pull-request"),
                       json={"from_device_id": "dev-a", "kind": "network-upload"})
    assert r.status_code == 409


def test_upload_flips_row_and_exposes_share_id(live_server, tmp_path):
    a, rom, share = _owner(live_server, tmp_path)
    master = netrom.upload_to_network(a, "dev-a", "metroid")
    assert master == str(share / "g.gba") and os.path.isfile(master) and rom.exists()
    gd = a.get_game_device("metroid")
    assert (gd.rom_source, gd.rom_path, gd.local_rom_path, gd.rom_rel_path) == ("network", master, str(rom), "g.gba")
    assert gd.rom_sha256 and str(rom) not in gd.launch_command
    src = a._client.get(a._url("/games/metroid/network-source")).json()
    assert src["share_id"] == SHARE_ID and src["rom_rel_path"] == "g.gba"


def test_upload_refuses_marker_mismatch_or_missing(live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path, marker="other-share")
    try:
        netrom.upload_to_network(a, "dev-a", "metroid")
        assert False, "expected LocalizeError"
    except netrom.LocalizeError:
        pass
    assert not (share / "g.gba").exists()
    (share / netrom.SHARE_MARKER).unlink()
    try:
        netrom.upload_to_network(a, "dev-a", "metroid")
        assert False, "expected LocalizeError"
    except netrom.LocalizeError:
        pass


def test_upload_never_overwrites_existing_master(live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path)
    (share / "g.gba").write_bytes(b"existing master")
    netrom.upload_to_network(a, "dev-a", "metroid")
    assert (share / "g.gba").read_bytes() == b"existing master"
    assert a.get_game_device("metroid").rom_source == "network"


def test_rom_outside_local_folder_uses_basename(live_server, tmp_path):
    a, rom, share = _owner(live_server, tmp_path)
    elsewhere = tmp_path / "elsewhere" / "x.gba"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"X")
    gd = a.get_game_device("metroid")
    gd.rom_path, gd.launch_command = str(elsewhere), ""
    a.set_game_device("metroid", gd)
    assert netrom.upload_to_network(a, "dev-a", "metroid") == str(share / "x.gba")


def _cfg(monkeypatch, tmp_path, live_server, max_mb):
    cfg = _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")
    cfg.network_upload_auto_max_mb = max_mb
    cfg_module.save(cfg)


def test_daemon_fulfills_small_request(monkeypatch, live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path)
    _cfg(monkeypatch, tmp_path, live_server, 512)
    b, res = _request(live_server)
    assert _handle_network_upload(a, res["pull_request_id"], "metroid", "Metroid", log=lambda m: None)
    assert (share / "g.gba").exists()
    assert b._client.get(b._url("/rom-pull-requests/outgoing")).json()[0]["status"] == "fulfilled"


def test_daemon_leaves_oversize_request_pending(monkeypatch, live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path)
    _cfg(monkeypatch, tmp_path, live_server, 0)
    b, res = _request(live_server)
    assert not _handle_network_upload(a, res["pull_request_id"], "metroid", "Metroid", log=lambda m: None)
    assert not (share / "g.gba").exists()
    assert b._client.get(b._url("/rom-pull-requests/outgoing")).json()[0]["status"] == "pending"


def test_daemon_leaves_request_pending_when_share_unmounted(monkeypatch, live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path)
    (share / netrom.SHARE_MARKER).unlink()
    _cfg(monkeypatch, tmp_path, live_server, 512)
    b, res = _request(live_server)
    assert not _handle_network_upload(a, res["pull_request_id"], "metroid", "Metroid", log=lambda m: None)
    assert b._client.get(b._url("/rom-pull-requests/outgoing")).json()[0]["status"] == "pending"


def test_daemon_marks_failed_on_marker_mismatch(monkeypatch, live_server, tmp_path):
    a, _, _ = _owner(live_server, tmp_path, marker="other-share")
    _cfg(monkeypatch, tmp_path, live_server, 512)
    b, res = _request(live_server)
    assert not _handle_network_upload(a, res["pull_request_id"], "metroid", "Metroid", log=lambda m: None)
    assert b._client.get(b._url("/rom-pull-requests/outgoing")).json()[0]["status"] == "failed"


def test_cli_approve_and_decline(monkeypatch, live_server, tmp_path):
    a, _, share = _owner(live_server, tmp_path)
    _cfg(monkeypatch, tmp_path, live_server, 0)
    _, res = _request(live_server)
    r = CliRunner().invoke(fulfill_network_upload, [res["pull_request_id"]])
    assert r.exit_code == 0, r.output
    assert (share / "g.gba").exists()


def test_cli_decline_marks_failed(monkeypatch, live_server, tmp_path):
    _owner(live_server, tmp_path)
    _cfg(monkeypatch, tmp_path, live_server, 0)
    b, res = _request(live_server)
    r = CliRunner().invoke(fulfill_network_upload, [res["pull_request_id"], "--decline"])
    assert r.exit_code == 0, r.output
    assert b._client.get(b._url("/rom-pull-requests/outgoing")).json()[0]["status"] == "failed"
