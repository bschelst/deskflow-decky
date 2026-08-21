"""Settings validation.

Pure functions with no ``decky`` import so they can be unit-tested off-device.

Two rules govern everything here, both from docs/SECURITY.md §2:

* Whitelist, never blacklist. A value is accepted only when it matches an explicit
  positive rule.
* Never coerce. A wrong type is a validation failure, not a cast -- silent coercion
  hides frontend bugs and makes the backend contract untestable.

Nothing in this module mutates its arguments; validated results are new objects.
"""

import ipaddress
import math
import os
import re
import string

__all__ = [
    "DEFAULTS",
    "FIELDS",
    "ValidationError",
    "sanitize_loaded",
    "validate_field",
    "validate_patch",
]

MAX_HOSTNAME_LENGTH = 253
MAX_LABEL_LENGTH = 63
MIN_PORT = 1
MAX_PORT = 65535
MIN_BACKOFF_S = 1
MAX_BACKOFF_S = 300
MIN_SENSITIVITY = 0.25
MAX_SENSITIVITY = 4.0
MAX_CLIENT_NAME_LENGTH = 63

# \Z, not $: in Python `$` also matches immediately before a trailing newline, so
# `^[A-Za-z0-9._-]+$` accepts "deck\n" -- which would inject a line break into the
# generated Deskflow INI file.
_LABEL_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\Z")
_CLIENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,%d}\Z" % (MAX_CLIENT_NAME_LENGTH - 1))
_SAFE_TEXT = frozenset(string.printable) - frozenset(string.whitespace) | {" "}


class ValidationError(Exception):
    """Raised when a value fails its rule.

    ``message`` is safe to show a user: it names the field and the rule, never the
    rejected value, which may be private (a hostname) or hostile (an injection attempt).
    """

    def __init__(self, field, message):
        super().__init__("{0}: {1}".format(field, message))
        self.field = field
        self.message = message


# --------------------------------------------------------------------------- primitives


def _is_bool(value):
    return isinstance(value, bool)


def _is_int(value):
    # bool is a subclass of int; accepting True as a port number would be absurd.
    return isinstance(value, int) and not _is_bool(value)


def _has_control_characters(text):
    return any(ch not in _SAFE_TEXT for ch in text)


def _boolean(field, value):
    if not _is_bool(value):
        raise ValidationError(field, "must be true or false")
    return value


def _bounded_int(field, value, low, high):
    if not _is_int(value):
        raise ValidationError(field, "must be a whole number")
    if not low <= value <= high:
        raise ValidationError(field, "must be between {0} and {1}".format(low, high))
    return value


