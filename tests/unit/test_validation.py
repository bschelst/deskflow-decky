"""Validation is the crash-safety keystone: every value crossing a boundary goes through it.

Per docs/TESTING.md §1.1, every field gets four cases (valid, boundary, just-outside,
malformed) plus type-specific hostile input.
"""

import pytest
from validation import (
    DEFAULTS,
    ValidationError,
    sanitize_loaded,
    validate_field,
    validate_patch,
)

# --------------------------------------------------------------------------- helpers


def base():
    """A valid full settings dict to patch against."""
    return dict(DEFAULTS, server_host="192.168.1.10")


def expect_invalid(name, value):
    with pytest.raises(ValidationError) as exc:
        validate_field(name, value)
    assert exc.value.field == name
    return exc.value


# --------------------------------------------------------------------------- defaults


def test_defaults_are_themselves_valid():
    # A default that fails its own rule is a latent crash on first run.
    for name, value in DEFAULTS.items():
        validate_field(name, value)


def test_defaults_pass_cross_field_rules_for_server_mode():
    settings = dict(DEFAULTS, mode="server")
    assert validate_patch({}, settings) == settings


# --------------------------------------------------------------------------- mode


def test_mode_accepts_both_members():
    assert validate_field("mode", "client") == "client"
    assert validate_field("mode", "server") == "server"


@pytest.mark.parametrize("bad", ["Client", "CLIENT", "", "clients", None, 0, 1, True, ["client"]])
def test_mode_rejects_near_misses_and_wrong_types(bad):
    expect_invalid("mode", bad)


# --------------------------------------------------------------------------- server_host


@pytest.mark.parametrize(
    "good",
    [
        "192.168.1.10",
        "10.0.0.1",
        "255.255.255.255",
        "::1",
        "fe80::1ff:fe23:4567:890a",
        "2001:db8::8a2e:370:7334",
        "desktop",
        "desktop.local",
        "my-pc.example.com",
        "a",
        "a" * 63,
        "x" * 63 + "." + "y" * 63 + "." + "z" * 63 + "." + "w" * 61,  # 253 chars
    ],
)
def test_server_host_accepts_valid_addresses(good):
    assert validate_field("server_host", good) == good


@pytest.mark.parametrize(
    "bad",
    [
        " ",
        "  desktop  ",
        "desk top",
        "desktop\n",
        "desktop\x00",
        "-leading.hyphen",
        "trailing.hyphen-",
        "a" * 64,  # label too long
        "x" * 63 + "." + "y" * 63 + "." + "z" * 63 + "." + "w" * 62,  # 254 chars
        "256.1.1.1",
        "1.1.1",
        "http://desktop",
        "desktop:24800",
        "desktop;reboot",
        "desktop|whoami",
        "desktop&&id",
        "$(hostname)",
        "`hostname`",
        "../../etc/hosts",
        "desktop$USER",
        None,
        24800,
        True,
        ["desktop"],
    ],
)
def test_server_host_rejects_malformed_and_hostile_input(bad):
    expect_invalid("server_host", bad)


def test_server_host_allows_empty_meaning_not_configured_yet():
    # Empty is a valid field value -- it is the cross-field rule that decides whether
    # an unset host is acceptable in the current mode. DEFAULTS ships this way.
    assert validate_field("server_host", "") == ""


# --------------------------------------------------------------------------- server_port


@pytest.mark.parametrize("good", [1, 24800, 65535])
def test_server_port_accepts_in_range(good):
    assert validate_field("server_port", good) == good


@pytest.mark.parametrize("bad", [0, -1, 65536, 100000])
def test_server_port_rejects_out_of_range(bad):
    expect_invalid("server_port", bad)


@pytest.mark.parametrize("bad", ["24800", "", 24800.0, None, True, False, [24800]])
def test_server_port_rejects_wrong_types_without_coercing(bad):
    # A string port must be an error, never a silent cast: coercion hides frontend bugs.
    expect_invalid("server_port", bad)


# --------------------------------------------------------------------------- client_name


@pytest.mark.parametrize("good", ["steamdeck", "deck-1", "a", "A" * 63, "my.deck_2"])
def test_client_name_accepts_valid(good):
    assert validate_field("client_name", good) == good


