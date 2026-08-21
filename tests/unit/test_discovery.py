"""Discovery of Gamescope's EIS socket.

Gamescope creates `<wayland-display>-ei` in $XDG_RUNTIME_DIR and exports LIBEI_SOCKET
to its children. A Decky-launched process does not inherit that, so we look for it --
carefully, and never by walking the filesystem.
"""

import os
import socket

import pytest
from discovery import DiscoveryResult, discover_socket


@pytest.fixture
def runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("LIBEI_SOCKET", raising=False)
    return tmp_path


def make_socket(path):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    return server


def test_finds_the_gamescope_socket(runtime_dir):
    sock = make_socket(runtime_dir / "gamescope-0-ei")
    try:
        result = discover_socket({})
        assert result.found
        assert result.path == str(runtime_dir / "gamescope-0-ei")
        assert result.source == "runtime-dir-scan"
    finally:
        sock.close()


def test_explicit_override_wins_over_scanning(runtime_dir):
    scanned = make_socket(runtime_dir / "gamescope-0-ei")
    chosen = make_socket(runtime_dir / "chosen-ei")
    try:
        result = discover_socket({"socket_path_override": str(runtime_dir / "chosen-ei")})
        assert result.path == str(runtime_dir / "chosen-ei")
        assert result.source == "override"
    finally:
        scanned.close()
        chosen.close()


def test_override_that_does_not_exist_fails_loudly(runtime_dir):
    make_socket(runtime_dir / "gamescope-0-ei")
    result = discover_socket({"socket_path_override": str(runtime_dir / "missing-ei")})
    # An explicit choice is never silently replaced by a guess.
    assert not result.found
    assert result.source == "override"


def test_libei_socket_env_is_used_when_present(runtime_dir, monkeypatch):
    sock = make_socket(runtime_dir / "inherited-ei")
    monkeypatch.setenv("LIBEI_SOCKET", "inherited-ei")
    try:
        result = discover_socket({})
        assert result.found
        assert result.source == "libei-socket-env"
    finally:
        sock.close()


def test_absolute_libei_socket_env_is_honoured(runtime_dir, monkeypatch):
    sock = make_socket(runtime_dir / "abs-ei")
    monkeypatch.setenv("LIBEI_SOCKET", str(runtime_dir / "abs-ei"))
    try:
        assert discover_socket({}).found
    finally:
        sock.close()


def test_relay_file_is_consulted(runtime_dir, tmp_path):
    sock = make_socket(runtime_dir / "relayed-ei")
    relay = tmp_path / "relay.txt"
    relay.write_text(str(runtime_dir / "relayed-ei") + "\n")
    try:
        result = discover_socket({}, relay_path=str(relay))
        assert result.found
        assert result.source == "relay-file"
    finally:
        sock.close()


def test_relay_file_pointing_outside_the_runtime_dir_is_rejected(runtime_dir, tmp_path):
    outside = tmp_path.parent / "elsewhere-ei"
    relay = tmp_path / "relay.txt"
    relay.write_text(str(outside))
    result = discover_socket({}, relay_path=str(relay))
    assert not result.found


def test_a_regular_file_is_not_mistaken_for_a_socket(runtime_dir):
    (runtime_dir / "decoy-ei").write_text("not a socket")
    result = discover_socket({})
    assert not result.found


def test_search_is_not_recursive(runtime_dir):
    # A filesystem walk is both slow and a way to touch things we have no business
    # touching; discovery is deliberately depth-1.
    nested = runtime_dir / "sub"
    nested.mkdir()
    sock = make_socket(nested / "gamescope-0-ei")
    try:
        assert not discover_socket({}).found
    finally:
        sock.close()


def test_failure_reports_every_location_checked(runtime_dir):
    result = discover_socket({})
    assert not result.found
    assert result.checked, "a failure with no detail is not actionable"
    assert all(isinstance(entry, str) for entry in result.checked)


def test_failure_report_mentions_the_runtime_directory(runtime_dir):
    result = discover_socket({})
    assert any(str(runtime_dir) in entry for entry in result.checked)


def test_result_is_serialisable(runtime_dir):
    sock = make_socket(runtime_dir / "gamescope-0-ei")
    try:
        payload = discover_socket({}).as_dict()
        assert payload["found"] is True
        assert set(payload) == {"found", "path", "source", "checked"}
    finally:
        sock.close()


def test_missing_runtime_dir_is_handled(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.delenv("LIBEI_SOCKET", raising=False)
    result = discover_socket({})
    assert not result.found
    assert result.checked


def test_prefers_gamescope_named_sockets_over_other_ei_sockets(runtime_dir):
    other = make_socket(runtime_dir / "aaa-other-ei")
    game = make_socket(runtime_dir / "gamescope-0-ei")
    try:
        # Sorting alone would pick "aaa-other-ei"; the gamescope socket is the target.
        assert discover_socket({}).path == str(runtime_dir / "gamescope-0-ei")
    finally:
        other.close()
        game.close()


def test_symlink_escaping_the_runtime_dir_is_rejected(runtime_dir, tmp_path):
    real_dir = tmp_path.parent / "outside"
    real_dir.mkdir(exist_ok=True)
    sock = make_socket(real_dir / "real-ei")
    os.symlink(str(real_dir / "real-ei"), str(runtime_dir / "sneaky-ei"))
    try:
        assert not discover_socket({}).found
    finally:
        sock.close()


def test_isinstance_of_discovery_result(runtime_dir):
    assert isinstance(discover_socket({}), DiscoveryResult)
