/**
 * Frontend mirror of the backend's validation rules.
 *
 * This exists purely so a typo shows an error next to the field instead of after a
 * round trip. The backend re-validates everything and is the authority -- see
 * docs/SECURITY.md §2. If these ever disagree, the backend wins and this file is the
 * one that is wrong.
 */

import type { Settings } from "../api/types";
import { ACTIVATION_MODES, INPUT_BACKENDS, LOG_LEVELS, MODES } from "../api/types";

const MAX_HOSTNAME_LENGTH = 253;
const MAX_LABEL_LENGTH = 63;

const LABEL = /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/;
const CLIENT_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$/;
const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
const HEX_AND_COLONS = /^[0-9a-fA-F:]+$/;
const NUMERIC_ONLY = /^[0-9.]+$/;
const DISALLOWED_IN_HOST = /[\s]/;

function isValidIpv4(host: string): boolean {
  const match = host.match(IPV4);
  if (!match) return false;
  return match.slice(1).every((part) => {
    const value = Number(part);
    return Number.isInteger(value) && value >= 0 && value <= 255;
  });
}

function isValidHostname(host: string): boolean {
  if (host.length > MAX_HOSTNAME_LENGTH) return false;
  const labels = host.split(".");
  return labels.every(
    (label) => label.length >= 1 && label.length <= MAX_LABEL_LENGTH && LABEL.test(label),
  );
}

export function isValidServerHost(host: string): boolean {
  if (host === "") return true; // "not configured yet"; the mode rule decides
  if (host !== host.trim() || DISALLOWED_IN_HOST.test(host)) return false;

  if (host.includes(":") && !NUMERIC_ONLY.test(host)) {
    // Crude IPv6 acceptance; the backend performs the authoritative parse. Anything
    // with a colon that is not hex-and-colons (e.g. "desktop:24800") is refused.
    return HEX_AND_COLONS.test(host);
  }

  // A string that could only be an IPv4 attempt must actually parse as one, so
  // "256.1.1.1" and "1.1.1" are rejected rather than read as hostnames.
  if (NUMERIC_ONLY.test(host)) return isValidIpv4(host);

  return isValidHostname(host);
}

/** Returns an error message, or null when the value is acceptable. */
export function validateField(field: keyof Settings, value: unknown): string | null {
  switch (field) {
    case "server_host":
      if (typeof value !== "string") return "Must be text.";
      return isValidServerHost(value) ? null : "Enter a valid hostname or IP address.";

    case "server_port":
      if (typeof value !== "number" || !Number.isInteger(value)) {
        return "Must be a whole number.";
      }
      return value >= 1 && value <= 65535 ? null : "Must be between 1 and 65535.";

    case "client_name":
      if (typeof value !== "string") return "Must be text.";
      return CLIENT_NAME.test(value)
        ? null
        : "Use letters, digits, dots, hyphens or underscores (max 63).";

    case "screen_width":
    case "screen_height":
      if (typeof value !== "number" || !Number.isInteger(value)) {
        return "Must be a whole number.";
      }
      // 0 means "detect from the running session".
      return value === 0 || (value >= 320 && value <= 32767)
        ? null
        : "Use 0 to detect automatically, or a value between 320 and 32767.";

    case "reconnect_max_backoff_s":
      if (typeof value !== "number" || !Number.isInteger(value)) {
        return "Must be a whole number.";
      }
      return value >= 1 && value <= 300 ? null : "Must be between 1 and 300 seconds.";

    case "pointer_sensitivity":
      if (typeof value !== "number" || !Number.isFinite(value)) return "Must be a number.";
      return value >= 0.25 && value <= 4 ? null : "Must be between 0.25 and 4.";

    case "mode":
      return (MODES as readonly string[]).includes(value as string) ? null : "Unknown mode.";

    case "input_backend":
      return (INPUT_BACKENDS as readonly string[]).includes(value as string)
        ? null
        : "Unknown backend.";

    case "activation_mode":
      return (ACTIVATION_MODES as readonly string[]).includes(value as string)
        ? null
        : "Unknown activation mode.";

    case "log_level":
      return (LOG_LEVELS as readonly string[]).includes(value as string)
        ? null
        : "Unknown log level.";

    case "keyboard_layout":
      if (typeof value !== "string") return "Must be text.";
      if (value === "") return null;
      return /^[a-z]{2,10}$/.test(value) ? null : "Lowercase XKB layout name (e.g. us, be, de).";

    case "tls_enabled":
    case "check_peer_fingerprints":
    case "autostart_gaming_mode":
    case "reconnect_enabled":
      return typeof value === "boolean" ? null : "Must be true or false.";

    case "socket_path_override":
      if (typeof value !== "string") return "Must be text.";
      if (value === "") return null;
      if (!value.startsWith("/")) return "Must be an absolute path.";
      return value.split("/").includes("..") ? "Must not contain '..'." : null;

    default:
      return null;
  }
}
