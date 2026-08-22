// Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

/**
 * Shapes crossing the backend boundary.
 *
 * These are declarations only. Nothing here proves a value at runtime -- that is what
 * the guards in `guards.ts` are for. A TypeScript interface is a promise about data we
 * control; backend responses are data we merely hope about.
 */

export const HELPER_STATES = [
  "stopped",
  "starting",
  "connected",
  "degraded",
  "disconnected",
  "error",
] as const;
export type HelperStateName = (typeof HELPER_STATES)[number];

export const MODES = ["client", "server"] as const;
export type Mode = (typeof MODES)[number];

export const INPUT_BACKENDS = ["auto", "gamescope-libei", "x11-xtest", "uinput"] as const;
export type InputBackend = (typeof INPUT_BACKENDS)[number];

export const ACTIVATION_MODES = ["manual", "always"] as const;
export type ActivationMode = (typeof ACTIVATION_MODES)[number];

export const LOG_LEVELS = ["error", "warn", "info", "debug"] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

/** Error codes are API; each one is documented on the in-plugin troubleshooting page. */
export const ERROR_CODES = [
  "validation",
  "internal",
  "not_installed",
  "install_failed",
  "already_running",
  "not_running",
  "socket_not_found",
  "backend_unavailable",
  "server_mode_unsupported",
  "not_configured",
  "tls_setup_failed",
  "fingerprint_pending",
  "timeout",
  "transport",
  "desktop_app_running",
  "desktop_app_not_found",
  "desktop_app_setup_failed",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export interface BackendError {
  code: ErrorCode;
  message: string;
}

/** The result of a backend call once it has been validated. */
export type Result<T> = { ok: true; data: T } | { ok: false; error: BackendError };

export interface Status {
  state: HelperStateName;
  since: number;
  lastError: string | null;
  backend: InputBackend | null;
  requestedBackend: InputBackend;
  mode: Mode;
  server: string;
  serverPort: number;
  clientName: string;
  inputEnabled: boolean;
  fingerprintPending: boolean;
  gamingMode: boolean;
}

export interface Settings {
  mode: Mode;
  server_host: string;
  server_port: number;
  client_name: string;
  tls_enabled: boolean;
  check_peer_fingerprints: boolean;
  input_backend: InputBackend;
  socket_path_override: string;
  autostart_gaming_mode: boolean;
  reconnect_enabled: boolean;
  notifications_enabled: boolean;
  reconnect_max_backoff_s: number;
  pointer_sensitivity: number;
  screen_width: number;
  screen_height: number;
  activation_mode: ActivationMode;
  keyboard_layout: string;
  log_level: LogLevel;
}

export interface SelfTestCheck {
  id: string;
  /** Human-readable name; the id is a stable key, not something to show a user. */
  label: string;
  ok: boolean;
  detail: string;
}

export interface SelfTestResult {
  checks: SelfTestCheck[];
  passed: number;
  total: number;
}

export interface PendingFingerprint {
  fingerprint: string;
  algorithm: string;
  host: string;
  classification: "unknown" | "changed" | "trusted";
  previous: string | null;
}

export interface HelperInfo {
  installed: boolean;
  appId: string;
  reference: string;
  version: string;
  /** The sandbox permissions the helper's manifest grants, for display in About. */
  permissions: string[];
}

/** Whether the stock Deskflow desktop app (a separate flatpak) matches this Deck. */
export interface DesktopDeskflowStatus {
  installed: boolean;
  /** False also covers "installed but never run" -- it has no config yet either way. */
  present: boolean;
  /** Syncing while it holds an open config handle would be undone when it exits. */
  running: boolean;
  inSync: boolean;
  remoteHost: string | null;
  computerName: string | null;
}
