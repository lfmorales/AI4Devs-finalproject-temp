import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..", "..", "..");
// The features whose actions take the shared client of `lib/api/browser-client.ts`. The others (campaigns, catalogue,
// exceptions) still build their own: they are listed in the report of committed-billing-and-review.
const FEATURES = ["margin", "billing", "status"];

function sources(feature: string): [string, string][] {
  const folder = join(ROOT, "features", feature);
  return readdirSync(folder)
    .filter((name) => /\.(ts|tsx)$/.test(name))
    .map((name) => [`features/${feature}/${name}`, readFileSync(join(folder, name), "utf8")]);
}

describe("the API client of a page action", () => {
  it.each(FEATURES)("is the shared one in features/%s, which never builds its own", (feature) => {
    for (const [file, source] of sources(feature)) {
      expect(source, file).not.toMatch(/\bcreateApiClient\b/);
      expect(source, file).not.toMatch(/NEXT_PUBLIC_API_URL/);
    }
  });
});
