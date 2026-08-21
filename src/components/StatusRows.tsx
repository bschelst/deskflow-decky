import { Field, Marquee, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { Status } from "../api/types";
import {
  STATE_COLOUR,
  STATE_LABEL,
  describeBackend,
  describeMode,
  describeServer,
  serverModeUnavailable,
} from "../lib/format";

/**
 * A coloured glyph beside the state word. The word carries the meaning; the colour is
 * advisory, because colour alone is not an accessible signal.
 *
 * Colour is the only style applied. docs/UI-SPEC.md §1 permits colour-only styling for
 * state indication and bans everything dimensional, so this uses a text glyph rather
 * than a sized-and-spaced box.
 */
const StateDot: FC<{ state: Status["state"] }> = ({ state }) => (
  <span aria-hidden="true" style={{ color: STATE_COLOUR[state] }}>
    {"● "}
  </span>
);

/**
 * Read-only status rows.
 *
 * Each is a `Field` inside a `PanelSectionRow` so it shares Steam's label/control
 * gutter with the interactive rows below. No wrappers, no spacing styles -- see
 * docs/UI-SPEC.md §1.
 */
export const StatusRows: FC<{ status: Status }> = ({ status }) => (
  <>
    <PanelSectionRow>
      <Field label="Status" bottomSeparator="none">
        <StateDot state={status.state} />
        {STATE_LABEL[status.state]}
      </Field>
    </PanelSectionRow>

    <PanelSectionRow>
      <Field label="Backend" bottomSeparator="none">
        {describeBackend(status)}
      </Field>
    </PanelSectionRow>

    <PanelSectionRow>
      <Field
        label="Mode"
        bottomSeparator="none"
        description={
          serverModeUnavailable(status)
            ? "Server mode cannot capture input in Gaming Mode."
            : undefined
        }
      >
        {describeMode(status)}
      </Field>
    </PanelSectionRow>

    <PanelSectionRow>
      <Field label="Server">
        <Marquee>{describeServer(status)}</Marquee>
      </Field>
    </PanelSectionRow>
  </>
);
