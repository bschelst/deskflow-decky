"""Discovery of Gamescope's EIS socket.

Gamescope creates a socket named ``<wayland-display>-ei`` in ``$XDG_RUNTIME_DIR`` and
exports ``LIBEI_SOCKET`` to its own children (``src/wlserver.cpp``). A process started
by Decky is not one of those children, so the path has to be found.

Every failure returns the list of places that were checked. "Socket not found" with no
detail is not something a user can act on.
"""

import os
import stat

__all__ = ["DiscoveryResult", "discover_socket"]

#: Only ever a depth-1 listing of the runtime directory. A filesystem walk would be
#: slow and would touch things this plugin has no business touching.
_SOCKET_SUFFIX = "-ei"
_PREFERRED_PREFIX = "gamescope"


class DiscoveryResult:
    def __init__(self, found, path=None, source=None, checked=None):
        self.found = found
        self.path = path
        self.source = source
        self.checked = list(checked or [])

    def as_dict(self):
        return {
            "found": self.found,
            "path": self.path,
            "source": self.source,
            "checked": list(self.checked),
        }

    def __repr__(self):
        return f"DiscoveryResult(found={self.found!r}, path={self.path!r}, source={self.source!r})"


def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def _is_usable_socket(path, root):
    """A candidate must be a socket, owned by us, and genuinely inside the runtime dir.

    The containment check happens after realpath so a symlink cannot point somewhere
    else and borrow the runtime directory's trust.
    """
    resolved = os.path.realpath(path)
    if not (resolved == root or resolved.startswith(root + os.sep)):
        return False, "resolves outside the runtime directory"
    try:
        info = os.stat(resolved)
    except OSError as exc:
        return False, f"cannot be inspected ({exc.strerror})"
    if not stat.S_ISSOCK(info.st_mode):
        return False, "is not a socket"
    if info.st_uid != os.getuid():
        return False, "is owned by another user"
    return True, None


def _candidates(root, checked):
    try:
        entries = sorted(os.listdir(root))
    except OSError as exc:
        checked.append(f"Runtime directory {root}: cannot be listed ({exc.strerror}).")
        return []

    names = [name for name in entries if name.endswith(_SOCKET_SUFFIX)]
    if not names:
        checked.append(
            f"Runtime directory {root}: no '*{_SOCKET_SUFFIX}' socket present."
        )
        return []

    # Gamescope's own socket wins over any other libei socket that happens to exist.
    names.sort(key=lambda name: (not name.startswith(_PREFERRED_PREFIX), name))
    return names


def discover_socket(settings, relay_path=None):
    """Locate the EIS socket, in priority order, and explain any failure."""
    checked = []
    root = os.path.realpath(_runtime_dir())

    # 1. An explicit choice is never silently replaced by a guess.
    override = (settings or {}).get("socket_path_override") or ""
    if override:
        usable, why = _is_usable_socket(override, root)
        if usable:
            return DiscoveryResult(True, override, "override", checked)
        checked.append(f"Configured socket path {override}: {why}.")
        return DiscoveryResult(False, None, "override", checked)

    # 2. A relay file, for the case where the socket path must be published to us.
    if relay_path:
        if os.path.isfile(relay_path):
            try:
                published = open(relay_path, encoding="utf-8").read().strip()
            except OSError as exc:
                published = ""
                checked.append(f"Relay file {relay_path}: unreadable ({exc.strerror}).")
            if published:
                usable, why = _is_usable_socket(published, root)
                if usable:
                    return DiscoveryResult(True, published, "relay-file", checked)
                checked.append(f"Relay file target {published}: {why}.")
        else:
            checked.append(f"Relay file {relay_path}: not present.")

    # 3. LIBEI_SOCKET, if this process happened to inherit it.
    env_value = os.environ.get("LIBEI_SOCKET", "").strip()
    if env_value:
        path = env_value if os.path.isabs(env_value) else os.path.join(root, env_value)
        usable, why = _is_usable_socket(path, root)
        if usable:
            return DiscoveryResult(True, path, "libei-socket-env", checked)
        checked.append(f"LIBEI_SOCKET points at {path}: {why}.")
    else:
        checked.append("LIBEI_SOCKET is not set in the plugin's environment.")

    # 4. A bounded scan of the runtime directory.
    for name in _candidates(root, checked):
        path = os.path.join(root, name)
        usable, why = _is_usable_socket(path, root)
        if usable:
            return DiscoveryResult(True, path, "runtime-dir-scan", checked)
        checked.append(f"Candidate {path}: {why}.")

    return DiscoveryResult(False, None, None, checked)
