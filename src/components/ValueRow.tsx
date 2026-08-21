import { Field, PanelSectionRow, TextField } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

/**
 * A compact input row: name on the left, the input in the control column on the right.
 *
 * `TextField` given its own `label` renders the label above, the input across the full
 * width, and its description centred in the leftover space — which is out of
 * proportion for a short value and looks nothing like the dropdown and toggle rows
 * around it. Wrapping a bare `TextField` in a `Field` puts the control where every
 * other control lives and the description where every other description lives.
 *
 * Keeps a local draft and commits on blur, so the backend sees one write per edit
 * rather than one per keystroke.
 */
export const ValueRow: FC<{
  label: string;
  description?: string;
  value: string | number;
  numeric?: boolean;
  disabled?: boolean;
  /**
   * How much of the row the input may take.
   *
   * The default control column is sized for a toggle, which truncates a hostname to
   * "bsc" and a port to "248". `max` for anything of unknown length, `fixed` for
   * values with a known short shape like a port or a screen dimension.
   */
  width?: "min" | "max" | "fixed";
  onCommit: (raw: string) => void;
}> = ({ label, description, value, numeric, disabled, width = "max", onCommit }) => {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  return (
    <PanelSectionRow>
      <Field
        label={label}
        description={description}
        bottomSeparator="standard"
        childrenContainerWidth={width}
      >
        <TextField
          mustBeNumeric={numeric}
          disabled={disabled}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => {
            if (draft !== String(value)) onCommit(draft);
          }}
        />
      </Field>
    </PanelSectionRow>
  );
};
