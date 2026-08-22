/**
 * Runtime validation of backend responses.
 *
 * Hand-written rather than schema-library-driven: these guards are small, auditable,
 * and add nothing to the supply chain -- which matters more here than the ergonomics
 * of a DSL, because this file is the only thing standing between a malformed response
 * and an unmounted Quick Access Menu.
 */

import {
  ACTIVATION_MODES,
  ERROR_CODES,
  HELPER_STATES,
  INPUT_BACKENDS,
  LOG_LEVELS,
  MODES,
  type BackendError,
  type DesktopDeskflowStatus,
  type ErrorCode,
  type HelperInfo,
  type PendingFingerprint,
  type Result,
  type SelfTestResult,
  type Settings,
  type Status,
} from "./types";

// --------------------------------------------------------------------------- primitives

type Dict = Record<string, unknown>;

const isObject = (value: unknown): value is Dict =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === "string";

const isBool = (value: unknown): value is boolean => typeof value === "boolean";

/** Finite only: NaN and Infinity are numbers to `typeof` but not to anything useful. */
const isNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const isInt = (value: unknown): value is number => isNumber(value) && Number.isInteger(value);

const isMember = <T extends readonly string[]>(
  value: unknown,
  members: T,
): value is T[number] => isString(value) && (members as readonly string[]).includes(value);

const isNullOr = <T>(value: unknown, check: (v: unknown) => v is T): value is T | null =>
  value === null || check(value);

// --------------------------------------------------------------------------- errors

const GENERIC_ERROR: BackendError = {
  code: "internal",
  message: "The plugin backend returned an unexpected response.",
};

const toError = (raw: unknown): BackendError => {
  if (!isObject(raw)) return GENERIC_ERROR;
  const code: ErrorCode = isMember(raw.code, ERROR_CODES) ? raw.code : "internal";
  const message = isString(raw.message) && raw.message ? raw.message : GENERIC_ERROR.message;
  return { code, message };
};

export const transportError = (message: string): BackendError => ({
  code: "transport",
  message,
});

// --------------------------------------------------------------------------- envelope

/**
 * Validate a raw backend response and narrow its payload.
 *
 * A guard failure is an error, never "absent but fine" -- silently rendering a
 * half-understood payload is how a subtle backend change becomes a blank panel.
 */
export function unwrap<T>(raw: unknown, guard: (value: unknown) => value is T): Result<T> {
  if (!isObject(raw) || !isBool(raw.ok)) {
    return { ok: false, error: GENERIC_ERROR };
  }
  if (!raw.ok) {
    return { ok: false, error: toError(raw.error) };
  }
  if (!guard(raw.data)) {
    return { ok: false, error: GENERIC_ERROR };
  }
  return { ok: true, data: raw.data };
}

/** For methods whose success carries no payload worth inspecting. */
export function unwrapVoid(raw: unknown): Result<null> {
  if (!isObject(raw) || !isBool(raw.ok)) {
    return { ok: false, error: GENERIC_ERROR };
  }
  if (!raw.ok) {
    return { ok: false, error: toError(raw.error) };
  }
  return { ok: true, data: null };
}

// --------------------------------------------------------------------------- shapes

/**
 * The wire shape, before it is mapped to the camelCase `Status` the UI uses.
 *
 * Declared explicitly rather than as `Status & Record<string, unknown>`: an index
 * signature widens every property back to `unknown`, which defeats the narrowing the
 * guard just performed.
 */
interface RawStatus {
  state: Status["state"];
  since: unknown;
  last_error: string | null;
  backend: Status["backend"];
  requested_backend: unknown;
  mode: Status["mode"];
  server: string;
  server_port: number;
  client_name: string;
  input_enabled: boolean;
  fingerprint_pending: unknown;
  gaming_mode: unknown;
}

export function isStatus(value: unknown): value is RawStatus {
  if (!isObject(value)) return false;
  return (
    isMember(value.state, HELPER_STATES) &&
    isMember(value.mode, MODES) &&
    isString(value.server) &&
    isInt(value.server_port) &&
    isString(value.client_name) &&
    isBool(value.input_enabled) &&
    isNullOr(value.backend, (v): v is string => isMember(v, INPUT_BACKENDS)) &&
    isNullOr(value.last_error, isString)
  );
}

