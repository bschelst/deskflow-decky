import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
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
import { LogsModal } from "../components/LogsModal";
import type { HelperInfo, SelfTestCheck, Settings } from "../api/types";
import { ACTIVATION_MODES, INPUT_BACKENDS, LOG_LEVELS, MODES } from "../api/types";
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

export const SettingsPage: FC = () => {
  const { status } = useDeskflowStatus();
  const [settings, setLocal] = useState<Settings | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<string | null>(null);
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

  useEffect(() => {
    void (async () => {
      const result = await getSettings();
      if (result.ok) setLocal(result.data);
      else setBanner(result.error.message);

      const info = await getHelperInfo();
      if (info.ok) setHelper(info.data);
    })();
  }, []);

  /**
   * Frontend validation is for immediate feedback only. The backend re-validates and
   * is the authority; a value that passes here can still be rejected there.
   */
  const commit = useCallback(
    async (patch: Partial<Settings>) => {
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
        setBanner(null);
      } else {
        setFieldErrors((current) => ({ ...current, [field]: result.error.message }));
      }
    },
    [],
  );

  if (settings === null) {
    return <PanelSection title="Settings" spinner />;
  }

  const serverModeInGamingMode = settings.mode === "server" && (status?.gamingMode ?? false);

  return (
    <>
      {banner ? (
        <PanelSection>
          <PanelSectionRow>
            <Field bottomSeparator="none">{banner}</Field>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      <PanelSection title="Connection">
        <PanelSectionRow>
          <DropdownItem
            label="Mode"
            description="Client receives input from another computer. Server shares this Deck's own input."
            rgOptions={modeOptions}
            selectedOption={settings.mode}
            onChange={(option) => void commit({ mode: option.data })}
          />
        </PanelSectionRow>

        {serverModeInGamingMode ? (
          <PanelSectionRow>
            <Field bottomSeparator="none">
              Server mode cannot capture input in Gaming Mode, because Gamescope
              provides no input-capture portal. Switch to Desktop Mode to use it.
            </Field>
          </PanelSectionRow>
        ) : null}

        {settings.mode === "client" ? (
          <PanelSectionRow>
            <TextField
              label="Server address"
              description={fieldErrors.server_host ?? "Hostname or IP of the Deskflow server."}
              value={settings.server_host}
              onBlur={(event) => void commit({ server_host: event.currentTarget.value.trim() })}
            />
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          <TextField
            label="Port"
            mustBeNumeric
            description={fieldErrors.server_port ?? "Deskflow's default is 24800."}
            value={String(settings.server_port)}
            onBlur={(event) => {
              const parsed = Number.parseInt(event.currentTarget.value, 10);
              // Send a number, never a string: the backend refuses to coerce.
              if (Number.isInteger(parsed)) void commit({ server_port: parsed });
              else setFieldErrors((c) => ({ ...c, server_port: "Must be a whole number." }));
            }}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <TextField
            label="This Deck's name"
            description={fieldErrors.client_name ?? "How this Deck appears to the server."}
            value={settings.client_name}
            onBlur={(event) => void commit({ client_name: event.currentTarget.value.trim() })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Security">
        <PanelSectionRow>
          <ToggleField
            label="Use TLS"
            description="Encrypt the connection. Leave this on unless you know why you are turning it off."
            checked={settings.tls_enabled}
            onChange={(checked) =>
              void commit(
                checked
                  ? { tls_enabled: true }
                  : { tls_enabled: false },
              )
            }
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
                setBanner(
                  result.ok ? "Trusted fingerprint forgotten." : result.error.message,
                );
              })
            }
          >
            Forget trusted fingerprint
          </ButtonItem>
        </PanelSectionRow>

        {!settings.tls_enabled ? (
          <PanelSectionRow>
            <Field bottomSeparator="none">
              TLS is off. Input from the server travels unencrypted over your network.
            </Field>
          </PanelSectionRow>
        ) : null}
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
                  setBanner("Helper installed.");
                } else {
                  setBanner(result.error.message);
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
                if (!result.ok) setBanner(result.error.message);
              })
            }
          >
            Restart helper
          </ButtonItem>
        </PanelSectionRow>
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
            layout="inline"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const result = await runSelfTest();
                if (result.ok) setChecks(result.data.checks);
                else setBanner(result.error.message);
              })
            }
          >
            Run self-test
          </ButtonItem>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem layout="inline" onClick={() => showModal(<LogsModal />)}>
            View recent logs
          </ButtonItem>
        </PanelSectionRow>

        {(checks ?? []).map((check) => (
          <PanelSectionRow key={check.id}>
            <Field label={check.id} bottomSeparator="none" description={check.detail}>
              {check.ok ? "Pass" : "Fail"}
            </Field>
          </PanelSectionRow>
        ))}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description="Writes a redacted report that is safe to attach to a bug report."
            onClick={() =>
              void act(async () => {
                const result = await exportDiagnostics();
                setBanner(
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
      </PanelSection>
    </>
  );
};
