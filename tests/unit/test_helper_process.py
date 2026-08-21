"""Helper launch: argument construction, environment, backend resolution, backoff.

The command is always an argument list. There is no shell anywhere in this path, so a
hostile hostname cannot become a second command -- but the pure builders are still
tested against injection attempts, because "it's a list" is a property that a future
refactor could quietly remove.
"""

import pytest
from discovery import DiscoveryResult
from helper_process import (
    APP_ID,
    LaunchError,
    build_command,
    build_environment,
    next_backoff_delay,
    resolve_backend,
)
from validation import DEFAULTS


def settings(**overrides):
    base = dict(DEFAULTS)
    base.update(mode="client", server_host="desktop.local")
    base.update(overrides)
    return base


def found(path="/run/user/1000/gamescope-0-ei"):
    return DiscoveryResult(True, path, "runtime-dir-scan")


def missing():
    return DiscoveryResult(False, None, None, ["nothing here"])


# --------------------------------------------------------------------------- command


def test_command_is_a_list_of_arguments():
    argv = build_command(settings(), "/cfg/Deskflow.conf", "gamescope-libei", found())
    assert isinstance(argv, list)
    assert all(isinstance(part, str) for part in argv)


def test_command_runs_the_engine_not_the_gui():
    # The flatpak's default command is the Qt GUI; the engine is deskflow-core.
    argv = build_command(settings(), "/cfg/Deskflow.conf", "gamescope-libei", found())
    assert "--command=deskflow-core" in argv


def test_command_is_a_user_scope_flatpak_run():
    argv = build_command(settings(), "/cfg/Deskflow.conf", "gamescope-libei", found())
    assert argv[0] == "flatpak"
    assert argv[1] == "run"
    assert "--user" in argv


def test_app_id_precedes_the_subcommand():
    argv = build_command(settings(), "/cfg/Deskflow.conf", "gamescope-libei", found())
    assert argv.index(APP_ID) < argv.index("client")


def test_client_and_server_modes_pick_their_subcommand():
    client = build_command(settings(), "/c", "gamescope-libei", found())
    server = build_command(settings(mode="server"), "/c", "gamescope-libei", found())
    assert "client" in client and "server" not in client
    assert "server" in server and "client" not in server


def test_config_path_is_passed_with_the_settings_flag():
    argv = build_command(settings(), "/cfg/Deskflow.conf", "gamescope-libei", found())
    assert argv[argv.index("-s") + 1] == "/cfg/Deskflow.conf"


def test_socket_is_granted_to_the_sandbox_explicitly():
    argv = build_command(settings(), "/c", "gamescope-libei", found("/run/user/1000/gs-ei"))
    assert any(part == "--filesystem=/run/user/1000/gs-ei" for part in argv)


def test_no_socket_grant_when_the_backend_does_not_need_one():
    argv = build_command(settings(), "/c", "x11-xtest", missing())
    assert not any(part.startswith("--filesystem=") for part in argv)


def test_a_value_containing_spaces_stays_one_argument():
    argv = build_command(settings(), "/cfg/with space/Deskflow.conf", "x11-xtest", missing())
    assert "/cfg/with space/Deskflow.conf" in argv


@pytest.mark.parametrize("hostile", ["/cfg\nDeskflow.conf", "/cfg\x00", "/cfg\rx"])
def test_arguments_containing_control_characters_are_refused(hostile):
    with pytest.raises(LaunchError):
        build_command(settings(), hostile, "x11-xtest", missing())


# --------------------------------------------------------------------------- environment


def test_environment_is_explicit_not_inherited():
    env = build_environment(settings(), "gamescope-libei", found())
    # Whatever Decky's own process carries must not leak into the helper.
    assert "PATH" not in env or env["PATH"]
    assert set(env).issubset(
        {
            "HOME",
            "PATH",
            "LIBEI_SOCKET",
            "XDG_RUNTIME_DIR",
            "XDG_SESSION_TYPE",
            "QT_QPA_PLATFORM",
            "DESKFLOW_EI_BACKEND",
            "DISPLAY",
            "WAYLAND_DISPLAY",
        }
    )


def test_libei_backend_selects_the_socket_path_and_patched_backend():
    env = build_environment(settings(), "gamescope-libei", found("/run/user/1000/gs-ei"))
    assert env["LIBEI_SOCKET"] == "/run/user/1000/gs-ei"
    # The patch reads this; without it upstream Deskflow uses the portal and fails
    # in Gaming Mode.
    assert env["DESKFLOW_EI_BACKEND"] == "socket"
    assert env["XDG_SESSION_TYPE"] == "wayland"


def test_x11_backend_forces_the_x11_session_type():
    # PlatformInfo::isWayland() reads XDG_SESSION_TYPE, so this is what selects XTest.
    env = build_environment(settings(), "x11-xtest", missing(), display=":1")
    assert env["XDG_SESSION_TYPE"] == "x11"
    assert env["DISPLAY"] == ":1"
    assert "LIBEI_SOCKET" not in env


def test_libei_backend_without_a_socket_is_refused():
    with pytest.raises(LaunchError):
        build_environment(settings(), "gamescope-libei", missing())


def test_environment_values_are_all_strings():
    env = build_environment(settings(), "gamescope-libei", found())
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())


# --------------------------------------------------------------------------- resolution


def test_auto_prefers_libei_when_the_socket_exists():
    assert resolve_backend("auto", found(), display=None) == "gamescope-libei"


def test_auto_falls_back_to_x11_when_a_display_is_available():
    assert resolve_backend("auto", missing(), display=":0") == "x11-xtest"


def test_auto_with_nothing_available_raises():
    with pytest.raises(LaunchError):
        resolve_backend("auto", missing(), display=None)


def test_an_explicit_backend_is_not_second_guessed():
    # If the user picked one, a silent substitution would make diagnostics lie.
    assert resolve_backend("x11-xtest", found(), display=":0") == "x11-xtest"


def test_explicit_libei_without_a_socket_raises_rather_than_falling_back():
    with pytest.raises(LaunchError):
        resolve_backend("gamescope-libei", missing(), display=":0")


# --------------------------------------------------------------------------- backoff


def test_backoff_grows():
    delays = [next_backoff_delay(n, maximum=30) for n in range(1, 6)]
    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


def test_backoff_is_capped():
    assert next_backoff_delay(50, maximum=30) == 30


def test_backoff_never_returns_zero():
    assert next_backoff_delay(1, maximum=30) > 0


def test_backoff_respects_a_small_cap():
    assert next_backoff_delay(10, maximum=1) == 1
