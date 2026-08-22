"""Decky backend for deskflow-decky.

Every public method is decorated with ``@safe`` and returns the uniform envelope from
``py_modules/envelope.py``. None of them raise: an unhandled exception here surfaces as
a rejected promise in the frontend and, if it reaches a render path, can unmount the
Quick Access Menu -- which in Gaming Mode is genuinely hard to recover from.
"""

import asyncio
import contextlib
import os
import signal
from asyncio import create_subprocess_exec as spawn_process  # argv list only, no shell

from deskflow_config import write_config
from desktop_deskflow import (
    DESKTOP_APP_ID,
    SyncError,
    bootstrap_client_config,
    desktop_client_config_needs_bootstrap,
    desktop_config_path,
    is_desktop_app_running,
    read_desktop_identity,
    sync_desktop_identity,
    write_autostart_entry,
)
from diagnostics import build_report, redact_line
from discovery import discover_socket
from envelope import err, ok, safe, set_logger
from helper_process import (
    APP_ID,
    HelperProcess,
    LaunchError,
    build_command,
    build_environment,
    clean_subprocess_env,
    find_stray_helpers,
    is_gamescope_running,
    next_backoff_delay,
    resolve_backend,
)
from identity import derive_client_name
from log_watch import FingerprintWatcher, classify_connection, eis_disconnected
from screen_size import choose_screen_size, detection_commands
from session_env import sync_keyboard_layout
from settings import SettingsManager  # provided by the loader
from state import HelperState, IllegalTransition
from tls import (
    PinnedHosts,
    TrustStore,
    ensure_certificate,
    format_fingerprint,
    write_private,
)
from validation import DEFAULTS, sanitize_loaded, validate_patch

import decky


class CommandTimeout(RuntimeError):
    """A subprocess exceeded its deadline. Mapped to the `timeout` error code."""

SETTINGS_DIR = decky.DECKY_PLUGIN_SETTINGS_DIR
RUNTIME_DIR = decky.DECKY_PLUGIN_RUNTIME_DIR
LOG_DIR = decky.DECKY_PLUGIN_LOG_DIR

# The helper runs inside a flatpak sandbox and cannot see Decky's directories at all.
# Anything it must READ therefore lives in its own app config tree, which the sandbox
# always has access to -- writing there needs no extra --filesystem grant, and widening
# the sandbox to reach ~/homebrew would be a much worse trade.
#
# Found the hard way on hardware: with the config under RUNTIME_DIR, QSettings pointed
# at an unreadable path, returned empty values, and the helper died with
# "No server addresses configured" while claiming to have loaded the file.
HELPER_CONFIG_DIR = os.path.join(
    decky.HOME, ".var", "app", APP_ID, "config", "Deskflow"
)
CONFIG_PATH = os.path.join(HELPER_CONFIG_DIR, "Deskflow.conf")
TLS_DIR = os.path.join(HELPER_CONFIG_DIR, "tls")
CERT_PATH = os.path.join(TLS_DIR, "deskflow.pem")
TRUSTED_SERVERS_PATH = os.path.join(TLS_DIR, "trusted-servers")

#: The stock Deskflow desktop app's own config, a completely separate flatpak install.
DESKTOP_DESKFLOW_CONFIG_PATH = desktop_config_path(decky.HOME)

# Plugin-owned state the helper never reads stays in Decky's own directories.
PINNED_HOSTS_PATH = os.path.join(SETTINGS_DIR, "pinned-hosts.json")
RELAY_PATH = os.path.join(RUNTIME_DIR, "eis-socket")

STATE_EVENT = "deskflow_state"
NOTIFY_EVENT = "deskflow_notify"

#: States that mean "we had a working connection and lost it".
_LOST_STATES = ("disconnected", "error")
_HEALTHY_STATES = ("connected", "degraded")
MAX_LOG_LINES = 1000
MAX_CONSECUTIVE_FAILURES = 5
SUBPROCESS_TIMEOUT_S = 30

#: How long the helper must stay up before a run counts as a real connection.
#: `flatpak run` against an app that is not installed spawns successfully and exits
#: within milliseconds, so "the process started" is not evidence of anything.
MIN_HEALTHY_UPTIME_S = 5

#: How long to wait when probing whether the server accepts connections.
SERVER_PROBE_TIMEOUT_S = 4

#: `flatpak install` fetches over the network; generous on purpose.
INSTALL_TIMEOUT_S = 180

#: The offscreen bootstrap launch of the desktop app: always runs the full duration
#: (nothing makes a GUI app exit on its own), so this is a deliberate wait, not a
#: generous ceiling. 6s matched hardware testing (2026-08-22) -- long enough for Qt to
#: write its default config, short enough not to make "Install" feel stuck.
BOOTSTRAP_LAUNCH_TIMEOUT_S = 6

#: How often to poll for Gaming Mode returning. A cheap env-var read, not a subprocess
#: call, so polling this often costs nothing worth avoiding; the point is noticing the
#: return promptly, not saving cycles.
GAMING_MODE_POLL_INTERVAL_S = 3

#: Autostart retry schedule for the boot race: plugin_loader regularly comes up
#: before gamescope has created its EIS socket, and a single attempt then parks the
#: plugin in "error" until someone presses start. Retry while the socket is simply
#: not there yet; give up only once the schedule is exhausted (~90s covers even a
#: slow session start). Manual starts are unaffected and stay single-shot.
AUTOSTART_RETRY_DELAYS_S = (2, 3, 5, 5, 10, 15, 15, 15, 20)

#: Error codes that mean "the environment is not ready yet", worth retrying at boot.
_AUTOSTART_RETRYABLE = ("socket_not_found", "backend_unavailable")

#: Minimum seconds between two toast notifications. A server that is stopped and
#: restarted rapidly would otherwise produce a connected/disconnected pair per cycle.
NOTIFY_COOLDOWN_S = 60

_LOG_SEVERITY = {"error": 0, "warn": 1, "info": 2, "debug": 3}


_ALWAYS_LOG = ("LANGUAGES", "LANGUAGE", "KEYMAP", "XKB")


