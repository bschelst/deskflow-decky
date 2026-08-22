"""Sync the deck user's session environment with the chosen keyboard layout.

gamescope builds its xkb keymap from ``XKB_DEFAULT_LAYOUT`` in the session
environment, which systemd reads from ``~/.config/environment.d`` when the
Gaming Mode session starts. The layout chosen in the plugin therefore has to be
written there so the compositor decodes injected key positions with that same
layout. A change only takes effect after the Gaming Mode session restarts.
"""

import os

ENV_FILE_NAME = "50-deskflow-decky-xkb.conf"

_HEADER = (
    "# Managed by the DeskFlow Decky plugin; do not edit.\n"
    "# Removed automatically when the keyboard layout setting is cleared.\n"
)


def environment_file_path(user_home):
    return os.path.join(user_home, ".config", "environment.d", ENV_FILE_NAME)


def _wanted_content(layout):
    if not layout:
        return None
    # ``layout`` has already passed validation (^[a-z]{2,10}$), so it is safe to
    # embed verbatim.
    return f"{_HEADER}XKB_DEFAULT_LAYOUT={layout}\n"


def _chown_like_home(path, home_stat):
    # The plugin runs as root; the file must belong to the session user or the
    # user cannot remove or edit it themselves.
    os.chown(path, home_stat.st_uid, home_stat.st_gid)


def sync_keyboard_layout(user_home, layout, logger=None):
    """Write or remove the environment.d entry for ``layout``.

    Returns ``True`` when the file on disk changed (a Gaming Mode restart is
    then needed before gamescope picks the layout up) and ``False`` when it was
    already in the wanted state. Failures are logged and reported as ``False``:
    a settings save must not fail because the session file could not be
    written.
    """
    path = environment_file_path(user_home)
    wanted = _wanted_content(layout)
    try:
        current = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                current = handle.read()

        if current == wanted:
            return False

        if wanted is None:
            os.remove(path)
            if logger:
                logger.info("Removed session keyboard layout file %s", path)
            return True

        home_stat = os.stat(user_home)
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory)
            _chown_like_home(directory, home_stat)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(wanted)
        _chown_like_home(path, home_stat)
        if logger:
            logger.info("Wrote session keyboard layout %s to %s", layout, path)
        return True
    except OSError as error:
        if logger:
            logger.warning("Could not update session keyboard layout: %s", error)
        return False
