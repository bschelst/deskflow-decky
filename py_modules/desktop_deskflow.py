"""Syncing this Deck's identity into the stock Deskflow desktop app.

Both apps share the same ``Deskflow.conf`` INI schema: the desktop app (Flathub's
``org.deskflow.deskflow``) is a Qt GUI wrapper around the same ``deskflow-core`` engine
our own helper runs. Confirmed on hardware (2026-08-22) -- its config has the identical
``[client] remoteHost`` / ``[core] computerName`` keys ours writes.

Only those two are worth copying. TLS here is TOFU-per-client (see tls.py): the server
never authenticates a client by certificate, so each app keeping its own certificate is
correct, not a gap to close -- copying private key material across the sandbox boundary
would be pure downside for zero protocol benefit.
"""

import os
import re
import tempfile

__all__ = [
    "DESKTOP_APP_ID",
    "SyncError",
    "desktop_config_path",
    "is_desktop_app_running",
    "read_desktop_identity",
    "sync_desktop_identity",
]

#: Flathub's own app id. Never confuse with our APP_ID (helper_process.py) -- that
#: would collide with a user's existing install.
DESKTOP_APP_ID = "org.deskflow.deskflow"

_FORBIDDEN = ("\n", "\r", "\x00", "\x1b")
_REMOTE_HOST_LINE = re.compile(r"(?m)^remoteHost=.*$")
_COMPUTER_NAME_LINE = re.compile(r"(?m)^computerName=.*$")


class SyncError(Exception):
    pass


def _safe(field, value):
    text = str(value)
    for bad in _FORBIDDEN:
        if bad in text:
            raise SyncError(f"{field} contains an illegal character")
    return text


def desktop_config_path(home):
    return os.path.join(home, ".var", "app", DESKTOP_APP_ID, "config", "Deskflow", "Deskflow.conf")


def is_desktop_app_running(app_id=DESKTOP_APP_ID, proc_root="/proc"):
    """Whether the desktop app has a live process.

    Writing to its config while it holds an open QSettings handle is a race: Qt flushes
    its in-memory copy back to disk on exit, which would silently undo the sync.
    """
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return False

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, entry, "cmdline"), "rb") as handle:
                cmdline = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if app_id in cmdline:
            return True
    return False


def read_desktop_identity(path):
    """``{"remote_host", "computer_name"}`` from the desktop app's config, or None.

    None covers both "the app was never installed" and "installed but never run" (no
    config written yet) -- the caller does not need to tell those apart.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None

    remote = _REMOTE_HOST_LINE.search(text)
    name = _COMPUTER_NAME_LINE.search(text)
    if remote is None or name is None:
        return None

    return {
        "remote_host": remote.group(0).split("=", 1)[1],
        "computer_name": name.group(0).split("=", 1)[1],
    }


def sync_desktop_identity(path, server_host, client_name):
    """Rewrite only ``remoteHost=`` and ``computerName=`` in the desktop app's config.

    Surgical substitution, not a full INI re-serialize: the file also holds Qt-escaped
    keys (``screens\\1\\name=``) and a binary ``@Variant(...)`` blob
    (``clipboardSharingSize``) that round-tripping through a generic parser could
    mangle. Touching only the two lines we came to touch leaves everything else, and
    the file's own permissions, byte-for-byte.

    Raises SyncError if the file is missing or does not already have both keys --
    appending a key Qt never wrote itself risks a shape QSettings has never seen.
    """
    host = _safe("server_host", server_host)
    name = _safe("client_name", client_name)

    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        mode = os.stat(path).st_mode & 0o777
    except OSError as exc:
        raise SyncError(f"could not read {path}: {exc}") from exc

    if _REMOTE_HOST_LINE.search(text) is None or _COMPUTER_NAME_LINE.search(text) is None:
        raise SyncError(
            "the desktop app's config is missing the expected remoteHost/computerName "
            "keys -- run it once first so it writes its own config"
        )

    text = _REMOTE_HOST_LINE.sub(f"remoteHost={host}", text, count=1)
    text = _COMPUTER_NAME_LINE.sub(f"computerName={name}", text, count=1)

    directory = os.path.dirname(path)
    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".Deskflow.conf.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    return path
