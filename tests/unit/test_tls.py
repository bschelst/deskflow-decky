"""TLS trust handling.

Two stores are involved. Deskflow reads a flat list of fingerprints from
`tls/trusted-servers`; that file has no host association, so the plugin also keeps its
own host -> fingerprint map in order to tell "first contact" apart from "the
fingerprint changed", which is the case that actually matters.
"""

import os
import stat

import pytest
from tls import (
    PinnedHosts,
    TrustStore,
    format_fingerprint,
    normalise_fingerprint,
)

FP_A = "a" * 64
FP_B = "b" * 64


# --------------------------------------------------------------------------- formatting


def test_normalise_lowercases_and_strips():
    assert normalise_fingerprint("  " + "AB" * 32 + " ") == ("ab" * 32)


def test_normalise_accepts_colon_separated_input():
    colonised = ":".join("ab" for _ in range(32))
    assert normalise_fingerprint(colonised) == "ab" * 32


def test_normalise_accepts_a_prefixed_line():
    assert normalise_fingerprint("v2:sha256:" + FP_A) == FP_A


@pytest.mark.parametrize("bad", ["", "xyz", "a" * 63, "a" * 65, "g" * 64, None, 5])
def test_normalise_rejects_anything_that_is_not_a_sha256(bad):
    with pytest.raises(ValueError):
        normalise_fingerprint(bad)


def test_format_groups_for_human_comparison():
    formatted = format_fingerprint(FP_A)
    assert formatted.count(":") == 31
    assert formatted.upper() == formatted
    assert normalise_fingerprint(formatted) == FP_A


# --------------------------------------------------------------------------- trust store


def test_empty_store_trusts_nothing(tmp_path):
    store = TrustStore(str(tmp_path / "trusted-servers"))
    assert store.all() == []
    assert not store.is_trusted(FP_A)


def test_add_then_trust(tmp_path):
    store = TrustStore(str(tmp_path / "trusted-servers"))
    store.add(FP_A)
    assert store.is_trusted(FP_A)
    assert not store.is_trusted(FP_B)


def test_add_writes_deskflows_v2_line_format(tmp_path):
    path = tmp_path / "trusted-servers"
    TrustStore(str(path)).add(FP_A)
    assert path.read_text().strip() == "v2:sha256:" + FP_A


def test_add_is_idempotent(tmp_path):
    path = tmp_path / "trusted-servers"
    store = TrustStore(str(path))
    store.add(FP_A)
    store.add(FP_A)
    assert len(path.read_text().strip().splitlines()) == 1


def test_store_is_owner_only(tmp_path):
    path = tmp_path / "trusted-servers"
    TrustStore(str(path)).add(FP_A)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_malformed_lines_are_ignored_not_fatal(tmp_path):
    path = tmp_path / "trusted-servers"
    path.write_text(
        "\n".join(["", "# a comment", "garbage", "v2:sha256:" + FP_A, "v2:sha256:short", ""])
    )
    store = TrustStore(str(path))
    assert store.all() == [FP_A]


def test_legacy_v1_lines_do_not_grant_sha256_trust(tmp_path):
    # A v1 line is a SHA-1 fingerprint; treating it as SHA-256 trust would be wrong.
    path = tmp_path / "trusted-servers"
    path.write_text("v1:" + ":".join("ab" for _ in range(20)) + "\n")
    assert TrustStore(str(path)).all() == []


def test_remove_revokes_trust(tmp_path):
    path = tmp_path / "trusted-servers"
    store = TrustStore(str(path))
    store.add(FP_A)
    store.add(FP_B)
    store.remove(FP_A)
    assert store.all() == [FP_B]


def test_missing_file_is_not_an_error(tmp_path):
    store = TrustStore(str(tmp_path / "nested" / "trusted-servers"))
    assert store.all() == []
    store.add(FP_A)
    assert store.is_trusted(FP_A)


def test_unreadable_garbage_file_degrades_to_empty(tmp_path):
    path = tmp_path / "trusted-servers"
    path.write_bytes(b"\xff\xfe\x00binary junk")
    assert TrustStore(str(path)).all() == []


# --------------------------------------------------------------------------- pinning


def test_first_contact_is_reported_as_unknown(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    assert pins.classify("desktop", FP_A) == "unknown"


def test_matching_pin_is_trusted(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    pins.pin("desktop", FP_A)
    assert pins.classify("desktop", FP_A) == "trusted"


def test_changed_fingerprint_is_distinguished_from_first_contact(tmp_path):
    # This is the whole point of the pin file: a change is a possible interception,
    # and must not be presented with the same dialog as a first pairing.
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    pins.pin("desktop", FP_A)
    assert pins.classify("desktop", FP_B) == "changed"


def test_pin_is_per_host(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    pins.pin("desktop", FP_A)
    assert pins.classify("laptop", FP_A) == "unknown"


def test_previous_fingerprint_is_available_for_the_warning(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    pins.pin("desktop", FP_A)
    assert pins.get("desktop") == FP_A


def test_pins_survive_a_reload(tmp_path):
    path = str(tmp_path / "pinned.json")
    PinnedHosts(path).pin("desktop", FP_A)
    assert PinnedHosts(path).classify("desktop", FP_A) == "trusted"


def test_corrupt_pin_file_degrades_to_empty(tmp_path):
    path = tmp_path / "pinned.json"
    path.write_text("{not json")
    assert PinnedHosts(str(path)).classify("desktop", FP_A) == "unknown"


def test_pin_file_is_owner_only(tmp_path):
    path = tmp_path / "pinned.json"
    PinnedHosts(str(path)).pin("desktop", FP_A)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_unpin_forgets_the_host(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    pins.pin("desktop", FP_A)
    pins.unpin("desktop")
    assert pins.classify("desktop", FP_A) == "unknown"


def test_pinning_rejects_a_malformed_fingerprint(tmp_path):
    pins = PinnedHosts(str(tmp_path / "pinned.json"))
    with pytest.raises(ValueError):
        pins.pin("desktop", "not-a-fingerprint")
