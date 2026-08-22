"""The session environment file that hands gamescope the chosen keyboard layout."""

import os

import pytest
from session_env import environment_file_path, sync_keyboard_layout


@pytest.fixture
def home(tmp_path):
    return str(tmp_path)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_a_layout_is_written_into_environment_d(home):
    assert sync_keyboard_layout(home, "be") is True
    content = read(environment_file_path(home))
    assert "XKB_DEFAULT_LAYOUT=be" in content
    # The header explains ownership so nobody wonders where the file came from.
    assert "DeskFlow Decky" in content


def test_writing_the_same_layout_twice_reports_no_change(home):
    sync_keyboard_layout(home, "be")
    assert sync_keyboard_layout(home, "be") is False


def test_changing_the_layout_rewrites_the_file(home):
    sync_keyboard_layout(home, "be")
    assert sync_keyboard_layout(home, "us") is True
    assert "XKB_DEFAULT_LAYOUT=us" in read(environment_file_path(home))


def test_clearing_the_layout_removes_the_file(home):
    sync_keyboard_layout(home, "be")
    assert sync_keyboard_layout(home, "") is True
    assert not os.path.exists(environment_file_path(home))


def test_clearing_when_nothing_was_written_is_a_no_op(home):
    assert sync_keyboard_layout(home, "") is False


def test_an_unwritable_home_reports_failure_instead_of_raising(home):
    missing = os.path.join(home, "does-not-exist")
    assert sync_keyboard_layout(missing, "be") is False
