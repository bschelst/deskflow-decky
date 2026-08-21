import type { FC } from "react";

/**
 * The status glyph, shared by the Status row and the self-test rows so they are
 * provably identical rather than similar-looking.
 *
 * Colour is the only style applied: docs/UI-SPEC.md §1 permits colour-only styling for
 * state indication and bans anything dimensional. The colour never carries the meaning
 * on its own — it always sits beside a word.
 */
export const Dot: FC<{ colour: string }> = ({ colour }) => (
  <span aria-hidden="true" style={{ color: colour }}>
    {"● "}
  </span>
);
