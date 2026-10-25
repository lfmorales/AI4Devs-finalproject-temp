import type { CSSProperties } from "react";

// Next.js inlines NEXT_PUBLIC_* at build time, so this reads as a build setting. Only the exact value "true" masks.
function namesAreMasked(): boolean {
  return process.env.NEXT_PUBLIC_MASK_NAMES === "true";
}

const MASKED_STYLE: CSSProperties = {
  filter: "blur(6px)",
  userSelect: "none",
  WebkitUserSelect: "none",
  // No pointer events: nothing to select, and no hover that could reveal it.
  pointerEvents: "none",
};

/** An Adform campaign or line name; blurred and unselectable when NEXT_PUBLIC_MASK_NAMES is "true". */
export function AdformName({ name }: { name: string }) {
  return <span data-adform-name="" style={namesAreMasked() ? MASKED_STYLE : undefined}>{name}</span>;
}
