/**
 * Display strings.
 *
 * State is rendered from a fixed vocabulary rather than free text so a status row
 * never changes width when the state changes -- a reflowing row in the Quick Access
 * panel reads as a layout bug.
 */

import type { HelperStateName, InputBackend, Mode, Status } from "../api/types";

export const STATE_LABEL: Record<HelperStateName, string> = {
  stopped: "Stopped",
  starting: "Connecting",
  connected: "Connected",
  degraded: "Degraded",
  disconnected: "Disconnected",
  error: "Error",
};

/**
 * Advisory only. The label carries the meaning, because colour alone fails for
 * colour-blind users and washes out on the Deck's screen in sunlight.
 */
export const STATE_COLOUR: Record<HelperStateName, string> = {
  stopped: "#8b929a",
  starting: "#e0b528",
  connected: "#5ba32b",
  degraded: "#e0b528",
  disconnected: "#8b929a",
  error: "#c0392b",
};

/** Pass/fail colours for self-test rows. Paired with a ✓/✗ glyph, never colour alone. */
export const PASS_COLOUR = "#5ba32b";
export const FAIL_COLOUR = "#c0392b";

export const BACKEND_LABEL: Record<InputBackend, string> = {
  auto: "Automatic",
  "gamescope-libei": "Gamescope (libei)",
  "x11-xtest": "XWayland (XTest)",
  uinput: "uinput",
};

export const MODE_LABEL: Record<Mode, string> = {
  client: "Client",
  server: "Server",
};

export function describeBackend(status: Status): string {
  if (status.backend === null) {
    return status.requestedBackend === "auto"
      ? "Not resolved yet"
      : `${BACKEND_LABEL[status.requestedBackend]} (not active)`;
  }
  return BACKEND_LABEL[status.backend];
}

export function describeServer(status: Status): string {
  if (status.mode === "server") return `Listening on port ${status.serverPort}`;
  if (!status.server) return "Not configured";
  return `${status.server}:${status.serverPort}`;
}

/** Server mode cannot capture input in Gaming Mode: there is no InputCapture portal. */
export function serverModeUnavailable(status: Status): boolean {
  return status.mode === "server" && status.gamingMode;
}

export function describeMode(status: Status): string {
  return serverModeUnavailable(status)
    ? "Server (unavailable)"
    : MODE_LABEL[status.mode];
}

const SHA256_HEX_LENGTH = 64;

/**
 * Group a fingerprint so a human can compare it against the one on the server.
 *
 * Only reformats something that is actually a SHA-256 fingerprint. Stripping non-hex
 * characters unconditionally would turn arbitrary text into convincing-looking
 * nonsense ("not a fingerprint" -> "AF:E"), which is exactly the wrong thing to show
 * beside a security decision.
 */
export function groupFingerprint(fingerprint: string): string {
  const cleaned = fingerprint.replace(/:/g, "").toUpperCase();
  if (cleaned.length !== SHA256_HEX_LENGTH || !/^[0-9A-F]+$/.test(cleaned)) {
    return fingerprint;
  }
  return (cleaned.match(/.{2}/g) ?? []).join(":");
}

export function truncate(text: string, limit = 160): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
}
