/**
 * Display formatting.
 *
 * `serverModeUnavailable` and `describeMode` gate the Gaming-Mode server warning
 * (docs/UI-SPEC.md §5), so they get direct tests rather than being covered only
 * incidentally through a component.
 */

import { describe, expect, it } from "vitest";
import {
  BACKEND_LABEL,
  STATE_COLOUR,
  STATE_LABEL,
  describeBackend,
  describeMode,
  describeServer,
  groupFingerprint,
  serverModeUnavailable,
  truncate,
} from "../../src/lib/format";
import { HELPER_STATES, INPUT_BACKENDS, type Status } from "../../src/api/types";

const status = (overrides: Partial<Status> = {}): Status => ({
  state: "connected",
  since: 0,
  lastError: null,
  backend: "gamescope-libei",
  requestedBackend: "auto",
  mode: "client",
  server: "desktop.local",
  serverPort: 24800,
  clientName: "steamdeck",
  inputEnabled: true,
  fingerprintPending: false,
  gamingMode: true,
  ...overrides,
});

describe("label maps", () => {
  it("covers every helper state", () => {
    for (const state of HELPER_STATES) {
      expect(STATE_LABEL[state]).toBeTruthy();
      expect(STATE_COLOUR[state]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("covers every input backend", () => {
    for (const backend of INPUT_BACKENDS) {
      expect(BACKEND_LABEL[backend]).toBeTruthy();
    }
  });
});

describe("describeBackend", () => {
  it("names the resolved backend", () => {
    expect(describeBackend(status())).toBe("Gamescope (libei)");
  });

  it("says so when automatic has not resolved yet", () => {
    expect(describeBackend(status({ backend: null, requestedBackend: "auto" }))).toBe(
      "Not resolved yet",
    );
  });

  it("distinguishes a requested-but-inactive backend from an active one", () => {
    const text = describeBackend(status({ backend: null, requestedBackend: "uinput" }));
    expect(text).toContain("uinput");
    expect(text).toContain("not active");
  });
});

describe("describeServer", () => {
  it("shows host and port in client mode", () => {
    expect(describeServer(status())).toBe("desktop.local:24800");
  });

  it("says not configured when no host is set", () => {
    expect(describeServer(status({ server: "" }))).toBe("Not configured");
  });

  it("shows the listening port in server mode", () => {
    expect(describeServer(status({ mode: "server", server: "" }))).toContain("24800");
  });
});

describe("server mode in Gaming Mode", () => {
  it("is unavailable in Gaming Mode", () => {
    expect(serverModeUnavailable(status({ mode: "server", gamingMode: true }))).toBe(true);
  });

  it("is available in Desktop Mode", () => {
    expect(serverModeUnavailable(status({ mode: "server", gamingMode: false }))).toBe(false);
  });

  it("never applies to client mode", () => {
    expect(serverModeUnavailable(status({ mode: "client", gamingMode: true }))).toBe(false);
  });

  it("is surfaced in the mode label", () => {
    expect(describeMode(status({ mode: "server", gamingMode: true }))).toBe(
      "Server (unavailable)",
    );
    expect(describeMode(status({ mode: "server", gamingMode: false }))).toBe("Server");
    expect(describeMode(status())).toBe("Client");
  });
});

describe("groupFingerprint", () => {
  it("groups into colon-separated byte pairs", () => {
    const grouped = groupFingerprint("ab".repeat(32));
    expect(grouped.split(":")).toHaveLength(32);
    expect(grouped).toBe(Array(32).fill("AB").join(":"));
  });

  it("is idempotent on already-grouped input", () => {
    const once = groupFingerprint("ab".repeat(32));
    expect(groupFingerprint(once)).toBe(once);
  });

  it("returns the input unchanged when there is no hex to group", () => {
    expect(groupFingerprint("not a fingerprint")).toBe("not a fingerprint");
  });
});

describe("truncate", () => {
  it("leaves short text alone", () => {
    expect(truncate("short")).toBe("short");
  });

  it("shortens long text and marks it", () => {
    const result = truncate("x".repeat(500));
    expect(result.length).toBeLessThanOrEqual(160);
    expect(result.endsWith("…")).toBe(true);
  });

  it("honours a custom limit", () => {
    expect(truncate("abcdefghij", 5)).toHaveLength(5);
  });
});
