import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  showModal,
} from "@decky/ui";
import { useCallback, useEffect, useState, type FC } from "react";

import {
  exportDiagnostics,
  forgetFingerprint,
  getHelperInfo,
  getSettings,
  installHelper,
  restartHelper,
  runSelfTest,
  setSettings,
} from "../api/backend";
import type { HelperInfo, SelfTestResult, Settings } from "../api/types";
import { ACTIVATION_MODES, INPUT_BACKENDS, LOG_LEVELS, MODES } from "../api/types";
import { LogsModal } from "../components/LogsModal";
import { ValueRow } from "../components/ValueRow";
import { SelfTestRows } from "../components/SelfTestRows";
import { useDeskflowStatus } from "../hooks/useDeskflowStatus";
import { BACKEND_LABEL, MODE_LABEL } from "../lib/format";
import { validateField } from "../lib/validate";

const backendOptions = INPUT_BACKENDS.map((value) => ({
  data: value,
  label: BACKEND_LABEL[value],
}));

const modeOptions = MODES.map((value) => ({ data: value, label: MODE_LABEL[value] }));

const activationOptions = ACTIVATION_MODES.map((value) => ({
  data: value,
  label: value === "manual" ? "Manual" : "Always on",
}));

const logLevelOptions = LOG_LEVELS.map((value) => ({
  data: value,
  label: value.charAt(0).toUpperCase() + value.slice(1),
}));

/** Prose row. `description` spans the full width; children would sit in the right
 *  control column and leave the label gutter empty. */
const Note: FC<{ children: string }> = ({ children }) => (
  <PanelSectionRow>
    <Field description={children} bottomSeparator="none" focusable />
  </PanelSectionRow>
);

/**
 * Where a message came from, so it can be shown beside the control that produced it.
 *
 * A single banner at the top of the page is invisible when the button that set it sits
 * several sections further down — the action then looks like it did nothing at all,
 * which is exactly how "Install helper" appeared to fail.
 */
type NoticeWhere = "connection" | "security" | "helper" | "diagnostics";
interface Notice {
  where: NoticeWhere;
  text: string;
}

/**
 * One self-test result.
 *
 * A coloured dot matching the Status row, then the check's name — so a failing row is
 * findable at a glance and reads left-to-right. The dot is paired with wording in the
 * detail line, never colour alone.
 */

