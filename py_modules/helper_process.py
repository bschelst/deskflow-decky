"""Lifecycle of the Deskflow helper flatpak.

Everything that builds a command or an environment is a pure function so it can be
asserted in tests. The async supervisor around them stays thin.

The command is always an argument list handed to ``create_subprocess_exec``. No shell
is involved anywhere in this module, and configuration travels through the INI file
rather than argv, which is world-readable via ``/proc/<pid>/cmdline``.
"""

import asyncio
import os

__all__ = [
    "APP_ID",
    "HelperProcess",
    "LaunchError",
    "build_command",
    "build_environment",
    "next_backoff_delay",
    "resolve_backend",
]

#: Our own application ID. Never reuse upstream's org.deskflow.deskflow -- colliding
#: with it would break a user's existing Flathub install.
APP_ID = "io.github.bschelst.DeskflowDeck"

HELPER_COMMAND = "deskflow-core"
BACKENDS_NEEDING_SOCKET = ("gamescope-libei",)
_FORBIDDEN_IN_ARGUMENT = ("\n", "\r", "\x00")

INITIAL_BACKOFF_S = 1
BACKOFF_FACTOR = 2
TERMINATE_GRACE_S = 5


class LaunchError(Exception):
    pass


def _clean(field, value):
    text = str(value)
    for bad in _FORBIDDEN_IN_ARGUMENT:
        if bad in text:
            raise LaunchError("{0} contains an illegal character".format(field))
    return text


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


def build_environment(settings, backend, discovery, display=None, home=None):
    """The complete environment for the helper, built from nothing.

    Inheriting Decky's environment would hand the helper a pile of variables it has no
    use for, and would make behaviour depend on how the loader happened to be started.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/{0}".format(os.getuid())
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
        # display. Verify on hardware before relying on this (PROJECT.md M2c).
        env["QT_QPA_PLATFORM"] = "offscreen"

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
        raise LaunchError("unknown input backend: {0}".format(backend))

    return {key: str(value) for key, value in env.items() if value != ""}


def build_command(settings, config_path, backend, discovery, display=None, app_id=APP_ID):
    """Build the flatpak invocation as an argument list."""
    subcommand = "server" if settings["mode"] == "server" else "client"
    env = build_environment(settings, backend, discovery, display=display)

    argv = ["flatpak", "run", "--user", "--command={0}".format(HELPER_COMMAND)]
    for key in sorted(env):
        argv.append("--env={0}={1}".format(key, _clean(key, env[key])))

    if backend in BACKENDS_NEEDING_SOCKET:
        # Scope the sandbox grant to exactly the one socket, never a directory.
        argv.append("--filesystem={0}".format(_clean("socket path", discovery.path)))

    argv.append(_clean("app id", app_id))
    argv.append(subcommand)
    argv += ["-s", _clean("config path", config_path)]
    return argv


def next_backoff_delay(attempt, maximum):
    """Bounded exponential backoff. Attempt is 1-based."""
    if attempt < 1:
        attempt = 1
    delay = INITIAL_BACKOFF_S * (BACKOFF_FACTOR ** (attempt - 1))
    return min(delay, maximum)


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
        try:
            await self._reader
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._reader = None

    async def stop(self, grace=TERMINATE_GRACE_S):
        """Ask, then wait, then force -- and confirm death before reporting success."""
        process = self._process
        if process is None or process.returncode is not None:
            await self._stop_reader()
            self._process = None
            return True

        try:
            process.terminate()
        except ProcessLookupError:
            await self._stop_reader()
            self._process = None
            return True

        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
        except asyncio.TimeoutError:
            self._log("warning", "Helper did not exit within %ss; killing it", grace)
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=grace)
            except asyncio.TimeoutError:
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
