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
import type { HelperInfo, SelfTestCheck, Settings } from "../api/types";
import { ACTIVATION_MODES, INPUT_BACKENDS, LOG_LEVELS, MODES } from "../api/types";
import { EditableTextField } from "../components/EditableTextField";
import { LogsModal } from "../components/LogsModal";
import { useDeskflowStatus } from "../hooks/useDeskflowStatus";
import { BACKEND_LABEL, FAIL_COLOUR, MODE_LABEL, PASS_COLOUR } from "../lib/format";
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

const SelfTestRow: FC<{ check: SelfTestCheck }> = ({ check }) => (
  <PanelSectionRow>
    <Field
      // Status lives in the label so it reads left-to-right. The glyph carries the
      // meaning; the colour reinforces it.
      label={
        <span style={{ color: check.ok ? PASS_COLOUR : FAIL_COLOUR }}>
          {check.ok ? "✓" : "✗"} {check.id}
        </span>
      }
      description={check.detail}
      bottomSeparator="standard"
    />
  </PanelSectionRow>
);

export const SettingsPage: FC = () => {
  const { status } = useDeskflowStatus();
  const [settings, setLocal] = useState<Settings | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [helper, setHelper] = useState<HelperInfo | null>(null);
  const [checks, setChecks] = useState<SelfTestCheck[] | null>(null);
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
          <PanelSectionRow>
            <EditableTextField
              label="Server address"
              description={fieldErrors.server_host ?? "Hostname or IP of the Deskflow server."}
              value={settings.server_host}
              onCommit={(value) => void commit({ server_host: value })}
            />
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          <EditableTextField
            label="Port"
            mustBeNumeric
            description={fieldErrors.server_port ?? "Deskflow's default is 24800."}
            value={String(settings.server_port)}
            onCommit={(value) => {
              const parsed = Number.parseInt(value, 10);
              // Send a number, never a string: the backend refuses to coerce.
              if (Number.isInteger(parsed)) void commit({ server_port: parsed });
              else setFieldErrors((c) => ({ ...c, server_port: "Must be a whole number." }));
            }}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <EditableTextField
            label="This Deck's name"
            description={fieldErrors.client_name ?? "How this Deck appears to the server."}
            value={settings.client_name}
            onCommit={(value) => void commit({ client_name: value })}
          />
        </PanelSectionRow>

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
            label="Start automatically in Gaming Mode"
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

      <PanelSection title="Helper">
        <PanelSectionRow>
          <Field label="Helper status" bottomSeparator="none">
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
            description={`Installs or updates ${helper?.appId ?? "the helper flatpak"} at user scope.`}
            onClick={() =>
              void act(async () => {
                const result = await installHelper();
                if (result.ok) {
                  setHelper(result.data);
                  say("helper", "Helper installed.");
                } else {
                  say("helper", result.error.message);
                }
              })
            }
          >
            {helper?.installed ? "Update helper" : "Install helper"}
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
                say("helper", result.ok ? "Helper restarted." : result.error.message);
              })
            }
          >
            Restart helper
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
                if (result.ok) setChecks(result.data.checks);
                else say("diagnostics", result.error.message);
              })
            }
          >
            Run self-test
          </ButtonItem>
        </PanelSectionRow>

        {(checks ?? []).map((check) => (
          <SelfTestRow key={check.id} check={check} />
        ))}

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
