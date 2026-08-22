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
import shutil
import tempfile

__all__ = [
    "DESKTOP_APP_ID",
    "DESKTOP_DESKTOP_FILE_NAME",
    "SYSTEM_EXPORT_DIR",
    "SyncError",
    "autostart_path",
    "bootstrap_client_config",
    "desktop_client_config_needs_bootstrap",
    "desktop_config_path",
    "find_exported_desktop_file",
    "is_desktop_app_running",
    "read_desktop_identity",
    "sync_desktop_identity",
    "write_autostart_entry",
]

#: Flathub's own app id. Never confuse with our APP_ID (helper_process.py) -- that
#: would collide with a user's existing install.
DESKTOP_APP_ID = "org.deskflow.deskflow"
DESKTOP_DESKTOP_FILE_NAME = f"{DESKTOP_APP_ID}.desktop"

_FORBIDDEN = ("\n", "\r", "\x00", "\x1b")
_REMOTE_HOST_LINE = re.compile(r"(?m)^remoteHost=.*$")
_COMPUTER_NAME_LINE = re.compile(r"(?m)^computerName=.*$")
_CORE_MODE_LINE = re.compile(r"(?m)^coreMode=.*$")

#: Deskflow's own core mode enum (matches CORE_MODE_CLIENT in deskflow_config.py).
_CORE_MODE_CLIENT = 1


class SyncError(Exception):
    pass


def _safe(field, value):
    text = str(value)
    for bad in _FORBIDDEN:
        if bad in text:
            raise SyncError(f"{field} contains an illegal character")
    return text


def _atomic_rewrite(path, text, mode):
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

    return _atomic_rewrite(path, text, mode)


def desktop_client_config_needs_bootstrap(path):
    """True if a first launch wrote ``[core]`` but the app has never been configured.

    A plain launch of a fresh install writes computerName and a default coreMode=0, but
    no ``[client]`` section at all -- that only appears once a human completes
    Deskflow's own setup wizard (confirmed on hardware, 2026-08-22). This is the signal
    that bootstrap_client_config is needed instead of sync_desktop_identity.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    return _COMPUTER_NAME_LINE.search(text) is not None and "[client]" not in text


def bootstrap_client_config(path, server_host, client_name):
    """Add a ``[client]`` section to a freshly-launched, not-yet-configured config.

    Only for that specific gap: a first launch never asks the user anything, so no
    wizard ever runs to write ``[client] remoteHost=`` on its own. This adds the same
    section QSettings would write on that wizard's completion, and flips coreMode from
    its unconfigured default (0) to client (1) -- otherwise the app would run with a
    server address set but not actually acting as a client.

    Raises SyncError if the file was never bootstrapped by a first launch (no
    computerName at all), or if a [client] section already exists -- that is
    sync_desktop_identity's job, not this one.
    """
    host = _safe("server_host", server_host)
    name = _safe("client_name", client_name)

    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        mode = os.stat(path).st_mode & 0o777
    except OSError as exc:
        raise SyncError(f"could not read {path}: {exc}") from exc

    if _COMPUTER_NAME_LINE.search(text) is None:
        raise SyncError(
            "the desktop app's config has not been bootstrapped by a first launch yet"
        )
    if "[client]" in text:
        raise SyncError("a [client] section already exists; use sync_desktop_identity instead")

    text = _COMPUTER_NAME_LINE.sub(f"computerName={name}", text, count=1)
    if _CORE_MODE_LINE.search(text) is not None:
        text = _CORE_MODE_LINE.sub(f"coreMode={_CORE_MODE_CLIENT}", text, count=1)
    text = text.rstrip("\n") + f"\n\n[client]\nremoteHost={host}\n"

    return _atomic_rewrite(path, text, mode)


#: The real system-scope export dir. A parameter everywhere below, not a literal
#: inlined into the search -- otherwise a test can never isolate itself from whatever
#: happens to be installed system-wide on the machine running it.
SYSTEM_EXPORT_DIR = "/var/lib/flatpak/exports/share/applications"


def _export_search_paths(home, system_export_dir):
    """Where flatpak may have exported the desktop app's launcher, user scope first.

    User scope is what our own install button uses; system scope covers an install
    the user made some other way (found on hardware, 2026-08-22: a manually installed
    system-scope copy from a since-disabled custom remote).
    """
    return [
        os.path.join(
            home, ".local", "share", "flatpak", "exports", "share", "applications",
            DESKTOP_DESKTOP_FILE_NAME,
        ),
        os.path.join(system_export_dir, DESKTOP_DESKTOP_FILE_NAME),
    ]


def find_exported_desktop_file(home, system_export_dir=SYSTEM_EXPORT_DIR):
    """The real flatpak-exported launcher, or None if the app is not installed.

    Copied rather than hand-built: the file's Exec= line encodes flatpak's own branch
    and arch choices, which are not ours to guess and can change on update.
    """
    for path in _export_search_paths(home, system_export_dir):
        if os.path.isfile(path):
            return path
    return None


def autostart_path(home):
    return os.path.join(home, ".config", "autostart", DESKTOP_DESKTOP_FILE_NAME)


def write_autostart_entry(home, system_export_dir=SYSTEM_EXPORT_DIR):
    """Copy the real exported launcher into ~/.config/autostart. Returns the path written.

    Raises SyncError if no exported launcher can be found -- the app is not installed.
    """
    source = find_exported_desktop_file(home, system_export_dir)
    if source is None:
        raise SyncError("no exported launcher found; is the desktop app installed?")

    target = autostart_path(home)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(source, target)
    os.chmod(target, 0o644)
    return target
