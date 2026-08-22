# Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

"""This Deck's identity on a Deskflow network.

Every Steam Deck and Steam Machine ships with the hostname ``steamdeck``, so using it
as the client name collides as soon as a second device connects to the same server --
Deskflow refuses the duplicate with "a client with name X is already connected".

The derived name must be:

* **unique** per machine, so two Steam devices can share one server; and
* **stable** across reboots and reinstalls of this plugin, because the name has to be
  present in the server's screen layout. A name that changed on every start would mean
  editing the server's configuration after every restart.

``/etc/machine-id`` satisfies both. It is not used verbatim: systemd's documentation is
explicit that the machine id should not be handed out directly, and this name is
broadcast to every peer on the network, so a keyed hash is used instead.
"""

import hashlib
import socket

__all__ = ["DEFAULT_NAME_PREFIX", "derive_client_name"]

DEFAULT_NAME_PREFIX = "steamos-"
MACHINE_ID_PATH = "/etc/machine-id"
DBUS_MACHINE_ID_PATH = "/var/lib/dbus/machine-id"

#: Fixed salt, so the published name cannot be matched back to a machine id by anyone
#: hashing candidate ids from another context.
_SALT = b"deskflow-decky/client-name/v1"

SUFFIX_LENGTH = 4


def _read_machine_id(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def derive_client_name(machine_id_path=MACHINE_ID_PATH, fallback=None):
    """Return a stable, machine-unique screen name such as ``steamos-4f2a``.

    Falls back through the D-Bus machine id and then the hostname. Never raises: this
    runs during plugin startup, where an exception would be far worse than a name that
    happens to be less unique than intended.
    """
    seed = _read_machine_id(machine_id_path)

    if not seed and machine_id_path == MACHINE_ID_PATH:
        seed = _read_machine_id(DBUS_MACHINE_ID_PATH)

    if not seed:
        if fallback:
            seed = str(fallback)
        else:
            try:
                seed = socket.gethostname()
            except OSError:
                seed = ""

    if not seed:
        # Everything failed. A constant is still better than a crash, and it is no
        # worse than the "steamdeck" default it replaces.
        seed = "unidentified"

    digest = hashlib.sha256(_SALT + seed.encode("utf-8", "replace")).hexdigest()
    return DEFAULT_NAME_PREFIX + digest[:SUFFIX_LENGTH]
