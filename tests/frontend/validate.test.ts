/**
 * The frontend mirror must agree with py_modules/validation.py.
 *
 * The shared case table below is deliberately duplicated from the Python suite. If
 * the two ever disagree, the backend is right and this file is the bug -- but the
 * disagreement must be visible, which is what these tests are for.
 */

import { describe, expect, it } from "vitest";
import { isValidServerHost, validateField } from "../../src/lib/validate";

describe("server_host, mirroring the backend", () => {
  it.each([
    "192.168.1.10",
    "255.255.255.255",
    "desktop",
    "desktop.local",
    "my-pc.example.com",
    "a",
    "a".repeat(63),
    "::1",
    "fe80::1ff:fe23:4567:890a",
  ])("accepts %s", (host) => {
    expect(isValidServerHost(host)).toBe(true);
  });

  it.each([
    " ",
    "  desktop  ",
    "desk top",
    "desktop\n",
    "-leading.hyphen",
    "trailing.hyphen-",
    "a".repeat(64),
    "256.1.1.1",
    "1.1.1",
    "http://desktop",
    "desktop:24800",
    "desktop;reboot",
    "desktop|whoami",
    "$(hostname)",
    "../../etc/hosts",
  ])("rejects %s", (host) => {
    expect(isValidServerHost(host)).toBe(false);
  });

  it("accepts empty, meaning not configured yet", () => {
    expect(isValidServerHost("")).toBe(true);
  });
});

describe("validateField", () => {
  it("rejects a port supplied as a string, matching the backend's no-coercion rule", () => {
    expect(validateField("server_port", "24800")).not.toBeNull();
  });

  it.each([1, 24800, 65535])("accepts port %s", (port) => {
    expect(validateField("server_port", port)).toBeNull();
  });

  it.each([0, -1, 65536, 1.5])("rejects port %s", (port) => {
    expect(validateField("server_port", port)).not.toBeNull();
  });

  it.each(["steamdeck", "deck-1", "my.deck_2"])("accepts client name %s", (name) => {
    expect(validateField("client_name", name)).toBeNull();
  });

  it.each(["", "-deck", "my deck", "deck;rm", "a".repeat(64)])(
    "rejects client name %s",
    (name) => {
      expect(validateField("client_name", name)).not.toBeNull();
    },
  );

  it.each([0.25, 1, 4])("accepts sensitivity %s", (value) => {
    expect(validateField("pointer_sensitivity", value)).toBeNull();
  });

  it.each([0.24, 4.01, NaN, Infinity])("rejects sensitivity %s", (value) => {
    expect(validateField("pointer_sensitivity", value)).not.toBeNull();
  });

  it("rejects a boolean field given a string", () => {
    expect(validateField("tls_enabled", "true")).not.toBeNull();
  });

  it("rejects an unknown enum member", () => {
    expect(validateField("log_level", "verbose")).not.toBeNull();
    expect(validateField("mode", "Client")).not.toBeNull();
  });

  it("rejects a socket path escaping upwards", () => {
    expect(validateField("socket_path_override", "/run/user/1000/../etc")).not.toBeNull();
  });

  it("accepts an empty socket path override", () => {
    expect(validateField("socket_path_override", "")).toBeNull();
  });
});
