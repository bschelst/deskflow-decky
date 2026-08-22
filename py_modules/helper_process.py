# Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

"""Lifecycle of the Deskflow helper flatpak.

Everything that builds a command or an environment is a pure function so it can be
asserted in tests. The async supervisor around them stays thin.

The command is always an argument list handed to ``create_subprocess_exec``. No shell
is involved anywhere in this module, and configuration travels through the INI file
rather than argv, which is world-readable via ``/proc/<pid>/cmdline``.
"""

import asyncio
import contextlib
import os
import signal

__all__ = [
    "APP_ID",
    "HelperProcess",
    "LaunchError",
    "build_command",
    "build_environment",
    "clean_subprocess_env",
    "find_stray_helpers",
    "is_gamescope_running",
    "next_backoff_delay",
    "resolve_backend",
]

#: Our own application ID. Never reuse upstream's org.deskflow.deskflow -- colliding
#: with it would break a user's existing Flathub install.
APP_ID = "org.schelstraete.DeskFlowDecky"

HELPER_COMMAND = "deskflow-core"
BACKENDS_NEEDING_SOCKET = ("gamescope-libei",)
_FORBIDDEN_IN_ARGUMENT = ("\n", "\r", "\x00")

#: Present in the launching process's environment but NOT forwarded into the sandbox.
#:
#: PATH is needed outside so execvpe can find the `flatpak` binary, but forwarding it
#: with --env=PATH overrides the sandbox's own PATH, which is what makes /app/bin
#: reachable. Observed on hardware as `bwrap: execvp deskflow-core: No such file or
#: directory` -- the helper is in /app/bin, and our PATH did not include it.
NOT_FORWARDED_TO_SANDBOX = frozenset({"PATH"})

#: Supervisor restart schedule, in seconds, settling at a steady interval.
#:
#: Mirrors the helper's own internal reconnect schedule so the two do not fight: a
#: doubling backoff on top of a 1s inner retry produced a burst of failures per second
#: against an unreachable server, which on a battery-powered device is pure waste.
RESTART_SCHEDULE_S = (1, 2, 5, 10, 15, 30)

#: Logical screen size claimed when libei reports no usable region.
#:
#: This must match the compositor's pointer coordinate space, which is NOT necessarily
#: the panel resolution: gamescope runs a nested surface and scales it, so a Deck
#: docked to a 4K display can have a 2560x1600 pointer space. Getting it wrong is
#: immediately visible -- the pointer stops partway across the screen.
DEFAULT_SCREEN_SIZE = (1280, 800)

TERMINATE_GRACE_S = 5


class LaunchError(Exception):
    pass


def _clean(field, value):
    text = str(value)
    for bad in _FORBIDDEN_IN_ARGUMENT:
        if bad in text:
            raise LaunchError(f"{field} contains an illegal character")
    return text


def find_stray_helpers(app_id=APP_ID, proc_root="/proc", own_pid=None):
    """PIDs of helper processes belonging to ``app_id`` that we do not own.

    A helper orphaned by a crash keeps Deskflow's single-instance lock, and every
    later start then fails with "an instance of deskflow core is already running" --
    a permanently wedged plugin that no amount of retrying fixes. Killing our own
    process group handles the normal case; this covers processes whose parent already
    died, where there is no group left to signal.

    Matching is on the app id appearing in the command line, so only this project's
    own helper can ever be selected.
    """
    if own_pid is None:
        own_pid = os.getpid()

    found = []
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return found

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == own_pid:
            continue
        try:
            with open(os.path.join(proc_root, entry, "cmdline"), "rb") as handle:
                cmdline = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if app_id in cmdline and HELPER_COMMAND in cmdline:
            found.append(pid)
    return found


def is_gamescope_running(proc_root="/proc"):
    """Whether Gamescope's own compositor process is alive right now.

    The only reliable way to tell Gaming Mode from Desktop Mode from inside this
    process. ``plugin_loader`` is a bare systemd *system* service with no graphical
    session environment at all -- confirmed on hardware, 2026-08-22: WAYLAND_DISPLAY
    is simply absent from its environ, in Gaming Mode or Desktop Mode alike, so a
    check like ``os.environ.get("WAYLAND_DISPLAY", "").startswith("gamescope")``
    silently returns "not gaming" unconditionally, forever. Gamescope's own process
    presence does not depend on what plugin_loader happened to inherit at boot.
    """
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return False

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, entry, "cmdline"), "rb") as handle:
                cmdline = handle.read()
        except OSError:
            continue
        argv0 = cmdline.split(b"\x00", 1)[0]
        # basename: the real binary is /usr/bin/gamescope, argv[0] may be either.
        # Exact match, not a substring test: must not also match "start-gamescope"
        # (the wrapper script) or "gamescope-session" (the systemd target/wrapper).
        if os.path.basename(argv0) == b"gamescope":
            return True
    return False


