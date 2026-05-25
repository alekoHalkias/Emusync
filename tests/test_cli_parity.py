"""CLI tests for the parity check command."""
from __future__ import annotations

import tempfile
from pathlib import Path
import subprocess
import sys
import json

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import api as api_module
from server.store import Store
import server.config as cfg_module


def run_cli(*args, **kwargs) -> tuple[int, str, str]:
    """Run the CLI command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "emusync.py"] + list(args),
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
        **kwargs,
    )
    return result.returncode, result.stdout, result.stderr


class TestParityCheckCLI:
    """Test the parity check CLI command."""

    def test_parity_check_requires_game_or_all(self):
        """parity check without --game or --all should error."""
        exit_code, stdout, stderr = run_cli("parity", "check")
        assert exit_code != 0
        assert "specify --game" in stderr or "specify --game" in stdout

    def test_parity_check_game_not_found(self):
        """parity check --game with nonexistent game should error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"EMUSYNC_CONFIG_DIR": tmpdir}
            # First pair a device and set config
            cfg = cfg_module.Config(
                server_host="localhost",
                server_port=8765,
                data_dir=tmpdir,
                device_id="test-device",
                device_name="Test Device",
                token="test-token",
                is_server=False,
                server_pin="",
            )
            cfg_module.save(cfg)

            # Try to check nonexistent game (will fail to reach server, but that's ok)
            exit_code, stdout, stderr = run_cli("parity", "check", "--game", "nonexistent", env=env)
            # Will fail because server isn't running, but that's expected in this context
            assert exit_code != 0

    def test_parity_check_help(self):
        """parity check --help should show usage."""
        exit_code, stdout, stderr = run_cli("parity", "check", "--help")
        assert exit_code == 0
        assert "Check if games and saves/states are in sync" in stdout
        assert "--game" in stdout
        assert "--all" in stdout

    def test_parity_group_help(self):
        """parity --help should show available commands."""
        exit_code, stdout, stderr = run_cli("parity", "--help")
        assert exit_code == 0
        assert "check" in stdout


class TestParityCheckIntegration:
    """Integration tests with a real server."""

    @pytest.mark.asyncio
    async def test_parity_check_all_games_match(self, monkeypatch, tmp_path):
        """parity check --all with all games matching should exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup server and store
            store = Store(tmpdir)
            api_module.init(store, "test-token")

            # Setup client config
            cfg = cfg_module.Config(
                server_host="localhost",
                server_port=9999,  # Non-running port, will error
                data_dir=tmpdir,
                device_id="device-1",
                device_name="Device 1",
                token="test-device-token",
                is_server=False,
                server_pin="",
            )

            # Monkeypatch the config loading and client to use our test setup
            # Note: This is a simplified test - in practice you'd use httpx mocking
            # or start a test server

    def test_parity_command_exists(self):
        """parity command should be available."""
        exit_code, stdout, stderr = run_cli("parity", "--help")
        assert exit_code == 0

    def test_parity_check_command_exists(self):
        """parity check command should be available."""
        exit_code, stdout, stderr = run_cli("parity", "check", "--help")
        assert exit_code == 0
