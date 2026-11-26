## Context

See `proposal.md` (Why). The current state that shapes the approach:

- **One function prices every unfrozen flight.** `price_flights` (`backend/app/domain/services/priced_flights.py:13-68`) runs the rebate engine on `rebate_base(facts)` and then `calculate_flight_margin`; the closing (`margin_closing_service.py:60-66`) and the reads (`margin_query_service.py:63-77`) both call it, so a pending-close figure is the figure the closing freezes.
- **The committed revenue reads only the contracted volume.** `flight_revenue` (`flight_margin.py:20-22`) feeds the closed revenue (`:93`) and `rebate_base` (`:37`); a running committed flight pro-rates revenue and rebate by elapsed days (`:86-91`). The engine charges a running flight its full base from the closed position and does not advance the counter (`rebate_engine.py:68-76`).
- **`FlightFacts` already carries the delivered volume in the channel's unit**, with OTS decimals (`priced_flight.py:13-44`), summed in the database inside the flight's window (`sqlalchemy_margin_repositories.py:157-221`); the same query serves the closing and the reads.
- **A closed flight is read from its snapshot** (`closed_flight.py:61-89`) and checked against its current delivery with the frozen revenue of a committed flight (`:92-123`). The snapshot table and `applied_rates` are append-only through `reject_append_only_change()`; `applied_rates.revenue_amount` and `rebate_base_amount` are filled only for target flights (`sqlalchemy_margin_repositories.py:431-449`). The migration head is `3a08cce1c979`.
- **The closing checks two things before pricing**: `previous_month_open` and, for target flights only, `month_delivery_not_loaded` (`margin_closing_service.py:47-53`, `sqlalchemy_margin_repositories.py:262-287`), under a month advisory lock (`:548-552`).
- **The campaign × month grain exists**: `campaign_periods` (`models/campaign.py:29-38`), whose `status` column is written `open` at registration and read by nothing.
- **The pacing reads the flight's contracted volume** (`campaign_status_service.py:29-33`, `sqlalchemy_campaign_status_repository.py:58`).
- **Error bodies are `code` and `message` only under fixed prefixes** (`presentation/errors.py:230-239`: `/margin`, `/users`); `/flights/preview` keeps FastAPI's `detail`.
- **`ACCESS_MATRIX`** (`backend/tests/api/test_route_protection.py:80-107`) is checked route by route against the routers; `test_the_margin_routes_are_the_four_of_this_change` (`:149-157`) pins the `/margin` routes.

## Goals / Non-Goals

**Goals:**
- The billing rule, the adjustment, the cap with a billable carry-over and the review state are pure domain functions, tested without a database, and the closing and the reads keep going through one pricing function.
- Every new table of facts that must not change is append-only in the database, like the closing's tables.
- The access matrix and its test change before any route exists.

**Non-Goals:**
- Changing how a target flight is priced, or the rebate brackets and ladder.
- A history of carry-over changes beyond the review events they cause.

## Decisions

### 1. One billing function in the domain, called by `price_flights`

A value object `Billing` (`billable: Decimal | None`, `amount: Decimal`, `basis: BillingBasis`), the adjustment in force `BillingAdjustment` (basis and amount, validated) and an enum `BillingBasis` (`minimum`, `delivered`, `contracted`, `custom`, `reported`) live in `backend/app/domain/value_objects/billing.py`. A pure function `committed_billing(contracted, carryover, carryover_billable, delivered, sale_cpm, adjustment) -> Billing` in `backend/app/domain/services/flight_margin.py`, next to `round_amount` (a module of its own would import it while `flight_margin` imports the function), applies, in order: the adjustment in force when there is one (`custom` returns its amount and no volume; `delivered` the delivered volume; `contracted` the cap, contracted + carry-over when billable), otherwise the rule `min(delivered, contracted + (carryover if billable else 0))`; the amount is `round_amount(volume / 1000 × cpm)`, rounded once.

`FlightFacts` and `FlightEconomics` gain `carryover: int`, `carryover_billable: bool` and `adjustment: BillingAdjustment | None`, with no default in the domain (the test builders default them to none). `rebate_base` returns the billing amount for a committed flight, so the engine and the counters advance by it without change (`rebate_engine.py` changes only its docstring). `calculate_flight_margin` calls `committed_billing` on those inputs instead of computing a committed revenue, and loses the pro-rating branch (`flight_margin.py:86-91`): a running committed flight's revenue is its billing to date and its rebate is the engine's, unrounded, rounded once. `flight_revenue` stays only for `contracted_revenue`. `FlightMargin` gains `billable` and `billing_basis`; a target flight gets `reported` and no volume.

*Alternatives*: computing the billing in the repository query (rejected: the rule would be SQL and the domain could not test it); keeping the pro-rating for running flights (rejected by the business, option B of 2026-11-26).

### 2. Adjustments: an append-only table, the latest row wins

