// Tests of the master the E2E campaigns choose. Run: node --test support/campaigns.test.mjs
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { chooseMasterId } from "./campaigns.ts";

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
