"""Deriving this Deck's default Deskflow screen name.

Every Steam Deck and Steam Machine ships with the hostname "steamdeck", so that name
collides the moment a second device connects to the same server. The derived name must
be unique per machine AND stable across reboots -- an unstable name would mean editing
the server's screen layout after every restart.
"""

import re

from identity import DEFAULT_NAME_PREFIX, derive_client_name

MACHINE_ID = "3f9a1c7e5b2d48a69e0f1234567890ab"


def write_machine_id(tmp_path, value=MACHINE_ID):
    path = tmp_path / "machine-id"
    path.write_text(value + "\n")
    return str(path)


def test_name_has_the_expected_shape(tmp_path):
    name = derive_client_name(write_machine_id(tmp_path))
    assert re.fullmatch(r"steamos-[0-9a-f]{4}", name), name


def test_name_is_stable_for_the_same_machine(tmp_path):
    path = write_machine_id(tmp_path)
    assert derive_client_name(path) == derive_client_name(path)


def test_different_machines_get_different_names(tmp_path):
    a = derive_client_name(write_machine_id(tmp_path / "a" if False else tmp_path))
    other = tmp_path / "other"
    other.mkdir()
    b = derive_client_name(write_machine_id(other, "0123456789abcdef0123456789abcdef"))
    assert a != b


def test_surrounding_whitespace_does_not_change_the_result(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    spaced = tmp_path / "spaced"
    spaced.mkdir()
    a = derive_client_name(write_machine_id(plain, MACHINE_ID))
    b = derive_client_name(write_machine_id(spaced, "  " + MACHINE_ID + "  \n"))
    assert a == b


def test_the_machine_id_is_not_exposed_in_the_name(tmp_path):
    # systemd treats the machine id as something not to hand out verbatim; a keyed
    # hash gives uniqueness without publishing it to every peer on the network.
    name = derive_client_name(write_machine_id(tmp_path))
    assert MACHINE_ID[:4] not in name or name != DEFAULT_NAME_PREFIX + MACHINE_ID[:4]
    assert MACHINE_ID not in name


def test_falls_back_when_the_machine_id_is_missing(tmp_path):
    name = derive_client_name(str(tmp_path / "nope"), fallback="steamdeck-xyz")
    assert re.fullmatch(r"steamos-[0-9a-f]{4}", name), name


def test_fallback_is_also_stable(tmp_path):
    missing = str(tmp_path / "nope")
    assert derive_client_name(missing, fallback="host-a") == derive_client_name(
        missing, fallback="host-a"
    )


def test_an_empty_machine_id_uses_the_fallback(tmp_path):
    path = tmp_path / "machine-id"
    path.write_text("\n")
    assert re.fullmatch(r"steamos-[0-9a-f]{4}", derive_client_name(str(path), fallback="h"))


def test_result_passes_the_client_name_rule(tmp_path):
    from validation import validate_field

    name = derive_client_name(write_machine_id(tmp_path))
    assert validate_field("client_name", name) == name


def test_unreadable_machine_id_does_not_raise(tmp_path):
    # A directory where the file should be: must degrade, not explode at startup.
    d = tmp_path / "machine-id"
    d.mkdir()
    assert derive_client_name(str(d), fallback="h").startswith(DEFAULT_NAME_PREFIX)