def _bounded_float(field, value, low, high):
    if _is_bool(value) or not isinstance(value, (int, float)):
        raise ValidationError(field, "must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(field, "must be a finite number")
    if not low <= number <= high:
        raise ValidationError(field, "must be between {0} and {1}".format(low, high))
    return number


def _one_of(field, value, members):
    if not isinstance(value, str) or _is_bool(value):
        raise ValidationError(field, "must be text")
    if value not in members:
        raise ValidationError(field, "must be one of: {0}".format(", ".join(sorted(members))))
    return value


def _enum(members):
    frozen = frozenset(members)

    def validator(field, value):
        return _one_of(field, value, frozen)

    return validator


# --------------------------------------------------------------------------- host names


def _looks_numeric(host):
    return all(ch in "0123456789." for ch in host)


def _valid_hostname(host):
    if len(host) > MAX_HOSTNAME_LENGTH:
        return False
    labels = host.split(".")
    if any(len(label) < 1 or len(label) > MAX_LABEL_LENGTH for label in labels):
        return False
    return all(_LABEL_RE.match(label) for label in labels)


def _server_host(field, value):
    if not isinstance(value, str) or _is_bool(value):
        raise ValidationError(field, "must be text")
    # Empty means "not configured yet"; the cross-field rules decide whether that is
    # acceptable in the current mode.
    if value == "":
        return value
    if value != value.strip() or _has_control_characters(value) or " " in value:
        raise ValidationError(field, "must not contain spaces or control characters")

    if ":" in value and not _looks_numeric(value):
        # Could be IPv6, or someone pasting "host:port".
        try:
            ipaddress.IPv6Address(value)
        except ValueError:
            raise ValidationError(
                field, "must be a hostname or IP address, without a port"
            ) from None
        return value

    if _looks_numeric(value):
        # Anything that could only be an IPv4 attempt must actually parse as one,
        # so "256.1.1.1" and "1.1.1" are rejected rather than read as hostnames.
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            raise ValidationError(field, "is not a valid IP address") from None
        return value

    if not _valid_hostname(value):
        raise ValidationError(field, "is not a valid hostname or IP address")
    return value


def _client_name(field, value):
    if not isinstance(value, str) or _is_bool(value):
        raise ValidationError(field, "must be text")
    if not _CLIENT_NAME_RE.match(value):
        raise ValidationError(
            field,
            "must start with a letter or digit and contain only letters, digits, "
            "dots, hyphens and underscores (max {0} characters)".format(MAX_CLIENT_NAME_LENGTH),
        )
    return value


# --------------------------------------------------------------------------- paths


def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR") or "/run/user/{0}".format(os.getuid())


def _socket_path_override(field, value):
    if not isinstance(value, str) or _is_bool(value):
        raise ValidationError(field, "must be text")
    if value == "":
        return value
    if _has_control_characters(value) or value != value.strip():
        raise ValidationError(field, "must not contain control characters")
    if not os.path.isabs(value):
        raise ValidationError(field, "must be an absolute path")
    if ".." in value.split(os.sep):
        raise ValidationError(field, "must not contain '..' path segments")

    root = os.path.realpath(_runtime_dir())
    resolved = os.path.realpath(value)
    # Re-check containment *after* resolution; that is what catches symlink escapes.
    if not (resolved == root or resolved.startswith(root + os.sep)):
        raise ValidationError(field, "must be inside the session runtime directory")
    return value


# --------------------------------------------------------------------------- schema


def _port(field, value):
    return _bounded_int(field, value, MIN_PORT, MAX_PORT)


def _backoff(field, value):
    return _bounded_int(field, value, MIN_BACKOFF_S, MAX_BACKOFF_S)


def _sensitivity(field, value):
    return _bounded_float(field, value, MIN_SENSITIVITY, MAX_SENSITIVITY)


MODES = ("client", "server")
INPUT_BACKENDS = ("auto", "gamescope-libei", "x11-xtest", "uinput")
ACTIVATION_MODES = ("manual", "always")
LOG_LEVELS = ("error", "warn", "info", "debug")

#: field name -> (default, validator). The single source of truth for the schema.
FIELDS = {
    "mode": ("client", _enum(MODES)),
    "server_host": ("", _server_host),
    "server_port": (24800, _port),
    "client_name": ("steamdeck", _client_name),
    "tls_enabled": (True, _boolean),
    "check_peer_fingerprints": (True, _boolean),
    "input_backend": ("auto", _enum(INPUT_BACKENDS)),
    "socket_path_override": ("", _socket_path_override),
    "autostart_gaming_mode": (False, _boolean),
    "reconnect_enabled": (True, _boolean),
    "reconnect_max_backoff_s": (30, _backoff),
    "pointer_sensitivity": (1.0, _sensitivity),
    "activation_mode": ("manual", _enum(ACTIVATION_MODES)),
    "log_level": ("info", _enum(LOG_LEVELS)),
}

DEFAULTS = {name: default for name, (default, _) in FIELDS.items()}


def validate_field(name, value):
    """Validate one field. Returns the normalised value, raises ValidationError."""
    try:
        _, validator = FIELDS[name]
    except KeyError:
        raise ValidationError(name, "is not a known setting") from None
    return validator(name, value)


# --------------------------------------------------------------------------- cross-field

# Each rule declares the fields it governs. A rule is enforced only when the patch
# touches at least one of them, so an unconfigured install (client mode, no host yet)
# is allowed to sit at rest without every unrelated write failing.


def _rule_tls_requires_verification(settings):
    if settings["tls_enabled"] and not settings["check_peer_fingerprints"]:
        return (
            "check_peer_fingerprints",
            "cannot be turned off while TLS is on: encryption without "
            "verification offers no protection against interception",
        )
    return None


def _rule_client_needs_host(settings):
    if settings["mode"] == "client" and settings["server_host"] == "":
        return ("server_host", "is required when this Deck runs as a client")
    return None


_CROSS_FIELD_RULES = (
    (frozenset({"tls_enabled", "check_peer_fingerprints"}), _rule_tls_requires_verification),
    (frozenset({"mode", "server_host"}), _rule_client_needs_host),
)


def _check_cross_field(settings, touched):
    for governed, rule in _CROSS_FIELD_RULES:
        if not governed & touched:
            continue
        failure = rule(settings)
        if failure is not None:
            raise ValidationError(*failure)


def validate_patch(patch, current):
    """Apply a partial update to ``current`` and return a new, fully valid settings dict.

    All-or-nothing: if any field fails, ``current`` is left untouched and nothing is
    applied. ``current`` is never mutated.
    """
    if not isinstance(patch, dict):
        raise ValidationError("settings", "must be an object")

    unknown = set(patch) - set(FIELDS)
    if unknown:
        raise ValidationError(sorted(unknown)[0], "is not a known setting")

    updated = dict(current)
    for name, value in patch.items():
        updated[name] = validate_field(name, value)

    # Fill any gap left by an incomplete `current` so rules see a complete picture.
    for name, default in DEFAULTS.items():
        updated.setdefault(name, default)

    _check_cross_field(updated, frozenset(patch))
    return updated


# --------------------------------------------------------------------------- loading


def sanitize_loaded(raw):
    """Turn whatever is on disk into usable settings. Never raises.

    Returns ``(settings, warnings)``. A hand-edited or truncated file degrades to
    defaults with warnings rather than taking the plugin down on startup.
    """
    warnings = []

    if not isinstance(raw, dict):
        return dict(DEFAULTS), ["Settings file was not an object; using defaults."]

    settings = {}
    for name, (default, validator) in FIELDS.items():
        if name not in raw:
            settings[name] = default
            continue
        try:
            settings[name] = validator(name, raw[name])
        except ValidationError as exc:
            settings[name] = default
            warnings.append(
                "Setting '{0}' was invalid ({1}); reset to its default.".format(name, exc.message)
            )

    for name in sorted(set(raw) - set(FIELDS)):
        warnings.append("Unknown setting '{0}' was ignored.".format(name))

    # Repair cross-field violations rather than refusing to start. Repairs fail safe:
    # turning verification back on, never turning security off to make a file load.
    if settings["tls_enabled"] and not settings["check_peer_fingerprints"]:
        settings["check_peer_fingerprints"] = True
        warnings.append(
            "Fingerprint verification was disabled while TLS was on; it has been re-enabled."
        )

    if settings["mode"] == "client" and settings["server_host"] == "":
        # Not an error: this is simply an install that has not been configured yet.
        warnings.append("No server address is configured; the helper cannot start until one is set.")

    return settings, warnings
