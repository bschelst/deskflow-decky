/**
 * Typed wrappers around the Python backend.
 *
 * Every call goes through `unwrap` plus a guard, and every call is wrapped in a
 * try/catch: `callable` from @decky/api rejects on transport failure, and an unhandled
 * rejection during a Steam UI transition is a known way to break the panel.
 *
 * Nothing in this module throws. Callers get a `Result`.
 */

import { callable } from "@decky/api";

import {
  isDesktopDeskflowStatus,
  isDiagnostics,
  isHelperInfo,
  isLogLines,
  isPathResult,
  isPendingFingerprint,
  isSelfTest,
  isSettings,
  isStatus,
  toDesktopDeskflowStatus,
  toHelperInfo,
  toStatus,
  transportError,
  unwrap,
  unwrapVoid,
} from "./guards";
import type {
  DesktopDeskflowStatus,
  HelperInfo,
  PendingFingerprint,
  Result,
  SelfTestResult,
  Settings,
  Status,
} from "./types";

const TRANSPORT_MESSAGE = "Could not reach the plugin backend.";

/** Run a backend call, validate its response, and never throw. */
async function guarded<T>(
  invoke: () => Promise<unknown>,
  validate: (raw: unknown) => Result<T>,
): Promise<Result<T>> {
  try {
    return validate(await invoke());
  } catch {
    // The detail lives in the backend log; surfacing it here would leak paths.
    return { ok: false, error: transportError(TRANSPORT_MESSAGE) };
  }
}

const viaGuard =
  <T>(guard: (value: unknown) => value is T) =>
  (raw: unknown): Result<T> =>
    unwrap(raw, guard);

// --------------------------------------------------------------------------- status

const rawGetStatus = callable<[], unknown>("get_status");

export const getStatus = (): Promise<Result<Status>> =>
  guarded(rawGetStatus, (raw) => {
    const result = unwrap(raw, isStatus);
    if (!result.ok) return result;
    const status = toStatus(result.data);
    return status
      ? { ok: true, data: status }
      : { ok: false, error: transportError(TRANSPORT_MESSAGE) };
  });

// --------------------------------------------------------------------------- settings

const rawGetSettings = callable<[], unknown>("get_settings");
const rawSetSettings = callable<[patch: Partial<Settings>], unknown>("set_settings");

export const getSettings = (): Promise<Result<Settings>> =>
  guarded(rawGetSettings, viaGuard(isSettings));

export const setSettings = (patch: Partial<Settings>): Promise<Result<Settings>> =>
  guarded(() => rawSetSettings(patch), viaGuard(isSettings));

// --------------------------------------------------------------------------- lifecycle

const rawStart = callable<[], unknown>("start_helper");
const rawStop = callable<[], unknown>("stop_helper");
const rawRestart = callable<[], unknown>("restart_helper");
const rawEnableInput = callable<[], unknown>("enable_input");
const rawDisableInput = callable<[], unknown>("disable_input");
export const startHelper = (): Promise<Result<null>> => guarded(rawStart, unwrapVoid);
export const stopHelper = (): Promise<Result<null>> => guarded(rawStop, unwrapVoid);
export const restartHelper = (): Promise<Result<null>> => guarded(rawRestart, unwrapVoid);
export const enableInput = (): Promise<Result<null>> => guarded(rawEnableInput, unwrapVoid);
export const disableInput = (): Promise<Result<null>> => guarded(rawDisableInput, unwrapVoid);

// --------------------------------------------------------------------------- trust

const rawPendingFingerprint = callable<[], unknown>("get_pending_fingerprint");
const rawAcceptFingerprint = callable<[fingerprint: string], unknown>("accept_fingerprint");
const rawRejectFingerprint = callable<[], unknown>("reject_fingerprint");
const rawForgetFingerprint = callable<[], unknown>("forget_fingerprint");

export const getPendingFingerprint = (): Promise<Result<PendingFingerprint | null>> =>
  guarded(rawPendingFingerprint, viaGuard(isPendingFingerprint));

export const acceptFingerprint = (fingerprint: string): Promise<Result<null>> =>
  guarded(() => rawAcceptFingerprint(fingerprint), unwrapVoid);

export const rejectFingerprint = (): Promise<Result<null>> =>
  guarded(rawRejectFingerprint, unwrapVoid);

export const forgetFingerprint = (): Promise<Result<null>> =>
  guarded(rawForgetFingerprint, unwrapVoid);

// --------------------------------------------------------------------------- helper

const rawHelperInfo = callable<[], unknown>("get_helper_info");
const rawInstallHelper = callable<[], unknown>("install_helper");

const asHelperInfo = (raw: unknown): Result<HelperInfo> => {
  const result = unwrap(raw, isHelperInfo);
  if (!result.ok) return result;
  const info = toHelperInfo(result.data);
  return info ? { ok: true, data: info } : { ok: false, error: transportError(TRANSPORT_MESSAGE) };
};

export const getHelperInfo = (): Promise<Result<HelperInfo>> =>
  guarded(rawHelperInfo, asHelperInfo);

export const installHelper = (): Promise<Result<HelperInfo>> =>
  guarded(rawInstallHelper, asHelperInfo);

// -------------------------------------------------------------- desktop app sync

const rawDesktopDeskflowStatus = callable<[], unknown>("get_desktop_deskflow_status");
const rawSyncDesktopDeskflow = callable<[], unknown>("sync_desktop_deskflow");
const rawInstallDesktopDeskflow = callable<[], unknown>("install_desktop_deskflow");

export const getDesktopDeskflowStatus = (): Promise<Result<DesktopDeskflowStatus>> =>
  guarded(rawDesktopDeskflowStatus, (raw) => {
    const result = unwrap(raw, isDesktopDeskflowStatus);
    if (!result.ok) return result;
    const status = toDesktopDeskflowStatus(result.data);
    return status
      ? { ok: true, data: status }
      : { ok: false, error: transportError(TRANSPORT_MESSAGE) };
  });

export const syncDesktopDeskflow = (): Promise<Result<null>> =>
  guarded(rawSyncDesktopDeskflow, unwrapVoid);

export const installDesktopDeskflow = (): Promise<Result<null>> =>
  guarded(rawInstallDesktopDeskflow, unwrapVoid);

// --------------------------------------------------------------------------- diagnostics

const rawSelfTest = callable<[], unknown>("run_self_test");
const rawGetLogs = callable<[lines: number], unknown>("get_logs");
const rawDiagnostics = callable<[], unknown>("get_diagnostics");
const rawExportDiagnostics = callable<[], unknown>("export_diagnostics");

export const runSelfTest = (): Promise<Result<SelfTestResult>> =>
  guarded(rawSelfTest, viaGuard(isSelfTest));

export const getLogs = (lines: number): Promise<Result<{ lines: string[] }>> =>
  guarded(() => rawGetLogs(lines), viaGuard(isLogLines));

export const getDiagnostics = (): Promise<Result<Record<string, string>>> =>
  guarded(rawDiagnostics, viaGuard(isDiagnostics));

export const exportDiagnostics = (): Promise<Result<{ path: string }>> =>
  guarded(rawExportDiagnostics, viaGuard(isPathResult));
