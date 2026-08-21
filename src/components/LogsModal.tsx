import { Field, ModalRoot, PanelSectionRow, SteamSpinner } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

import { getLogs } from "../api/backend";

const LINES = 200;

/** Recent plugin log lines. The backend redacts them before they get here. */
export const LogsModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => {
  const [lines, setLines] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await getLogs(LINES);
      if (result.ok) setLines(result.data.lines);
      else setError(result.error.message);
    })();
  }, []);

  return (
    <ModalRoot closeModal={closeModal}>
      {lines === null && error === null ? <SteamSpinner /> : null}

      {error !== null ? (
        <PanelSectionRow>
          <Field description={error} bottomSeparator="none" />
        </PanelSectionRow>
      ) : null}

      {lines !== null && lines.length === 0 ? (
        <PanelSectionRow>
          <Field description="No log entries yet." bottomSeparator="none" />
        </PanelSectionRow>
      ) : null}

      {(lines ?? []).map((line, index) => (
        // Log lines have no stable identity; index is the honest key here.
        <PanelSectionRow key={index}>
          <Field description={line} bottomSeparator="none" />
        </PanelSectionRow>
      ))}
    </ModalRoot>
  );
};
