import { Field, Marquee, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { Status } from "../api/types";
import { Dot } from "./Dot";
import {
  STATE_COLOUR,
  STATE_LABEL,
  describeBackend,
  describeMode,
  describeServer,
  serverModeUnavailable,
} from "../lib/format";

/** The state's glyph, using the same component the self-test rows use. */
const StateDot: FC<{ state: Status["state"] }> = ({ state }) => (
  <Dot colour={STATE_COLOUR[state]} />
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
        <Marquee>{describeBackend(status)}</Marquee>
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
