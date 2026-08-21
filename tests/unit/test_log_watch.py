"""Extraction of peer TLS fingerprints from helper output.

This is the input side of the TOFU confirmation flow: without it the plugin can never
ask the user to trust a server, and docs/SECURITY.md §3 would be an unimplemented
promise.
"""

import pytest
from log_watch import FingerprintWatcher, extract_peer_fingerprint

FP = "ab" * 32
COLONISED = ":".join("ab" for _ in range(32))


@pytest.mark.parametrize(
    "line",
    [
        "WARNING: server fingerprint: v2:sha256:" + FP,
        "NOTE: server fingerprint (SHA256): " + COLONISED,
        "peer fingerprint " + FP,
        "remote fingerprint is v2:sha256:" + COLONISED.upper(),
        "The server's fingerprint: " + COLONISED,
    ],
)
def test_extracts_a_peer_fingerprint(line):
    assert extract_peer_fingerprint(line) == FP


@pytest.mark.parametrize(
    "line",
    [
        "local fingerprint: v2:sha256:" + FP,
        "our fingerprint is " + COLONISED,
        "client local fingerprint (SHA256): " + FP,
    ],
)
def test_ignores_our_own_fingerprint(line):
    # Prompting the user to trust the Deck's own certificate would be nonsense.
    assert extract_peer_fingerprint(line) is None


@pytest.mark.parametrize(
    "line",
    [
        "",
        "connected to server",
        "fingerprint",  # the word with no value
        "server fingerprint: short",
        "server fingerprint: " + "ab" * 20,  # SHA-1 length, not SHA-256
        "started on port 24800",
        "v2:sha256:" + FP,  # a hex run with no fingerprint context
    ],
)
def test_ignores_lines_without_a_usable_peer_fingerprint(line):
    assert extract_peer_fingerprint(line) is None


def test_handles_non_string_input():
    assert extract_peer_fingerprint(None) is None
    assert extract_peer_fingerprint(42) is None


def test_extraction_is_case_insensitive():
    assert extract_peer_fingerprint("SERVER FINGERPRINT: " + FP.upper()) == FP


# --------------------------------------------------------------------------- watcher


def test_watcher_reports_the_first_fingerprint_it_sees():
    seen = []
    watcher = FingerprintWatcher(on_fingerprint=seen.append)
    watcher.feed("connected to server")
    watcher.feed("server fingerprint: v2:sha256:" + FP)
    assert seen == [FP]


def test_watcher_does_not_report_the_same_fingerprint_twice():
    # Deskflow logs the fingerprint on every reconnect; re-prompting each time would
    # train the user to accept without reading.
    seen = []
    watcher = FingerprintWatcher(on_fingerprint=seen.append)
    watcher.feed("server fingerprint: " + FP)
    watcher.feed("server fingerprint: " + FP)
    assert len(seen) == 1


def test_watcher_reports_a_different_fingerprint():
    other = "cd" * 32
    seen = []
    watcher = FingerprintWatcher(on_fingerprint=seen.append)
    watcher.feed("server fingerprint: " + FP)
    watcher.feed("server fingerprint: " + other)
    assert seen == [FP, other]


def test_watcher_resets_between_connections():
    seen = []
    watcher = FingerprintWatcher(on_fingerprint=seen.append)
    watcher.feed("server fingerprint: " + FP)
    watcher.reset()
    watcher.feed("server fingerprint: " + FP)
    assert len(seen) == 2


def test_watcher_survives_a_failing_callback():
    def broken(_fingerprint):
        raise RuntimeError("boom")

    watcher = FingerprintWatcher(on_fingerprint=broken)
    watcher.feed("server fingerprint: " + FP)  # must not raise


def test_watcher_ignores_ordinary_output():
    seen = []
    watcher = FingerprintWatcher(on_fingerprint=seen.append)
    for line in ["starting", "ei backend: socket", "connected", ""]:
        watcher.feed(line)
    assert seen == []


def test_watcher_records_the_resolved_backend():
    # The patch logs this line; diagnostics reports what is actually in use.
    watcher = FingerprintWatcher()
    watcher.feed("INFO: ei backend: socket")
    assert watcher.reported_backend == "socket"


def test_watcher_backend_defaults_to_none():
    assert FingerprintWatcher().reported_backend is None