export const SettingsPage: FC = () => {
  const { status } = useDeskflowStatus();
  const [settings, setLocal] = useState<Settings | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [helper, setHelper] = useState<HelperInfo | null>(null);
  const [selfTest, setSelfTest] = useState<SelfTestResult | null>(null);
  // One flag for every action button on the page: without it a double-tap can issue
  // two concurrent lifecycle calls to the backend.
  const [busy, setBusy] = useState(false);

  const act = useCallback(async (run: () => Promise<void>) => {
    setBusy(true);
    try {
      await run();
    } finally {
      setBusy(false);
    }
  }, []);

  const say = useCallback((where: NoticeWhere, text: string) => {
    setNotice({ where, text });
  }, []);

  /** Renders the current message only in the section that raised it. */
  const NoticeFor: FC<{ where: NoticeWhere }> = ({ where }) =>
    notice && notice.where === where ? <Note>{notice.text}</Note> : null;

  useEffect(() => {
    void (async () => {
      const result = await getSettings();
      if (result.ok) setLocal(result.data);
      else setNotice({ where: "connection", text: result.error.message });

      const info = await getHelperInfo();
      if (info.ok) setHelper(info.data);
    })();
  }, []);

  /**
   * Frontend validation is for immediate feedback only. The backend re-validates and
   * is the authority; a value that passes here can still be rejected there.
   */
  const commit = useCallback(async (patch: Partial<Settings>) => {
    const [field] = Object.keys(patch);
    const localProblem = validateField(field as keyof Settings, Object.values(patch)[0]);
    if (localProblem) {
      setFieldErrors((current) => ({ ...current, [field]: localProblem }));
      return;
    }

    const result = await setSettings(patch);
    if (result.ok) {
      setLocal(result.data);
      setFieldErrors((current) => {
        const next = { ...current };
        delete next[field];
        return next;
      });
      setNotice(null);
    } else {
      setFieldErrors((current) => ({ ...current, [field]: result.error.message }));
    }
  }, []);

  /**
   * Commit a numeric field, reporting bad input instead of ignoring it.
   *
   * Number.parseInt("12abc") is 12 and parseInt("abc") is NaN, so a bare parse either
   * accepts nonsense or silently does nothing — and a field that quietly discards what
   * you typed gives no clue whether the value was taken. The backend refuses to coerce
   * strings, so a real number has to be sent.
   */
  const commitNumber = (field: keyof Settings, raw: string) => {
    const text = raw.trim();
    if (!/^\d+$/.test(text)) {
      setFieldErrors((current) => ({ ...current, [field]: "Enter digits only." }));
      return;
    }
    const parsed = Number(text);
    if (!Number.isSafeInteger(parsed)) {
      setFieldErrors((current) => ({ ...current, [field]: "That number is too large." }));
      return;
    }
    void commit({ [field]: parsed } as Partial<Settings>);
  };

  if (settings === null) {
    return <PanelSection title="Settings" spinner />;
  }

  const serverModeInGamingMode = settings.mode === "server" && (status?.gamingMode ?? false);

  return (
    <>
      <PanelSection title="Connection">
        <PanelSectionRow>
          <DropdownItem
            label="Mode"
            description={
              fieldErrors.mode ??
              "Client receives input from another computer. Server shares this Deck's own input."
            }
            rgOptions={modeOptions}
            selectedOption={settings.mode}
            onChange={(option) => void commit({ mode: option.data })}
          />
        </PanelSectionRow>

        {serverModeInGamingMode ? (
          <Note>
            Server mode cannot capture input in Gaming Mode, because Gamescope provides no
            input-capture portal. Switch to Desktop Mode to use it.
          </Note>
        ) : null}

        {settings.mode === "client" ? (
          <ValueRow
            label="Server address"
            description={fieldErrors.server_host ?? "Hostname or IP of the Deskflow server."}
            value={settings.server_host}
            onCommit={(value) => void commit({ server_host: value.trim() })}
          />
        ) : null}

        <ValueRow
          label="Port"
          numeric
          description={fieldErrors.server_port ?? "Deskflow's default is 24800."}
          value={settings.server_port}
          onCommit={(raw) => commitNumber("server_port", raw)}
        />

        <ValueRow
          label="This Deck's name"
          description={
            fieldErrors.client_name ??
            "How this Deck appears to the server. A screen with exactly this name must " +
              "exist in the server's layout."
          }
          value={settings.client_name}
          onCommit={(value) => void commit({ client_name: value.trim() })}
        />

        <NoticeFor where="connection" />
      </PanelSection>

      <PanelSection title="Security">
        <PanelSectionRow>
          <ToggleField
            label="Use TLS"
            description="Encrypt the connection. Leave this on unless you know why you are turning it off."
            checked={settings.tls_enabled}
            onChange={(checked) => void commit({ tls_enabled: checked })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ToggleField
            label="Verify server fingerprint"
            description={
              settings.tls_enabled
                ? "Required while TLS is on: encryption without verification does not protect against interception."
                : "Only applies when TLS is on."
            }
            checked={settings.check_peer_fingerprints}
            disabled={settings.tls_enabled}
            onChange={(checked) => void commit({ check_peer_fingerprints: checked })}
          />
        </PanelSectionRow>

        {!settings.tls_enabled ? (
          <Note>
            TLS is off. Input from the server travels unencrypted over your network.
          </Note>
        ) : null}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description={
              "Forget the trusted certificate for this server. You will be asked to " +
              "confirm its fingerprint again on the next connection."
            }
            onClick={() =>
              void act(async () => {
                const result = await forgetFingerprint();
                say(
                  "security",
                  result.ok ? "Trusted fingerprint forgotten." : result.error.message,
                );
              })
            }
          >
            Forget trusted fingerprint
          </ButtonItem>
        </PanelSectionRow>

        <NoticeFor where="security" />
      </PanelSection>

      <PanelSection title="Input">
        <PanelSectionRow>
          <DropdownItem
            label="Input backend"
            description="Automatic prefers Gamescope's own input socket."
            rgOptions={backendOptions}
            selectedOption={settings.input_backend}
            onChange={(option) => void commit({ input_backend: option.data })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <SliderField
            label="Pointer sensitivity"
            value={settings.pointer_sensitivity}
            min={0.25}
            max={4}
            step={0.05}
            showValue
            resetValue={1}
            onChange={(value) => void commit({ pointer_sensitivity: value })}
          />
        </PanelSectionRow>

        <ValueRow
          label="Screen width"
          numeric
          description={
            fieldErrors.screen_width ??
            "0 detects it from this session. Set it only if the pointer cannot reach " +
              "the whole screen."
          }
          value={settings.screen_width}
          onCommit={(raw) => commitNumber("screen_width", raw)}
        />

        <ValueRow
          label="Screen height"
          numeric
          description={fieldErrors.screen_height ?? "0 detects it from this session."}
          value={settings.screen_height}
          onCommit={(raw) => commitNumber("screen_height", raw)}
        />

        <PanelSectionRow>
          <ToggleField
            label="Share clipboard"
            description={
              "Copy and paste text between this Deck and the server. Only works in " +
              "Desktop Mode: Gamescope does not implement the protocol the clipboard " +
              "tools need, so in Gaming Mode this has no effect."
            }
            checked={settings.clipboard_enabled}
            onChange={(checked) => void commit({ clipboard_enabled: checked })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <DropdownItem
            label="Activation"
            description="Manual means input is delivered only while you enable it."
            rgOptions={activationOptions}
            selectedOption={settings.activation_mode}
            onChange={(option) => void commit({ activation_mode: option.data })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Behaviour">
        <PanelSectionRow>
          <ToggleField
            label="Start automatically"
            description={
              "Starts the Deskflow Decky helper whenever the plugin loads, so it survives a restart. " +
              "The toggle in the Quick Access panel is for the current session only. " +
              "Turned off automatically if the helper repeatedly fails to connect."
            }
            checked={settings.autostart_gaming_mode}
            onChange={(checked) => void commit({ autostart_gaming_mode: checked })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ToggleField
            label="Reconnect automatically"
            checked={settings.reconnect_enabled}
            onChange={(checked) => void commit({ reconnect_enabled: checked })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ToggleField
            label="Notify me when disconnected"
            description={
              "Shows a Steam notification if a working connection drops. One per " +
              "outage, not one per reconnect attempt."
            }
            checked={settings.notifications_enabled}
            onChange={(checked) => void commit({ notifications_enabled: checked })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <SliderField
            label="Maximum reconnect delay"
            value={settings.reconnect_max_backoff_s}
            min={1}
            max={300}
            step={1}
            showValue
            valueSuffix=" s"
            disabled={!settings.reconnect_enabled}
            onChange={(value) => void commit({ reconnect_max_backoff_s: Math.round(value) })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Deskflow Decky helper">
        <PanelSectionRow>
          <Field label="Status" bottomSeparator="none">
            {helper === null
              ? "Checking…"
              : helper.installed
                ? helper.version || "Installed"
                : "Not installed"}
          </Field>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description={`Installs or updates the Deskflow Decky helper (${helper?.appId ?? "flatpak"}) at user scope.`}
            onClick={() =>
              void act(async () => {
                const result = await installHelper();
                if (result.ok) {
                  setHelper(result.data);
                  say("helper", "Deskflow Decky helper installed.");
                } else {
                  say("helper", result.error.message);
                }
              })
            }
          >
            {helper?.installed ? "Update Deskflow Decky helper" : "Install Deskflow Decky helper"}
          </ButtonItem>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description="Applies configuration changes that need a restart."
            onClick={() =>
              void act(async () => {
                const result = await restartHelper();
                say("helper", result.ok ? "Deskflow Decky helper restarted." : result.error.message);
              })
            }
          >
            Restart Deskflow Decky helper
          </ButtonItem>
        </PanelSectionRow>

        <NoticeFor where="helper" />
      </PanelSection>

      <PanelSection title="Diagnostics">
        <PanelSectionRow>
          <DropdownItem
            label="Log level"
            rgOptions={logLevelOptions}
            selectedOption={settings.log_level}
            onChange={(option) => void commit({ log_level: option.data })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const result = await runSelfTest();
                if (result.ok) {
                  setSelfTest(result.data);
                  const failed = result.data.total - result.data.passed;
                  say(
                    "diagnostics",
                    failed === 0
                      ? `All ${result.data.total} checks passed.`
                      : `${failed} of ${result.data.total} checks need attention.`,
                  );
                } else {
                  say("diagnostics", result.error.message);
                }
              })
            }
          >
            Run self-test
          </ButtonItem>
        </PanelSectionRow>

        {selfTest ? <SelfTestRows checks={selfTest.checks} /> : null}

        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => showModal(<LogsModal />)}>
            View recent logs
          </ButtonItem>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description="Writes a redacted report that is safe to attach to a bug report."
            onClick={() =>
              void act(async () => {
                const result = await exportDiagnostics();
                say(
                  "diagnostics",
                  result.ok
                    ? `Diagnostics written to ${result.data.path}`
                    : result.error.message,
                );
              })
            }
          >
            Export diagnostics
          </ButtonItem>
        </PanelSectionRow>

        <NoticeFor where="diagnostics" />
      </PanelSection>
    </>
  );
};
