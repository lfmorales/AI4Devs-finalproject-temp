> Reports go in `docs/reports/`, as in the previous changes. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/` (design.md, decision 12).
>
> Every implementation task starts with its failing test; a task is done when that test and the suite it names pass.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Verify `git branch --show-current` reports `feature/ctv-and-delivery-metric` and `git status --short` is empty before the first code change

## 1. Channels in Seeds, Fixtures and the Masters File

- [ ] 1.1 Write failing tests in `backend/tests/scripts/test_seed_dev_data.py` that the seed loads exactly `Directo`, `Deal`, `DOOH` and `CTV` and no `OOH` or `Digital`, and that it adds, next to the existing any-channel schedule of `Default Holding Group`, a fictitious schedule with `channel_id` = CTV and no agency or scope; adjust the existing assertion at `:74` so it selects the any-channel schedule
- [ ] 1.2 Write a failing test that a CTV line of `Default Holding Group` resolves the CTV schedule at the group-and-channel step and a `Directo` line of the same group resolves the any-channel schedule, against the seeded development data
- [ ] 1.3 Change `backend/scripts/seed_dev_data.py` to the four channels and the CTV schedule, idempotent like the rest of the seed, and verify 1.1 and 1.2 pass
- [ ] 1.4 Write a failing test that `tests/fixtures/master_data.py` loads `Directo`, `Deal`, `DOOH`, `CTV` with ids 1 to 4 in that order; change the fixture and verify the backend suite still passes with `channel_id=1` now `Directo`
- [ ] 1.5 Write a failing test in `backend/tests/scripts/test_load_masters.py` that `deploy/masters.example.json` passes `--check` and lists exactly the four channels; replace `Example Channel` with them and verify it passes

## 2. Metrics in the Adform Request

- [ ] 2.1 Change `backend/tests/infrastructure/test_adform_delivery_client.py:73` to expect the seven metrics and add `ots` and `videoCompletionRate` to `COLUMN_HEADERS` and `report_row` in `backend/tests/fixtures/fake_adform.py`; extend the missing-column test (`:247`) with both new columns; verify they fail
- [ ] 2.2 Add `ots` and `videoCompletionRate` to `_METRICS` in `adform_delivery_client.py` and verify 2.1 passes

## 3. Row Translation

- [ ] 3.1 Write failing tests for `_to_delivery_row`: 7,500.12345 OTS read as 7500.1234; 50,000 impressions at 0.8123 give 40,615 completions; 5 and 3 impressions at 0.5 give 2 and 2 (half to even); 100 impressions at 0.575 give 58, not the 57 of `round()` on a float, and 100.00035 OTS give 100.0004, not 100.0003, both with the cell given as a `Decimal`, a text and a `float`; an empty `ots` cell and a `"-"` rate give 0 and 0 with 1,200 impressions, never 1,200 OTS; `"n/a"` in `ots` raises `DspResponseFormatError`
- [ ] 3.2 Write failing value-object tests that `DspDeliveryRow` carries `ots: Decimal` and `video_completions: int`
- [ ] 3.3 Add the two fields to `DspDeliveryRow`, read the cells as `Decimal(str(value))` rounded with `quantize` and `ROUND_HALF_EVEN`, never with `round()` or through `float` (design.md decision 5), give `tests/fixtures/delivery_rows.py` zero defaults, and verify 3.1 and 3.2 pass with the rest of the ingestion tests

## 4. Combination per Line and Day

- [ ] 4.1 Write failing tests in `backend/tests/domain/test_delivery_combination.py`: 410 impressions with 7,500.50 OTS plus 90 with 1,499.25 give 500 and 8999.7500; 1,000 impressions at 0.75 plus 3 at 0.5 give 752 completions; no rate field exists on `DailyDelivery`
- [ ] 4.2 Add `ots` and `video_completions` to `DailyDelivery`, sum them in `_from_row` and `_add`, and verify 4.1 passes

## 5. Storage (migration)

- [ ] 5.1 Write failing model tests in `backend/tests/infrastructure/test_delivery_models.py` that `daily_deliveries.ots` is `Numeric(18,4) NOT NULL DEFAULT 0` and `video_completions` is `BigInteger NOT NULL DEFAULT 0`, and a repository test in `test_sqlalchemy_delivery_repository.py` that a DOOH day of 8999.7500 OTS and a CTV day of 40,615 completions read back exactly
- [ ] 5.2 Add the columns and generate the Alembic migration with `--autogenerate`; review it by hand; verify `upgrade head`, `downgrade -1` and `upgrade head` on a database holding delivery rows, that the old rows read 0.0000 OTS and 0 completions, and the schema-sync test
- [ ] 5.3 Write the two fields in `sqlalchemy_delivery_repository.py` and verify 5.1 and `test_ingestion_service_postgres.py` extended with one DOOH and one CTV line from the fake Adform report

## 6. Unmatched Row with OTS

- [ ] 6.1 Write failing tests in `backend/tests/application/test_unmatched_delivery_exceptions.py`: an unmatched row with 0 impressions, 0.00 € and 2,400.5 OTS records an `unmatched_delivery` exception whose retained day holds zeros and is not counted as a zero unmatched row; a row with zero impressions, cost and OTS is counted and not worked
- [ ] 6.2 Add OTS to `has_something_to_work` in `unmatched_delivery_recording.py` and verify 6.1 passes

## 7. Delivery Metric on the Channel (migration)

- [ ] 7.1 Write failing model tests that `channels.delivery_metric` is `NOT NULL`, defaults to `impressions` and refuses any value other than `impressions` and `ots`
- [ ] 7.2 Add the column with its check and generate the Alembic migration, adding by hand `UPDATE channels SET delivery_metric = 'ots' WHERE name = 'DOOH'`; write a migration test that a database holding `DOOH`, `Directo` and `DEMO Channel` upgrades to `ots`, `impressions`, `impressions`; verify `upgrade head`, `downgrade -1`, `upgrade head` and the schema-sync test
- [ ] 7.3 Write failing tests that the development seed, `tests/fixtures/master_data.py` and `deploy/masters.example.json` give `DOOH` the metric `ots` and the other three `impressions`; update the three and verify
- [ ] 7.4 Write failing tests in `test_load_masters_validation.py` and `test_load_masters.py`: `delivery_metric` is an accepted channel key; `views` is rejected; a new channel is created with its metric; a file naming an existing `ots` channel as `impressions` is rejected reporting `channels[2]` with nothing written; then implement in `scripts/load_masters.py` and verify
- [ ] 7.5 Write a failing test that the master repository's `Channel` carries `delivery_metric`, implement it, and return it from the in-memory registration fixture

## 8. One Delivery Metric per Campaign

- [ ] 8.1 Write failing service tests in `backend/tests/application/test_campaign_registration_service.py`: `DOOH` with `Directo` raises the mixed-metric error and saves nothing; `Directo`, `Deal` and `CTV` register; two `DOOH` lines register; `Directo` with an unknown channel still fails for the unknown channel
- [ ] 8.2 Write a failing API test in `backend/tests/api/test_campaign_registration.py` that `DOOH` with `Directo` answers 422 `{"code": "mixed_delivery_metrics", "message": …}` and creates no campaign, period, line, flight or purchase order
- [ ] 8.3 Add `MixedDeliveryMetricsError`, check it after the reference loop of `CampaignRegistrationService`, map it in `presentation/errors.py`, and verify 8.1 and 8.2 pass with the existing registration tests unchanged

## 9. Daily Status

- [ ] 9.1 Write failing repository tests in `test_sqlalchemy_campaign_status_repository.py`: a DOOH flight that delivered 95,000.75 OTS and 4,800 impressions up to D-1 returns `delivered` 95000.7500, `delivered_impressions` 4800 and metric `ots`; a CTV flight returns its impressions in both; a DOOH row with 12 impressions and 0 OTS on D-1 still sets the latest delivery date
- [ ] 9.2 Sum the delivered volume by the channel's metric in `sqlalchemy_campaign_status_repository.py`, add `delivered` and `delivery_metric` to `FlightDeliveryFigures` and `CampaignStatusRow`, compute the ratio on `delivered`, keep pacing on `delivered_impressions` until task 10, and verify 9.1 and `test_campaign_status_service.py`

## 10. Pacing

- [ ] 10.1 Write failing tests in `backend/tests/domain/test_pacing.py`: 300,000 OTS from 2026-09-01 to 2026-09-30 at 2026-09-10 with 95,000.75 delivered is −4.99925 % and on pace; 90,000.0000 is −10 % and on pace; 89,999.5000 is −10.0005 % and under-delivering with 20 days remaining
- [ ] 10.2 Change `calculate_pacing` to take the delivered volume as `Decimal`, pass `delivered` from the status service, and verify 10.1, `test_pacing.py` and a service test that a DOOH flight with 4,800 impressions and 0 OTS is under-delivering

## 11. Margin and Month Close

- [ ] 11.1 Write failing repository tests in `test_margin_repositories.py` that `list_flights` and `open_ended_flights` return, for a DOOH flight, `delivered` 280000.5000, `delivered_impressions` 12000 and metric `ots`
- [ ] 11.2 Write failing domain tests in `test_flight_margin.py` that the closed DOOH flight of 300,000 OTS at 5.00 € has revenue 1,500.00 € and, at 1.00 € per thousand, platform cost 12.00 €, and in `test_margin_totals.py` that a line and a campaign sum `delivered` exactly (280,000.50 plus 1,499.25 is 281,499.75) and keep their one metric
- [ ] 11.3 Add `delivered` and `delivery_metric` to `FlightFacts`, `FlightEconomics`, `FlightMargin`, `MarginTotals` and `WindowDelivery`, sum them in the repositories and in `margin_totals.py`, keep the platform cost on `delivered_impressions`, and verify 11.1 and 11.2
- [ ] 11.4 Write a failing test that the grand total of `MarginQueryService` with a DOOH and a CTV campaign has null `delivery_metric`, `contracted_impressions` and `delivered`, `delivered_impressions` 210,800 and every amount summed; and that totals of impressions campaigns only are summed with metric `impressions`; implement and verify
- [ ] 11.5 Write a failing test in `test_margin_closing_service.py` that closing the DOOH flight's month freezes a platform cost of 12.00 € and that the flight reads the same `delivered`, `delivered_impressions` and metric before and after the close; verify it passes

## 12. Line Without Delivery

- [ ] 12.1 Write failing tests in `test_sqlalchemy_ingestion_target_repository.py`: a finished DOOH flight with 12,000 impressions and 0.0000 OTS is a candidate; one with 0 impressions and 0.5 OTS is not; a finished CTV flight with 0 impressions and 300.0 OTS is a candidate
- [ ] 12.2 Sum the delivered volume by the channel's metric in `find_lines_missing_delivery` and verify 12.1 and `test_missing_delivery_detection.py`

## 13. Response Schemas

- [ ] 13.1 Write failing API tests in `test_campaign_status_endpoint.py`: the DOOH row carries `contracted_impressions` 300000, `delivery_metric` `"ots"`, `delivered` `"95000.7500"` and `delivered_impressions` 4800
- [ ] 13.2 Write a failing API test in `test_campaign_status_endpoint.py` with a user holding only `trading`: the response for the DOOH row carries `delivered` `"95000.7500"` and `delivery_metric` `"ots"`, and walking every key of the response, however nested, finds no cost, revenue, rebate, platform-cost or margin field
- [ ] 13.3 Write failing API tests in `test_margin_endpoint.py`: flight, line and campaign carry `delivered` as a four-decimal string and `delivery_metric`; mixed totals carry null `delivery_metric`, `contracted_impressions` and `delivered`
- [ ] 13.4 Add the fields to `schemas/campaign_status.py` and `schemas/margin.py`, make the totals' `contracted_impressions` nullable, and verify 13.1 to 13.3 and that `test_route_protection.py` passes with `ACCESS_MATRIX` unchanged: no route is added, so no new negative case is needed beyond the existing ones of the three routes

## 14. Screens

- [ ] 14.1 Write failing Vitest tests in `frontend/tests/unit/app/status/status-page.test.tsx` that a DOOH row shows its volumes labelled «OTS» with decimals as received and a CTV row «impresiones»
- [ ] 14.2 Write failing Vitest tests in `frontend/tests/unit/features/margin/messages.test.ts` and `margin-page.test.tsx` that the legend reads «Entregado 280.000,5 de 300.000 OTS» for the DOOH flight, «… impresiones» for a CTV one, and that a totals level with a null metric shows no legend
- [ ] 14.3 Write a failing test in `frontend/tests/unit/app/campaigns/error-mapping.test.tsx` that `mixed_delivery_metrics` shows its own message
- [ ] 14.4 Update `frontend/lib/api/status.ts` and `margin.ts`, `StatusTable.tsx`, `features/margin/messages.ts` and the form's error messages, and verify 14.1 to 14.3 and the frontend suite, with the no-arithmetic test still passing

## 15. E2E with a DOOH Line

- [ ] 15.1 Write a failing check, in `e2e/support` beside `compose-project.test.mjs`, that the channel chosen by `e2e/support/campaigns.ts` is the `DEMO` one when `GET /api/masters/channels` lists `CTV`, `DEMO Channel`, `Deal`, `Directo` and `DOOH`; make the helper prefer the `DEMO` channel like `campaign-form.ts:26`, and verify the check passes, so the E2E campaigns do not move onto the CTV schedule (design.md decision 1)
- [ ] 15.2 Write failing tests in `backend/tests/scripts/test_seed_margin_demo.py` that the margin demo keeps `DEMO Channel` counted in impressions and adds one campaign on the real `DOOH` channel whose invented days carry OTS with decimals and fewer impressions than OTS, idempotently; implement it in `scripts/seed_margin_demo.py` and verify, together with `test_seed_margin_demo_states.py` and the exceptions demo tests
- [ ] 15.3 Write the E2E in `e2e/tests/status.spec.ts` and `e2e/tests/margin.spec.ts`: the DOOH demo row says «OTS» with the volume of `GET /api/campaign-status`, its margin legend says «Entregado … de … OTS», and the `DEMO Channel` rows still say «impresiones»; adjust `margin.spec.ts:68` to read `delivered` and the metric

## 16. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 16.1 Review every backend and frontend test that builds a delivery row, a flight or a margin response (`tests/fixtures/delivery_rows.py`, `delivery_data.py`, `frontend/tests/helpers/margin-data.ts`) so it carries the new fields, and that no test still names `OOH` or `Digital` as a channel; verify with `git grep -nwE "OOH|Digital" -- backend/tests backend/scripts frontend/tests e2e deploy`

## 17. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 17.1 Capture the pre-test baseline of the development database: row counts of `channels`, `daily_deliveries`, `rebate_schedules`, `campaigns` and `ingestion_exceptions`
- [ ] 17.2 Run the targeted tests of tasks 1 to 15, then the whole backend suite (`pytest`) and the frontend suite (`npm test`), recording totals, failures and runtime
- [ ] 17.3 Re-check the baseline and restore any change the tests left
- [ ] 17.4 Create `docs/reports/YYYY-MM-DD-step-17-unit-test-and-db-verification.md`; the step is complete only once it exists

## 18. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 18.1 With the stack running and a test-issuer token, call `GET /api/campaign-status` and `GET /api/margin` as `operations` and check `delivered` and `delivery_metric` on a DOOH and an impressions row, and the totals' nulls when mixed
- [ ] 18.2 Call `GET /api/campaign-status` as `trading` and check OTS are present and no money field is
- [ ] 18.3 `POST /api/campaigns` with a `DOOH` and a `Directo` line, check 422 `mixed_delivery_metrics`; post a valid `DOOH` campaign, check 201, then delete it to restore the database
- [ ] 18.4 Run `scripts.load_masters --check` on a file that changes an existing channel's metric and check the rejection names the position and writes nothing
- [ ] 18.5 Document every command and response in `docs/reports/YYYY-MM-DD-step-18-curl.md` and verify the database matches the baseline of 17.1

## 19. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 19.1 Reset the E2E data with `e2e/scripts/reset-data.sh` and run the whole Playwright suite, including the DOOH cases of task 15
- [ ] 19.2 Check in the browser that the status and margin screens label the DOOH demo in OTS and the rest in impressions, restore the data, and document the run in `docs/reports/YYYY-MM-DD-step-19-e2e.md`

## 20. Update Technical Documentation and Archive (MANDATORY)

- [ ] 20.1 Update `docs/product-description.md` (§5.3 table: `CTV` on Adform, measured in impressions, and `DOOH` measured in OTS; the PO decision at `:629` corrected to say that CTV reports are read in Adform like Display and CTV enters through the Adform ingestion; the email-intake row at `:71-77` no longer naming CTV), `docs/deploy.md` (the `delivery_metric` key of the masters file, the rejection of a changed metric and the operator `UPDATE`) and `readme.md` (data model of `channels` and `daily_deliveries`, ingestion criteria 1 and 5, margin criteria 1 and 2); verify with a read-through against the specs of this change
- [ ] 20.2 Run `openspec validate ctv-and-delivery-metric --strict`, sync the delta specs into `openspec/specs/` and archive the change, verifying the archived change and the updated main specs