@pytest.mark.parametrize(
    "bad",
    ["", "-deck", ".deck", "_deck", "a" * 64, "my deck", "deck\n", "dëck", "deck;rm", None, 5],
)
def test_client_name_rejects_invalid(bad):
    expect_invalid("client_name", bad)


# --------------------------------------------------------------------------- booleans


@pytest.mark.parametrize(
    "name", ["tls_enabled", "check_peer_fingerprints", "autostart_gaming_mode", "reconnect_enabled"]
)
def test_booleans_accept_only_real_booleans(name):
    assert validate_field(name, True) is True
    assert validate_field(name, False) is False
    for bad in ["true", "false", 1, 0, None, ""]:
        expect_invalid(name, bad)


# --------------------------------------------------------------------------- enums


@pytest.mark.parametrize(
    "value", ["auto", "gamescope-libei", "x11-xtest", "uinput"]
)
def test_input_backend_accepts_members(value):
    assert validate_field("input_backend", value) == value


@pytest.mark.parametrize("bad", ["Auto", "libei", "", None, 0, "gamescope_libei"])
def test_input_backend_rejects_non_members(bad):
    expect_invalid("input_backend", bad)


@pytest.mark.parametrize("value", ["manual", "always"])
def test_activation_mode_accepts_members(value):
    assert validate_field("activation_mode", value) == value


@pytest.mark.parametrize("value", ["error", "warn", "info", "debug"])
def test_log_level_accepts_members(value):
    assert validate_field("log_level", value) == value


@pytest.mark.parametrize("bad", ["DEBUG", "trace", "", None])
def test_log_level_rejects_non_members(bad):
    expect_invalid("log_level", bad)


# --------------------------------------------------------------------------- numerics


@pytest.mark.parametrize("good", [0.25, 1.0, 4.0, 2.5, 1])
def test_pointer_sensitivity_accepts_in_range(good):
    assert validate_field("pointer_sensitivity", good) == float(good)


@pytest.mark.parametrize("bad", [0.24, 4.01, 0, -1.0, float("nan"), float("inf"), "1.0", None, True])
def test_pointer_sensitivity_rejects_out_of_range_and_wrong_types(bad):
    expect_invalid("pointer_sensitivity", bad)


@pytest.mark.parametrize("good", [1, 30, 300])
def test_reconnect_backoff_accepts_in_range(good):
    assert validate_field("reconnect_max_backoff_s", good) == good


@pytest.mark.parametrize("bad", [0, 301, -5, 30.0, "30", None, True])
def test_reconnect_backoff_rejects_invalid(bad):
    expect_invalid("reconnect_max_backoff_s", bad)


# --------------------------------------------------------------------------- socket path


def test_socket_path_override_accepts_empty():
    assert validate_field("socket_path_override", "") == ""


def test_socket_path_override_accepts_path_under_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    p = str(tmp_path / "gamescope-0-ei")
    assert validate_field("socket_path_override", p) == p


@pytest.mark.parametrize(
    "bad_tmpl",
    [
        "{root}/../escape",
        "{root}/sub/../../escape",
        "relative/path",
        "/etc/passwd",
        "{root}/sock\x00",
        "{root}/sock\n",
    ],
)
def test_socket_path_override_rejects_escapes_and_outside_paths(monkeypatch, tmp_path, bad_tmpl):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    expect_invalid("socket_path_override", bad_tmpl.format(root=str(tmp_path)))


