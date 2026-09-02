"""Tests for the CLI launcher: process management, duplicate prevention,
stop/status, Python version detection, and dependency compatibility.
"""

import os
import sys

import pytest

from termux_mcp import cli, process


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Point process state files at a temp dir."""
    monkeypatch.setattr(process, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(process, "PID_FILE", str(tmp_path / "server.pid"))
    monkeypatch.setattr(process, "TUNNEL_PID_FILE", str(tmp_path / "tunnel.pid"))
    monkeypatch.setattr(process, "LOG_FILE", str(tmp_path / "server.log"))
    return tmp_path


# ── Python version detection ─────────────────────────────────────────────────

def test_python_version_detection():
    py = sys.version.split()[0]
    assert py >= "3.10"


def test_pkg_version_found():
    assert cli._pkg_version("mcp") is not None


def test_pkg_version_missing():
    assert cli._pkg_version("definitely-not-a-package-xyz-123") is None


# ── Duplicate process prevention ─────────────────────────────────────────────

def test_duplicate_process_prevention(isolated_state):
    # Simulate a running server by writing our own PID.
    process.write_pid(os.getpid())
    assert process.is_running() is True
    with pytest.raises(RuntimeError):
        process.start_server()
    process.clear_pid()
    assert process.is_running() is False


def test_start_server_writes_pid(isolated_state):
    # start_server spawns a real child; verify PID file + running state.
    pid = process.start_server()
    try:
        assert process.read_pid() == pid
        # Wait for the child to actually start executing (writes to the log).
        # On Windows under load, process creation can lag; stopping a child
        # that is still in loader initialization is racy.
        import time
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.tail_log(1):
                break
            time.sleep(0.2)
        assert process.is_running() is True
    finally:
        process.stop_server(timeout=10)
    assert process.is_running() is False


# ── stop / status ────────────────────────────────────────────────────────────

def test_stop_when_not_running(isolated_state):
    assert process.is_running() is False
    assert process.stop_server() is False


def test_stop_clears_stale_pid(isolated_state):
    process.write_pid(99999999)  # almost certainly dead
    assert process.is_running() is False
    process.stop_server()
    assert process.read_pid() is None


def test_tunnel_pid_roundtrip(isolated_state):
    process.write_tunnel_pid(12345)
    assert process.read_tunnel_pid() == 12345
    process.clear_tunnel_pid()
    assert process.read_tunnel_pid() is None


def test_port_open_closed(isolated_state):
    # A port we are not listening on.
    assert process.port_open(1, timeout=0.2) is False


# ── CLI command wiring ───────────────────────────────────────────────────────

def test_parse_args_default_runs_server():
    args = cli._parse_args([])
    assert args.command is None


def test_parse_args_start_tunnel_choices():
    for choice in ("auto", "pinggy", "cloudflare", "localhost-run", "none"):
        args = cli._parse_args(["start", "--tunnel", choice])
        assert args.command == "start"
        assert args.tunnel == choice


def test_parse_args_no_tunnel():
    args = cli._parse_args(["start", "--no-tunnel"])
    assert args.no_tunnel is True


def test_parse_args_token_rotate():
    args = cli._parse_args(["token", "--rotate"])
    assert args.command == "token"
    assert args.rotate is True


def test_doctor_runs_without_crashing(capsys):
    rc = cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "PASS" in out or "WARN" in out or "FAIL" in out
    assert rc in (0, 1)