## Why

DOOH campaigns are sold and measured in OTS (opportunity to see), not in impressions, yet every delivered figure in AdOps360 is the impression count, so the daily status, the pacing and the margin of a DOOH line compare impressions against a volume contracted in OTS. At the same time CTV is a channel of the catalogue that no seed, fixture or example file carries, while the seeds still hold an `OOH` channel and a `Digital` channel that the channel catalogue does not define. Adform already reports OTS and the video completion rate in the same statistics API the nightly ingestion uses, so both can be stored now without a new route.

**Phase 1** per `docs/product-description.md` §6: it extends the Adform ingestion and the views of the MVP; it adds no DSP and no intake route.

## What Changes

- **Channel catalogue.** The channels are `Directo`, `Deal`, `DOOH` and `CTV`, as `masters/commercial-masters` already states. `OOH` and `Digital` disappear from the seeds, the test fixtures and `deploy/masters.example.json`, with no data migration because no real database holds them. Each channel keeps its own rebate counter; the development seed adds a fictitious rebate schedule for `CTV` only.
- **Delivery metric per channel.** A channel carries `delivery_metric`, `impressions` by default or `ots`; `DOOH` is `ots`. The migration sets it on an existing `DOOH` row, and `load_masters` accepts it when it creates a channel.
- **One delivery metric per campaign.** A registration whose lines carry channels of different delivery metrics is rejected with 422 `mixed_delivery_metrics`.
- **Two more Adform metrics.** The ingestion asks Adform for `ots` and `videoCompletionRate` and stores, per line and day, `ots` (four decimals) and `video_completions` (`round(rate × impressions)` per row). Combined rows sum OTS and completions, never rates. An empty cell is 0; an unreadable value or a missing column fails the run as a format error. OTS is never replaced by impressions.
- **Unmatched rows with OTS.** An unmatched row with OTS different from zero is worked as an `unmatched_delivery` exception, like one with impressions or cost.
- **Delivered volume in the channel's metric.** For a DOOH line the contracted and the delivered volume are OTS: the daily status, the pacing, the margin views and the missing-delivery exception read OTS; every other channel reads impressions. The delivered volume is decimal; the contracted volume stays an integer. Revenue is still contracted volume / 1000 × CPM; the platform cost stays on delivered impressions for every channel.
- **Responses.** `delivered_impressions` keeps meaning impressions everywhere. The daily status rows and the margin flights, lines and campaigns add `delivered` and `delivery_metric`; the margin totals carry them, and `contracted_impressions`, only when every campaign shares one metric, and null otherwise. The screens label the volumes «impresiones» or «OTS».
- **No route is added or changed**: `ACCESS_MATRIX` is unchanged. OTS and video completions are not money figures, so the trading role may read them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `masters/commercial-masters`: the channel catalogue's exact members, the per-channel rebate counter, and the channel's delivery metric.
- `campaign/campaign-registration`: every line of a campaign shares one delivery metric.
- `delivery/delivery-ingestion`: the stored delivery adds OTS and video completions, the Adform request asks for two more metrics, and combined rows sum them.
- `delivery/ingestion-exceptions`: an unmatched row with OTS is worked, and a DOOH flight is missing delivery when its OTS are zero.
- `campaign/daily-status`: the delivered volume, the pacing and the ratio use the channel's delivery metric, and each row names it.
- `finance/margin-calculation`: the contracted volume of a DOOH flight is OTS, and the platform cost stays on impressions.
- `finance/margin-reporting`: every level adds `delivered` and `delivery_metric`, and the totals null the volumes that would mix metrics.

## Impact

- Backend: the Adform client, the delivery value objects and their combination, the unmatched-row rule, the delivery and channel models with one Alembic migration, the campaign registration service, the status, margin and ingestion-target repositories, the pacing function, the margin totals, the status and margin schemas, `scripts/seed_dev_data.py`, `scripts/seed_margin_demo.py`, `scripts/load_masters.py`, the test fixtures.
- API: new fields `delivered` and `delivery_metric` on `GET /api/campaign-status` and `GET /api/margin`; `contracted_impressions` on the margin totals becomes nullable; new 422 code `mixed_delivery_metrics` on `POST /api/campaigns`.
- Frontend: the status table, the margin legends, the API types and the error message of the campaign form.
- Configuration: `deploy/masters.example.json`.
- Documentation: `docs/product-description.md`, `docs/deploy.md`, `readme.md`.

## Non-goals

- Any email intake of delivery reports. CTV reports are read in Adform, like Display, so CTV needs none.
- Equativ and Displayce, which have no connector yet.
- Showing video completions or a completion rate on any screen or response: they are stored only.
- Retaining OTS on the delivery kept by an `unmatched_delivery` exception.
- A route to change a channel's delivery metric, and changing it for a channel that already exists through `load_masters`.
- Renaming `contracted_impressions`, `delivered_impressions` or the pacing's `expected_impressions`.
- Labelling the contracted volume of the campaign form by channel: it stays «Impresiones contratadas».
- Re-tagging any campaign into `CTV` or out of `OOH`.
