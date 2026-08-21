import { Field, PanelSectionRow } from "@decky/ui";
import type { FC } from "react";

import type { SelfTestCheck } from "../api/types";
import { FAIL_COLOUR, PASS_COLOUR } from "../lib/format";
import { Dot } from "./Dot";

/**
 * One self-test result, laid out exactly like the Status row: name on the left, a
 * coloured dot and a word on the right, the explanation underneath.
 *
 * Shared by the Quick Access panel and the Settings page so the two cannot drift.
 */
export const SelfTestRow: FC<{ check: SelfTestCheck }> = ({ check }) => (
  <PanelSectionRow>
    <Field label={check.label} description={check.detail} bottomSeparator="standard" focusable>
      <Dot colour={check.ok ? PASS_COLOUR : FAIL_COLOUR} />
      {check.ok ? "OK" : "Failed"}
    </Field>
  </PanelSectionRow>
);

export const SelfTestRows: FC<{ checks: SelfTestCheck[] }> = ({ checks }) => (
  <>
    {checks.map((check) => (
      <SelfTestRow key={check.id} check={check} />
    ))}
  </>
);
