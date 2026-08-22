// Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

import { ConfirmModal, Field, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { PendingFingerprint } from "../api/types";
import { fingerprintLines } from "../lib/format";

/**
 * The one modal in the plugin (docs/UI-SPEC.md §4).
 *
 * A toast would be wrong here: a trust decision must not be made by accident, and a
 * missed toast silently means "not trusted" with no explanation.
 */

/**
 * The fingerprint, split across lines.
 *
 * Rendered as one string it is 95 characters and overflows the modal, running off the
 * screen edge — which hides the trailing bytes of the exact value the user is being
 * asked to compare. Each line is its own row so nothing can overflow.
 */
const Fingerprint: FC<{ label: string; value: string }> = ({ label, value }) => {
  const lines = fingerprintLines(value);
  return (
    <>
      {lines.map((line, index) => (
        <PanelSectionRow key={line}>
          <Field
            label={index === 0 ? label : ""}
            bottomSeparator={index === lines.length - 1 ? "standard" : "none"}
            focusable
          >
            <span style={{ fontFamily: "monospace", letterSpacing: "0.05em" }}>{line}</span>
          </Field>
        </PanelSectionRow>
      ))}
    </>
  );
};

export const FingerprintModal: FC<{
  pending: PendingFingerprint;
  onAccept: () => void;
  onReject: () => void;
  closeModal?: () => void;
}> = ({ pending, onAccept, onReject, closeModal }) => {
  const changed = pending.classification === "changed";

  return (
    <ConfirmModal
      strTitle={changed ? "This server's identity has changed" : "Trust this server?"}
      // Reject is the default action: the safe choice should be the one that happens
      // when someone presses through without reading.
      strOKButtonText="Trust this server"
      strCancelButtonText="Reject"
      bAlertDialog={false}
      bDestructiveWarning={changed}
      onOK={() => {
        onAccept();
        closeModal?.();
      }}
      onCancel={() => {
        onReject();
        closeModal?.();
      }}
      closeModal={closeModal}
    >
      <PanelSectionRow>
        <Field label="Server" bottomSeparator="none" focusable>
          {pending.host}
        </Field>
      </PanelSectionRow>

      <Fingerprint label="Fingerprint (SHA-256)" value={pending.fingerprint} />

      {changed && pending.previous ? (
        <Fingerprint label="Previously" value={pending.previous} />
      ) : null}

      <PanelSectionRow>
        <Field
          bottomSeparator="none"
          focusable
          description={
            changed
              ? "You trusted a different certificate for this server before. That can " +
                "mean the server was reinstalled — or that something is intercepting " +
                "the connection. Do not accept this unless you know which."
              : "Compare this fingerprint against the one shown on the server before " +
                "accepting. Accepting trusts this certificate for future connections."
          }
        />
      </PanelSectionRow>
    </ConfirmModal>
  );
};
