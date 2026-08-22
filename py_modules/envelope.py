"""The uniform backend response envelope.

Every backend method returns ``{"ok": bool, "data": Any, "error": {...} | None}`` and
none of them raise. An unhandled exception in a Decky backend method surfaces as a
rejected promise in the frontend and, if it reaches a render path, can unmount the
Quick Access Menu -- which in Gaming Mode is genuinely hard to recover from.
"""

import asyncio
import functools

from validation import ValidationError

__all__ = ["ERROR_CODES", "err", "ok", "safe", "set_logger"]

#: Error codes are API. Every one of these is documented in the in-plugin
#: troubleshooting page, so new codes get added here deliberately, not ad hoc.
ERROR_CODES = frozenset(
    {
        "validation",  # a supplied value failed its rule
        "internal",  # unexpected fault; details are in the log, not the response
        "not_installed",  # the helper flatpak is missing
        "install_failed",  # helper install or update did not complete
        "already_running",  # start requested while the helper is up
        "not_running",  # an operation needs a running helper
        "socket_not_found",  # Gamescope EIS socket could not be discovered
        "backend_unavailable",  # the selected input backend cannot be used here
        "server_mode_unsupported",  # server mode requested in Gaming Mode
        "not_configured",  # required settings are missing
        "tls_setup_failed",  # certificate generation or trust store write failed
        "fingerprint_pending",  # blocked awaiting the user's trust decision
        "timeout",  # an operation exceeded its deadline
    }
)

_GENERIC_INTERNAL_MESSAGE = (
    "Something went wrong inside the plugin. Check the plugin log for details."
)

_logger = None


def set_logger(logger):
    """Install the logger used for tracebacks. Called once from main.py with decky.logger."""
    global _logger
    _logger = logger


def ok(data=None):
    return {"ok": True, "data": data, "error": None}


def err(code, message):
    if code not in ERROR_CODES:
        raise KeyError(f"undeclared error code: {code}")
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def _is_envelope(value):
    return isinstance(value, dict) and "ok" in value and "error" in value


def safe(method):
    """Guarantee a method returns an envelope and never raises.

    ``asyncio.CancelledError`` is deliberately re-raised: swallowing it would break
    task shutdown during ``_unload``.
    """

    @functools.wraps(method)
    async def wrapper(*args, **kwargs):
        try:
            result = await method(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except ValidationError as exc:
            return err("validation", f"{exc.field}: {exc.message}")
        except Exception:
            if _logger is not None:
                _logger.exception("Unhandled error in %s", method.__name__)
            # The real message may contain paths or hostnames; it stays in the log.
            return err("internal", _GENERIC_INTERNAL_MESSAGE)
        return result if _is_envelope(result) else ok(result)

    return wrapper
