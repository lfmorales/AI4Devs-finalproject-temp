> Reports go in `docs/reports/`, as in the previous changes. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/` (design.md, decision 12).
>
> Every implementation task starts with its failing test; a task is done when that test and the suite it names pass. The billing, the adjustment, the cap, the shortfall and the review state are domain functions tested without a database.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Verify `git branch --show-current` reports `feature/committed-billing-and-review` (renamed from `feature/billing-review` with `git branch -m`) and `git status --short` is clean after the commit of this specification, before the first code change
- [ ] 0.2 Check that `docs/product-description.md`, revised with this specification (§4, §5, §5.1, §5.3, §5.5, §5.8, §6 and §8), agrees with the specs of this change; verify with a read-through

## 1. Access Matrix First

- [ ] 1.1 Write the failing tests in `backend/tests/api/test_route_protection.py`: add `OPERATIONS_TRADING`, the seven `/billing` entries with `MARGIN_READERS` and `("/flights/{flight_id}/carryover", "PUT")` with `OPERATIONS_TRADING` to `ACCESS_MATRIX`; a test that the `/billing` routes are exactly the seven of `identity/access-matrix`; leave `test_the_margin_routes_are_the_four_of_this_change` unchanged. Verify that `test_the_access_matrix_has_an_entry_for_every_route_and_no_entry_without_a_route` fails for the eight missing routes
- [ ] 1.2 Add the two routers with the eight routes, their `require_roles` and a 501 body, registered in `backend/app/main.py`; verify 1.1 and that every route answers 401 without a token and 403, with only `code` and `message`, to each role outside its entry

## 2. Domain: the Billing of a Committed Flight

- [ ] 2.1 Write failing tests in a new `backend/tests/domain/test_billing.py` for `committed_billing` with the scenarios of `finance/margin-calculation` («The revenue of a committed flight is its billing»): 726,202 delivered of 726,202 at 5.00 € gives 3,631.01; 700,000 of 1,000,000 gives 3,500.00; 296,052 of 291,610 at 6.00 € gives 1,749.66; 280,000.50 OTS of 300,000 gives 1,400.00 with a billable volume of 280,000.5000; 580,000 of 500,000 with a carry-over of 100,000 gives 2,500.00 not billable and 2,900.00 billable; the adjustments `delivered`, `contracted` (the cap: 2,500.00 with the carry-over not billable and 3,000.00 billable), `custom` (4,200.00 and 0.00) and `minimum` of `finance/billing-adjustment`; every amount a `Decimal` rounded once, half up
- [ ] 2.2 Implement `Billing`, `BillingBasis` and `BillingAdjustment` in `backend/app/domain/value_objects/billing.py` and `committed_billing` in `backend/app/domain/services/billing.py`, reusing `round_amount`; add the module to `MARGIN_MODULES` in `test_margin_model_integrity.py`; verify 2.1 and that file
- [ ] 2.3 Write failing tests in `backend/tests/domain/test_flight_margin.py` and `test_priced_flights.py`: a closed committed flight that under-delivered earns its billing and its rebate is on it; a running committed flight from 2026-09-01 to 2026-09-30 with 90,000 delivered by 2026-09-10 earns 450.00 €, a rebate of 90.00 € at 20 % and a margin of 120.00 €, not pro-rated; 310,000 by then earns 1,500.00 €; no delivery earns 0.00 €; `FlightMargin` carries `billable` and `billing_basis` (`reported` and no volume for a target flight); `rebate_base` of a committed flight is its billing; a target flight's figures are unchanged. Invert `test_under_delivery_does_not_reduce_revenue` (`:113`) and `test_a_closed_dooh_flight_earns_the_revenue_of_its_contracted_ots` (`:331`), and `test_contracted_volume.py:20`
- [ ] 2.4 Add `carryover`, `carryover_billable` and `adjustment` to `FlightFacts` (and to the builder of `backend/tests/fixtures/flight_inputs.py`, defaulting to none), pass the `Billing` through `FlightEconomics`, make `rebate_base` and `calculate_flight_margin` use it and delete the pro-rating branch (`flight_margin.py:86-91`); verify 2.3, the domain suite, and a random comparison against `HEAD`, as in `equativ-deals`: tens of thousands of random target flights, and of committed flights that delivered at least their contracted volume and closed, give exactly the same `FlightMargin` field by field apart from the two new fields; mypy on the touched files reports no more errors than in a temporary worktree of `HEAD` (`docs/base-standards.md` §4)

## 3. Acceptance Against the Sheets

- [ ] 3.1 Write failing tests in `backend/tests/acceptance/`: `expected_billing`, `expected_rebate` and `expected_margin` of each sheet row computed from its own served, contracted, CPM, rebate rate, purchase cost and platform columns with the new rule; every comparison of the 12 closed-month and 11 running-month tests made against them instead of the sheet's sale and accrual; a test per sheet that the rows whose expected billing departs from the sheet's sale are exactly those that served less than they contracted (on the closed sheet, the ten of `finance/margin-calculation`, with the totals of that scenario recorded with `record_property`); no figure written in the tests
- [ ] 3.2 Add the helpers to `closed_month_sheet.py` and `running_month_sheet.py`; verify 3.1 and that the closed-month aggregates are −1,258.41 € of revenue and −1,040.18 € of margin against the sheet, as recorded

## 4. Carry-over: Columns and Domain

- [ ] 4.1 Write failing migration tests in a new `backend/tests/infrastructure/test_carryover_columns_migration.py`, on a scratch database as `test_closing_snapshot_migration.py` does: the seven columns exist with their types and defaults; a negative carry-over, a non-zero one without reason, author or moment, and a billable flag set to true without author or moment are refused; existing flights get 0 and false; `downgrade -1` drops them; the history has one head
- [ ] 4.2 Add the columns to `CampaignLinePeriodRecord`, generate the migration with `--autogenerate`, add the checks by hand and review it; verify 4.1, a second `--autogenerate` with no difference and `test_migration_schema_sync.py`
- [ ] 4.3 Write failing tests in a new `backend/tests/domain/test_carryover.py` for the shortfall (500,000 − 400,000 = 100,000; 520,000 delivered gives 0; a previous flight with its own carry-over of 50,000 that delivered 480,000 gives 70,000; OTS decimals compared exactly) and for the validation of a carry-over (no previous flight, previous not ended, above the shortfall, month closed, volume negative), each with its error code
- [ ] 4.4 Implement them in `backend/app/domain/services/carryover.py` with their domain errors; verify 4.3

## 5. Pacing on the Delivery Target

- [ ] 5.1 Write failing tests in `backend/tests/application/test_campaign_status_service.py` and `backend/tests/infrastructure/test_sqlalchemy_campaign_status_repository.py`: the November flight with 500,000 contracted, a carry-over of 100,000 and 190,000 delivered at D-1 2026-11-10 expects 200,000, deviates −5 % and is not flagged, and without the carry-over is flagged at +14 %; the ratio is over the delivery target; the row carries `carryover` and `delivery_target`; the flight id is in the row
- [ ] 5.2 Read the carry-over in the status repository and pass the delivery target to `calculate_pacing`; verify 5.1 and the status suite
- [ ] 5.3 Write failing API tests in `backend/tests/api/test_campaign_status_endpoint.py`: the row of the scenario carries `carryover` 100000 and `delivery_target` 600000 for each of the four roles, and no field, however nested, is an amount, a billable flag or a reason
- [ ] 5.4 Add the fields to `backend/app/presentation/schemas/campaign_status.py`; verify 5.3

## 6. Carry-over Routes

- [ ] 6.1 Write failing tests in a new `backend/tests/api/test_carryover_endpoint.py` for `PUT /flights/{flight_id}/carryover` with every scenario of `campaign/carryover` («A carry-over is written on the flight that receives it»), as `trading` and as `operations`; 403 as `finance` and as `business`; 401 without a token; error bodies of only `code` and `message`; the response walked for `trading` has no amount, no billable flag and no adjustment field; nothing written on a refusal; the contracted volume of the flight and of the line unchanged
- [ ] 6.2 Implement `CarryoverService` (month lock, previous flight, shortfall, write) and its repository, and the route and schema; add the carry-over path to the error-body patterns of `presentation/errors.py` without changing `/flights/preview`; verify 6.1 and `test_flight_preview_endpoint.py`
- [ ] 6.3 Write failing tests for `PUT /billing/flights/{flight_id}/carryover/billable` with the scenarios of `campaign/carryover` («Operations and Finance decide whether a carry-over is billable»): set as `finance` and as `operations`, 403 as `trading` and `business`, 409 `target_line_not_adjustable`, `no_carryover` and `month_closed`; the flag kept when the volume changes
- [ ] 6.4 Implement it; verify 6.3

## 7. Billing Adjustments

- [ ] 7.1 Write failing migration tests in a new `backend/tests/infrastructure/test_billing_adjustments_migration.py`: the table, its checks (basis values, amount with `custom` only, amount not negative, blank reason refused), its foreign keys, the append-only trigger refusing an update and a delete, no floating-point column, `downgrade -1`
- [ ] 7.2 Add the model and the migration, review it; verify 7.1 and `test_migration_schema_sync.py`
- [ ] 7.3 Write failing repository tests in `backend/tests/infrastructure/test_margin_repositories.py`: `open_ended_flights` and `list_flights` carry the carry-over, its flag and the latest adjustment of each flight (by highest id), and a flight without adjustment carries none
- [ ] 7.4 Add them to `_flight_facts_query` with a lateral subquery; verify 7.3 and the repository suite
- [ ] 7.5 Write failing tests in a new `backend/tests/api/test_billing_adjustments_endpoint.py` with every scenario of `finance/billing-adjustment`: the worked flight adjusted to `contracted` (5,000.00 €, rebate 1,250.00 €, margin 1,850.00 € in `GET /margin`), to `custom` 4,200.00 € fixed after a reingestion, to `delivered` following a reingestion to 720,000 (3,600.00 €), to 0.00; the 422 cases; 409 `target_line_not_adjustable`, `flight_not_ended`, `flight_closed`; 404 `flight_not_found`; the history latest first with the one in force; 403 as `trading` and `business`, 401 without a token; no body of `trading` carries an amount
- [ ] 7.6 Implement `BillingAdjustmentService` (month lock, checks, insert) and the two routes; verify 7.5

## 8. Monthly Review

- [ ] 8.1 Write failing tests in a new `backend/tests/domain/test_review_state.py` for `review_state` with every scenario of `finance/monthly-review` («A campaign has a review state in each month»)
- [ ] 8.2 Implement it in `backend/app/domain/services/monthly_review.py`; verify 8.1
- [ ] 8.3 Write failing migration tests for `campaign_period_reviews`: kinds and causes paired, the flight required for the three edit causes, the append-only trigger, `downgrade -1`
- [ ] 8.4 Add the model and the migration, review it; verify 8.3 and `test_migration_schema_sync.py`
- [ ] 8.5 Write failing tests in a new `backend/tests/api/test_monthly_review_endpoint.py`: review and withdrawal with every scenario of `finance/monthly-review`, 404 and 409 codes, reviewing twice writes once; an adjustment, a carry-over and a flag reopen a reviewed campaign with their cause, flight and user, write nothing when it was pending, and write nothing when the edit is refused; an ingestion does not reopen; 403 as `trading` and `business`, 401 without a token
- [ ] 8.6 Implement `MonthlyReviewService`, the two routes and `reopen_if_reviewed` called by the services of tasks 6 and 7 in their transactions; verify 8.5, 6.1, 6.3 and 7.5

## 9. Closing: Every DSP, the Review and the Billing Snapshot

- [ ] 9.1 Write failing migration tests in `backend/tests/infrastructure/test_billing_snapshot_migration.py`: the five snapshot columns, their checks (legacy rows all null together; `reported` exactly with `target`; the adjustment required with `delivered`, `contracted` and `custom`; no billable volume with `custom` and `reported`), an existing snapshot migrated with nulls, `downgrade -1`
- [ ] 9.2 Add the columns and the migration, review it; verify 9.1
- [ ] 9.3 Write failing domain tests in `backend/tests/domain/test_closed_flight.py`: `snapshot_of` copies the billing basis, billable volume, carry-over, flag and adjustment; `margin_from_snapshot` returns `billable` and `billing_basis`, and null for a legacy snapshot; `check_closed_delivery` gives the restated committed example (current billing 5,000.00, current margin −75.00, difference −800.00, billable +300,000, billing +1,500.00), keeps the legacy example at −450.00 with null billing differences, keeps a custom billing, and the OTS 1 % scenario with a contracted volume of 300,000
- [ ] 9.4 Implement them in `closed_flight.py` and `ClosedFlightSnapshot`; verify 9.3 and `test_closed_flight.py`
- [ ] 9.5 Write failing service tests in `backend/tests/infrastructure/test_margin_closing_service.py`: a committed-only month waits for the last day of its DSP (409 `month_delivery_not_loaded` naming Adform); a month with a running flight is refused with `month_not_reviewed` naming its campaign as in progress; a month with a campaign pending review is refused naming it; the checks run in order; a reviewed month closes and writes the billing in the snapshot and in `applied_rates.revenue_amount` and `rebate_base_amount` for committed flights; an adjusted flight freezes its adjustment; the counter advances by the billing; an edit waiting on the month lock gets `flight_closed`. Add a helper in `backend/tests/fixtures/margin_data.py` that reviews every campaign of a month through the service, and use it in every existing closing test (`test_margin_closing_service.py`, `test_margin_closing_concurrency.py` and the API tests of task 13.1)
- [ ] 9.6 Implement the three checks, `MonthNotReviewedError` and its handler, and the snapshot and `applied_rates` writing; verify 9.5 and every closing test

## 10. Reads: the Margin and the Billing

- [ ] 10.1 Write failing tests in `backend/tests/api/test_margin_endpoint.py` and `test_margin_contracted_revenue.py`: `billable` and `billing_basis` on every flight with the scenarios of `finance/margin-reporting`; `delivery_change` with `billable_difference` and `billing_difference`; a closed under-delivered flight with `revenue` "3500.00" and `contracted_revenue` "5000.00"; a running flight with 180,000 delivered at 5.00 € with `revenue` "900.00"; `test_response_schema_descriptions.py` checks the new descriptions
- [ ] 10.2 Add the fields to `backend/app/presentation/schemas/margin.py` and `MarginQueryService`; verify 10.1
- [ ] 10.3 Write failing tests in a new `backend/tests/api/test_billing_endpoint.py` with every scenario of `finance/billing-report` («The billing of a month is read per campaign, line and flight» and «Errors under the billing routes are code and message»): the November month with the billable carry-over and the custom adjustment, the review states, `billing` equal to `GET /margin`'s `revenue` for every flight, nothing written, 404, 422; 403 as `trading` and `business`
- [ ] 10.4 Implement `BillingQueryService` and the route; verify 10.3
- [ ] 10.5 Write failing tests in a new `backend/tests/api/test_billing_export_endpoint.py` with every scenario of «A closed month's billing is exported as a CSV»: the byte order mark, `;` separator, decimal comma and quoted reason of «The file opens in columns in Excel set to Spanish», header row, values and order, the adjusted and the target rows, a legacy row, identical files after a reingestion, `Content-Type` and file name, 409 `month_not_closed`; 403 as `trading` and `business`
- [ ] 10.6 Implement `BillingExportService` and the route; verify 10.5

## 11. Database Acceptance

- [ ] 11.1 Update `backend/tests/api/test_acceptance_closed_month_database.py`: review the five campaigns through `POST /billing/reviews` before closing; compare each real row with the domain and with the expected billing of task 3; keep the over-delivery test as is
- [ ] 11.2 Update `backend/tests/api/test_acceptance_running_month_database.py`: closing October with running flights answers 409 `month_not_reviewed` naming them and writes nothing; the ended rows are read as pending close with their expected billing; the running rows with their billing to date; verify the 39 acceptance tests and the new ones

## 12. Screens

- [ ] 12.1 Write failing Vitest tests in `frontend/tests/unit/features/margin/`: «Facturable» on an ended flight and on a level without a running flight, «Facturable a la fecha» on a running flight and its levels, «Ajustado» on an adjusted flight, no «Devengado» anywhere; the closing control off with «Hay campañas pendientes de revisión»; `no-arithmetic.test.ts` still passes
- [ ] 12.2 Change `frontend/features/margin/messages.ts`, `Figures.tsx`, `MarginTree.tsx` and `MarginPage.tsx`, and the types of `frontend/lib/api/margin.ts`; verify 12.1 and the frontend suite
- [ ] 12.3 Write failing Vitest tests for a new `frontend/features/billing/` screen with the scenarios of «The billing screen shows a month's billing» and «The billing screen shows and changes the review»: states and labels, the adjustment form (reason required, amount only for custom), the billable flag, the review and withdrawal buttons, the CSV download, the Spanish message of each refusal, hidden for `trading` and `business`
- [ ] 12.4 Implement `frontend/lib/api/billing.ts`, the feature module and the route, with its role guard and its navigation entry; verify 12.3
- [ ] 12.5 Write failing Vitest tests for the status screen: «Arrastre» and «Objetivo de entrega» on every row; the carry-over form for `operations` and `trading` with the shortfall of a refusal; no form for `business` and `finance`; no billable flag for anyone
- [ ] 12.6 Implement them in the status feature and `frontend/lib/api/campaign-status.ts`; verify 12.5 and the frontend suite

## 13. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 13.1 Review the tests whose meaning changed and record each in `docs/reports/YYYY-MM-DD-step-13-test-review.md`: the inverted domain tests of task 2.3; `test_contracted_revenue.py:38`; `test_closed_flight.py` (the committed example and the DOOH snapshot); `test_priced_flights.py`; `test_margin_contracted_revenue.py:55` and `:68`; `test_margin_coherence.py`, `test_margin_end_to_end.py`, `test_margin_endpoint.py`, `test_margin_zero_sale.py`, `test_margin_delivery_change_endpoint.py`, `test_margin_closings_endpoint.py`, `test_seed_margin_demo_states.py` and the three `tests/scripts/test_run_ingestion*` that close a month (all review first); `test_frozen_revenue_migration.py` and `test_closing_snapshot_migration.py` with their revisions pinned; `test_margin_schema.py` with the new tables; the builders of `frontend/tests/helpers/margin-data.ts` and the types of `e2e/support/margin.ts`

## 14. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 14.1 Capture the pre-test baseline of the development database: row counts of `applied_rates`, `closed_flight_snapshots`, `month_closings`, `flight_billing_adjustments`, `campaign_period_reviews`, `campaign_line_periods` with a carry-over, `daily_deliveries` and `ingestion_batches`
- [ ] 14.2 Run the targeted tests of tasks 1 to 12, then the whole backend suite (`pytest`), the acceptance tests, mypy on the touched files as `docs/base-standards.md` §4 says, and the frontend suite (`npm test`), recording totals, failures and runtime; compare test by test with `HEAD`, not totals
- [ ] 14.3 Re-check the baseline and restore any change the tests left
- [ ] 14.4 Create `docs/reports/YYYY-MM-DD-step-14-unit-test-and-db-verification.md`; the step is complete only once it exists

## 15. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 15.1 With the stack reset by `e2e/scripts/reset-data.sh` and test-issuer tokens: `GET /api/billing` of the demo's pending month as `finance`; `POST /api/billing/flights/{id}/adjustments` to `contracted` with a reason, then the history, then `GET /api/margin` with the adjusted revenue; the 422 without reason and the 409 on a running flight; as `trading` 403 on each `/api/billing` route
- [ ] 15.2 `PUT /api/flights/{id}/carryover` as `trading` within and above the shortfall; `GET /api/campaign-status` as `trading` with `carryover` and `delivery_target` and no amount or flag; `PUT /api/billing/flights/{id}/carryover/billable` as `finance`, and 403 as `trading`
- [ ] 15.3 `POST /api/margin/closings` refused with `month_not_reviewed`; `POST /api/billing/reviews` for each campaign, a withdrawal and a new review; the closing accepted; `GET /api/billing/export` as `operations` saved and checked column by column against `GET /api/billing`; 409 `month_not_closed` for an open month
- [ ] 15.4 Restore the development database with `e2e/scripts/reset-data.sh` (a closing cannot be undone), check the baseline of 14.1, and document every command and response in `docs/reports/YYYY-MM-DD-step-15-curl.md` with no identifier, name, amount or token of a real DSP

## 16. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 16.1 Make `backend/scripts/seed_margin_demo.py` review the campaigns of the month the E2E closes and give one flight a carry-over; update `test_seed_margin_demo_states.py`
- [ ] 16.2 Update `e2e/tests/margin.spec.ts`: the closing flows review first through the billing screen; «Facturable» and «Facturable a la fecha» instead of «Devengado» (search the old text in `e2e/` first); add `e2e/tests/billing.spec.ts`: Finance adjusts a pending-close flight, the campaign returns to pending, Finance reviews it, Operations closes the month and downloads the CSV; add to `status.spec.ts` a trading flow that writes a carry-over and sees «Objetivo de entrega» and no amount; update `roles-matrix.spec.ts` and `navigation-roles.spec.ts` for the billing screen and the carry-over
- [ ] 16.3 Reset the E2E data with `e2e/scripts/reset-data.sh`, run the whole Playwright suite, check in the browser the billing screen and the status screen as `trading`, restore the data, and document the run in `docs/reports/YYYY-MM-DD-step-16-e2e.md`

## 17. Update Technical Documentation (MANDATORY)

- [ ] 17.1 Check that the invariants of `openspec/config.yaml` agree with the implementation: the revenue invariant was updated with this specification (billing of a committed line, reported revenue of a target line)
- [ ] 17.2 Update `readme.md`: the economic model, the data model of the three new tables and the new columns, the eight routes with their roles, the closing errors, the billing screen and the CSV
- [ ] 17.3 Update `docs/deploy.md`: closing requires the review and the last day of every DSP, a month cannot be closed while a flight runs, and the CSV download; and check that `docs/product-description.md` still agrees with the specs after the implementation
