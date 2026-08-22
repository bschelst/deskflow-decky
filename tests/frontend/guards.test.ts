/**
 * The frontend's crash barrier.
 *
 * A backend response is untrusted data. If a render path dereferences it without
 * proof, one malformed field unmounts the Quick Access Menu -- which in Gaming Mode
 * the user cannot easily recover from.
 */

import { describe, expect, it } from "vitest";
import {
  isDesktopDeskflowStatus,
  isSettings,
  isStatus,
  toDesktopDeskflowStatus,
  unwrap,
  unwrapVoid,
} from "../../src/api/guards";
import type { Settings } from "../../src/api/types";

const validStatusPayload = {
  state: "connected",
  since: 1700000000,
  last_error: null,
  backend: "gamescope-libei",
  requested_backend: "auto",
  mode: "client",
  server: "desktop.local",
  server_port: 24800,
  client_name: "steamdeck",
  input_enabled: true,
  fingerprint_pending: false,
  gaming_mode: true,
};

const validSettings: Settings = {
  mode: "client",
  server_host: "desktop.local",
  server_port: 24800,
  client_name: "steamdeck",
  tls_enabled: true,
  check_peer_fingerprints: true,
  input_backend: "auto",
  socket_path_override: "",
  autostart_gaming_mode: false,
  reconnect_enabled: true,
  notifications_enabled: true,
  reconnect_max_backoff_s: 30,
  pointer_sensitivity: 1.0,
  screen_width: 0,
  screen_height: 0,
  activation_mode: "manual",
  keyboard_layout: "",
  log_level: "info",
};

const envelope = (data: unknown) => ({ ok: true, data, error: null });

describe("unwrap", () => {
  it("accepts a well-formed success envelope", () => {
    const result = unwrap(envelope(validStatusPayload), isStatus);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.state).toBe("connected");
  });

  it("passes a backend error through with its code", () => {
    const result = unwrap(
      { ok: false, data: null, error: { code: "not_configured", message: "no server" } },
      isStatus,
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("not_configured");
  });

  it("treats a guard failure as an error rather than as missing-but-fine", () => {
    const result = unwrap(envelope({ state: "banana" }), isStatus);
    expect(result.ok).toBe(false);
  });

  it.each([null, undefined, 42, "string", [], true])(
    "rejects a non-envelope response (%s)",
    (bad) => {
      expect(unwrap(bad, isStatus).ok).toBe(false);
    },
  );

  it("rejects an envelope that claims success but carries no data", () => {
    expect(unwrap({ ok: true, data: null, error: null }, isStatus).ok).toBe(false);
  });

  it("rejects an envelope missing the ok field", () => {
    expect(unwrap({ data: validStatusPayload, error: null }, isStatus).ok).toBe(false);
  });

  it("survives an error object that is itself malformed", () => {
    const result = unwrap({ ok: false, data: null, error: "just a string" }, isStatus);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(typeof result.error.message).toBe("string");
  });

  it("normalises an unrecognised error code rather than trusting it", () => {
    const result = unwrap(
      { ok: false, data: null, error: { code: "surprise", message: "hi" } },
      isStatus,
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("internal");
  });

  it("never throws, whatever it is handed", () => {
    const nasty: Record<string, unknown> = { ok: true, error: null };
    nasty.data = nasty; // circular
    expect(() => unwrap(nasty, isStatus)).not.toThrow();
  });
});

describe("unwrapVoid", () => {
  it("accepts a success envelope with no payload", () => {
    expect(unwrapVoid({ ok: true, data: null, error: null }).ok).toBe(true);
  });

  it("still reports backend errors", () => {
    const result = unwrapVoid({
      ok: false,
      data: null,
      error: { code: "not_running", message: "nope" },
    });
    expect(result.ok).toBe(false);
  });
});

describe("isStatus", () => {
  it("accepts the canonical payload", () => {
    expect(isStatus(validStatusPayload)).toBe(true);
  });

  it("accepts a null backend, which means not yet resolved", () => {
    expect(isStatus({ ...validStatusPayload, backend: null })).toBe(true);
  });

  it.each([
    "state",
    "mode",
    "server",
    "server_port",
    "client_name",
    "input_enabled",
  ])("rejects a payload missing %s", (field) => {
    const payload: Record<string, unknown> = { ...validStatusPayload };
    delete payload[field];
    expect(isStatus(payload)).toBe(false);
  });

  it("rejects a state outside the known set", () => {
    expect(isStatus({ ...validStatusPayload, state: "exploded" })).toBe(false);
  });

  it("rejects a port that arrived as a string", () => {
    expect(isStatus({ ...validStatusPayload, server_port: "24800" })).toBe(false);
  });

  it("rejects a boolean field that arrived as a number", () => {
    expect(isStatus({ ...validStatusPayload, input_enabled: 1 })).toBe(false);
  });

  it("tolerates an unknown extra field", () => {
    expect(isStatus({ ...validStatusPayload, future_field: "x" })).toBe(true);
  });
});

describe("isSettings", () => {
  it("accepts a complete settings object", () => {
    expect(isSettings(validSettings)).toBe(true);
  });

  it.each(Object.keys(validSettings))("rejects a settings object missing %s", (field) => {
    const payload: Record<string, unknown> = { ...validSettings };
    delete payload[field];
    expect(isSettings(payload)).toBe(false);
  });

  it("rejects an out-of-set enum value", () => {
    expect(isSettings({ ...validSettings, log_level: "verbose" })).toBe(false);
  });

  it("rejects a numeric field that arrived as a string", () => {
    expect(isSettings({ ...validSettings, server_port: "24800" })).toBe(false);
  });

  it("rejects NaN in a numeric field", () => {
    expect(isSettings({ ...validSettings, pointer_sensitivity: NaN })).toBe(false);
  });

  it.each([null, undefined, [], "x", 0])("rejects a non-object (%s)", (bad) => {
    expect(isSettings(bad)).toBe(false);
  });
});

describe("isDesktopDeskflowStatus / toDesktopDeskflowStatus", () => {
  const present = {
    present: true,
    running: false,
    in_sync: false,
    remote_host: "desktop.local",
    computer_name: "steamdeck2",
  };

  const absent = {
    present: false,
    running: false,
    in_sync: false,
    remote_host: null,
    computer_name: null,
  };

  it("accepts the present case", () => {
    expect(isDesktopDeskflowStatus(present)).toBe(true);
  });

  it("accepts the absent case, where the string fields are null", () => {
    expect(isDesktopDeskflowStatus(absent)).toBe(true);
  });

  it.each(["present", "running", "in_sync"])("rejects a non-boolean %s", (field) => {
    expect(isDesktopDeskflowStatus({ ...present, [field]: "yes" })).toBe(false);
  });

  it("converts snake_case to the camelCase the UI uses", () => {
    expect(toDesktopDeskflowStatus(present)).toEqual({
      present: true,
      running: false,
      inSync: false,
      remoteHost: "desktop.local",
      computerName: "steamdeck2",
    });
  });

  it("maps a non-string remote_host/computer_name to null rather than passing it through", () => {
    expect(toDesktopDeskflowStatus({ ...present, remote_host: 42 })).toEqual(
      expect.objectContaining({ remoteHost: null }),
    );
  });

  it("returns null for a malformed payload", () => {
    expect(toDesktopDeskflowStatus({ present: true })).toBeNull();
  });
});
