## Why

`Deal` inventory is bought through Equativ, and AdOps360 ingests only Adform, so a `Deal` line never receives delivery: its daily status carries both flags, the check for lines without delivery never evaluates it, and its margin shows revenue and rebate with no platform cost (`docs/product-description.md` §6, known limitation). The business has since closed how a Deal is priced (2026-11-20), replacing the PO decisions of 2026-09-15 that priced it like `Directo`: the volume of a Deal line is a target, not a commitment; GeoQ's income is the curator margin Equativ reports, not the contracted sale; there is no media cost; the platform cost applies on served impressions; and the rebate is paid on the served gross. Two probes of the Equativ API (2026-11-24) confirmed that the asynchronous report returns exactly the figures Equativ bills: one row per day and auction package, keyed by `auctionPackageDealId`, with the total curator margin at 80 % of the buyer's spend.

**Phase 2** per `docs/product-description.md` §6: it adds the Equativ connector, which the Adform connector's contract anticipated.

## What Changes

- **Volume commitment on the line.** Every campaign line carries `volume_commitment`, `committed` or `target`. **BREAKING** for API clients: `POST /api/campaigns` requires it on every line; the existing lines become `committed`. The registration form proposes `target` when the line's channel is `Deal` and `committed` otherwise; the user can change it. The margin and the status never read the channel: they read this attribute.
- **Equativ ingestion through its API.** The nightly command takes `--dsp Equativ` and ingests the D-7 to D-1 window from one asynchronous report (`POST /async-report`, `Etc/UTC`, no scheduling, no email, no S3), read through its paginated preview. The key is `auctionPackageDealId`; the stored day is the UTC day. It uses the same service, the same idempotent replacement, the same batches, catalogue, unmatched exceptions and linking as Adform, and a custom range works the same way. Operations maps a Deal line by writing its `auctionPackageDealId`; that mapping counts as validated by the user from the moment it is created, whether or not the package is in the catalogue, which only suggests packages and feeds the exception route. A wrong id, or a Deal that never receives bids, surfaces as a line without delivery.
- **Four amounts per day.** `daily_deliveries` adds `buyer_spend`, `reported_revenue` (the total curator margin, `paidBuyerConnectCompanyVendorCostCompanyCurrency`), `third_party_data_cost` and `audience_data_cost`. Adform rows read zero in all four; Equativ rows store a media cost of zero.
- **Margin of a target flight.** Revenue is the reported revenue of the flight's window, never pro-rated and never the contracted volume; the rebate base is the served gross (served impressions / 1000 × the line's CPM) and the rebate is not pro-rated; the platform cost stays on served impressions; the data costs are stored and flagged when above zero, never subtracted. The margin percentage stays margin over revenue. Each flight, line, campaign and the totals add `gross_revenue`, and a flight is flagged when its gross differs from the buyer's spend by more than 1 %. The lesser-of-contracted-and-served rule never applies to a target line.
- **Closing.** Closing a month freezes the revenue and the rebate base of its target flights, and is refused with 409 `month_delivery_not_loaded` until a succeeded ingestion of the DSP of every target flight of the month covers the month's last day.
- **Daily status.** A target flight raises the pacing flag only when it under-delivers; delivering more than its target is never flagged. Each row and each margin line carries `volume_commitment`; the screens say «Objetivo» and «Venta objetivo» on target lines.
- **Lines without delivery on Equativ.** The absence check runs after every Equativ ingestion that starts at or after 06:00 UTC; an earlier run skips it and says so.
- **No route is added**: `ACCESS_MATRIX` is unchanged. The amounts are money and appear only in `GET /api/margin`.
- **Documentation**: `docs/product-description.md` records the business decisions of 2026-11-20 and marks the Deal decisions of 2026-09-15 as superseded.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `campaign/campaign-registration`: every line declares its volume commitment.
- `delivery/delivery-ingestion`: stored delivery adds four amounts, the nightly command and the custom range take a DSP, Equativ is read through its asynchronous report and fills the catalogue, and an Equativ mapping written by operations is validated by the user.
- `delivery/ingestion-exceptions`: the check for lines without delivery runs for Equativ, after 06:00 UTC.
- `campaign/daily-status`: a target flight is never flagged for over-delivery, and each row names the commitment.
- `finance/margin-calculation`: revenue, rebate base, pro-rating and media cost of a target flight, the gross and the two new flags.
- `finance/margin-reporting`: every level carries the gross, the commitment and the counts of the two flags; the contracted revenue of a target line is its target.
- `finance/rebate-accrual`: the base of a target flight is its served gross, a running one is not pro-rated, and closing freezes the revenue and is blocked until the month's last day is loaded.

## Impact

- Backend: the campaign line model and registration, the delivery value objects and their combination, the delivery and margin models with Alembic migrations, a new Equativ client beside the Adform one, `scripts/run_ingestion.py`, the DSP client resolver, the ingestion-target, margin and status repositories, `flight_margin.py`, `priced_flights.py`, `margin_totals.py`, the pacing flag, the closing service, the margin and status schemas, the seeds and the test fixtures.
- API: `volume_commitment` required on each line of `POST /api/campaigns` and returned in its response, in `GET /api/campaign-status` and in `GET /api/margin`; new fields `gross_revenue`, `gross_differs_from_buyer_spend`, `data_cost_reported` and their counts in `GET /api/margin`; new 409 `month_delivery_not_loaded` on `POST /api/margin/closings`.
- Configuration: `EQUATIV_CLIENT_ID` and `EQUATIV_CLIENT_SECRET` only in `.env` (placeholders in `.env.example`), optional for the API and the development compose; a second crontab line after 06:00 UTC.
- Frontend: the campaign form, writing an Equativ package to map a line, the status table, the margin tree and the closing error message.
- Documentation: `docs/product-description.md`, `docs/deploy.md`, `readme.md`, `openspec/config.yaml` (its revenue invariant).

## Non-goals

- The `BuyerActual` CSV, any upload route, email intake and S3 storage of Equativ reports.
- Downloading the report file (`downloadUrl`), Equativ's scheduled reports and the `postProcessingConfiguration`.
- Deleting the asynchronous reports in Equativ after reading them.
- `childDealId` (targeted deals): it is 0 on every row of the probes.
- Displayce.
- Subtracting the data costs from the margin, and alerting by email or Teams.
- Restating a closed month when Equativ restates its figures, and freezing the served impressions or the platform cost at closing (the immutable month-end snapshot of phase 2).
- Reconciling the reported revenue against what Equativ pays.
- Restricting `target` to a DSP or a channel at registration.
- Retaining the four amounts on the delivery of an `unmatched_delivery` exception.
