import { expect, type APIRequestContext } from "@playwright/test";

interface MasterItem {
  id: number;
  name: string;
}

export interface CampaignWindow {
  name: string;
  /** First and last day of the campaign and of its only line, as YYYY-MM-DD. */
  start: string;
  end: string;
  orderReceivedOn: string;
}

/**
 * The master an E2E campaign registers with: the first one whose name starts with DEMO, or the first one when there
 * is none, as the campaign form does. The channel needs it: with CTV and DOOH loaded the first channel by name is
 * CTV, and a campaign on it would join the CTV rebate schedule instead of staying on the demonstration data.
 */
export function chooseMasterId(items: MasterItem[], path: string): number {
  const chosen = items.find((item) => item.name.startsWith("DEMO")) ?? items[0];
  if (chosen === undefined) throw new Error(`GET /api/${path} has no item: the masters are not loaded.`);
  return chosen.id;
}

async function firstOf(api: APIRequestContext, path: string): Promise<number> {
  const items = (await (await api.get(path)).json()) as MasterItem[];
  const first = items[0];
  if (first === undefined) throw new Error(`GET /api/${path} has no item: the masters are not loaded.`);
  return first.id;
}

async function demoOrFirstOf(api: APIRequestContext, path: string): Promise<number> {
  return chooseMasterId((await (await api.get(path)).json()) as MasterItem[], path);
}

export interface LineMasters {
  dsp: number;
  channel: number;
  format: number;
}

/**
 * The only line of an E2E campaign: national, 1,000,000 impressions at 1.00 €, over the campaign's window. Its volume
 * is committed: the API requires the commitment on every line and has no default.
 */
export function campaignLine(masters: LineMasters, window: CampaignWindow) {
  return {
    start_date: window.start,
    end_date: window.end,
    dsp_id: masters.dsp,
    channel_id: masters.channel,
    format_id: masters.format,
    scope: "national",
    market_description: "E2E",
    contracted_impressions: 1_000_000,
    sale_cpm: "1.00",
    volume_commitment: "committed",
  };
}

/**
 * Registers an active campaign with one national line and no delivery, over the given window. The body follows
 * CampaignCreateRequest and CampaignLineCreateRequest of the backend's OpenAPI schema; the masters are the first
 * item of each master list, except the channel and the DSP (see chooseMasterId). The DSP is the DEMO one because a
 * month closes only once its DSP has loaded its last day, and seed_margin_demo records that load for the DEMO DSP.
 */
export async function registerCampaign(api: APIRequestContext, window: CampaignWindow): Promise<void> {
  const registration = await api.post("campaigns", {
    data: {
      name: window.name,
      display_name: window.name,
      agency_id: await firstOf(api, "masters/agencies"),
      advertiser_id: await firstOf(api, "masters/advertisers"),
      campaign_type_id: await firstOf(api, "masters/campaign-types"),
      sector_id: await firstOf(api, "masters/sectors"),
      sales_rep_id: await firstOf(api, "masters/sales-reps"),
      start_date: window.start,
      end_date: window.end,
      order_reference: window.name,
      order_received_on: window.orderReceivedOn,
      lines: [
        campaignLine(
          {
            dsp: await demoOrFirstOf(api, "masters/dsps"),
            channel: await demoOrFirstOf(api, "masters/channels"),
            format: await firstOf(api, "masters/formats"),
          },
          window,
        ),
      ],
    },
  });
  expect(registration.status(), "the registration of the campaign").toBe(201);
}
