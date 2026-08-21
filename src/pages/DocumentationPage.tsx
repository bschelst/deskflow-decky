import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import type { FC, ReactNode } from "react";

import type { ErrorCode } from "../api/types";

/**
 * Static content, compiled in.
 *
 * Not fetched: the Deck is frequently offline, and reaching out to the network to
 * render a help page would be an egress nobody asked for.
 */

const Paragraph: FC<{ children: ReactNode }> = ({ children }) => (
  <PanelSectionRow>
    <Field bottomSeparator="none">{children}</Field>
  </PanelSectionRow>
);

/** Every code the backend can return, and what to do about it. */
const TROUBLESHOOTING: Array<{ code: ErrorCode; meaning: string; fix: string }> = [
  {
    code: "not_configured",
    meaning: "No server address is set.",
    fix: "Enter the address of the machine running the Deskflow server on the Settings page.",
  },
  {
    code: "socket_not_found",
    meaning: "Gamescope's input socket could not be found.",
    fix: "Run the self-test to see everywhere that was checked. This usually means the plugin is running outside a Gamescope session, or Gamescope was built without input-emulation support.",
  },
  {
    code: "backend_unavailable",
    meaning: "The selected input backend cannot be used here.",
    fix: "Set the input backend to Automatic, or pick the one the self-test reports as available.",
  },
  {
    code: "server_mode_unsupported",
    meaning: "Server mode was selected in Gaming Mode.",
    fix: "Gamescope provides no input-capture portal, so the Deck cannot share its own keyboard and mouse from Gaming Mode. Switch to Desktop Mode, or use client mode.",
  },
  {
    code: "not_installed",
    meaning: "The Deskflow helper flatpak is not installed.",
    fix: "Install it from the Settings page, or run packaging/install-helper.sh in Desktop Mode.",
  },
  {
    code: "tls_setup_failed",
    meaning: "The certificate could not be generated.",
    fix: "Check that openssl is available. Deskflow's own engine cannot create this file, so the plugin does it.",
  },
  {
    code: "already_running",
    meaning: "The helper is already running.",
    fix: "Use Reconnect rather than starting it a second time.",
  },
  {
    code: "not_running",
    meaning: "The action needs a running helper.",
    fix: "Turn the Helper toggle on first.",
  },
  {
    code: "timeout",
    meaning: "An operation took too long.",
    fix: "Check the network connection to the server, then retry.",
  },
  {
    code: "validation",
    meaning: "A setting was rejected.",
    fix: "The message names the field. Correct it and try again.",
  },
  {
    code: "internal",
    meaning: "Something unexpected went wrong.",
    fix: "Export diagnostics and open an issue; the detail is in the plugin log.",
  },
  {
    code: "transport",
    meaning: "The plugin frontend could not reach its backend.",
    fix: "Reload the plugin from Decky's settings, or restart the Steam client.",
  },
];

export const DocumentationPage: FC = () => (
  <>
    <PanelSection title="What this does">
      <Paragraph>
        This plugin lets a computer running a Deskflow server drive this Deck's
        keyboard and mouse, including inside Gaming Mode -- the Steam UI, native Linux
        games, and Proton games.
      </Paragraph>
      <Paragraph>
        It delivers keyboard input, mouse buttons, the scroll wheel, and relative
        pointer motion. Clipboard sharing, drag-and-drop, and moving the pointer across
        a screen edge are not supported.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Setting up the server">
      <Paragraph>
        1. Install Deskflow on the computer whose keyboard and mouse you want to use,
        and configure it as a server.
      </Paragraph>
      <Paragraph>
        2. Add a screen to its layout whose name exactly matches this Deck's name from
        the Settings page (the default is "steamdeck").
      </Paragraph>
      <Paragraph>
        3. Note the server's IP address, and make sure port 24800 is reachable from the
        Deck.
      </Paragraph>
    </PanelSection>

    <PanelSection title="First connection">
      <Paragraph>
        The first time the Deck connects, it shows the server's TLS fingerprint and
        asks whether to trust it. Compare it against the fingerprint shown on the
        server before accepting.
      </Paragraph>
      <Paragraph>
        If the fingerprint of a server you already trusted changes, the plugin says so
        explicitly. That can mean the server was reinstalled -- or that something is
        intercepting the connection. Do not accept it without knowing which.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Input backends">
      <Paragraph>
        <b>Gamescope (libei)</b> sends input straight into the Gamescope compositor
        through its own input socket. This is the one that works in Gaming Mode and is
        what Automatic prefers.
      </Paragraph>
      <Paragraph>
        <b>XWayland (XTest)</b> is a fallback that goes through Gamescope's X server.
        Pointer behaviour can be unreliable, particularly with cursor grabbing.
      </Paragraph>
      <Paragraph>
        <b>uinput</b> creates virtual kernel input devices. It is a last resort: it
        needs extra permissions and delivers input to every session rather than to
        Gamescope specifically.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Server mode">
      <Paragraph>
        The Deck can also act as a Deskflow server, sharing its own input with other
        computers -- but only in Desktop Mode. In Gaming Mode there is no
        input-capture portal behind Gamescope, so capture is impossible. The plugin
        refuses rather than pretending to work.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Troubleshooting">
      {TROUBLESHOOTING.map((entry) => (
        <PanelSectionRow key={entry.code}>
          <Field label={entry.code} description={entry.fix} bottomSeparator="standard">
            {entry.meaning}
          </Field>
        </PanelSectionRow>
      ))}
    </PanelSection>

    <PanelSection title="Known limitations">
      <Paragraph>
        Games that grab the pointer, or that switch capture mode during play, may
        behave inconsistently. Steam Input can also intercept events before they reach
        a game.
      </Paragraph>
      <Paragraph>
        Anti-cheat systems may treat synthesised input as suspicious. This plugin makes
        no claim about compatibility with any anti-cheat, and you use it with such
        games at your own risk.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Reporting a problem">
      <Paragraph>
        Use Export diagnostics on the Settings page. The report is built from a fixed
        list of fields and contains no typed text, keys, or credentials, so it is safe
        to attach to an issue.
      </Paragraph>
    </PanelSection>
  </>
);
