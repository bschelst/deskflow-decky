import { ConfirmModal, Field, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { PendingFingerprint } from "../api/types";

/**
 * The one modal in the plugin (docs/UI-SPEC.md §4).
 *
 * A toast would be wrong here: a trust decision must not be made by accident, and a
 * missed toast silently means "not trusted" with no explanation.
 */
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
        <Field label="Server" bottomSeparator="none">
          {pending.host}
        </Field>
      </PanelSectionRow>

      <PanelSectionRow>
        <Field label="Fingerprint (SHA-256)" bottomSeparator="none">
          {pending.fingerprint}
        </Field>
      </PanelSectionRow>

      {changed && pending.previous ? (
        <PanelSectionRow>
          <Field label="Previously" bottomSeparator="none">
            {pending.previous}
          </Field>
        </PanelSectionRow>
      ) : null}

      <PanelSectionRow>
        <Field bottomSeparator="none">
          {changed
            ? "You trusted a different certificate for this server before. That can mean " +
              "the server was reinstalled — or that something is intercepting the " +
              "connection. Do not accept this unless you know which."
            : "Compare this fingerprint against the one shown on the server before " +
              "accepting. Accepting trusts this certificate for future connections."}
        </Field>
      </PanelSectionRow>
    </ConfirmModal>
  );
};
