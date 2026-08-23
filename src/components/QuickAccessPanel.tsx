// Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

import {
  ButtonItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
} from "@decky/ui";
import { useCallback, useEffect, useRef, useState, type FC } from "react";

import {
  acceptFingerprint,
  disableInput,
  enableInput,
  getHelperInfo,
  getPendingFingerprint,
  installHelper,
  rejectFingerprint,
  restartHelper,
  runSelfTest,
  startHelper,
  stopHelper,
} from "../api/backend";
import type { HelperInfo, SelfTestCheck, Status } from "../api/types";
import { useAction, useDeskflowStatus } from "../hooks/useDeskflowStatus";
import { truncate } from "../lib/format";
import { PLUGIN_ROUTE } from "../routes";
import { FingerprintModal } from "./FingerprintModal";
import { SelfTestRows } from "./SelfTestRows";
import { StatusRows } from "./StatusRows";

const isRecoverable = (status: Status) =>
  status.state === "disconnected" || status.state === "degraded" || status.state === "error";

const isRunning = (status: Status) =>
  status.state !== "stopped" && status.state !== "error";

export const QuickAccessPanel: FC = () => {
  const { status, error, loading, refresh } = useDeskflowStatus();
  const [busy, perform, actionError] = useAction(refresh);
  const [note, setNote] = useState<string | null>(null);
  const [checks, setChecks] = useState<SelfTestCheck[] | null>(null);
  const [helper, setHelper] = useState<HelperInfo | null>(null);
  // Guards against re-opening the dialog on every status poll while it is already up.
  const promptOpen = useRef(false);

  useEffect(() => {
    void (async () => {
      const result = await getHelperInfo();
      if (result.ok) setHelper(result.data);
    })();
  }, []);

  const promptForFingerprint = useCallback(async () => {
    if (promptOpen.current) return;
    const result = await getPendingFingerprint();
    if (!result.ok || result.data === null) return;

    promptOpen.current = true;
    const pending = result.data;
    showModal(
      <FingerprintModal
        pending={pending}
        onAccept={() => {
          promptOpen.current = false;
          void (async () => {
            await acceptFingerprint(pending.fingerprint);
            await refresh();
          })();
        }}
        onReject={() => {
          promptOpen.current = false;
          void (async () => {
            await rejectFingerprint();
            await refresh();
          })();
        }}
      />,
    );
  }, [refresh]);

  useEffect(() => {
    if (status?.fingerprintPending) void promptForFingerprint();
  }, [status?.fingerprintPending, promptForFingerprint]);

  if (loading && status === null) {
    // A spinner beats an empty panel or a flash of "Disconnected" that is not true yet.
    return <PanelSection title="Status" spinner />;
  }

  if (status === null) {
    return (
      <PanelSection title="Status">
        <PanelSectionRow>
          <Field label="Status" bottomSeparator="none">
            Unavailable
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            description={error?.message ?? "The plugin backend did not respond."}
            bottomSeparator="none"
          />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const diagnostic = note ?? actionError?.message ?? status.lastError ?? error?.message ?? null;

  // Shown in place of the normal panel until the helper is installed -- otherwise a
  // first-time user lands on toggles for a helper that does not exist yet, with no
  // hint that Settings has an install button several screens down.
  if (helper !== null && !helper.installed) {
    return (
      <PanelSection title="Get started">
        <PanelSectionRow>
          <Field
            description="Deskflow Decky needs its helper installed before it can connect to your Deskflow server."
            bottomSeparator="none"
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const result = await installHelper();
                if (result.ok) {
                  setHelper(result.data);
                  setNote("Deskflow Decky helper installed.");
                }
                return result;
              })
            }
          >
            Install Deskflow Decky helper
          </ButtonItem>
        </PanelSectionRow>
        {diagnostic ? (
          <PanelSectionRow>
            <Field description={truncate(diagnostic)} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    );
  }

  return (
    <>
      {/* "Status", not "Deskflow": the panel header directly above already carries
          the plugin name, and repeating it labelled nothing. */}
      <PanelSection title="Status">
        <StatusRows status={status} />
      </PanelSection>

      <PanelSection title="Control">
        <PanelSectionRow>
          <ToggleField
            label="Deskflow Decky helper"
            description="Connect to the Deskflow server."
            checked={isRunning(status)}
            disabled={busy}
            onChange={(next) => {
              setNote(null);
              void perform(() => (next ? startHelper() : stopHelper()));
            }}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ToggleField
            label="Input enabled"
            description={
              "Same as the helper toggle above: deskflow-core has no way to pause " +
              "input delivery without dropping the connection, so this starts and " +
              "stops it too."
            }
            checked={status.inputEnabled}
            disabled={busy}
            onChange={(next) => {
              setNote(null);
              void perform(() => (next ? enableInput() : disableInput()));
            }}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || !isRecoverable(status)}
            onClick={() => {
              setNote(null);
              void perform(restartHelper);
            }}
          >
            Reconnect
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Diagnostics">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const result = await runSelfTest();
                if (result.ok) {
                  setChecks(result.data.checks);
                  const failed = result.data.checks.filter((check) => !check.ok);
                  setNote(
                    failed.length === 0
                      ? `All ${result.data.total} checks passed.`
                      : `${failed.length} of ${result.data.total} need attention.`,
                  );
                }
                return result;
              })
            }
          >
            Run self-test
          </ButtonItem>
        </PanelSectionRow>

        {checks ? <SelfTestRows checks={checks} /> : null}

        {diagnostic ? (
          <PanelSectionRow>
            <Field description={truncate(diagnostic)} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => Navigation.Navigate(PLUGIN_ROUTE)}>
            Settings, docs &amp; about
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