def _should_log_helper_line(line, configured_level):
    """Return True if this helper output line passes the configured log level filter.

    The helper prefixes lines with ``INFO:``, ``WARNING:``, ``NOTE:``, ``IPC:``, etc.
    Anything at or above the configured severity passes; unrecognised prefixes always pass.
    Diagnostic lines about languages and keymaps always pass regardless of level.
    """
    upper = line.upper()
    if any(kw in upper for kw in _ALWAYS_LOG):
        return True
    threshold = _LOG_SEVERITY.get(configured_level, 2)
    if "ERROR:" in upper or "FATAL:" in upper:
        return True
    if "WARNING:" in upper:
        return threshold >= 1
    if "INFO:" in upper or "NOTE:" in upper or "IPC:" in upper:
        return threshold >= 2
    if "DEBUG:" in upper:
        return threshold >= 3
    return True


async def run_command(argv, timeout=SUBPROCESS_TIMEOUT_S):
    """Run an argument list and return stdout.

    ``spawn_process`` is ``asyncio.create_subprocess_exec``: it takes an argv list and
    never involves a shell, so no value here can become a second command.

    The environment is scrubbed of PyInstaller's bundled library path first -- Decky
    runs plugins inside a frozen bundle, and a system binary that inherits it resolves
    against the wrong libraries.
    """
    process = await spawn_process(
        *argv,
        env=clean_subprocess_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise CommandTimeout(f"command timed out: {argv[0]}") from None
    if process.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"{argv[0]} failed: {detail[:200]}")
    return stdout


def _is_gaming_mode():
    """Whether the deck is currently in Gaming Mode.

    Not an env var check: plugin_loader is a bare systemd system service with no
    graphical session environment at all (confirmed on hardware, 2026-08-22 --
    WAYLAND_DISPLAY is simply absent from its environ), so that used to silently
    return False unconditionally, forever, regardless of the actual mode.
    """
    return is_gamescope_running()


