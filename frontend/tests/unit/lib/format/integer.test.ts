import { describe, expect, it } from "vitest";

import { formatInteger } from "@/lib/format/integer";
import { formatImpressions } from "@/features/status/format";

const plain = (text: string) => text.replace(/\s/g, " ");

describe("formatInteger", () => {
  it.each([[0, "0"], [999, "999"], [1234, "1.234"], [40000, "40.000"], [1234567, "1.234.567"]])(
    "writes %i as %s, grouping from four digits", (value, expected) => {
      expect(plain(formatInteger(value))).toBe(expected);
    },
  );

  it("is the formatter the status table uses for impressions", () => {
    expect(plain(formatImpressions(3100))).toBe("3.100");
  });
});