@pytest.mark.parametrize("bad", [None, 5, True, []])
def test_socket_path_override_rejects_wrong_types(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    expect_invalid("socket_path_override", bad)


# --------------------------------------------------------------------------- patch semantics


def test_patch_returns_new_dict_and_does_not_mutate_current():
    current = base()
    snapshot = dict(current)
    result = validate_patch({"server_port": 1234}, current)
    assert result is not current
    assert current == snapshot
    assert result["server_port"] == 1234


def test_patch_leaves_untouched_fields_alone():
    current = base()
    result = validate_patch({"log_level": "debug"}, current)
    assert result["server_host"] == current["server_host"]
    assert result["log_level"] == "debug"


def test_patch_rejects_unknown_keys():
    with pytest.raises(ValidationError) as exc:
        validate_patch({"totally_made_up": 1}, base())
    assert exc.value.field == "totally_made_up"


def test_patch_is_all_or_nothing():
    # One bad field means nothing is applied at all.
    current = base()
    with pytest.raises(ValidationError):
        validate_patch({"log_level": "debug", "server_port": 99999}, current)
    assert current["log_level"] == DEFAULTS["log_level"]


def test_patch_rejects_non_dict():
    for bad in [None, [], "x", 5]:
        with pytest.raises(ValidationError):
            validate_patch(bad, base())


# --------------------------------------------------------------------------- cross-field


def test_tls_without_fingerprint_checking_is_rejected():
    # Encryption without authentication looks secure in the UI but is not.
    with pytest.raises(ValidationError) as exc:
        validate_patch({"tls_enabled": True, "check_peer_fingerprints": False}, base())
    assert exc.value.field == "check_peer_fingerprints"


def test_fingerprint_checking_may_be_off_when_tls_is_off():
    result = validate_patch({"tls_enabled": False, "check_peer_fingerprints": False}, base())
    assert result["tls_enabled"] is False


def test_client_mode_without_a_host_is_allowed_at_configuration_time():
    # Enforcing this here deadlocked the UI on hardware: the server-address field is
    # only shown in client mode, so refusing the switch back left no way to enter one.
    # The requirement is enforced at start time instead (main.py refuses to launch).
    result = validate_patch({"mode": "client", "server_host": ""}, base())
    assert result["mode"] == "client"
    assert result["server_host"] == ""


def test_switching_back_to_client_mode_without_a_host_is_allowed():
    current = dict(DEFAULTS, mode="server", server_host="")
    assert validate_patch({"mode": "client"}, current)["mode"] == "client"


def test_server_mode_does_not_require_a_host():
    current = dict(DEFAULTS, mode="server", server_host="")
    assert validate_patch({}, current)["server_host"] == ""


# --------------------------------------------------------------------------- loading


def test_sanitize_loaded_accepts_a_good_file():
    settings, warnings = sanitize_loaded(base())
    assert warnings == []
    assert settings["server_host"] == "192.168.1.10"


def test_sanitize_loaded_never_raises_on_garbage():
    for garbage in [None, [], "string", 5, {"server_port": "nope"}, {"mode": 12}]:
        settings, warnings = sanitize_loaded(garbage)
        # Always returns a usable, valid settings dict.
        for name, value in settings.items():
            validate_field(name, value)
        assert isinstance(warnings, list)


def test_sanitize_loaded_replaces_invalid_values_with_defaults_and_warns():
    settings, warnings = sanitize_loaded(dict(base(), server_port=999999))
    assert settings["server_port"] == DEFAULTS["server_port"]
    assert any("server_port" in w for w in warnings)


def test_sanitize_loaded_drops_unknown_keys_with_a_warning():
    settings, warnings = sanitize_loaded(dict(base(), legacy_key="x"))
    assert "legacy_key" not in settings
    assert any("legacy_key" in w for w in warnings)


def test_sanitize_loaded_fills_in_missing_keys():
    settings, _ = sanitize_loaded({"server_host": "desktop"})
    assert set(settings) == set(DEFAULTS)
    assert settings["server_port"] == DEFAULTS["server_port"]


def test_sanitize_loaded_repairs_a_broken_cross_field_combination():
    settings, warnings = sanitize_loaded(
        dict(base(), tls_enabled=True, check_peer_fingerprints=False)
    )
    # Repair must fail safe: keep verification on rather than silently disabling TLS.
    assert settings["check_peer_fingerprints"] is True
    assert warnings


def test_sanitize_loaded_repairs_client_mode_without_host():
    settings, warnings = sanitize_loaded(dict(DEFAULTS, mode="client", server_host=""))
    settings_are_valid = validate_patch({}, settings)
    assert settings_are_valid == settings
    assert warnings


# --------------------------------------------------------------------------- error shape


def test_validation_error_names_the_field_and_has_a_safe_message():
    err = expect_invalid("server_port", 99999)
    assert err.field == "server_port"
    assert isinstance(err.message, str) and err.message
    assert "99999" not in err.message or "range" in err.message.lower()


def test_validation_error_does_not_echo_potentially_sensitive_values():
    # Hostnames can be private; the message names the field, not the value.
    err = expect_invalid("server_host", "secret-internal-host.corp;rm -rf /")
    assert "rm -rf" not in err.message
