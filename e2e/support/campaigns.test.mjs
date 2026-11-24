// Tests of the master the E2E campaigns choose. Run: node --test support/campaigns.test.mjs
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { campaignLine, chooseMasterId } from "./campaigns.ts";

// The channels the API lists once CTV and DOOH exist, in the order of their names.
const CHANNELS = [
  { id: 4, name: "CTV" },
  { id: 3, name: "DEMO Channel" },
  { id: 2, name: "Deal" },
  { id: 1, name: "Directo" },
  { id: 5, name: "DOOH" },
];

describe("the master an E2E campaign registers with", () => {
  it("is the DEMO channel when the API lists CTV, DEMO Channel, Deal, Directo and DOOH", () => {
    assert.equal(chooseMasterId(CHANNELS, "masters/channels"), 3);
  });

  it("is still the DEMO one whatever the order of the list", () => {
    assert.equal(chooseMasterId([...CHANNELS].reverse(), "masters/channels"), 3);
  });

  it("is the first item when no name starts with DEMO", () => {
    assert.equal(chooseMasterId(CHANNELS.filter((item) => item.name !== "DEMO Channel"), "masters/channels"), 4);
  });

  it("says which master is empty when there is none", () => {
    assert.throws(() => chooseMasterId([], "masters/channels"), /masters\/channels/);
  });
});

describe("the line an E2E campaign registers", () => {
  const masters = { dsp: 7, channel: 3, format: 9 };
  const window = { name: "E2E", start: "2026-11-01", end: "2026-11-30", orderReceivedOn: "2026-10-31" };

  it("declares a committed volume, which the API requires on every line", () => {
    assert.equal(campaignLine(masters, window).volume_commitment, "committed");
  });

  it("keeps the masters, the window and the volume it always sent", () => {
    assert.deepEqual(campaignLine(masters, window), {
      start_date: "2026-11-01",
      end_date: "2026-11-30",
      dsp_id: 7,
      channel_id: 3,
      format_id: 9,
      scope: "national",
      market_description: "E2E",
      contracted_impressions: 1_000_000,
      sale_cpm: "1.00",
      volume_commitment: "committed",
    });
  });
});