def clean_subprocess_env(source=None):
    """An environment safe for launching *system* binaries from the Decky backend.

    Decky runs plugins inside a PyInstaller bundle, which prepends its own unpacked
    library directory to ``LD_LIBRARY_PATH``. A system binary inherited into that
    environment resolves against the bundle's libraries instead of the system's, and
    fails. Observed on hardware as::

        openssl: /tmp/_MEIxxxxxx/libssl.so.3: version `OPENSSL_3.4.0' not found

    PyInstaller preserves whatever was there before in ``LD_LIBRARY_PATH_ORIG``, so
    restore that when present and otherwise drop the variable entirely.
    """
    env = dict(os.environ if source is None else source)

    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)

    # Other markers of the frozen bundle; harmless to remove, confusing to inherit.
    for name in ("_MEIPASS2", "LD_PRELOAD_ORIG", "PYINSTALLER_RESET_ENVIRONMENT"):
        env.pop(name, None)

    return env


def resolve_backend(requested, discovery, display=None):
    """Turn the configured backend into the one that will actually be used.

    An explicitly chosen backend is never silently substituted: a fallback the user
    did not ask for would make the diagnostics display a lie.
    """
    if requested == "auto":
        if discovery is not None and discovery.found:
            return "gamescope-libei"
        if display:
            return "x11-xtest"
        raise LaunchError(
            "No input backend is available: Gamescope's input socket was not found "
            "and no X display is set."
        )

    if requested in BACKENDS_NEEDING_SOCKET and not (discovery is not None and discovery.found):
        raise LaunchError(
            "The Gamescope input backend was selected but its socket was not found."
        )
    if requested == "x11-xtest" and not display:
        # Not fatal here: the caller may know the display. Only complain when it is
        # genuinely absent at launch time.
        return requested
    return requested


