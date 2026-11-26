> Reports go in `docs/reports/`, as in the previous changes. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/` (design.md, decision 10).
>
> Every implementation task starts with its failing test; a task is done when that test and the suite it names pass. The domain functions of the snapshot and of the check are tested without a database.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Verify `git branch --show-current` reports `feature/closing-snapshot` and `git status --short` shows only this change's artifacts before the first code change
- [x] 0.2 Check that `docs/product-description.md`, revised with this specification (§4 diagram and key decisions, §6 Phase 2, §8 Resolved), agrees with the specs of this change; verify with a read-through

## 1. Snapshot Tables (migration)

- [x] 1.1 Write failing tests in a new `backend/tests/infrastructure/test_closing_snapshot_migration.py`, on a scratch database as `test_frozen_revenue_migration.py` does: migrating from `950895fa2d75` with one `applied_rates` row fails with a message naming `e2e/scripts/reset-data.sh` and creates no table; on a database without closed flights it creates `month_closings`, `month_closing_batches` and `closed_flight_snapshots`; every column is `NOT NULL` except `gross_revenue`; `gross_revenue` is refused on a committed row and required on a target row; `delivery_metric` and `volume_commitment` refuse other values; `applied_rate_id` is unique; an update or a delete of any of the three tables is refused by the append-only trigger; no column is floating point; `downgrade -1` drops the three tables; the history has one head
- [x] 1.2 Add the three models to `backend/app/infrastructure/persistence/models/margin.py` and generate the migration with `--autogenerate`; add by hand the guard on `applied_rates` and the triggers; review it; verify 1.1, that a second `--autogenerate` finds no difference, that `test_migration_schema_sync.py` lists the three tables, and that `test_frozen_revenue_migration.py` still passes with its revisions pinned

## 2. Domain: the Snapshot of a Closed Flight

- [x] 2.1 Write failing tests in a new `backend/tests/domain/test_closed_flight.py` that `snapshot_of` copies the amounts of `priced.margin` and the delivery and line of `priced.facts` for a committed flight, the worked Deal flight (gross 5,500.00, revenue 4,400.00, rebate 550.00, platform cost 1,100.00, margin 2,750.00) and the DOOH flight (280,000.5000 OTS, 12,000 impressions); that `ClosedFlightSnapshot` refuses a committed snapshot with a gross, a target one without, and any amount that is not a `Decimal`
- [x] 2.2 Implement `ClosedFlightSnapshot` in `backend/app/domain/value_objects/closed_flight.py` and `snapshot_of` in `backend/app/domain/services/closed_flight.py`; add the module to `MARGIN_MODULES` in `test_margin_model_integrity.py`; verify 2.1 and that file
- [x] 2.3 Write failing tests that `margin_from_snapshot` returns a closed, non-provisional `FlightMargin` with `accrued_days` equal to `window_days`, every amount, volume, flag and attribute of the snapshot, `below_cost` from the frozen margin, `zero_sale` from the frozen CPM and `margin_pct` from the frozen margin and revenue; and that `margin_from_snapshot(snapshot_of(priced))` equals `priced.margin` for a closed committed, target, zero-sale and DOOH flight; and that, for a committed and a target flight, `margin_from_snapshot` gives the same `FlightMargin` as `calculate_flight_margin` on the same `FlightEconomics` at the closing date
- [x] 2.4 Implement `margin_from_snapshot` without calling `calculate_flight_margin`; verify 2.3

## 3. Domain: the Check, the Counts and the Closed Days

- [x] 3.1 Write failing tests for `check_closed_delivery` with the scenarios of `finance/margin-calculation` («A closed flight is checked against its current delivery»): the restated committed flight (current margin −450.00, difference −2,300.00, impressions +500,000, media cost +1,800.00, flagged); an unchanged delivery (all zero, not flagged); a media cost moved by 0.99 € (not flagged) and by 1.00 € (flagged); 303,000.0000 against 300,000.0000 OTS (flagged) and 302,999.9999 (not); a frozen zero with 10 impressions now (flagged); the restated Deal flight (current margin 3,350.00, difference 600.00, revenue +800.00, spend +1,000.00, flagged); a committed flight with no revenue or spend difference
- [x] 3.2 Implement `check_closed_delivery` and `ClosedDeliveryCheck` with `MARGIN_CHANGE_TOLERANCE` and `DELIVERED_CHANGE_TOLERANCE`, reusing `round_amount` and `WindowDelivery`; verify 3.1
- [x] 3.3 Write failing tests in `backend/tests/domain/test_margin_totals.py` that `FlightMargin.delivery_changed` defaults to false, that `total_flights` and `total_lines` count it in `delivery_changed_count`, and that no amount, volume or other count of a total changes with it
- [x] 3.4 Add the field and the count; verify 3.3 and `test_margin_totals.py`
- [x] 3.5 Write failing tests for `days_in_closed_months`: 2026-11-26 to 2026-12-02 with November closed gives 5 and with nothing closed 0; 2026-10-15 to 2026-11-14 with October closed gives 17; implement it in the domain and verify

## 4. Closing Writes the Snapshot and the Header

- [x] 4.1 Write failing repository tests in `backend/tests/infrastructure/test_margin_repositories.py`: adding a header stores the month, the moment, the user, `as_of` and, per DSP of the frozen flights' lines, the latest succeeded batch (latest `finished_at`, then highest id), never a failed one, leaving out a DSP with none; `save` writes one snapshot per `applied_rates` row under that header; a target snapshot's revenue and gross equal the row's `revenue_amount` and `rebate_base_amount`; counting the headers of a month
- [x] 4.2 Implement the header repository in `MarginClosingTransaction` and the snapshot writing in `SqlAlchemyAppliedRateRepository.save`; verify 4.1
- [x] 4.3 Write failing service tests in `backend/tests/infrastructure/test_margin_closing_service.py`: a closing writes one header and one snapshot per frozen flight and answers `closings` 1; each snapshot holds the pending-close figures (extend `test_pending_close_figures_are_the_figures_closing_freezes`); closing twice adds no header and answers `closings` 1; a month with no ended flight writes no header and answers `closings` 0; a flight registered in the closed month and closed by a second closing gets a second header, `closings` 2, and leaves the first closing's rows unchanged; a failure halfway leaves no rate, snapshot or header (extend `test_a_failure_halfway_leaves_no_row`); two concurrent closings leave one header (`test_margin_closing_concurrency.py`)
- [x] 4.4 Implement the header and `ClosingResult.closings` in `MarginClosingService._close`; verify 4.3 and the existing closing tests

## 5. A Closed Flight Is Read from Its Snapshot

- [x] 5.1 Write failing repository tests that `list_flights` returns the snapshot of a frozen flight with its rates, and the current window sums with the delivered volume in the snapshot's metric after the channel's metric is changed
- [x] 5.2 Implement the join and the metric of the current sums in `SqlAlchemyMarginReadRepository.list_flights`; verify 5.1 and the existing repository tests
- [x] 5.3 Write failing service tests: invert `test_a_restatement_after_closing_moves_neither_the_revenue_nor_the_gross_nor_the_rebate_of_the_closed_month` (`test_margin_closing_service.py:485`) so that the platform cost stays 1,100.00 €, `gross_differs_from_buyer_spend` stays false, and the flight carries `delivery_changed` with its current margin; add the committed Adform example, ingested again for 28 November through `DeliveryIngestionService` with the test DSP client, whose closed margin stays 1,850.00 € with `delivery_changed` and a current margin of −450.00 €; unlinking a line with a closed flight; a channel whose metric changed after closing; a running and a pending-close flight carry no check
- [x] 5.4 Build a closed flight with `margin_from_snapshot` and `check_closed_delivery` in `MarginQueryService._report`, add `delivery_change` to `FlightReport`, delete `_margin_from_frozen`; verify 5.3, `test_margin_coherence.py`, `test_margin_contracted_revenue.py` and `test_margin_zero_sale.py`; and a random comparison against `HEAD`, as in equativ-deals: tens of thousands of random committed and target flights, priced with `price_flights` at a random `as_of` (before, during and after the flight), give exactly the same `FlightMargin`, field by field, and the same line and campaign totals with the code of `HEAD` and with the new code when they are not closed; and every closed flight, read with `margin_from_snapshot` from the snapshot of its pricing at the closing date, gives exactly its `priced.margin` of that closing, whatever its delivery is afterwards

## 6. Response Schemas and Acceptance

- [x] 6.1 Write failing API tests: `POST /margin/closings` answers `closings` as an integer (`test_margin_closings_endpoint.py`), 1 after a first closing and 2 after a closing of a late flight; `GET /margin` carries `delivery_changed`, `delivery_change` with the fields, strings and nulls of `finance/margin-reporting` for the committed example and the Deal example, `delivery_change` null on a running and a pending-close flight, and `delivery_changed_count` on every line, campaign and the totals; `test_response_schema_descriptions.py` checks that the descriptions of `delivery_change` and `current_margin` say the closing's rebate and rates are used and no total adds it; a user holding neither `operations` nor `finance` is still forbidden on both routes and `test_route_protection.py` passes with `ACCESS_MATRIX` unchanged
- [x] 6.2 Add `closings`, `delivery_changed`, `DeliveryChangeResponse` and `delivery_changed_count` to `backend/app/presentation/schemas/margin.py` and the closing route; verify 6.1
- [x] 6.3 Write the database acceptance test in `backend/tests/api/test_acceptance_closed_month_database.py`: close the month, ingest its window again through the ingestion service with different figures, and check that every flight, line, campaign and total reads the same amounts, volumes, flags and counts as before, apart from the change warning; update the exact closing responses of that file and of `test_acceptance_running_month_database.py` to carry `closings`; verify the 38 existing acceptance tests and the new one

## 7. The Command Reports the Days in Closed Months

- [x] 7.1 Write failing tests in `backend/tests/scripts/test_run_ingestion_output.py` and `test_run_ingestion_range.py`: a succeeded run prints `closed_month_days` with 5 for the window 2026-11-26 to 2026-12-02 and November closed, 0 with November open, 17 for the range 2026-10-15 to 2026-11-14 with October closed; the days of a closed month are still ingested; a failed run prints no count
- [x] 7.2 Read the closed months of the window in `scripts/run_ingestion.py` after a succeeded run, print the count and update the module docstring; verify 7.1 and the script tests

## 8. Screens

- [x] 8.1 Write failing Vitest tests in `frontend/tests/unit/features/margin/`: a flight with `delivery_changed` shows «Cambió tras el cierre», the current margin and the differences of the response and the note that the rebate and the rates are the closing's; a line, a campaign and the period show the count; a flight with `delivery_changed` false shows no label; `no-arithmetic.test.ts` still passes
- [x] 8.2 Add the fields to `frontend/lib/api/margin.ts`, the tag and its detail to `Flags.tsx` and `TotalsFlags`, and the text to `messages.ts`; update `frontend/tests/helpers/margin-data.ts`; verify 8.1 and the frontend suite

## 9. Remove the Unused Gross Input

- [x] 9.1 Once a closed flight is read from its snapshot (task 5.4), no caller passes a frozen gross any more: remove `gross_revenue` from `FlightEconomics` (field, docstring and `__post_init__` check) and from `calculate_flight_margin`, which then always computes a target flight's gross from its served impressions, and from the call in `priced_flights.py`; the builder of `backend/tests/fixtures/flight_inputs.py` absorbs the change, so no test passes the field. Verify that the domain, application and API suites pass as before; that a random comparison against `HEAD`, as in equativ-deals, gives the same results for every flight: tens of thousands of random committed and target flights at a random `as_of` (not started, running and closed), priced with `calculate_flight_margin` in both trees (`gross_revenue=None` in `HEAD`), give exactly the same `FlightMargin`, field by field, and the same line and campaign totals; that mypy on the touched files reports no more errors than in a temporary worktree of `HEAD` (`docs/base-standards.md` §4); and that `git grep -n gross_revenue -- backend/app/domain/value_objects/margin.py backend/app/domain/services/flight_margin.py backend/app/domain/services/priced_flights.py` shows it only on `FlightMargin`, on `MarginTotals` and as the gross `calculate_flight_margin` computes, never as an input of `FlightEconomics`

## 10. Review and Update Existing Unit Tests (MANDATORY)

- [x] 10.1 Review the tests whose meaning changed and record each in `docs/reports/YYYY-MM-DD-step-10-test-review.md`, as in equativ-deals: in `test_margin_closing_service.py` the DOOH closing (`:338`), the restatement (`:485`), the pending-close figures (`:276`) and the failure halfway (`:204`); `test_margin_coherence.py:60` and `:103`; `test_margin_contracted_revenue.py:59` and `:130`; `test_margin_endpoint.py:81`; `test_margin_zero_sale.py:68`; the exact closing responses in the acceptance and endpoint tests; the floating-point check of `test_margin_schema.py:325`, which adds the three tables; the margin builders of `frontend/tests/helpers/margin-data.ts` and the types of `e2e/support/margin.ts`

## 11. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 11.1 Capture the pre-test baseline of the development database: row counts of `applied_rates`, `month_closings`, `month_closing_batches`, `closed_flight_snapshots`, `daily_deliveries` and `ingestion_batches`
- [ ] 11.2 Run the targeted tests of tasks 1 to 9, then the whole backend suite (`pytest`), the acceptance tests (38 plus the new one), mypy on the touched files as `docs/base-standards.md` §4 says, and the frontend suite (`npm test`), recording totals, failures and runtime
- [ ] 11.3 Re-check the baseline and restore any change the tests left
- [ ] 11.4 Create `docs/reports/YYYY-MM-DD-step-11-unit-test-and-db-verification.md`; the step is complete only once it exists

## 12. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 12.1 With the stack reset by `e2e/scripts/reset-data.sh` and a test-issuer token, `POST /api/margin/closings` for the demo's pending month as `finance` and check 200 with `closings` 1, and again with `closed` 0 and `closings` 1; as `trading` check 403 and that nothing is written
- [ ] 12.2 `GET /api/margin` as `operations` and check that the closed flights carry `delivery_changed` false and a `delivery_change` of zeros; change one closed flight's delivery in the database and check `delivery_changed` true, its differences, its current margin, unchanged amounts and the counts; as `business` check 403
- [ ] 12.3 If the Adform credentials are configured in the local `.env`, run `python -m scripts.run_ingestion --from <first day of the closed month> --to <a day of it>` and check `closed_month_days` and exit 0; otherwise record in the report that the count is covered by task 7.1 and no real DSP was called
- [ ] 12.4 Restore the development database with `e2e/scripts/reset-data.sh` (a closing cannot be undone), check the baseline of 11.1, and document every command and response in `docs/reports/YYYY-MM-DD-step-12-curl.md` with no identifier, name, amount or token of a real DSP

## 13. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 13.1 Reset the E2E data with `e2e/scripts/reset-data.sh` and run the whole Playwright suite; `margin.spec.ts` keeps checking that the closing changes no amount
- [ ] 13.2 Check in the browser that the margin screen of a closed month shows its figures and no «Cambió tras el cierre» label, restore the data, and document the run in `docs/reports/YYYY-MM-DD-step-13-e2e.md`

## 14. Update Technical Documentation (MANDATORY)

- [ ] 14.1 Update `docs/deploy.md`: replace «Closing a month: from the 8th of the next month» (`:266-268`) with what the snapshot guarantees, that the ingestion and the unlinking still rewrite the delivery of a closed month, that the margin screen flags it, and that a database holding closed flights must be reset before this migration
- [ ] 14.2 Update `readme.md`: the closed-month paragraphs (`:126`, `:1524`), the data model of the three tables, the closing response with `closings`, the margin response with the change warning, and the output of `run_ingestion` with `closed_month_days`
- [ ] 14.3 Update the invariant of frozen rates in `openspec/config.yaml` to the snapshot, and check that `docs/product-description.md` still agrees with the specs after the implementation
