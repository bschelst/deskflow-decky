import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { ErrorCode } from "../api/types";

/**
 * Static content, compiled in.
 *
 * Not fetched: the Deck is frequently offline, and reaching out to the network to
 * render a help page would be an egress nobody asked for.
 */

/**
 * Prose spans the full row width.
 *
 * `Field` puts children in the right-hand control column and reserves the left for a
 * label, so a paragraph passed as children renders beside a permanently empty gutter.
 * The `description` slot is the full-width one.
 */
/**
 * Every row is `focusable`.
 *
 * Steam scrolls a page by moving focus, so a page made entirely of static text has
 * nothing to focus and cannot be scrolled with the gamepad at all -- it just sits
 * there showing the first screenful. Marking prose rows focusable gives the D-pad
 * somewhere to land, and the view follows.
 */
const Paragraph: FC<{ children: string }> = ({ children }) => (
  <PanelSectionRow>
    <Field description={children} bottomSeparator="none" focusable />
  </PanelSectionRow>
);

/** A named thing and its explanation: name on the left, prose full-width beneath. */
const Entry: FC<{ term: string; detail: string }> = ({ term, detail }) => (
  <PanelSectionRow>
    <Field label={term} description={detail} bottomSeparator="standard" focusable />
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
    meaning: "The Deskflow Decky helper flatpak is not installed.",
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
        the Settings page. It defaults to something like "steamos-4f2a" rather than
        "steamdeck", because every Steam Deck and Steam Machine ships with that same
        hostname and two of them would collide on one server.
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
      <Entry
        term="If you rejected it"
        detail={
          "Nothing is trusted and the helper stops. Turn the Helper toggle back on and " +
          "you will be asked again on the next connection. Rejecting is not permanent " +
          "and nothing needs to be reset."
        }
      />
      <Entry
        term="If you accepted the wrong one"
        detail={
          "Use 'Forget trusted fingerprint' on the Settings page, then reconnect. The " +
          "next connection asks again from scratch."
        }
      />
    </PanelSection>

    <PanelSection title="Locking input to one screen">
      <Paragraph>
        Deskflow can pin the pointer to whichever screen it is on, so it cannot cross to
        another machine until you unlock it. This is the way out if the pointer ends up
        somewhere you cannot easily get it back from.
      </Paragraph>
      <Entry
        term="Scroll Lock"
        detail={
          "Works out of the box. Deskflow registers Scroll Lock as a lock/unlock toggle " +
          "automatically, unless disableLockToScreen is turned on in the server's " +
          "options or you have defined your own lock action."
        }
      />
      <Entry
        term="Your own shortcut"
        detail={
          "Add a hotkey to the options section of the server's configuration, for " +
          "example: keystroke(alt+shift+l) = lockCursorToScreen(toggle). The argument " +
          "may be on, off or toggle. Defining one replaces the automatic Scroll Lock " +
          "binding rather than adding to it."
        }
      />
      <Entry
        term="Start locked"
        detail={
          "Set defaultLockToScreenState = true in the server's options and input stays " +
          "on the screen it starts on until you unlock it."
        }
      />
      <Paragraph>
        The shortcut is handled by the server, because that is where the keyboard is.
        The plugin's own 'Input enabled' toggle does something similar from the Deck
        side: it stops input being delivered without dropping the connection.
      </Paragraph>
    </PanelSection>

    <PanelSection title="Input backends">
      <Entry
        term="Gamescope (libei)"
        detail={
          "Sends input straight into the Gamescope compositor through its own input " +
          "socket. This is the one that works in Gaming Mode, and what Automatic prefers."
        }
      />
      <Entry
        term="XWayland (XTest)"
        detail={
          "A fallback that goes through Gamescope's X server. Pointer behaviour can be " +
          "unreliable, particularly with cursor grabbing."
        }
      />
      <Entry
        term="uinput"
        detail={
          "Creates virtual kernel input devices. A last resort: it needs extra " +
          "permissions and delivers input to every session rather than to Gamescope."
        }
      />
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
        <Entry
          key={entry.code}
          term={entry.code}
          detail={`${entry.meaning} ${entry.fix}`}
        />
      ))}
    </PanelSection>

    <PanelSection title="Known limitations">
      <Entry
        term="The pointer is invisible until you click"
        detail={
          "Gamescope is started with --hide-cursor-delay 3000, so it hides the pointer " +
          "after three idle seconds. Injected motion does not appear to reset that " +
          "timer, while button events do — so the cursor reappears on a click. The flag " +
          "comes from the Steam session, not from this plugin. Worth trying: turn off " +
          "relativeMouseMoves in the server's options, which makes Deskflow send " +
          "absolute positions instead of deltas."
        }
      />
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
