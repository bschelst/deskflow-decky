# Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

"""Working out the compositor's pointer coordinate space.

The client has to announce a screen size, and it must match the space the compositor
actually addresses. Get it wrong and the pointer stops partway across the display,
because the server never sends a coordinate beyond the size it was told about.

This is **not** the panel resolution. gamescope renders a nested surface and scales it
to the output, so a machine on a 3840x2160 television can have a 1920x1200 pointer
space. Nothing here is hardcoded to any particular device: the size is read from the
running session, and only falls back to a fixed value when that fails.

The parsers are pure so they can be tested without an X server.
"""

import re

__all__ = [
    "FALLBACK_SIZE",
    "choose_screen_size",
    "detection_commands",
    "parse_xdpyinfo",
    "parse_xrandr",
]

#: Only used when the session cannot be interrogated at all.
FALLBACK_SIZE = (1280, 800)

MIN_EXTENT = 320
#: kMsgDInfo carries geometry as int16, so nothing larger can be announced.
MAX_EXTENT = 32767

_XRANDR_CURRENT = re.compile(r"current\s+(\d+)\s*x\s*(\d+)", re.IGNORECASE)
_XDPYINFO_DIMENSIONS = re.compile(r"dimensions:\s*(\d+)x(\d+)\s*pixels", re.IGNORECASE)


def _sane(width, height):
    if not (MIN_EXTENT <= width <= MAX_EXTENT):
        return None
    if not (MIN_EXTENT <= height <= MAX_EXTENT):
        return None
    return (width, height)


def _parse_with(pattern, text):
    if not isinstance(text, str):
        return None
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return _sane(int(match.group(1)), int(match.group(2)))
    except (TypeError, ValueError):
        return None


def parse_xrandr(text):
    """Extract the screen size from ``xrandr --current`` output."""
    return _parse_with(_XRANDR_CURRENT, text)


def parse_xdpyinfo(text):
    """Extract the screen size from ``xdpyinfo`` output."""
    return _parse_with(_XDPYINFO_DIMENSIONS, text)


def detection_commands(display):
    """Commands to try, in order, each paired with its parser.

    Both are read-only queries against the session's own X server.
    """
    return (
        (["xrandr", "--current"], parse_xrandr, display),
        (["xdpyinfo"], parse_xdpyinfo, display),
    )


def choose_screen_size(configured_width, configured_height, detected=None):
    """Resolve the size to announce.

    An explicitly configured size always wins: if someone typed a number, silently
    substituting a "better" detected one would be a surprise, and there are compositors
    where the detected value is not what the pointer space uses. Zero means "work it
    out", which is the default.
    """
    if configured_width and configured_height:
        return (int(configured_width), int(configured_height))
    if detected:
        return detected
    return FALLBACK_SIZE
