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
    HelperProcess,
    LaunchError,
    build_command,
    build_environment,
    clean_subprocess_env,
    find_stray_helpers,
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
            "DESKFLOW_SCREEN_SIZE",
            "DISPLAY",
            "WAYLAND_DISPLAY",
        }
    )


def test_libei_backend_declares_a_usable_screen_size():
    # Without this the patched helper announces 1x1, which the server rejects with
    # "invalid message from client: DINF" and which strands the pointer on the Deck.
    env = build_environment(settings(), "gamescope-libei", found())
    assert env["DESKFLOW_SCREEN_SIZE"] == "1280x800"


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


def test_path_is_not_forwarded_into_the_sandbox():
    # --env=PATH would override the sandbox's own PATH, which is what makes /app/bin
    # reachable; the helper then cannot be executed at all.
    argv = build_command(settings(), "/c", "gamescope-libei", found())
    assert not any(part.startswith("--env=PATH=") for part in argv)


def test_path_is_still_present_for_the_launching_process():
    # ...but it is needed outside the sandbox so `flatpak` itself can be located.
    env = build_environment(settings(), "gamescope-libei", found())
    assert env.get("PATH")


def test_other_variables_are_still_forwarded():
    argv = build_command(settings(), "/c", "gamescope-libei", found())
    assert any(part.startswith("--env=LIBEI_SOCKET=") for part in argv)
    assert any(part == "--env=DESKFLOW_EI_BACKEND=socket" for part in argv)


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


def test_backoff_follows_the_agreed_schedule():
    delays = [next_backoff_delay(n, maximum=60) for n in range(1, 7)]
    assert delays == [1, 2, 5, 10, 15, 30]


def test_backoff_settles_rather_than_growing_without_limit():
    # A server that is simply switched off should be retried steadily and cheaply.
    assert [next_backoff_delay(n, maximum=60) for n in (7, 20, 500)] == [30, 30, 30]


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


# --------------------------------------------------------------- pyinstaller environment

# Decky runs plugins inside a PyInstaller bundle. Observed on hardware: the system
# openssl inherited the bundle's LD_LIBRARY_PATH and failed with
# "libssl.so.3: version `OPENSSL_3.4.0' not found".


def test_bundle_library_path_is_removed():
    source = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/_MEIabc123"}
    assert "LD_LIBRARY_PATH" not in clean_subprocess_env(source)


def test_original_library_path_is_restored_when_pyinstaller_saved_one():
    source = {
        "LD_LIBRARY_PATH": "/tmp/_MEIabc123",
        "LD_LIBRARY_PATH_ORIG": "/usr/local/lib",
    }
    cleaned = clean_subprocess_env(source)
    assert cleaned["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in cleaned


def test_an_empty_original_is_treated_as_absent():
    source = {"LD_LIBRARY_PATH": "/tmp/_MEIabc", "LD_LIBRARY_PATH_ORIG": ""}
    assert "LD_LIBRARY_PATH" not in clean_subprocess_env(source)


def test_other_bundle_markers_are_dropped():
    source = {"_MEIPASS2": "/tmp/_MEIabc", "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    cleaned = clean_subprocess_env(source)
    assert "_MEIPASS2" not in cleaned
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in cleaned


def test_unrelated_variables_are_preserved():
    source = {"PATH": "/usr/bin", "HOME": "/home/deck", "XDG_RUNTIME_DIR": "/run/user/1000"}
    assert clean_subprocess_env(source) == source


def test_the_source_mapping_is_not_mutated():
    source = {"LD_LIBRARY_PATH": "/tmp/_MEIabc"}
    clean_subprocess_env(source)
    assert source == {"LD_LIBRARY_PATH": "/tmp/_MEIabc"}


def test_a_clean_environment_passes_through_unchanged():
    source = {"PATH": "/usr/bin"}
    assert clean_subprocess_env(source) == {"PATH": "/usr/bin"}


# --------------------------------------------------------------- process group cleanup

# `flatpak run` execs bwrap which runs deskflow-core. Killing only the direct child
# leaves the sandboxed process alive, and Deskflow then refuses every future start with
# "an instance of deskflow core is already running" -- observed on hardware as a
# permanently wedged plugin.


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.pid = 4242
        self.stdout = None

    async def wait(self):
        self.returncode = 0
        return 0


def test_helper_is_spawned_in_its_own_session():
    import asyncio as _asyncio

    recorded = {}

    async def fake_spawn(*argv, **kwargs):
        recorded.update(kwargs)
        return FakeProcess()

    helper = HelperProcess(spawn=fake_spawn)
    _asyncio.run(helper.start(["flatpak", "run", "x"], {"PATH": "/usr/bin"}))
    assert recorded.get("start_new_session") is True, (
        "without its own session the sandboxed grandchild survives stop()"
    )


def test_finds_a_stray_helper_by_app_id(tmp_path):
    # A fake /proc: only a process whose cmdline names our app id AND the helper
    # command should ever be selected.
    def make(pid, cmdline):
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(cmdline.encode())

    make(101, "deskflow-core\x00client\x00-s\x00/x/org.schelstraete.DeskFlowDecky/c.conf")
    make(102, "firefox\x00")
    make(103, "deskflow-core\x00client\x00-s\x00/some/other/app/c.conf")
    make(104, "flatpak\x00run\x00org.deskflow.deskflow\x00")
    (tmp_path / "notapid").mkdir()

    found = find_stray_helpers(proc_root=str(tmp_path), own_pid=999)
    assert found == [101]


def test_never_selects_our_own_process(tmp_path):
    d = tmp_path / "555"
    d.mkdir()
    (d / "cmdline").write_bytes(b"deskflow-core\x00org.schelstraete.DeskFlowDecky")
    assert find_stray_helpers(proc_root=str(tmp_path), own_pid=555) == []


def test_missing_proc_is_not_an_error():
    assert find_stray_helpers(proc_root="/nonexistent-proc") == []


def test_unreadable_cmdline_is_skipped(tmp_path):
    (tmp_path / "202").mkdir()  # no cmdline file at all
    assert find_stray_helpers(proc_root=str(tmp_path), own_pid=1) == []


# --------------------------------------------------------------------------- clipboard


def test_wayland_display_is_only_passed_when_clipboard_is_on():
    off = build_environment(settings(), "gamescope-libei", found(), wayland_display="gamescope-0")
    assert "WAYLAND_DISPLAY" not in off

    on = build_environment(
        settings(clipboard_enabled=True), "gamescope-libei", found(),
        wayland_display="gamescope-0",
    )
    assert on["WAYLAND_DISPLAY"] == "gamescope-0"


def test_clipboard_without_a_display_does_not_invent_one():
    env = build_environment(settings(clipboard_enabled=True), "gamescope-libei", found())
    assert "WAYLAND_DISPLAY" not in env
