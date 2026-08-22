"""Detecting the compositor's pointer coordinate space.

Getting this wrong is immediately visible: the pointer stops partway across the screen,
because the client announces a smaller screen than the compositor actually addresses.
It is NOT the panel resolution -- gamescope runs a nested surface and scales it.
"""

import pytest
from screen_size import (
    FALLBACK_SIZE,
    choose_screen_size,
    parse_xdpyinfo,
    parse_xrandr,
)

XRANDR = """Screen 0: minimum 16 x 16, current 1920 x 1200, maximum 32767 x 32767
XWAYLAND0 connected primary 1920x1200+0+0 (normal left inverted right x axis y axis) 0mm x 0mm
   1920x1200     59.88*+
"""

XDPYINFO = """name of display:    :0
version number:    11.0
  dimensions:    1920x1200 pixels (508x318 millimeters)
  resolution:    96x96 dots per inch
"""


def test_parses_xrandr_current():
    assert parse_xrandr(XRANDR) == (1920, 1200)


def test_parses_xdpyinfo_dimensions():
    assert parse_xdpyinfo(XDPYINFO) == (1920, 1200)


@pytest.mark.parametrize("junk", ["", "no screen here", "Screen 0: current", None, 42])
def test_parsers_return_none_on_junk(junk):
    assert parse_xrandr(junk) is None
    assert parse_xdpyinfo(junk) is None


def test_xrandr_rejects_absurd_values():
    # Beyond the protocol's int16 extent it cannot be announced at all.
    assert parse_xrandr("Screen 0: current 99999 x 99999, maximum 1 x 1") is None


def test_xrandr_rejects_zero():
    assert parse_xrandr("Screen 0: current 0 x 0, maximum 1 x 1") is None


# --------------------------------------------------------------------------- choosing


def test_an_explicit_setting_wins_over_detection():
    # If someone typed a size, a "smarter" detected value would be a surprise.
    assert choose_screen_size(1024, 768, detected=(1920, 1200)) == (1024, 768)


def test_zero_means_auto_detect():
    assert choose_screen_size(0, 0, detected=(1920, 1200)) == (1920, 1200)


def test_auto_falls_back_when_detection_fails():
    assert choose_screen_size(0, 0, detected=None) == FALLBACK_SIZE


def test_a_half_specified_size_is_treated_as_auto():
    assert choose_screen_size(1920, 0, detected=(2560, 1600)) == (2560, 1600)
    assert choose_screen_size(0, 1200, detected=(2560, 1600)) == (2560, 1600)


def test_fallback_is_usable():
    width, height = FALLBACK_SIZE
    assert width > 0 and height > 0