def build_environment(
    settings, backend, discovery, display=None, home=None, screen_size=None
):
    """The complete environment for the helper, built from nothing.

    Inheriting Decky's environment would hand the helper a pile of variables it has no
    use for, and would make behaviour depend on how the loader happened to be started.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env = {
        "HOME": home or os.environ.get("HOME", ""),
        "PATH": "/usr/bin:/bin",
        "XDG_RUNTIME_DIR": runtime_dir,
    }

    if backend == "gamescope-libei":
        if discovery is None or not discovery.found:
            raise LaunchError("the Gamescope input socket is not available")
        env["LIBEI_SOCKET"] = _clean("socket path", discovery.path)
        # Read by the patch in helper/patches; without it upstream Deskflow takes the
        # portal path, which has no backend behind Gamescope.
        env["DESKFLOW_EI_BACKEND"] = "socket"
        env["XDG_SESSION_TYPE"] = "wayland"
        # libei talks to the EIS socket directly, so the Qt platform does not need a
        # display. Confirmed working on hardware.
        env["QT_QPA_PLATFORM"] = "offscreen"
        # Gamescope's virtual devices are relative-only, so libei reports no region and
        # the patched helper needs to be told what screen shape to announce. Without
        # this it claims 1x1, which the server rejects and which strands the pointer.
        width, height = screen_size or DEFAULT_SCREEN_SIZE
        env["DESKFLOW_SCREEN_SIZE"] = f"{width}x{height}"

    elif backend == "x11-xtest":
        # PlatformInfo::isWayland() tests XDG_SESSION_TYPE, and that is what makes
        # Deskflow choose XWindowsScreen/XTest over EiScreen.
        env["XDG_SESSION_TYPE"] = "x11"
        env["QT_QPA_PLATFORM"] = "xcb"
        if display:
            env["DISPLAY"] = _clean("display", display)

    elif backend == "uinput":
        env["XDG_SESSION_TYPE"] = "x11"
        env["QT_QPA_PLATFORM"] = "offscreen"

    else:
        raise LaunchError(f"unknown input backend: {backend}")

    layout = settings.get("keyboard_layout", "")
    if layout:
        env["XKB_DEFAULT_LAYOUT"] = _clean("keyboard layout", layout)
        if backend == "gamescope-libei":
            # Replay the server's physical key positions and let gamescope's keymap
            # (set to the same layout via environment.d) decide the characters. This
            # is what makes the chosen layout hold regardless of the server's layout.
            env["DESKFLOW_KEYBOARD_POSITIONAL"] = "1"

    return {key: str(value) for key, value in env.items() if value != ""}


def build_command(
    settings, config_path, backend, discovery, display=None, app_id=APP_ID, screen_size=None,
):
    """Build the flatpak invocation as an argument list."""
    subcommand = "server" if settings["mode"] == "server" else "client"
    env = build_environment(
        settings, backend, discovery, display=display, screen_size=screen_size,
    )

    argv = ["flatpak", "run", "--user", f"--command={HELPER_COMMAND}"]
    for key in sorted(env):
        if key in NOT_FORWARDED_TO_SANDBOX:
            continue
        argv.append(f"--env={key}={_clean(key, env[key])}")

    if backend in BACKENDS_NEEDING_SOCKET:
        # Scope the sandbox grant to exactly the one socket, never a directory.
        argv.append("--filesystem={}".format(_clean("socket path", discovery.path)))

    argv.append(_clean("app id", app_id))
    argv.append(subcommand)
    argv += ["-s", _clean("config path", config_path)]
    return argv


def next_backoff_delay(attempt, maximum):
    """Delay before restart attempt ``attempt`` (1-based), capped at ``maximum``.

    Walks RESTART_SCHEDULE_S and then holds at its last value, rather than doubling
    without limit: a server that is merely switched off should be retried steadily and
    cheaply, not with ever-growing gaps.
    """
    if attempt < 1:
        attempt = 1
    index = min(attempt - 1, len(RESTART_SCHEDULE_S) - 1)
    return min(RESTART_SCHEDULE_S[index], maximum)


class HelperProcess:
    """Owns the child process. Knows nothing about settings beyond what it is handed."""

    def __init__(self, logger=None, spawn=None):
        self._logger = logger
        self._spawn = spawn or asyncio.create_subprocess_exec
        self._process = None
        self._reader = None

    @property
    def running(self):
        return self._process is not None and self._process.returncode is None

    @property
    def pid(self):
        return self._process.pid if self._process is not None else None

    async def start(self, argv, env, on_line=None):
        if self.running:
            raise LaunchError("the helper is already running")
        self._log("info", "Starting helper: %s", " ".join(argv))

        try:
            process = await self._spawn(
                *argv,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                # Own process group, so stop() can signal the whole tree.
                # `flatpak run` execs bwrap which runs deskflow-core; killing only our
                # direct child leaves the sandboxed process alive, and Deskflow then
                # refuses every future start with "an instance is already running".
                # `flatpak kill` is not a reliable cleanup either -- once the parent
                # dies the instance registry loses track and reports "not running"
                # while the process is plainly still there.
                start_new_session=True,
            )
        except BaseException:
            # Never leave a previous, already-dead process object behind: `pid` would
            # then report a stale value and `wait()` would return instantly, spinning
            # the supervisor.
            self._process = None
            raise

        self._process = process
        # The pipe MUST be drained. A Linux pipe buffer is ~64KB; once a chatty child
        # fills it the child's next write() blocks forever, and a wedged helper cannot
        # respond to SIGTERM -- which means it never releases held keys and buttons.
        self._reader = asyncio.get_event_loop().create_task(self._drain(process, on_line))
        return process.pid

    async def _drain(self, process, on_line):
        stream = process.stdout
        if stream is None:
            return
        try:
            while True:
                raw = await stream.readline()
                if not raw:
                    return
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if on_line is not None:
                    try:
                        on_line(line)
                    except Exception:  # noqa: BLE001 - an observer must not kill the drain
                        self._log("warning", "Helper output observer raised; continuing")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - draining is best-effort, never fatal
            self._log("warning", "Stopped reading helper output")

    async def _stop_reader(self):
        if self._reader is None:
            return
        self._reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._reader
        self._reader = None

    def _signal_group(self, process, sig):
        """Signal the helper's whole process group, falling back to the child alone."""
        try:
            os.killpg(os.getpgid(process.pid), sig)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            process.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass

    async def stop(self, grace=TERMINATE_GRACE_S):
        """Ask, then wait, then force -- and confirm death before reporting success."""
        process = self._process
        if process is None or process.returncode is not None:
            await self._stop_reader()
            self._process = None
            return True

        self._signal_group(process, signal.SIGTERM)

        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
        except TimeoutError:
            self._log("warning", "Helper did not exit within %ss; killing it", grace)
            self._signal_group(process, signal.SIGKILL)
            try:
                await asyncio.wait_for(process.wait(), timeout=grace)
            except TimeoutError:
                self._log("error", "Helper could not be killed")
                await self._stop_reader()
                return False

        await self._stop_reader()
        self._process = None
        return True

    async def wait(self):
        if self._process is None:
            return None
        return await self._process.wait()

    def _log(self, level, message, *args):
        if self._logger is not None:
            getattr(self._logger, level, self._logger.info)(message, *args)
