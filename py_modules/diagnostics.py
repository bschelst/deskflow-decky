"""Redacted diagnostics.

Built from an allowlist, never by filtering a full dump: a filter only removes what
someone thought of, while an allowlist can only ever emit what was deliberately added.
"""

import re

__all__ = ["ALLOWED_FIELDS", "build_report", "redact_line"]

MAX_VALUE_LENGTH = 500

#: Everything the export may contain. Adding a field here is a deliberate decision to
#: publish it. See docs/SECURITY.md §6 for what must never appear.
ALLOWED_FIELDS = (
    "plugin_version",
    "helper_version",
    "decky_version",
    "steamos_version",
    "gamescope_version",
    "session_type",
    "mode",
    "requested_backend",
    "resolved_backend",
    "helper_reported_backend",
    "state",
    "last_error",
    "socket_found",
    "socket_source",
    "socket_owner_ok",
    "socket_mode",
    "uinput_present",
    "screen_size",
    "helper_installed",
    "helper_pid",
    "tls_enabled",
    "fingerprint_verified",
    "input_released_on_last_stop",
    "discovery_checked",
)

_UNKNOWN = "unknown"

_KEY_MARKER = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def redact_line(line):
    """Scrub a log line of anything that must never leave the device."""
    if not isinstance(line, str):
        line = "" if line is None else str(line)
    line = _KEY_MARKER.sub("[redacted key material]", line)
    # Keep a short prefix so two occurrences can still be correlated in a bug report,
    # without reproducing the whole value.
    line = _LONG_HEX.sub(lambda m: m.group(0)[:8] + "...[truncated]", line)
    return line


def _present(value):
    if value is None:
        return _UNKNOWN
    if isinstance(value, bool):
        return "true" if value else "false"
    text = redact_line(str(value))
    if len(text) > MAX_VALUE_LENGTH:
        text = text[:MAX_VALUE_LENGTH] + "...[truncated]"
    return text


def build_report(sources):
    """Assemble the export. ``sources`` may contain anything; only the allowlist is read."""
    supplied = sources if isinstance(sources, dict) else {}
    return {field: _present(supplied.get(field)) for field in ALLOWED_FIELDS}
