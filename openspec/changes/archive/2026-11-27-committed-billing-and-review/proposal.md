## Why

A committed line earns its whole contracted volume today, whatever it delivered: `flight_revenue` multiplies the contracted volume by the CPM (`backend/app/domain/services/flight_margin.py:20-22`), the rebate is charged on that figure and the annual counter advances by it (`rebate_base`, `:30-37`; `rebate_engine.py:72`). The business confirmed on 2026-11-26 that GeoQ invoices a committed flight at the lesser of what it delivered and what it contracted, so revenue, rebate and counters are overstated wherever a flight under-delivers: on the closed-month sheet of Finance, 10 of the 51 rows compared under-delivered, by 1,258.41 € of revenue and 1,040.18 € of margin. Nothing lets Operations and Finance correct a flight's billing before the month is closed, lets Operations and Trading move undelivered volume to the next flight, or records that someone looked at a campaign before its month is frozen.

**Phase 2** per `docs/product-description.md` §6: it extends the immutable month-end snapshot of `closing-snapshot` with the billing it freezes.

## What Changes

- **A committed flight earns its billing.** Revenue is `min(delivered, cap) / 1000 × sale CPM`, rounded once, in the unit of the channel, where the cap is the contracted volume (or the contracted volume plus a billable carry-over). The rebate is computed on the billing and the counter advances by it. Target lines do not change. **BREAKING** for every reader that assumed `revenue == contracted_revenue` on a closed committed flight.
- **A running committed flight bills its delivery to date**, with no pro-rating of revenue or rebate, like a target flight. The screen says «Facturable» on an ended flight and «Facturable a la fecha» on a running one, instead of «Devengado». **BREAKING**: the running figures of every committed flight change.
- **A committed month waits for its last day**, like a target month: closing answers 409 `month_delivery_not_loaded` until each DSP of the month's flights has a succeeded batch covering it.
- **Manual billing adjustment.** Operations and Finance may set the billing of an ended, unfrozen committed flight to the minimum, the delivered, the contracted volume or a custom amount, with a mandatory reason; rows are only added and the latest wins. The first three recompute until the closing; a custom amount is fixed. The adjusted billing moves the rebate and the counter.
- **Carry-over.** Operations or Trading may carry undelivered volume of a flight to the next flight of the same line, with a mandatory reason, up to the shortfall of the previous flight and never into a closed month; December to January is allowed. The delivery target becomes contracted + carry-over and drives the pacing and the daily status. A billable flag, false by default and set only by Operations or Finance, decides whether the cap of the billing rises to contracted + carry-over. The contracted volume and the purchase order never change.
- **Monthly review.** Each campaign has, per month, a state: in progress, pending review, reviewed or closed. Operations and Finance mark it reviewed once all its flights of the month have ended, and may withdraw the mark. An adjustment, a carry-over or its flag returns it to pending; an ingestion does not. Closing answers 409 `month_not_reviewed`, naming the pending campaigns, until every campaign with flights in the month is reviewed or closed; **BREAKING**: a month with a flight still running can no longer be closed.
- **The snapshot freezes the billing.** It also stores the billing basis, the billable volume, the carry-over and its flag, and the adjustment in force. «Cambió tras el cierre» compares with the current billing. Snapshots of months closed before this change keep their revenue and their comparison.
- **The billing read and the CSV for Finance.** `GET /billing` returns, for a month, each campaign's review state and each flight's billing detail; `GET /billing/export` returns one CSV row per flight of a closed month, built from the snapshot.
- **Eight routes**: `GET /billing`, `POST` and `GET /billing/flights/{flight_id}/adjustments`, `POST /billing/reviews`, `POST /billing/reviews/withdrawals`, `PUT /billing/flights/{flight_id}/carryover/billable` and `GET /billing/export` for operations and finance; `PUT /flights/{flight_id}/carryover` for operations and trading. `ACCESS_MATRIX` and `identity/access-matrix` change first. Trading never receives an amount, an adjustment or its reason, or the billable flag.
- **Acceptance**: the expected values of the 39 acceptance tests are computed with the new rule from the sheets' own columns, with no figure written by hand, and the difference with the sheets is documented as known.
- **Documentation**: `docs/product-description.md` (with this specification: §4, §5, §5.1, §5.3, §5.5, §5.8, §6 and §8, confirmed by the business on 2026-11-26), then `openspec/config.yaml`, `readme.md` and `docs/deploy.md` after the implementation.

## Capabilities

### New Capabilities

- `finance/billing-adjustment`: the manual adjustment of a committed flight's billing, its history and its effect on the rebate and the snapshot.
- `campaign/carryover`: carrying undelivered volume to the next flight of a line, its billable flag, and the delivery target.
- `finance/monthly-review`: the review state of a campaign in a month, how it is marked, withdrawn and reopened, and how it gates the closing.
- `finance/billing-report`: the billing read per month and the CSV of a closed month for Finance.

### Modified Capabilities

- `finance/margin-calculation`: the revenue of a committed flight is its billing; a running committed flight bills its delivery to date without pro-rating; a closed flight reads its billing from its snapshot and is checked against its current billing.
- `finance/margin-reporting`: the contracted revenue may exceed the revenue of a closed committed flight; flights carry their billable volume and billing basis; the margin screen says «Facturable» and «Facturable a la fecha»; the change warning reports the billing difference.
- `finance/rebate-accrual`: the counter advances by the billing; a running committed flight's rebate is not pro-rated; closing waits for the last day of every DSP, requires the review, and freezes the billing in the snapshot.
- `campaign/daily-status`: the pacing and the ratio use the delivery target; each row carries the carry-over and the delivery target.
- `identity/access-matrix`: the eight new routes and their roles; trading may write a carry-over and still receives no amount.

## Impact

- Backend: the margin domain (`flight_margin.py`, `priced_flights.py`, `closed_flight.py`, `FlightFacts`, `FlightMargin`, `ClosedFlightSnapshot`), the closing service and its repositories, `MarginQueryService`, the pacing call of `CampaignStatusService` and its repository, three Alembic migrations (adjustments, carry-over columns, reviews; snapshot columns), new billing, adjustment, carry-over and review services and repositories, two routers and their schemas.
- API: `GET /margin` changes the meaning of `revenue` for committed flights and adds `billable` and `billing_basis`; `delivery_change` adds `billable_difference` and `billing_difference`; `GET /campaign-status` adds `carryover` and `delivery_target`; `POST /margin/closings` gains `month_not_reviewed`; eight new routes.
- Frontend: the margin labels, a billing screen (adjustments, review, CSV download), the carry-over on the status screen.
- Tests: the acceptance tests, every test that closes a month (they review first), and the tests that assumed revenue on the contracted volume.
- E2E: the closing flows review first; a billing flow that adjusts, reviews, closes and downloads the CSV; a trading flow for the carry-over.
- Data: no backfill; closed months keep their figures.

## Non-goals

- Restating, reopening or rebilling a month closed before or after this change.
- Changing the contracted volume, the purchase order or its versions for an adjustment or a carry-over.
- Splitting the billing of one flight between months, or carrying volume to any flight other than the next one of the same line.
- Billing target lines differently, or adjusting them.
- Invoicing, credit notes and ERP posting: the CSV is the hand-off to Finance.
- Reopening the review because of an ingestion, a master, a schedule or a platform rate.
- Notifications when a campaign returns to pending review.