`flight_billing_adjustments`: `id`, `campaign_line_period_id` (FK, indexed with `id`), `basis` (check: `minimum`, `delivered`, `contracted`, `custom`), `amount` `Numeric(18,2)` nullable with the checks `(basis = 'custom') = (amount IS NOT NULL)` and `amount >= 0`, `reason` `Text NOT NULL` with `length(btrim(reason)) > 0`, `created_by` (FK `users`), `created_at`; the existing append-only trigger. The adjustment in force is the row with the highest id of the flight, read by the margin query with a lateral subquery, so the closing and every read see the same one. An adjustment to `minimum` is a row like any other (the flight returns to the rule and the history keeps it).

*Alternatives*: one mutable column set on the flight (rejected: the business asked for every adjustment with its author and reason); a soft-delete flag (rejected: the tables of financial facts are append-only).

### 3. The carry-over: columns on the flight that receives it

`campaign_line_periods` gains `carryover` `BigInteger NOT NULL DEFAULT 0` (check `>= 0`), `carryover_reason` `Text`, `carryover_set_by` (FK `users`), `carryover_set_at`, `carryover_billable` `Boolean NOT NULL DEFAULT false`, `carryover_billable_set_by`, `carryover_billable_set_at`, with the checks that a non-zero carry-over has its reason, author and moment, and that a billable flag set to true has its author and moment. `contracted_impressions` is never written. The previous flight is the flight of the same line with the greatest `flight_end` before the receiving `flight_start`; its shortfall is `max(0, contracted + carryover − delivered)`, `delivered` summed in the channel's unit from the stored delivery as of the request, compared exactly. A target line may receive a carry-over (it raises its delivery target); its flag cannot be set.

*Alternatives*: an append-only table of carry-overs (rejected: the business asked for a field of the flight, and the reasons survive in the review events of decision 4); a carry-over on the giving flight (rejected: the delivery target and the cap belong to the receiving one).

### 4. The review: append-only events on the campaign period

`campaign_period_reviews`: `id`, `campaign_period_id` (FK to `campaign_periods`, the campaign × month grain), `kind` (`reviewed` or `reopened`), `cause` (null for `reviewed`; `withdrawn`, `adjustment`, `carryover`, `carryover_billable` for `reopened`, with a check pairing them), `campaign_line_period_id` (FK, set only for the three edit causes), `created_by`, `created_at`; the append-only trigger. The unused `campaign_periods.status` is left as it is: it is mutable and has no history.

A pure function `review_state(ended: int, frozen: int, total: int, latest_kind: ReviewKind | None) -> ReviewState` derives the four states of `finance/monthly-review` from counts the repository returns; `in_progress` and `closed` are never stored. The services that write an adjustment, a carry-over or a flag call one `reopen_if_reviewed(campaign_period_id, cause, flight_id, user)` inside their own transaction.

### 5. The month lock serialises edits with the closing

Every write of this change (adjustment, carry-over, flag, review, withdrawal) takes the closing's advisory lock of its flight's or campaign's month (`pg_advisory_xact_lock(4242, year * 100 + month)`) before checking and writing. A closing therefore never freezes a flight while it is being adjusted, and an edit cannot slip between the closing's review check and its freeze. An edit of a month that is being closed waits for the closing and then gets `flight_closed` or `month_closed`.

### 6. The closing: three checks in order, every DSP, then the snapshot

`MarginClosingService._close` keeps `previous_month_open`, then calls `dsps_without_the_months_last_day` without the `volume_commitment = 'target'` filter, then a new `MarginFlightRepository.campaigns_not_reviewed(year, month, as_of)` returning each campaign in progress or pending review with its state, raising `MonthNotReviewedError` (409 `month_not_reviewed`, its message naming the month and the campaigns). A month whose only flights are running fails the third check, so the `if not flights` path is reached only by a month with no flight or with every flight frozen.

`closed_flight_snapshots` gains `billing_basis` (nullable, check of the five values, `reported` exactly when `volume_commitment = 'target'`), `billable` `Numeric(18,4)` (null for `custom`, `reported` and legacy rows), `carryover` `BigInteger`, `carryover_billable` `Boolean` and `billing_adjustment_id` (FK, required when the basis is `delivered`, `contracted` or `custom`); all null together on rows written before this change. `snapshot_of` copies them from the `PricedFlight`. `applied_rates.revenue_amount` and `rebate_base_amount` are filled for committed flights too (both the billing). The migration does not refuse a database with closed flights: those rows keep their figures (decided with the user).

### 7. The check compares with the current billing

`check_closed_delivery` computes the current revenue of a committed snapshot with `committed_billing` on the current delivered volume and the frozen contracted volume, carry-over, flag, sale CPM and basis (`custom` keeps the frozen revenue); a legacy snapshot keeps its frozen revenue. `ClosedDeliveryCheck` gains `billable_difference` and `billing_difference`, null for target and legacy snapshots. The rebate stays the frozen one, as in `closing-snapshot`.

### 8. Pacing on the delivery target

`FlightDeliveryFigures` gains `carryover`; `CampaignStatusService._to_row` passes `contracted + carryover` to `calculate_pacing` and computes the ratio on it; `CampaignStatusRow` and the response add `carryover` and `delivery_target`. The billable flag and the reason never reach the status query.

### 9. Routes, services and error bodies

