import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..", "..");
const sheet = readFileSync(join(ROOT, "app", "globals.css"), "utf8");
const rootLayout = readFileSync(join(ROOT, "app", "layout.tsx"), "utf8");

function rootVariables(): Record<string, string> {
  const block = /:root\s*\{([^}]*)\}/.exec(sheet)?.[1] ?? "";
  const variables: Record<string, string> = {};
  for (const match of block.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) variables[match[1]!] = match[2]!.trim();
  return variables;
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG 2.x contrast ratio between two #RRGGBB colours. */
function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

// Every text-on-background pair the sheet uses, by variable name.
const PAIRS: [string, string][] = [
  ["color-text", "color-page"],
  ["color-text", "color-surface"],
  ["color-text", "color-surface-alt"],
  ["color-muted", "color-page"],
  ["color-muted", "color-surface"],
  ["color-muted", "color-surface-alt"],
  ["color-header-text", "color-header"],
  ["color-action-text", "color-action"],
  ["color-action-text", "color-action-hover"],
  ["color-danger-text", "color-danger"],
  ["color-danger-text", "color-danger-hover"],
  ["color-error-text", "color-page"],
  ["color-error-text", "color-surface"],
  ["color-action", "color-surface-alt"],
  ["color-action", "color-page"],
  ["color-action", "color-surface"],
  ["color-warning-text", "color-warning-bg"],
  ["color-error-text", "color-error-bg"],
  ["color-success-text", "color-success-bg"],
  ["color-info-text", "color-info-bg"],
];

describe("app/globals.css", () => {
  it("is imported by the root layout", () => {
    expect(rootLayout).toMatch(/import\s+["']\.\/globals\.css["']/);
  });

  it("uses no external resource: no @import url, no http:// and no https://", () => {
    expect(sheet).not.toMatch(/@import/i);
    expect(sheet).not.toMatch(/url\(/i);
    expect(sheet).not.toMatch(/https?:\/\//i);
  });

  it("is a single light theme with the system font stack", () => {
    expect(sheet).toMatch(/color-scheme:\s*light/);
    expect(sheet).toMatch(/system-ui,\s*-apple-system,\s*"Segoe UI",\s*Roboto,\s*"Helvetica Neue",\s*Arial,\s*sans-serif/);
    expect(sheet).toMatch(/font-variant-numeric:\s*tabular-nums/);
  });

  it("defines a visible :focus-visible outline", () => {
    expect(sheet).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px/);
  });

  it("dims the backdrop of the native dialog", () => {
    expect(sheet).toMatch(/dialog::backdrop\s*\{[^}]*background/);
  });

  it("removes transitions and animations when the user prefers reduced motion", () => {
    expect(sheet).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  });

  it("does not touch the name masking, which is an inline style", () => {
    expect(sheet).not.toMatch(/data-adform-name/);
    expect(sheet).not.toMatch(/blur\(/);
  });

  it("declares every colour as a variable on :root and nowhere else", () => {
    const outsideRoot = sheet.replace(/:root\s*\{[^}]*\}/, "");
    expect(outsideRoot).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it.each(PAIRS)("the pair %s on %s reaches the AA ratio of 4.5", (foreground, background) => {
    const variables = rootVariables();
    expect(variables[foreground], `--${foreground} is not defined`).toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(variables[background], `--${background} is not defined`).toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(contrast(variables[foreground]!, variables[background]!)).toBeGreaterThanOrEqual(4.5);
  });

  it("uses the colours of the specification", () => {
    const variables = rootVariables();
    const expected: Record<string, string> = {
      "color-page": "#F6F4EE", "color-surface": "#FFFFFF", "color-border": "#DDD8CB", "color-text": "#1B2433",
      "color-muted": "#5B6470", "color-header": "#0F1B2D", "color-header-text": "#F6F4EE", "color-action": "#0B6B74",
      "color-action-hover": "#08555C", "color-danger": "#B42318", "color-warning-bg": "#FFF4D6",
      "color-warning-text": "#7A4B00", "color-warning-border": "#F2B24B", "color-error-bg": "#FDECEA",
      "color-error-text": "#8A1C14", "color-success-bg": "#E4F4EE", "color-success-text": "#0B5D43",
      "color-info-bg": "#E8F1F8", "color-info-text": "#12456B",
    };
    for (const [name, value] of Object.entries(expected)) expect(variables[name]?.toUpperCase(), name).toBe(value);
  });
});

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

describe("the components", () => {
  it("keep no inline style (it would override the sheet) except the name masking", () => {
    const offenders = ["app", "features", "lib"]
      .flatMap((directory) => sourceFiles(join(ROOT, directory)))
      .filter((path) => /style=\{/.test(readFileSync(path, "utf8")))
      .map((path) => path.slice(ROOT.length + 1));

    expect(offenders).toEqual([join("features", "linking", "AdformName.tsx")]);
  });
});
