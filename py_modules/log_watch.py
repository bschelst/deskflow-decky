"""Observation of the helper's output.

The plugin does not speak the Deskflow protocol itself, so the only channel through
which it learns that a peer presented a TLS fingerprint is the helper's log. This
module turns that log stream into the two facts the plugin needs: the peer fingerprint
awaiting a trust decision, and which input backend the helper actually resolved.

**Unverified against a real helper.** The patterns below are written from Deskflow's
Barrier heritage, not from observed output on hardware. PROJECT.md M2 must confirm the
exact wording `deskflow-core` emits and correct these patterns; until then, treat a
fingerprint prompt that never appears as a likely pattern mismatch rather than as a
server that presented nothing. The tests pin the behaviour, so changing a pattern means
changing a test alongside it.
"""

import re

__all__ = ["FingerprintWatcher", "extract_peer_fingerprint"]

SHA256_HEX_LENGTH = 64

# A fingerprint may appear bare, colon-separated, or with Deskflow's v2 prefix.
_FINGERPRINT_VALUE = re.compile(
    r"(?:v2:sha256:)?((?:[0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2}|[0-9a-fA-F]{64})"
)

# Words that mark the fingerprint as belonging to the other end of the connection.
_PEER_WORDS = ("server", "peer", "remote")
# ...and words that mark it as our own, which must never raise a trust prompt.
_OWN_WORDS = ("local", "our ", "ours")

_BACKEND_LINE = re.compile(r"ei backend:\s*(\w+)", re.IGNORECASE)


def extract_peer_fingerprint(line):
    """Return the peer's SHA-256 fingerprint as bare lowercase hex, or None."""
    if not isinstance(line, str) or not line:
        return None

    lowered = line.lower()
    if "fingerprint" not in lowered:
        return None
    if any(word in lowered for word in _OWN_WORDS):
        return None
    if not any(word in lowered for word in _PEER_WORDS):
        return None

    match = _FINGERPRINT_VALUE.search(line)
    if match is None:
        return None

    hexed = match.group(1).replace(":", "").lower()
    return hexed if len(hexed) == SHA256_HEX_LENGTH else None


class FingerprintWatcher:
    """Consumes helper output lines and reports interesting facts.

    Deliberately synchronous and side-effect-free apart from the callback, so it can be
    driven directly from the process drain loop and tested without any I/O.
    """

    def __init__(self, on_fingerprint=None, logger=None):
        self._on_fingerprint = on_fingerprint
        self._logger = logger
        self._last_reported = None
        self.reported_backend = None

    def reset(self):
        """Forget what was already reported. Called when a new connection begins."""
        self._last_reported = None

    def feed(self, line):
        backend = _BACKEND_LINE.search(line) if isinstance(line, str) else None
        if backend is not None:
            self.reported_backend = backend.group(1).lower()

        fingerprint = extract_peer_fingerprint(line)
        if fingerprint is None:
            return None

        # Deskflow logs the fingerprint on every reconnect. Re-prompting each time
        # would train the user to accept without reading, which is worse than not
        # prompting at all.
        if fingerprint == self._last_reported:
            return None
        self._last_reported = fingerprint

        if self._on_fingerprint is not None:
            try:
                self._on_fingerprint(fingerprint)
            except Exception:  # noqa: BLE001 - a broken observer must not stop the drain
                if self._logger is not None:
                    self._logger.warning("Fingerprint observer raised; continuing")
        return fingerprint