/** Backend snake_case to the camelCase the UI uses, once the shape is proven. */
export function toStatus(raw: unknown): Status | null {
  if (!isStatus(raw)) return null;
  return {
    state: raw.state,
    since: isNumber(raw.since) ? raw.since : 0,
    lastError: isString(raw.last_error) ? raw.last_error : null,
    backend: isMember(raw.backend, INPUT_BACKENDS) ? raw.backend : null,
    requestedBackend: isMember(raw.requested_backend, INPUT_BACKENDS)
      ? raw.requested_backend
      : "auto",
    mode: raw.mode,
    server: raw.server,
    serverPort: raw.server_port,
    clientName: raw.client_name,
    inputEnabled: raw.input_enabled,
    fingerprintPending: isBool(raw.fingerprint_pending) ? raw.fingerprint_pending : false,
    gamingMode: isBool(raw.gaming_mode) ? raw.gaming_mode : false,
  };
}

export function isSettings(value: unknown): value is Settings {
  if (!isObject(value)) return false;
  return (
    isMember(value.mode, MODES) &&
    isString(value.server_host) &&
    isInt(value.server_port) &&
    isString(value.client_name) &&
    isBool(value.tls_enabled) &&
    isBool(value.check_peer_fingerprints) &&
    isMember(value.input_backend, INPUT_BACKENDS) &&
    isString(value.socket_path_override) &&
    isBool(value.autostart_gaming_mode) &&
    isBool(value.reconnect_enabled) &&
    isBool(value.notifications_enabled) &&
    isInt(value.reconnect_max_backoff_s) &&
    isNumber(value.pointer_sensitivity) &&
    isInt(value.screen_width) &&
    isInt(value.screen_height) &&
    isMember(value.activation_mode, ACTIVATION_MODES) &&
    isString(value.keyboard_layout) &&
    isMember(value.log_level, LOG_LEVELS)
  );
}

export function isSelfTest(value: unknown): value is SelfTestResult {
  if (!isObject(value) || !Array.isArray(value.checks)) return false;
  if (!isInt(value.passed) || !isInt(value.total)) return false;
  return value.checks.every(
    (check) =>
      isObject(check) &&
      isString(check.id) &&
      isString(check.label) &&
      isBool(check.ok) &&
      isString(check.detail),
  );
}

export function isLogLines(value: unknown): value is { lines: string[] } {
  return isObject(value) && Array.isArray(value.lines) && value.lines.every(isString);
}

interface RawHelperInfo {
  installed: boolean;
  app_id: string;
  reference: unknown;
  version: unknown;
  permissions: unknown;
}

export function isHelperInfo(value: unknown): value is RawHelperInfo {
  return isObject(value) && isBool(value.installed) && isString(value.app_id);
}

export function toHelperInfo(raw: unknown): HelperInfo | null {
  if (!isHelperInfo(raw)) return null;
  return {
    installed: raw.installed,
    appId: raw.app_id,
    reference: isString(raw.reference) ? raw.reference : "",
    version: isString(raw.version) ? raw.version : "",
    permissions: Array.isArray(raw.permissions) ? raw.permissions.filter(isString) : [],
  };
}

interface RawDesktopDeskflowStatus {
  present: boolean;
  running: boolean;
  in_sync: boolean;
  remote_host: unknown;
  computer_name: unknown;
}

export function isDesktopDeskflowStatus(value: unknown): value is RawDesktopDeskflowStatus {
  return (
    isObject(value) && isBool(value.present) && isBool(value.running) && isBool(value.in_sync)
  );
}

export function toDesktopDeskflowStatus(raw: unknown): DesktopDeskflowStatus | null {
  if (!isDesktopDeskflowStatus(raw)) return null;
  return {
    present: raw.present,
    running: raw.running,
    inSync: raw.in_sync,
    remoteHost: isString(raw.remote_host) ? raw.remote_host : null,
    computerName: isString(raw.computer_name) ? raw.computer_name : null,
  };
}

export function isPendingFingerprint(value: unknown): value is PendingFingerprint | null {
  if (value === null) return true;
  if (!isObject(value)) return false;
  return (
    isString(value.fingerprint) &&
    isString(value.host) &&
    isMember(value.classification, ["unknown", "changed", "trusted"] as const)
  );
}

export function isPathResult(value: unknown): value is { path: string } {
  return isObject(value) && isString(value.path);
}

export function isDiagnostics(value: unknown): value is Record<string, string> {
  return isObject(value) && Object.values(value).every(isString);
}