class Plugin:
    # ----------------------------------------------------------------- lifecycle

    async def _main(self):
        set_logger(decky.logger)
        self._loop = asyncio.get_event_loop()
        self._settings_manager = SettingsManager(name="settings", settings_directory=SETTINGS_DIR)
        self._helper = HelperProcess(logger=decky.logger)
        self._state = HelperState(on_change=self._on_state_change)
        self._trust = TrustStore(TRUSTED_SERVERS_PATH)
        self._pins = PinnedHosts(PINNED_HOSTS_PATH)
        self._supervisor = None
        self._resolved_backend = None
        self._pending_fingerprint = None
        self._last_discovery = None
        self._input_released_on_last_stop = None
        self._resolved_backend_reported = None
        self._helper_started_at = None
        self._helper_installed = None
        self._screen_size = None
        # One notification per outage, not one per reconnect attempt.
        self._notified_disconnect = False
        # One 'connected' announcement per helper start, not per reconnect.
        self._announced_connection = False
        self._last_notify_at = 0.0
        # Distinguishes 'never worked' (bad config) from 'worked then dropped' (outage).
        self._had_healthy_connection = False
        # Guards against scheduling _stop() once per buffered line: deskflow-core can
        # log the eis-lost warning several times before the first stop task even runs.
        self._eis_lost_stop_scheduled = False
        # True only while a stop was ours, for leaving Gaming Mode -- not a manual
        # stop, not the crash-loop failsafe. Only this case should ever be resumed
        # automatically; the other two are the user's or the failsafe's decision to
        # respect, not override.
        self._stopped_for_desktop_mode = False
        self._gaming_mode_watcher = None
        self._watcher = FingerprintWatcher(
            on_fingerprint=self._on_peer_fingerprint, logger=decky.logger
        )
        # Serialises start/stop/retry. Without it two concurrent calls can each pass
        # the "already running" check before either has spawned, and the second spawn
        # silently orphans the first process.
        self._lifecycle = asyncio.Lock()

        self._settings = self._load_settings()

        # A helper orphaned by a previous run (loader crash, forced restart) would
        # block every start from here on, so clear the ground before doing anything.
        await self._kill_helper_app()

        if self._settings.get("autostart_gaming_mode"):
            decky.logger.info("Autostart is enabled; starting helper.")
            # As a task: _main must not block the loader for the whole retry schedule.
            self._loop.create_task(self._autostart_with_patience())

        # plugin_loader runs continuously across a Gaming <-> Desktop switch -- _main
        # only ever runs once, at boot or plugin reload. Nothing else notices Gaming
        # Mode coming back, so without this the helper stays stopped until the user
        # restarts it by hand.
        self._gaming_mode_watcher = self._loop.create_task(self._watch_for_gaming_mode_return())

        decky.logger.info("deskflow-decky backend ready.")

    async def _unload(self):
        decky.logger.info("Unloading; stopping helper.")
        if self._gaming_mode_watcher is not None:
            self._gaming_mode_watcher.cancel()
        await self._stop()

    async def _uninstall(self):
        # Leaving a running helper or held input behind on uninstall would be both a
        # bug and a security problem.
        await self._stop()

    async def _migration(self):
        decky.migrate_logs(
            os.path.join(decky.DECKY_USER_HOME, ".config", "deskflow-decky", "logs")
        )
        decky.migrate_settings(os.path.join(decky.DECKY_USER_HOME, ".config", "deskflow-decky"))

    # ----------------------------------------------------------------- settings

    def _load_settings(self):
        self._settings_manager.read()
        raw = self._settings_manager.getSetting("settings", None)
        first_run = raw is None
        settings, warnings = sanitize_loaded(raw if raw is not None else dict(DEFAULTS))
        for warning in warnings:
            decky.logger.warning(warning)

        if first_run:
            # Every Steam Deck and Steam Machine is called "steamdeck" out of the box,
            # so that name collides the moment a second one talks to the same server.
            # Derive a stable, machine-unique one instead.
            #
            # Only on first run: the name has to match a screen in the server's layout,
            # so silently renaming an already-configured install would break a setup
            # that works.
            settings["client_name"] = derive_client_name()
            self._settings_manager.setSetting("settings", settings)
            decky.logger.info(
                "First run: this Deck will identify itself as '%s'. Add a screen with "
                "that name to your Deskflow server's layout.",
                settings["client_name"],
            )

        return settings

    @safe
    async def get_settings(self):
        return ok(dict(self._settings))

    @safe
    async def set_settings(self, patch):
        # validate_patch raises ValidationError, which @safe converts into a validation
        # envelope naming the offending field. Nothing is stored unless all of it passes.
        updated = validate_patch(patch, self._settings)
        self._settings = updated
        self._settings_manager.setSetting("settings", updated)
        decky.logger.info("Settings updated: %s", ", ".join(sorted(patch)))
        if "keyboard_layout" in patch:
            changed = sync_keyboard_layout(
                decky.DECKY_USER_HOME, updated.get("keyboard_layout", ""), decky.logger
            )
            if changed:
                decky.logger.info(
                    "Gamescope reads the layout at session start: restart Gaming Mode "
                    "for the new keyboard layout to take effect."
                )
        return ok(dict(updated))

    # ----------------------------------------------------------------- status

    def _status_payload(self):
        snapshot = self._state.snapshot()
        snapshot.update(
            {
                "backend": self._resolved_backend,
                "requested_backend": self._settings.get("input_backend"),
                "mode": self._settings.get("mode"),
                "server": self._settings.get("server_host"),
                "server_port": self._settings.get("server_port"),
                "client_name": self._settings.get("client_name"),
                # There is no way to pause injection without dropping the connection
                # -- deskflow-core has no such control channel -- so this now just
                # mirrors whether the helper is running rather than tracking a
                # separate flag nothing ever enforced.
                "input_enabled": self._helper.running,
                "fingerprint_pending": self._pending_fingerprint is not None,
                "gaming_mode": _is_gaming_mode(),
            }
        )
        return snapshot

    def _notify(self, title, body):
        """Send one toast, if the user wants them. Never raises into a state callback."""
        if not self._settings.get("notifications_enabled", True):
            return
        now = self._loop.time()
        if now - self._last_notify_at < NOTIFY_COOLDOWN_S:
            return
        self._last_notify_at = now
        self._loop.create_task(decky.emit(NOTIFY_EVENT, {"title": title, "body": body}))

    def _server_label(self):
        return self._settings.get("server_host") or "the Deskflow server"

    def _notify_disconnected(self, reason):
        """Tell the user once that a working connection dropped.

        Once per outage: the supervisor retries on a schedule, and a toast per attempt
        would be worse than no toast at all. Cleared when a connection succeeds.
        """
        if self._notified_disconnect:
            return
        self._notified_disconnect = True
        self._notify(
            "Deskflow Decky disconnected",
            "Lost the connection to {}. {}".format(
                self._server_label(),
                "Reconnecting automatically."
                if self._settings.get("reconnect_enabled")
                else "Automatic reconnect is off.",
            ),
        )

    def _notify_reconnected(self):
        """Announce recovery, but only as the counterpart to a loss already announced.

        Paired with _notify_disconnected via the same flag, so the two always come in
        twos: one "lost", one "back". A flapping link produces a pair per outage rather
        than a stream, and never a lone "reconnected" out of nowhere.
        """
        self._notify(
            "Deskflow Decky reconnected", f"Connected to {self._server_label()} again."
        )

    def _on_state_change(self, origin, target, reason):
        decky.logger.info("State %s -> %s (%s)", origin, target, reason or "no reason given")

        if target in _HEALTHY_STATES:
            if not self._announced_connection:
                # First connection since the helper was started: say so once, so the
                # user knows it came up without having to open the panel.
                self._announced_connection = True
                self._notify(
                    "Deskflow Decky connected",
                    f"Keyboard and mouse from {self._server_label()} are available.",
                )
            elif self._notified_disconnect:
                # Only announce a recovery if a loss was announced. A blip that never
                # produced a "disconnected" toast must not produce a "reconnected" one.
                self._notify_reconnected()
            self._notified_disconnect = False
            self._had_healthy_connection = True
        elif target in _LOST_STATES and origin in _HEALTHY_STATES:
            self._notify_disconnected(reason)
        # Push rather than making the UI poll; the frontend poll is only a safety net
        # for a missed event.
        self._loop.create_task(decky.emit(STATE_EVENT, self._status_payload()))

    @safe
    async def get_status(self):
        return ok(self._status_payload())

    # ----------------------------------------------------------------- helper control

    async def _detect_screen_size(self):
        """Ask the running session how large its pointer space is.

        Read-only queries against the session's own X server. Nothing is hardcoded to a
        particular device: whatever this machine reports is what gets announced.
        """
        display = os.environ.get("DISPLAY") or ":0"
        for argv, parse, _ in detection_commands(display):
            try:
                env = clean_subprocess_env()
                env["DISPLAY"] = display
                process = await spawn_process(
                    *argv, env=env, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
            except Exception:  # noqa: BLE001 - a missing tool is not an error here
                decky.logger.debug("Probe via %s did not work; trying the next tool.", argv[0])
                continue
            size = parse(stdout.decode("utf-8", "replace"))
            if size:
                decky.logger.info("Detected pointer space %sx%s via %s", size[0], size[1], argv[0])
                return size
        decky.logger.warning("Could not detect the pointer space; using the fallback size.")
        return None

    async def _resolve_screen_size(self):
        configured_w = self._settings.get("screen_width") or 0
        configured_h = self._settings.get("screen_height") or 0
        detected = None
        if not (configured_w and configured_h):
            detected = await self._detect_screen_size()
        size = choose_screen_size(configured_w, configured_h, detected)
        self._screen_size = size
        return size

    async def _prepare_launch(self):
        """Discover, resolve, and render everything needed to start. Raises LaunchError."""
        settings = self._settings
        discovery = discover_socket(settings, relay_path=RELAY_PATH)
        self._last_discovery = discovery
        display = os.environ.get("DISPLAY")

        backend = resolve_backend(settings["input_backend"], discovery, display)
        screen_size = await self._resolve_screen_size()
        env = build_environment(
            settings, backend, discovery, display=display, screen_size=screen_size,
        )
        argv = build_command(
            settings, CONFIG_PATH, backend, discovery, display=display, app_id=APP_ID,
            screen_size=screen_size,
        )
        return backend, argv, env, discovery

    def _on_peer_fingerprint(self, fingerprint):
        """Called from the helper's output drain when a peer presents a certificate."""
        host = self._settings.get("server_host", "")
        classification = self._pins.classify(host, fingerprint)

        if classification == "trusted":
            return

        # Unknown or changed: hold it for the user. The UI presents the two cases
        # differently -- a change on a previously trusted server may be interception.
        self._pending_fingerprint = fingerprint
        decky.logger.warning(
            "Server certificate awaiting a trust decision (%s).", classification
        )
        self._loop.create_task(decky.emit(STATE_EVENT, self._status_payload()))

    async def _start(self):
        async with self._lifecycle:
            return await self._start_locked()

    def _autostart_may_retry(self, result):
        """Whether an autostart attempt failed only because the session is not up yet."""
        if not isinstance(result, dict) or result.get("ok"):
            return False
        error = result.get("error") or {}
        return error.get("code") in _AUTOSTART_RETRYABLE

    async def _autostart_with_patience(self):
        result = await self._start()
        for delay in AUTOSTART_RETRY_DELAYS_S:
            if not self._autostart_may_retry(result):
                return
            await asyncio.sleep(delay)
            # The user may have started, stopped, or reconfigured in the meantime;
            # then this boot-time courtesy is over.
            if self._helper.running or self._state.state != "error":
                return
            decky.logger.info("Input socket not there yet; retrying autostart.")
            result = await self._start()
        if self._autostart_may_retry(result):
            decky.logger.warning(
                "Autostart gave up: the Gamescope input socket never appeared."
            )

    async def _watch_for_gaming_mode_return(self):
        """Restart the helper when Gaming Mode comes back, if we stopped it ourselves.

        plugin_loader runs continuously across a mode switch, so nothing else ever
        notices Gaming Mode returning -- without this, the eis-lost stop earlier
        leaves the helper down until the user restarts it by hand every single time.

        Only resumes a stop this exact code path caused (_stopped_for_desktop_mode).
        A manual stop or the crash-loop failsafe are the user's or the failsafe's
        decision to respect, not something to override the moment Gamescope reappears.
        """
        was_gaming = _is_gaming_mode()
        try:
            while True:
                await asyncio.sleep(GAMING_MODE_POLL_INTERVAL_S)
                now_gaming = _is_gaming_mode()
                if (
                    now_gaming
                    and not was_gaming
                    and self._stopped_for_desktop_mode
                    and self._settings.get("autostart_gaming_mode")
                    and not self._helper.running
                ):
                    self._stopped_for_desktop_mode = False
                    decky.logger.info("Gaming Mode returned; restarting the helper.")
                    self._loop.create_task(self._autostart_with_patience())
                was_gaming = now_gaming
        except asyncio.CancelledError:
            raise

    async def _start_locked(self):
        if self._helper.running:
            return err("already_running", "The helper is already running.")

        # A genuine new start, manual or automatic, always supersedes the reason the
        # helper was last stopped.
        self._stopped_for_desktop_mode = False

        settings = self._settings

        if settings["mode"] == "client" and not settings["server_host"]:
            return err("not_configured", "Set the Deskflow server address first.")

        if settings["mode"] == "server" and _is_gaming_mode():
            # Deskflow's server role needs the InputCapture portal, which has no
            # backend behind Gamescope. Refusing is honest; silently switching to
            # client mode would not be.
            return err(
                "server_mode_unsupported",
                "Server mode cannot capture input in Gaming Mode. Switch to Desktop "
                "Mode, or set this Deck to client mode.",
            )

        self._to_state("starting")
        await self.get_helper_info()  # refreshes self._helper_installed

        try:
            if settings["tls_enabled"]:
                await ensure_certificate(CERT_PATH, settings["client_name"], run_command)
            write_config(CONFIG_PATH, settings, cert_path=CERT_PATH)
            backend, argv, env, _discovery = await self._prepare_launch()
        except LaunchError as exc:
            self._to_state("error", reason=str(exc))
            found = self._last_discovery is not None and self._last_discovery.found
            return err("backend_unavailable" if found else "socket_not_found", str(exc))
        except CommandTimeout:
            decky.logger.exception("Preparation timed out")
            self._to_state("error", reason="preparation timed out")
            return err("timeout", "Preparing the helper took too long. Try again.")
        except Exception:  # noqa: BLE001 - reported to the user, not swallowed
            # The exception text can carry paths and hostnames, so it stays in the log;
            # the same discipline envelope.safe applies to unexpected faults.
            decky.logger.exception("Could not prepare the helper")
            self._to_state("error", reason="preparation failed")
            return err(
                "tls_setup_failed",
                "Could not prepare the helper. See the plugin log for details.",
            )

        self._resolved_backend = backend
        self._watcher.reset()
        self._eis_lost_stop_scheduled = False

        try:
            await self._helper.start(argv, env, on_line=self._on_helper_line)
            self._helper_started_at = self._loop.time()
        except Exception:  # noqa: BLE001
            decky.logger.exception("Helper failed to start")
            self._to_state("error", reason="helper failed to start")
            return err("internal", "The helper could not be started. See the plugin log.")

        # Stays in "starting" until the helper proves it can survive; _supervise
        # promotes it. Claiming "connected" on spawn is a lie a crashing helper
        # exposes immediately.
        self._supervisor = self._loop.create_task(self._supervise())
        return ok({"state": self._state.state})

    async def _trip_autostart_failsafe(self, failures):
        """Stop starting the helper by itself once it has proven it cannot run.

        Without this, a helper that crashes immediately is retried on every boot and
        every plugin reload, forever, with nobody watching. Turning autostart off is
        recoverable in one tap; an unattended crash loop is not.

        Only autostart is disabled -- a manual start still works, so the user can retry
        after fixing whatever was wrong.
        """
        if not self._settings.get("autostart_gaming_mode"):
            return
        if self._had_healthy_connection:
            # It worked at some point this session, so this is an outage rather than a
            # broken configuration. Leave autostart alone.
            return

        try:
            self._settings = validate_patch({"autostart_gaming_mode": False}, self._settings)
            self._settings_manager.setSetting("settings", self._settings)
        except Exception:  # noqa: BLE001
            decky.logger.exception("Could not disable autostart")
            return

        decky.logger.warning(
            "Disabled autostart after %s consecutive failures without a working connection.",
            failures,
        )
        if self._settings.get("notifications_enabled", True):
            self._loop.create_task(
                decky.emit(
                    NOTIFY_EVENT,
                    {
                        "title": "Deskflow Decky autostart disabled",
                        "body": (
                            f"The helper failed {failures} times without connecting, so it will "
                            "no longer start by itself. Run the self-test, then start it "
                            "manually once it passes."
                        ),
                    },
                )
            )

    def _give_up_reason(self, failures):
        """Why we stopped retrying, phrased so the next step is obvious."""
        base = f"The helper failed {failures} times in a row"
        if self._helper_installed is False:
            return base + ". The Deskflow helper does not appear to be installed."
        return base + ". See the plugin log for details."

    def _on_helper_line(self, line):
        """Observer for helper output. Runs in the drain task; must not raise."""
        if line.strip():
            if _should_log_helper_line(line, self._settings.get("log_level", "info")):
                decky.logger.info("deskflow-decky helper: %s", redact_line(line))

        self._watcher.feed(line)
        if self._watcher.reported_backend is not None:
            self._resolved_backend_reported = self._watcher.reported_backend

        # Track the *connection*, not just the process. deskflow-core stays alive and
        # retries internally when the server goes away, so waiting for the process to
        # exit would report "connected" for the whole outage and never notify.
        event = classify_connection(line)
        if event == "connected" and self._state.state != "connected":
            self._to_state("connected")
        elif event == "lost" and self._state.state in _HEALTHY_STATES:
            self._to_state("disconnected", reason="the server stopped responding")

        # Gamescope's socket disappearing does not mean the server connection dropped
        # -- deskflow-core just keeps retrying EIS forever on its own, silently holding
        # the screen name open. If we are no longer in Gaming Mode, that reconnect can
        # never succeed, so stop cleanly instead of squatting on the name.
        if (
            eis_disconnected(line)
            and not _is_gaming_mode()
            and not self._eis_lost_stop_scheduled
        ):
            self._eis_lost_stop_scheduled = True
            self._stopped_for_desktop_mode = True
            decky.logger.warning(
                "Lost Gamescope's input socket outside Gaming Mode; stopping so '%s' "
                "is not held open on the server for nothing.",
                self._settings.get("client_name"),
            )
            self._loop.create_task(self._stop())

    def _to_state(self, target, reason=None):
        """Transition, tolerating an illegal move rather than killing the caller.

        `_retry` runs inside a detached supervisor task, so an escaping
        IllegalTransition there would silently kill the reconnect loop while leaving
        the helper running and untracked.
        """
        try:
            return self._state.to(target, reason=reason)
        except IllegalTransition:
            decky.logger.warning(
                "Refused transition %s -> %s; forcing.", self._state.state, target
            )
            return self._state.force(target, reason=reason)

    async def _stop(self):
        async with self._lifecycle:
            return await self._stop_locked()

    async def _kill_helper_app(self):
        """Make sure no sandboxed helper survives.

        Terminating our direct child only kills the `flatpak run` wrapper; the actual
        deskflow-core runs under bwrap and can outlive it. An orphan then blocks every
        future start, because Deskflow refuses a second instance ("an instance of
        deskflow core is already running", exit 5) -- so the plugin wedges permanently.
        """
        # Suppress everything: "nothing was running" is the common case.
        with contextlib.suppress(Exception):
            await run_command(["flatpak", "kill", APP_ID], timeout=15)

        # flatpak kill is not enough on its own: once the launching process dies the
        # instance registry forgets the app and reports "not running" while the
        # sandboxed process is plainly still there. Sweep by app id as well.
        for pid in find_stray_helpers():
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                await asyncio.sleep(1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
            decky.logger.warning("Cleared a stray helper process (pid %s)", pid)

    async def _stop_locked(self):
        supervisor = self._supervisor
        self._supervisor = None
        if supervisor is not None:
            supervisor.cancel()
            # Await it. cancel() only schedules the CancelledError; returning before
            # the task has actually stopped lets a racing _retry spawn a helper that
            # nothing then owns.
            try:
                await supervisor
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                decky.logger.exception("Supervisor task ended with an error")

        stopped = await self._helper.stop()
        # ...and then make sure the sandboxed process itself is gone, not just our
        # direct child.
        await self._kill_helper_app()
        # The helper releases held keys and buttons as it shuts down; record whether
        # the exit was clean so diagnostics can report it.
        self._input_released_on_last_stop = stopped
        self._announced_connection = False
        self._notified_disconnect = False
        self._watcher.reset()

        self._to_state("stopped")
        return stopped

    async def _supervise(self):
        """Watch the child and reconnect with bounded backoff.

        Runs as a detached task, so it catches everything: an exception escaping here
        would kill the loop silently while leaving a helper process running.
        """
        failures = 0
        try:
            while True:
                waiter = self._loop.create_task(self._helper.wait())
                try:
                    code = await asyncio.wait_for(asyncio.shield(waiter), MIN_HEALTHY_UPTIME_S)
                except TimeoutError:
                    # Survived long enough to count as a real connection.
                    self._to_state("connected")
                    if self._resolved_backend == "x11-xtest" and (
                        self._settings["input_backend"] == "auto"
                    ):
                        # A fallback backend works, but not as well; say so rather than
                        # reporting a flat "connected" and letting the user wonder.
                        self._to_state(
                            "degraded",
                            reason=(
                                "Using the XWayland fallback; Gamescope's input socket "
                                "was not found."
                            ),
                        )
                    code = await waiter

                if code == 0:
                    self._to_state("stopped")
                    return

                uptime = self._loop.time() - (self._helper_started_at or self._loop.time())

                if code is None:
                    # A retry that never produced a process at all.
                    reason = "the helper could not be started"
                    uptime = 0.0
                else:
                    reason = f"helper exited with code {code} after {uptime:.1f}s"
                decky.logger.warning(reason)

                # Only a run that actually lasted counts as recovery. Resetting on
                # "the process spawned" retries forever when the binary exits
                # immediately -- which is exactly what an uninstalled flatpak does.
                if uptime >= MIN_HEALTHY_UPTIME_S:
                    failures = 0
                failures += 1

                if not self._settings.get("reconnect_enabled"):
                    self._to_state("error", reason=reason)
                    return

                if failures >= MAX_CONSECUTIVE_FAILURES:
                    self._to_state("error", reason=self._give_up_reason(failures))
                    return

                self._to_state("disconnected", reason=reason)
                await asyncio.sleep(
                    next_backoff_delay(failures, self._settings["reconnect_max_backoff_s"])
                )

                if not await self._retry():
                    failures += 1
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        self._to_state("error", reason=self._give_up_reason(failures))
                        await self._trip_autostart_failsafe(failures)
                        return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            decky.logger.exception("Supervisor stopped unexpectedly")
            self._to_state("error", reason="the connection supervisor stopped unexpectedly")

    async def _retry(self):
        """One reconnect attempt.

        Rediscovers first: after a Gamescope restart the old socket path is stale, and
        sending to it would be both futile and wrong.

        Takes the lifecycle lock so it cannot interleave with an explicit stop. If a
        stop is in progress it will have cancelled this task already; the cancellation
        is delivered at the await below.
        """
        async with self._lifecycle:
            if self._helper.running:
                return True
            try:
                backend, argv, env, _ = await self._prepare_launch()
                self._to_state("starting")
                self._watcher.reset()
                await self._helper.start(argv, env, on_line=self._on_helper_line)
                self._helper_started_at = self._loop.time()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                decky.logger.warning("Reconnect attempt failed: %s", exc)
                return False
            self._resolved_backend = backend
            return True

    @safe
    async def start_helper(self):
        return await self._start()

    @safe
    async def stop_helper(self):
        await self._stop()
        return ok({"state": self._state.state})

    @safe
    async def restart_helper(self):
        # One lock across both halves, so nothing can start the helper in the gap
        # between the stop and the start.
        async with self._lifecycle:
            await self._stop_locked()
            return await self._start_locked()

    @safe
    async def enable_input(self):
        """Alias for start_helper.

        There used to be a separate _input_enabled flag here, toggled independently of
        the helper -- but nothing downstream ever read it: deskflow-core has no control
        channel that could pause injection without dropping the connection. Aliasing to
        start/stop is less than the original "pause without disconnecting" promise, but
        it is honest about what is actually possible today.
        """
        return await self._start()

    @safe
    async def disable_input(self):
        """Alias for stop_helper. See enable_input for why."""
        return await self._stop()

    # ----------------------------------------------------------------- trust

    @safe
    async def get_pending_fingerprint(self):
        if self._pending_fingerprint is None:
            return ok(None)
        host = self._settings["server_host"]
        previous = self._pins.get(host)
        return ok(
            {
                "fingerprint": format_fingerprint(self._pending_fingerprint),
                "algorithm": "sha256",
                "host": host,
                "classification": self._pins.classify(host, self._pending_fingerprint),
                "previous": format_fingerprint(previous) if previous else None,
            }
        )

    @safe
    async def accept_fingerprint(self, fingerprint):
        host = self._settings["server_host"]
        self._trust.add(fingerprint)
        self._pins.pin(host, fingerprint)
        self._pending_fingerprint = None
        decky.logger.info("Trusted a server fingerprint for %s", host)
        return ok({"trusted": True})

    @safe
    async def reject_fingerprint(self):
        host = self._settings.get("server_host") or "the server"
        self._pending_fingerprint = None
        await self._stop()
        # Rejecting is not a dead end, but nothing else would say so: the helper is
        # stopped, no certificate is trusted, and the panel would otherwise show a bare
        # "Stopped" with no hint that turning it back on re-asks.
        self._to_state(
            "stopped",
            reason=(
                f"Certificate for {host} was rejected, so nothing is trusted. Turn the "
                "Helper back on to be asked again."
            ),
        )
        decky.logger.info("Server certificate rejected for %s", host)
        return ok({"trusted": False})

    @safe
    async def forget_fingerprint(self):
        host = self._settings["server_host"]
        known = self._pins.get(host)
        if known:
            self._trust.remove(known)
            self._pins.unpin(host)
        return ok({"trusted": False})

    # ------------------------------------------------------- stock desktop app sync

    async def _is_desktop_app_installed(self):
        """Either scope: this device's copy turned out to be a system-scope install
        from a now-disabled custom remote, not the user-scope Flathub install our own
        install button uses -- so both have to be checked, not just ours.
        """
        for scope in ("--user", "--system"):
            try:
                await run_command(["flatpak", "info", scope, DESKTOP_APP_ID], timeout=15)
                return True
            except Exception:  # noqa: BLE001 - "not installed at this scope" is not a fault
                continue
        return False

    @safe
    async def get_desktop_deskflow_status(self):
        installed = await self._is_desktop_app_installed()
        identity = await self._loop.run_in_executor(
            None, read_desktop_identity, DESKTOP_DESKFLOW_CONFIG_PATH
        )
        running = await self._loop.run_in_executor(None, is_desktop_app_running)

        if identity is None:
            return ok(
                {
                    "installed": installed,
                    "present": False,
                    "running": running,
                    "in_sync": False,
                    "remote_host": None,
                    "computer_name": None,
                }
            )

        in_sync = (
            identity["remote_host"] == self._settings.get("server_host")
            and identity["computer_name"] == self._settings.get("client_name")
        )
        return ok(
            {
                "installed": installed,
                "present": True,
                "running": running,
                "in_sync": in_sync,
                "remote_host": identity["remote_host"],
                "computer_name": identity["computer_name"],
            }
        )

    @safe
    async def sync_desktop_deskflow(self):
        """Copy this Deck's server address and screen name into the desktop app.

        Only those two: TLS trust is per-client TOFU (tls.py), so the desktop app
        keeping its own certificate is correct, not something to overwrite.
        """
        running = await self._loop.run_in_executor(None, is_desktop_app_running)
        if running:
            return err(
                "desktop_app_running",
                "Close the Deskflow desktop app first -- it would overwrite this on exit.",
            )

        try:
            await self._loop.run_in_executor(
                None,
                sync_desktop_identity,
                DESKTOP_DESKFLOW_CONFIG_PATH,
                self._settings.get("server_host"),
                self._settings.get("client_name"),
            )
        except SyncError as exc:
            return err("desktop_app_not_found", str(exc))

        decky.logger.info(
            "Synced this Deck's identity into the desktop Deskflow app (%s)",
            DESKTOP_DESKFLOW_CONFIG_PATH,
        )
        return ok({"path": DESKTOP_DESKFLOW_CONFIG_PATH})

    @safe
    async def sync_from_desktop_deskflow(self):
        """Pull the desktop app's server address and screen name into this plugin.

        The reverse of sync_desktop_deskflow: useful when the desktop app was already
        set up in Desktop Mode before this plugin was ever configured for Gaming Mode,
        so the same server address and screen name do not have to be typed in twice.
        """
        identity = await self._loop.run_in_executor(
            None, read_desktop_identity, DESKTOP_DESKFLOW_CONFIG_PATH
        )
        if identity is None:
            return err(
                "desktop_app_not_found",
                "The desktop Deskflow app has no config to read yet -- open it once in "
                "Desktop Mode first.",
            )

        result = await self.set_settings(
            {"server_host": identity["remote_host"], "client_name": identity["computer_name"]}
        )
        if result["ok"]:
            decky.logger.info(
                "Pulled server address and screen name from the desktop Deskflow app (%s)",
                DESKTOP_DESKFLOW_CONFIG_PATH,
            )
        return result

    @safe
    async def install_desktop_deskflow(self):
        """Install the desktop Deskflow app, configure it, and set it to autostart.

        User scope, matching how our own helper is installed: no elevated privilege
        needed at the flatpak layer, survives SteamOS updates cleanly. If it turns out
        to already be installed under any scope, the install step is skipped and this
        goes straight to configuration -- so retrying after a partial failure, or
        running it against an install the user made some other way, is always safe.
        """
        if not await self._is_desktop_app_installed():
            try:
                await run_command(
                    ["flatpak", "install", "--user", "--noninteractive", "flathub", DESKTOP_APP_ID],
                    timeout=INSTALL_TIMEOUT_S,
                )
            except CommandTimeout:
                return err("timeout", "Installing the desktop Deskflow app took too long.")
            except Exception:  # noqa: BLE001 - reported to the user, not swallowed
                decky.logger.exception("Could not install the desktop Deskflow app")
                return err(
                    "install_failed", "Could not install the desktop Deskflow app from Flathub."
                )

        # A first launch never asks the user anything, so nothing ever blocks on a
        # wizard here -- it just needs the chance to write its own [core] defaults.
        # The offscreen launch always runs the full timeout (there is nothing that
        # makes a GUI app exit on its own); that is the expected, successful path.
        identity = await self._loop.run_in_executor(
            None, read_desktop_identity, DESKTOP_DESKFLOW_CONFIG_PATH
        )
        if identity is None:
            try:
                await run_command(
                    [
                        "flatpak", "run", "--command=deskflow",
                        "--env=QT_QPA_PLATFORM=offscreen", DESKTOP_APP_ID,
                    ],
                    timeout=BOOTSTRAP_LAUNCH_TIMEOUT_S,
                )
            except CommandTimeout:
                pass
            except Exception:  # noqa: BLE001 - best-effort; the check below is authoritative
                decky.logger.warning("Bootstrap launch of the desktop app raised", exc_info=True)

        try:
            needs_bootstrap = await self._loop.run_in_executor(
                None, desktop_client_config_needs_bootstrap, DESKTOP_DESKFLOW_CONFIG_PATH
            )
            configure = bootstrap_client_config if needs_bootstrap else sync_desktop_identity
            await self._loop.run_in_executor(
                None,
                configure,
                DESKTOP_DESKFLOW_CONFIG_PATH,
                self._settings.get("server_host"),
                self._settings.get("client_name"),
            )
        except SyncError as exc:
            return err("desktop_app_setup_failed", str(exc))

        try:
            await self._loop.run_in_executor(None, write_autostart_entry, decky.HOME)
        except SyncError as exc:
            return err(
                "desktop_app_setup_failed",
                f"Installed and configured, but autostart setup failed: {exc}",
            )

        decky.logger.info("Installed, configured, and set up autostart for the desktop app.")
        return ok({"path": DESKTOP_DESKFLOW_CONFIG_PATH})

    # ----------------------------------------------------------------- helper install

    @safe
    async def get_helper_info(self):
        try:
            reference = (
                await run_command(["flatpak", "info", "--user", "--show-ref", APP_ID], timeout=15)
            ).decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001 - "not installed" is an answer, not a failure
            self._helper_installed = False
            return ok(
                {
                    "installed": False,
                    "app_id": APP_ID,
                    "reference": "",
                    "version": "",
                    "permissions": [],
                }
            )

        version = ""
        try:
            version = (
                await run_command(["flatpak", "info", "--user", "--show-version", APP_ID], 15)
            ).decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001 - a missing version is cosmetic
            decky.logger.debug("Could not read the helper version")

        self._helper_installed = True
        return ok(
            {
                "installed": True,
                "app_id": APP_ID,
                "reference": reference,
                "version": version,
                # Reported rather than read back from the sandbox: these are the
                # permissions the manifest grants, and they are documented one by one
                # in helper/README.md.
                "permissions": ["network", "ipc", "wayland", "fallback-x11"],
            }
        )

    @safe
    async def install_helper(self):
        """Install or update the helper from a bundle shipped alongside the plugin.

        Delegates to packaging/install-helper.sh, which verifies the bundle's SHA-256
        before unpacking anything and installs at user scope.
        """
        decky.logger.info("Helper install requested.")

        searched = [
            os.path.join(decky.DECKY_PLUGIN_DIR, "bin"),
            decky.DECKY_PLUGIN_DIR,
        ]
        bundle = None
        for directory in searched:
            candidate = os.path.join(directory, f"{APP_ID}.flatpak")
            if os.path.isfile(candidate):
                bundle = candidate
                break

        if bundle is None:
            # Expected until M2: the patched helper has not been built yet, so no
            # bundle ships with the plugin. Say that plainly rather than implying the
            # user mislaid a file.
            decky.logger.warning(
                "No helper bundle found. Looked in: %s", ", ".join(searched)
            )
            return err(
                "not_installed",
                "No helper bundle is bundled with this build yet. The patched Deskflow "
                "helper still has to be built (milestone M2). Once a release exists, "
                f"put {APP_ID}.flatpak in the plugin's bin/ folder and press this again.",
            )

        script = os.path.join(decky.DECKY_PLUGIN_DIR, "packaging", "install-helper.sh")
        if not os.path.isfile(script):
            decky.logger.error("Installer script missing at %s", script)
            return err("install_failed", "The installer script is missing from the plugin.")

        # Stop first: replacing the binary under a running helper would leave it
        # holding input devices with no way to shut it down cleanly.
        decky.logger.info("Installing helper from %s", bundle)
        await self._stop()

        try:
            await run_command(["bash", script, bundle], timeout=300)
        except CommandTimeout:
            return err("timeout", "Installing the helper took too long.")
        except Exception:  # noqa: BLE001
            decky.logger.exception("Helper install failed")
            return err("install_failed", "The helper could not be installed. See the plugin log.")

        decky.logger.info("Helper install completed.")
        info = await self.get_helper_info()
        return ok(info.get("data") or {})

    # ----------------------------------------------------------------- diagnostics

    @safe
    async def get_logs(self, lines=200):
        if not isinstance(lines, int) or isinstance(lines, bool):
            return err("validation", "lines: must be a whole number")
        count = max(1, min(lines, MAX_LOG_LINES))

        try:
            names = sorted(
                (name for name in os.listdir(LOG_DIR) if name.endswith(".log")), reverse=True
            )
        except OSError:
            return ok({"lines": []})
        if not names:
            return ok({"lines": []})

        try:
            with open(os.path.join(LOG_DIR, names[0]), encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-count:]
        except OSError as exc:
            return err("internal", f"Could not read the log: {exc.strerror}")

        return ok({"lines": [redact_line(line.rstrip("\n")) for line in tail]})

    def _diagnostics_payload(self):
        discovery = self._last_discovery
        return build_report(
            {
                "plugin_version": decky.DECKY_PLUGIN_VERSION,
                "decky_version": decky.DECKY_VERSION,
                "session_type": os.environ.get("XDG_SESSION_TYPE"),
                "mode": self._settings.get("mode"),
                "requested_backend": self._settings.get("input_backend"),
                # What we asked for, and what the helper itself said it used. A
                # mismatch is worth seeing in a bug report.
                "resolved_backend": self._resolved_backend,
                "helper_reported_backend": self._resolved_backend_reported,
                "state": self._state.state,
                "last_error": self._state.last_error,
                "socket_found": discovery.found if discovery else None,
                "socket_source": discovery.source if discovery else None,
                "discovery_checked": "; ".join(discovery.checked) if discovery else None,
                "uinput_present": os.path.exists("/dev/uinput"),
                "screen_size": "{}x{}".format(*self._screen_size) if self._screen_size else None,
                "helper_pid": self._helper.pid,
                "tls_enabled": self._settings.get("tls_enabled"),
                "input_released_on_last_stop": self._input_released_on_last_stop,
            }
        )

    @safe
    async def get_diagnostics(self):
        return ok(self._diagnostics_payload())

    async def _probe_server(self):
        """Can we open a TCP connection to the configured server? Bounded and harmless."""
        host = self._settings.get("server_host")
        port = self._settings.get("server_port")
        if not host:
            return False, "no server address is configured"
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=SERVER_PROBE_TIMEOUT_S
            )
            writer.close()
            with contextlib.suppress(Exception):  # closing is best effort
                await writer.wait_closed()
            return True, f"reachable at {host}:{port}"
        except TimeoutError:
            return False, f"no answer from {host}:{port} within {SERVER_PROBE_TIMEOUT_S}s"
        except OSError as exc:
            return False, "{}:{} - {}".format(host, port, exc.strerror or "unreachable")

    @safe
    async def run_self_test(self):
        """Checks phrased so the failing one tells the user what to do next."""
        checks = []

        def add(identifier, label, ok, detail):
            checks.append({"id": identifier, "label": label, "ok": bool(ok), "detail": detail})

        # 1. Is the helper there at all?
        helper = await self.get_helper_info()
        info = helper.get("data") or {}
        installed = bool(info.get("installed"))
        add(
            "helper",
            "Deskflow Decky helper installed",
            installed,
            info.get("version") or APP_ID if installed else "install it from this page",
        )

        # 2. Can we inject input into this session?
        discovery = discover_socket(self._settings, relay_path=RELAY_PATH)
        self._last_discovery = discovery
        add(
            "input_socket",
            "Gamescope input socket",
            discovery.found,
            discovery.path
            or "not found; the plugin can only inject input inside a Gamescope session",
        )

        # 3. Is it configured enough to start?
        mode = self._settings.get("mode")
        configured = bool(self._settings.get("server_host")) or mode == "server"
        add(
            "configured",
            "Server address set",
            configured,
            self._settings.get("server_host") or "enter the address of your Deskflow server",
        )

        # 4. Server mode cannot capture in Gaming Mode.
        if mode == "server":
            add(
                "server_mode",
                "Server mode supported here",
                not _is_gaming_mode(),
                "Gaming Mode has no input-capture portal; use Desktop Mode"
                if _is_gaming_mode()
                else "Desktop Mode",
            )

        # 5. Is the server actually up? The most common real failure.
        if configured and mode == "client":
            reachable, detail = await self._probe_server()
            add("server_reachable", "Server reachable", reachable, detail)

        # 6. The pointer space. A wrong value is why a pointer stops partway across.
        size = await self._resolve_screen_size()
        auto = not (self._settings.get("screen_width") and self._settings.get("screen_height"))
        add(
            "screen_size",
            "Screen size",
            True,
            "{}x{} ({}). If the pointer cannot reach the whole screen, set this "
            "manually.".format(size[0], size[1], "detected" if auto else "set manually"),
        )

        # 7. TLS material.
        if self._settings.get("tls_enabled"):
            add(
                "certificate",
                "This machine's certificate",
                os.path.exists(CERT_PATH),
                "present" if os.path.exists(CERT_PATH) else "will be generated on first start",
            )
            trusted = self._trust.all()
            add(
                "trusted_server",
                "Server certificate trusted",
                bool(trusted),
                f"{len(trusted)} trusted"
                if trusted
                else "you will be asked to confirm it on the next connection",
            )

        passed = sum(1 for check in checks if check["ok"])
        decky.logger.info("Self-test: %s of %s checks passed", passed, len(checks))
        return ok({"checks": checks, "passed": passed, "total": len(checks)})

    @safe
    async def export_diagnostics(self):
        report = self._diagnostics_payload()
        path = os.path.join(RUNTIME_DIR, "diagnostics.txt")
        body = "\n".join(f"{key}: {value}" for key, value in sorted(report.items()))
        # Same private-write discipline as the config and trust store: 0600 by
        # construction, then an atomic rename.
        write_private(path, body + "\n")
        return ok({"path": path})