- `backend/app/presentation/routers/billing.py` (prefix `/billing`): `GET ""`, `POST /flights/{flight_id}/adjustments`, `GET /flights/{flight_id}/adjustments`, `POST /reviews`, `POST /reviews/withdrawals`, `PUT /flights/{flight_id}/carryover/billable`, `GET /export`, all `require_roles(OPERATIONS, FINANCE)`.
- `backend/app/presentation/routers/carryover.py`: `PUT /flights/{flight_id}/carryover`, `require_roles(OPERATIONS, TRADING)`; its response schema has no money field by construction, and a test walks it.
- Services in `backend/app/application/services/`: `billing_adjustment_service.py`, `carryover_service.py`, `monthly_review_service.py`, `billing_query_service.py` (reads through `MarginQueryService`'s pricing so that `billing` equals `revenue`), `billing_export_service.py` (reads only snapshots, writes the CSV with the `csv` module: UTF-8 with a byte order mark, `;` as delimiter, decimal comma, no thousands separator).
- `presentation/errors.py` adds `/billing` to `_FIXED_BODY_ROUTE_PREFIXES` and the exact pattern `/flights/{id}/carryover`, leaving `/flights/preview` as it is; one handler per new domain error.
- `ACCESS_MATRIX` gains the eight entries and an `OPERATIONS_TRADING` set before the routers exist, so its test fails first; a new test checks that no `/billing` response schema is reachable by `trading` and that the carry-over response, for every role, has no amount, flag or adjustment field.

### 10. Screens

The margin screen replaces `ACCRUED_LABEL` («Devengado») with «Facturable» and «Facturable a la fecha» chosen from the flight's state and, for a line, a campaign or the period, from whether it holds a running flight (not from `provisional`, which a pending-close flight also carries), and shows «Ajustado». A new `frontend/features/billing/` module and route (`/billing`, under `app/(authenticated)/`) shows `GET /billing`, the adjustment form, the review buttons, the billable flag and the CSV download, guarded for operations and finance. The status screen adds «Arrastre» and «Objetivo de entrega» and, for operations and trading, the carry-over form. The closing control reads the review states of `GET /billing` for its off state. No screen computes a figure.

### 11. Acceptance: the rule applied to the sheet's own columns

`closed_month_sheet.py` and `running_month_sheet.py` gain `expected_billing(row)`, `expected_rebate(row)` and `expected_margin(row)`, computed from the sheet's served impressions, contracted volume, CPM, rebate rate, purchase cost and platform figures with the new rule, and the tests compare the domain with them instead of the sheet's sale. Two tests document the known difference: the rows whose expected billing departs from the sheet's sale are exactly those that served less than they contracted (ten on the closed sheet; on the running sheet every running row, plus Campaign 18 among the closed ones), and the aggregate difference is recorded with `record_property`. No figure is written in the tests. The database acceptance tests review their campaigns through `POST /billing/reviews` before closing; the running-month one expects 409 `month_not_reviewed` from closing October, since its flights are running, and reads its ended rows as pending close.

### 12. Reports

As in the previous changes, the reports go to `docs/reports/`, not to `specs/<change-name>/reports/` as `openspec/config.yaml` says.

## Risks / Trade-offs

- [Running committed figures drop, from the pro-rated contract to the billing to date] → Intended (option B). On the running sheet, the 23 running rows go down by 17,399.76 € of revenue and 11,615.61 € of margin; the screen says «Facturable a la fecha».
- [A month can no longer be closed before its last flight has ended, and a committed month waits for its DSP's last day] → Intended. An Adform run that failed on the last day blocks the closing until `run_ingestion --from/--to` covers it; the 409 names the DSP.
- [The shortfall is measured on the previous flight's delivery as stored when the carry-over is written] → A later restatement does not revalidate it; the carry-over keeps its value and the review shows who wrote it.
- [The carry-over keeps only its latest value] → Each change reopens a reviewed campaign with an event naming the cause, the flight and the user.
- [The current margin of a closed committed flight mixes the current billing with the frozen rebate] → Same trade-off as `closing-snapshot`: the counter has already advanced; the field descriptions say so.
- [The CSV's names are read now] → Only names: every figure comes from the snapshot. A renamed agency changes the CSV of a closed month.
- [Every test that closes a month must review first] → One fixture helper reviews every campaign of a month through the service; the closing tests and the demo seed call it.
- [A flight registered in a closed month] → As in `closing-snapshot`: its campaign is pending review and a second closing needs its review.

## Migration Plan

1. Four migrations after `3a08cce1c979`, one per task group: `flight_billing_adjustments` with its trigger; the carry-over columns of `campaign_line_periods` with their checks; `campaign_period_reviews` with its trigger; the billing columns of `closed_flight_snapshots` with their checks. None refuses existing rows; legacy snapshots get nulls. Each downgrade drops what it added.
2. Development: `e2e/scripts/reset-data.sh`; the demo seed reviews the campaigns of the month it closes.
3. Rollback: downgrade the four migrations and redeploy the previous image; adjustments, carry-overs and reviews are lost, and snapshots written meanwhile lose their billing columns but keep their revenue.
