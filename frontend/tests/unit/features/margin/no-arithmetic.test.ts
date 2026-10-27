import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..", "..", "..");
const DISPLAY_FILES = [
  ...readdirSync(join(ROOT, "features", "margin"))
    .filter((name) => /\.(ts|tsx)$/.test(name) && name !== "filters.ts")
    .map((name) => join(ROOT, "features", "margin", name)),
  join(ROOT, "lib", "format", "decimal.ts"),
  join(ROOT, "lib", "api", "margin.ts"),
];

// The browser neither adds, subtracts, divides nor rounds an amount: it shows the text the server sent. The few
// numbers it parses (the year, the month and the campaign of a filter) are parsed in filters.ts only.
const FORBIDDEN: [RegExp, string][] = [
  [/\bNumber\s*\(/, "Number(...)"],
  [/\bparseFloat\b/, "parseFloat"],
  [/\bparseInt\b/, "parseInt"],
  [/\.toFixed\s*\(/, ".toFixed()"],
  [/\bMath\./, "Math."],
  [/\bBigInt\b/, "BigInt"],
  [/\bIntl\.NumberFormat\b/, "Intl.NumberFormat"],
  [/\.toLocaleString\s*\(/, ".toLocaleString()"],
  [/(?<![\w)\]"'])\+(?=\w)/, "a unary plus"],
];

describe("the display code of the margin", () => {
  it("has files to check", () => {
    expect(DISPLAY_FILES.length).toBeGreaterThanOrEqual(4);
  });

  for (const file of DISPLAY_FILES) {
    it(`${file.slice(ROOT.length + 1)} does no arithmetic and no number conversion`, () => {
      const source = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      for (const [pattern, name] of FORBIDDEN) {
        expect(source, name).not.toMatch(pattern);
      }
    });
  }

  it("calls fetch nowhere in the margin features: only the client does", () => {
    for (const file of DISPLAY_FILES.filter((path) => path.includes(join("features", "margin")))) {
      expect(readFileSync(file, "utf8")).not.toMatch(/\bfetch\s*\(/);
    }
  });

  it("uses no inline style and no console output", () => {
    for (const file of DISPLAY_FILES.filter((path) => path.includes(join("features", "margin")))) {
      const source = readFileSync(file, "utf8");
      expect(source, file).not.toMatch(/style\s*=\s*\{/);
      expect(source, file).not.toMatch(/console\./);
    }
  });
});
