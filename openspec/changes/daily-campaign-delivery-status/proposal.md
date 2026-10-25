## Why

There is no ETL and no DSP API in use today. The "pipeline" is a Qlik script concatenating 1,999 manually downloaded spreadsheets, accumulated daily since December 2023 and re-loaded in ad-hoc batches named by whoever ran them — `carga 1`, `carga octopus`, `carga equativ 8/11`. Every morning someone downloads and filters a report per DSP by hand.

Nothing tells anyone when a campaign stops delivering. A mismatched campaign name and a campaign that genuinely delivered nothing look identical: 87 delivery keys have no configuration and 178 configured campaign-months have no delivery, and one of those is a commercial problem while the other is a typo.

This change ingests delivery automatically and makes both failures visible the day they happen.

**Phase 1** per `docs/product-description.md` §6, Adform only. The connector built here defines the contract that Equativ and Displayce implement in phase 2.

## What Changes

- **Nightly ingestion of D-7 to D-1 from the Adform API** for every campaign line that carries a validated DSP mapping and whose campaign overlaps the ingestion window, recording impressions, clicks, media cost and measurable and viewable impressions per line and day.
- **Ingestion is idempotent over a rolling 7-day window.** Re-running a range replaces it rather than appending, because DSPs restate figures after the fact.
- **Every run is recorded as a batch** with its route, source, timing, outcome and row count, replacing the hand-typed load labels of the current system.
- **Manual upload as a first-class route**, not a fallback bolted on later: it shares the ingestion contract, and it is both the only path that exists today and the migration route for the historical corpus.
- **Unmatched keys become worked exceptions in both directions** — delivery with no campaign line, and an active line with no delivery in a period that has ended.
- **The configured channel is authoritative.** The DSP's `line_format` is stored as contrast data only; where the two disagree the row is flagged for review and never silently reclassified.
- **A daily status view** showing contracted against delivered volume, pacing against expected-to-date and days remaining, with two flags: an active campaign missing D-1, and a pacing deviation beyond ±10%.

## Capabilities

### New Capabilities

- `delivery/delivery-ingestion`: retrieving delivery from a DSP or an uploaded file into one delivery model, idempotently, with every run recorded as a batch.
- `delivery/ingestion-exceptions`: unmatched keys on either side of the join, surfaced as work rather than discarded.
- `campaign/daily-status`: the operational view of active campaigns — delivered against contracted, pacing, and the flags that make a stalled or deviating campaign visible.

### Modified Capabilities

<!-- None yet. `campaign/dsp-mapping` is introduced by `register-campaign-from-purchase-order`,
     which has not been archived, so it does not exist under openspec/specs/ and cannot carry
     a delta. The requirement that ingestion resolves delivery through the mapping, and that an
     unmapped active line is skipped rather than failing the run, is stated in
     delivery/delivery-ingestion instead. Once that change is archived, consider moving it. -->

### Dependencies

- `register-campaign-from-purchase-order` must be applied first: this change ingests against the campaign lines and DSP mappings it creates.

## Impact

- **Database**: `daily_deliveries` at the line-and-day grain — the high-volume table of the system, sized from 8.5 M historical rows and roughly 4,600 new rows a day — plus `ingestion_batches` and `ingestion_exceptions`. Indexing and the idempotent replace strategy are the design problem.
- **Backend**: an Adform delivery client behind the DSP interface; an ingestion application service shared by API and upload routes; a spreadsheet parser in `infrastructure/spreadsheets/`; a scheduled nightly run; pacing calculation in the domain layer.
- **Frontend**: the daily status view with its flags, and the exception queue.
- **External**: Adform API, read-only.

## Non-goals

- **Equativ and Displayce connectors.** Phase 2. The interface is built so they slot in, but neither is implemented here.
- **Email intake.** Phase 2. It is the same ingestion contract with a different transport, deliberately kept off the critical path of the first release.
- **Alerting by email or Teams.** Phase 2. The flags are visible in the application; nothing is pushed.
- **Margin.** Delivery feeds it, but the calculation belongs to `campaign-margin-and-rebate-accrual`.
- **Reconciliation against the advertiser's own ad server.** Excluded by the PO.
- **Loading the 8.5 M historical delivery rows.** The upload route makes it possible; running the migration is separate work.
