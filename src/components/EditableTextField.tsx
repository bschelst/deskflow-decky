import { TextField } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

/**
 * A text field you can actually type in.
 *
 * `TextField` given a `value` with no `onChange` is a controlled React input with no
 * way to update itself, so every keystroke is discarded. This keeps a local draft,
 * updates it on change, and commits on blur -- so the backend sees one write per edit
 * rather than one per character.
 */
export const EditableTextField: FC<{
  label: string;
  description?: string;
  value: string;
  mustBeNumeric?: boolean;
  disabled?: boolean;
  onCommit: (value: string) => void;
}> = ({ label, description, value, mustBeNumeric, disabled, onCommit }) => {
  const [draft, setDraft] = useState(value);

  // Re-sync when the authoritative value changes underneath us (a backend rejection,
  // or another surface editing the same setting).
  useEffect(() => {
    setDraft(value);
  }, [value]);

  return (
    <TextField
      label={label}
      description={description}
      value={draft}
      mustBeNumeric={mustBeNumeric}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        const trimmed = draft.trim();
        if (trimmed !== value) onCommit(trimmed);
      }}
    />
  );
};
