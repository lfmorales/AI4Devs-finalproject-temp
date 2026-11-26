import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..", "..", "..");
const BILLING = join(ROOT, "features", "billing");
// The forms parse the year, the month and the volume of a request in their own files, and nothing else.
const PARSERS = new Set(["filters.ts", "adjustment-form.ts"]);
const DISPLAY_FILES = [
  ...(existsSync(BILLING) ? readdirSync(BILLING) : [])
    .filter((name) => /\.(ts|tsx)$/.test(name) && !PARSERS.has(name))
    .map((name) => join(BILLING, name)),
  join(ROOT, "lib", "api", "billing.ts"),
  join(ROOT, "lib", "format", "moment.ts"),
];

// The browser neither adds, subtracts, divides nor rounds an amount or a volume: it shows the text the server sent.
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

describe("the display code of the billing", () => {
  it("has files to check", () => {
    expect(DISPLAY_FILES.filter((file) => file.startsWith(BILLING)).length).toBeGreaterThanOrEqual(3);
  });

  for (const file of DISPLAY_FILES) {
    it(`${file.slice(ROOT.length + 1)} does no arithmetic and no number conversion`, () => {
      expect(existsSync(file), file).toBe(true);
      const source = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      for (const [pattern, name] of FORBIDDEN) {
        expect(source, name).not.toMatch(pattern);
      }
    });
  }

  it("calls fetch nowhere in the billing feature, and uses no inline style and no console output", () => {
    for (const file of DISPLAY_FILES.filter((path) => path.startsWith(BILLING))) {
      const source = readFileSync(file, "utf8");
      expect(source, file).not.toMatch(/\bfetch\s*\(/);
      expect(source, file).not.toMatch(/style\s*=\s*\{/);
      expect(source, file).not.toMatch(/console\./);
    }
  });
});
