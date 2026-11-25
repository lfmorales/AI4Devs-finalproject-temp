> Reports go in `docs/reports/`, as in the previous changes. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/` (design.md, decision 14).
>
> Every implementation task starts with its failing test; a task is done when that test and the suite it names pass. No Equativ package name or id taken from a real report is written in a test, a fixture or a seed: every package is invented.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Verify `git branch --show-current` reports `feature/equativ-deals` and `git status --short` is empty before the first code change

## 1. Volume Commitment on the Line (migration)

- [x] 1.1 Write failing model tests in `backend/tests/infrastructure/test_line_model_migration.py` (or a new `test_volume_commitment_column.py`) that `campaign_lines.volume_commitment` is `NOT NULL`, defaults to `committed` and refuses any value other than `committed` and `target`
- [x] 1.2 Add the column with its check and generate the Alembic migration with `--autogenerate`; review it by hand; verify `upgrade head`, `downgrade -1`, `upgrade head` on a database holding lines, that the old lines read `committed`, and the schema-sync test
- [x] 1.3 Write failing domain tests in `backend/tests/domain/test_campaign_entities.py` that `CampaignLine` carries a `VolumeCommitment` and refuses any other value; add the enum and the field, and verify
- [x] 1.4 Write failing service tests in `backend/tests/application/test_campaign_registration_service.py`: a `Deal` line registered `target` is stored `target`; a `Deal` line `committed` and a `Directo` line `target` keep what they declare; then store it through the campaign repository and verify, with `test_campaign_repository_flights.py` reading it back
- [x] 1.5 Write failing API tests in `backend/tests/api/test_campaign_registration.py`: a line without `volume_commitment`, or with `maybe`, answers 422 and creates nothing; the response carries each line's `volume_commitment`; add the field to `CampaignLineCreateRequest` and the line response, update every API test and fixture that posts a campaign, and verify the registration suites
- [x] 1.6 Make `_register_missing` in `backend/scripts/seed_margin_demo.py` (also used by `seed_exceptions_demo.py`) send `volume_commitment` `committed` explicitly, and verify `test_seed_margin_demo.py`, `test_seed_margin_demo_states.py`, `test_seed_exceptions_demo.py` and `test_seed_exceptions_demo_endpoints.py` (brought forward so that no seed breaks between commits; the Deal demo stays in 15.2)
- [x] 1.7 Task 14.1, brought forward from group 14 so that the form never posts a campaign the API refuses: write failing Vitest tests in `frontend/tests/unit/app/campaigns/` that the form shows a commitment selector per line, proposes «Objetivo» when the channel is `Deal` and «Compromiso» otherwise, keeps the user's choice when the channel changes afterwards, and sends the value shown, including when the user changes the proposal; update the Vitest tests and helpers that assert the body sent; implement it in `CreateCampaignForm.tsx` and the campaign request types; verify the frontend suite with typecheck
- [x] 1.8 Task 15.1, brought forward from group 15 so that no E2E breaks between commits: write a failing check beside `e2e/support/campaigns.test.mjs` that the body built by `registerCampaign` in `e2e/support/campaigns.ts` carries `volume_commitment` `committed`; implement it and verify the `node --test` checks of `e2e/`; `campaign-form.ts` needs no change because the form proposes «Compromiso» for the DEMO channel
- [x] 1.9 Verify the group end to end: the whole backend suite with the 38 acceptance tests, Vitest with typecheck, `node --test` of `e2e/` and of the root scripts, and the Playwright suite on clean data (42 tests) on the stack of this worktree at the new Alembic head

## 2. Delivery Amounts (migration)

- [x] 2.1 Write failing value-object tests in `backend/tests/domain/test_delivery_value_objects.py` that `DspDeliveryRow` and `DailyDelivery` carry `buyer_spend`, `reported_revenue`, `third_party_data_cost` and `audience_data_cost` as `Decimal` and refuse a `float`; give `tests/fixtures/delivery_rows.py` and `delivery_data.py` zero defaults
- [x] 2.2 Write failing tests in `backend/tests/domain/test_delivery_combination.py` that two rows of one line and day with reported revenues of 271.1632 and 50.30080 combine into 321.464000, and the other three amounts likewise; implement in `_from_row` and `_add` and verify
- [x] 2.3 Write failing model tests in `backend/tests/infrastructure/test_delivery_models.py` that the four columns are `Numeric(18,6) NOT NULL DEFAULT 0`, and a repository test in `test_sqlalchemy_delivery_repository.py` that an Equativ day of 338.954 spend and 271.1632 revenue reads back exactly and an Adform day reads zeros
- [x] 2.4 Add the columns and generate the Alembic migration; review it; verify `upgrade head`, `downgrade -1`, `upgrade head` on a database holding delivery rows, that old rows read zero in the four, and the schema-sync test; write the four fields in `sqlalchemy_delivery_repository.py` and verify 2.3

## 3. Equativ Client

- [x] 3.0 Write a failing test in `backend/tests/test_no_real_equativ_calls.py` that a real `httpx` request (sync and async) to `https://demand-api.eqtv.io/…` or `https://oauth.smartadserverapis.com/…` fails at once with an error naming the host, while a request through `httpx.MockTransport` to the same URL is served; add the autouse fixture to `backend/tests/conftest.py` (design.md decision 13) and verify, together with the whole backend suite still passing
- [x] 3.1 Write `backend/tests/fixtures/fake_equativ.py`: an `httpx.MockTransport` serving the token, `POST /async-report`, `GET /async-report/{id}/executions` and the paginated `GET /async-report/{id}/preview` from invented rows, recording every request
- [x] 3.2 Write failing tests in `backend/tests/infrastructure/test_equativ_delivery_client.py` that one run for 2026-11-17..2026-11-23 sends one token request and one report with `startDate` `2026-11-17T00:00:00.000Z`, `endDate` `2026-11-24T00:00:00.000Z`, `timezone` `Etc/UTC`, `useCaseId` `RTB`, the three dimensions and eight metrics of the spec, empty filters, and no `scheduling` or `postProcessingConfiguration` key
- [x] 3.3 Write failing tests for the wait: `PubSubPublishSuccessful` then `PostProcessingSuccessful` reads the preview after the second answer; a failed execution status raises `DspReportFailedError`; no final status within the timeout raises `DspReportTimeoutError`; poll interval and timeout injected so no test sleeps
- [x] 3.4 Write failing tests for the preview: 238 rows in pages of 100, 100 and 38 are all yielded; pages that yield fewer rows than `totalRows`, or a preview not `READY`, raise `DspResponseFormatError`; the `downloadUrl` is never requested
- [x] 3.5 Write failing tests for a row: the worked row of the spec (2026-11-19, invented package `900000001`, 61,628 impressions, spend 338.954, revenue 271.1632) gives the pair (`900000001`, `900000001`), the date, the counts, exact decimals and a zero media cost, measurable impressions and OTS; package `0` or empty gives `key=None`; `n/a` in a metric, an empty cell or a missing `videoComplete` column raises `DspResponseFormatError` naming the column and not the value
- [x] 3.6 Implement `backend/app/infrastructure/dsp/equativ_delivery_client.py` (design.md decisions 3 and 4) returning the report id for the batch source, add `equativ_client_id` and `equativ_client_secret` to the settings as optional values, with a test in `backend/tests/test_config.py` that the settings load and the API starts with neither set; verify 3.2 to 3.5
- [x] 3.7 Write a failing test, beside `test_adform_credentials_not_leaked.py`, that no error, log line or `repr` of the Equativ client carries the client secret or the token; make it pass

## 4. The Nightly Command Takes a DSP

- [x] 4.1 Write failing tests in `backend/tests/scripts/test_run_ingestion.py`: without `--dsp` the run ingests Adform exactly as today; `--dsp Equativ` ingests only Equativ lines from the fake Equativ client and records the DSP Equativ, the route `api`, the window and the report id as source; an Equativ run that fails after its report was created leaves a failed batch that names the report as its source; `--dsp Displayce`, an unknown name or missing Equativ credentials exit 3 with no batch
- [x] 4.2 Write failing tests that two runs of one DSP never overlap (exit 2) and that an Equativ run proceeds while an Adform run holds its lock
- [x] 4.3 Write failing tests with an injected clock that an Equativ run started at 05:59 UTC ingests and prints `absences: skipped, before 06:00 UTC`, and one started at 06:00 UTC detects absence with its batch's id; an Adform run is unaffected by the hour
- [x] 4.4 Write failing tests in `test_run_ingestion_range.py` that `--dsp Equativ --from 2026-11-01 --to 2026-11-23` makes one report from 2026-11-01 00:00 UTC to 2026-11-24 00:00 UTC and skips absence
- [x] 4.5 Implement `--dsp`, the client map, the per-DSP advisory lock and the 06:00 UTC rule in `scripts/run_ingestion.py` (design.md decision 6), and the recording of the report id as the batch source as soon as the report is created, in its own transaction (design.md decision 3), and verify 4.1 to 4.4 and `test_run_ingestion_output.py` (counts only, never an identifier)

## 5. Catalogue, Mapping Check and Linking for Equativ

- [x] 5.1 Write a failing test in `backend/tests/infrastructure/test_ingestion_service_postgres.py` that an Equativ run fills one catalogue row per package with the name in both names, no line dates and its seen dates, keeps a name with a zero-width space as received, and fills it with no Equativ mapping at all
- [x] 5.2 Write failing tests in `backend/tests/application/test_dsp_mapping_service.py`: a mapping of a line on Equativ with `900000001` in both ids is created with `validated_at` set and the outcome `user_validated`, asking no client and no catalogue; the same when the package is not in the catalogue, with `last_impressions_date` null; two different ids, a non-digit id, `0` or an id with a leading zero such as `0900000001` raise the error behind `invalid_equativ_package` and store nothing; an Adform mapping is checked with Adform exactly as before
- [x] 5.3 Write failing API tests in `backend/tests/api/test_dsp_mapping_endpoint.py`: the Equativ mapping answers 201 with `validation` `user_validated`; the malformed pair, `0` and `0900000001` answer 422 `invalid_equativ_package`; a user without `operations` gets 403 and no token 401 (existing negative cases, run for a line on Equativ)
- [x] 5.4 Implement the user-validated set in `DspMappingService` and `providers.py`, the new `IdentifierCheck` value and the error mapping (design.md decision 6b), and verify 5.2 and 5.3
- [x] 5.5 Write a failing test in `backend/tests/application/test_exception_linking_service.py` that an unmatched Equativ exception links to a line on Equativ, validated without asking Equativ, and that linking it to an Adform line answers `line_dsp_mismatch`; verify it passes (no code change expected)

## 6. Lines Without Delivery on Equativ

- [x] 6.1 Write failing tests in `backend/tests/infrastructure/test_missing_delivery_candidates.py`: a target line on Equativ with a validated Equativ mapping and no row in a flight that ended inside the window is a candidate for the Equativ DSP; a line delivering on some days of the flight is not; an Adform line is never a candidate of an Equativ check and an Equativ line never of an Adform one
- [x] 6.2 Write a failing test in `backend/tests/application/test_missing_delivery_detection.py` that the exception is recorded with the Equativ batch
- [x] 6.3 Write a failing end-to-end service test, through `run_ingestion --dsp Equativ` with the fake Equativ client, of the scenario «A Deal that never receives bids»: a target `Deal` line mapped on 2026-11-01 by writing `900000001`, a package that appears in no report and no catalogue row, a flight from 2026-11-01 to 2026-11-15 and a run started at 06:15 UTC on 2026-11-18 record one `missing_delivery` exception for that line and period, and the same for a line mapped to a well-formed id that names no package (`900000009`) while the report carries other packages; verify 6.1 to 6.3 pass with no change to the absence query

## 7. Margin of a Target Flight (domain)

- [x] 7.1 Write failing tests in `backend/tests/domain/test_flight_margin.py` for the worked example: a closed target flight with a target of 1,000,000 at 5.00 €, 1,100,000 served, reported revenue 4,400.00 €, spend 5,500.00 €, a flat 10 % rebate amount on its gross and a platform rate of 1.00 € gives revenue 4,400.00, media cost 0.00, gross 5,500.00, rebate 550.00, platform 1,100.00, margin 2,750.00 and 62.50 %
- [x] 7.2 Write failing tests: a running target flight at `as_of` 2026-11-10 with 400,000 served and 1,600.00 € reported earns 1,600.00 with rebate 200.00 and platform 400.00, not pro-rated, provisional; a target flight with no delivery earns 0.00 everywhere; a target flight with CPM 0.00, 10,000 served and 40.00 € reported has gross and rebate 0.00, margin 30.00 and `zero_sale`; a committed flight's figures are unchanged
- [x] 7.3 Write failing tests for the flags: gross 5,500.00 vs spend 5,500.00 not flagged; spend 6,050.00 flagged; spend 5,000.00 with gross 5,050.00 not flagged and 5,050.01 flagged; spend 0 with gross above 0 flagged; an audience data cost of 1.25 flags `data_cost_reported` and leaves the margin unchanged; a committed flight has no gross
- [x] 7.4 Add `VolumeCommitment`, `reported_revenue`, `buyer_spend` and `data_cost` to `FlightEconomics` and `FlightFacts`, the new fields to `FlightMargin`, the branch and `rebate_base` to `flight_margin.py` and `GROSS_TOLERANCE` (design.md decision 7); verify 7.1 to 7.3 and that `test_margin_model_integrity.py` still passes unchanged except the test at `:69`, rewritten to assert that a `Deal` and a `Directo` flight with the same commitment and figures have the same margin. The new fields of `FlightFacts` are required, with no default in the domain; until 10.3 the two places of `sqlalchemy_margin_repositories.py` that build it pass `VolumeCommitment.COMMITTED` and zeros explicitly, under a comment carrying `pendiente-10.3`, so every flight is still priced as committed, as before this change. A test checks that `rebate_base` is the contracted revenue of a committed flight and the gross of a target one. Before and after the code, tens of thousands of random committed flights, with reported revenue, buyer's spend and data costs filled at random, give the same status, amounts, flags, days and volumes as `HEAD`, and so do their line and campaign totals
- [x] 7.5 Write failing tests in `backend/tests/domain/test_flight_delivery.py` that `deliveries_in_window` sums the four amounts inside the window; implement in `WindowDelivery` and verify

## 8. Rebate Base of a Target Flight

- [x] 8.1 Write failing tests in `backend/tests/domain/test_priced_flights.py`: the worked example's rebate is 550.00 at a flat 10 % and its `position_after` is the position before plus 5,500.00 on the `Deal` counter; a counter at 95,000 € with brackets of 10 % up to 100,000 € and 15 % above charges a target flight of 10,000 € gross 1,250 €; a running target flight is priced on its gross to date and does not advance the counter
- [x] 8.2 Pass `rebate_base(facts)` to `RebateFlight.revenue` in `priced_flights.py` and verify 8.1 with `test_rebate_counters.py` and `test_rebate_opening_positions.py` unchanged

## 9. Totals

- [x] 9.1 Write failing tests in `backend/tests/domain/test_margin_totals.py`: a line and a campaign sum the gross of their target flights exactly and carry null when they have none; they count `gross_differs_count` and `data_cost_count`; a campaign with a target and a committed line carries a null commitment, one with only target lines carries `target`
- [x] 9.2 Implement in `margin_totals.py` and verify 9.1 and the float-free guards of `test_margin_model_integrity.py`
- [x] 9.3 Write a failing test in `backend/tests/domain/test_margin_totals.py` that the totals over a campaign whose metric is null, because its lines mix OTS and impressions, and a campaign counted in OTS carry `delivery_metric`, `contracted_impressions` and `delivered` null, not `ots` with the OTS campaign's sums (corrects `2026-11-20-ctv-and-delivery-metric` to meet its own requirement)
- [x] 9.4 In `total_lines`, count a level below with flights and a null metric as a mix, as the commitment already does, and a level below with no flights as nothing; verify 9.3 and that a random comparison against `HEAD` changes only totals that include a level below with a null metric, every one of them to null

## 10. Margin Repositories

- [x] 10.1 Merge the two flight queries of `sqlalchemy_margin_repositories.py` (`open_ended_flights` and `list_flights`) into one builder without changing behaviour; verify `test_margin_repositories.py`, `test_margin_query_delivery_metric.py` and `test_margin_closing_service.py` pass unchanged
- [x] 10.2 Write failing tests in `test_margin_repositories.py` that both methods return, for a target flight on Equativ, its commitment and the sums of reported revenue, buyer's spend and data costs inside its window, and zeros for an Adform flight
- [x] 10.3 Add the commitment and the sums to the builder, replacing the explicit `VolumeCommitment.COMMITTED` and zeros left by 7.4, and verify 10.2 with a test that reads from the database a target line with amounts and checks the repository returns `VolumeCommitment.TARGET` and its real reported revenue, not `COMMITTED` nor zeros; `git grep pendiente-10.3 -- backend` returns nothing (this file names the marker, so it is left out)

## 11. Closing (migration)

- [x] 11.1 Write failing model tests in `backend/tests/infrastructure/test_margin_schema.py` that `applied_rates.revenue_amount` and `rebate_base_amount` are `Numeric(24,12)`, nullable, and both null or both set
- [x] 11.2 Add the columns and their check and generate the Alembic migration; review it; verify `upgrade head`, `downgrade -1`, `upgrade head` on a database holding `applied_rates` rows and the schema-sync test
- [x] 11.3 Write failing tests in `test_margin_closing_service.py`: closing the worked example's month writes a revenue of 4,400.00 and a base of 5,500.00 on its row and none on a committed flight's row; after the day's reported revenue is restated and re-ingested, the closed flight reads the frozen revenue, gross and rebate
- [x] 11.4 Write failing tests: November with a target flight on Equativ and the latest succeeded Equativ batch ending 2026-11-29 raises `MonthDeliveryNotLoadedError` naming the month and Equativ, writing nothing; a succeeded Equativ batch whose window includes 2026-11-30 unblocks it; a failed Equativ batch or a succeeded Adform batch does not; a month of committed flights closes as before; `previous_month_open` is still reported first
- [x] 11.5 Add `gross_revenue: Decimal | None` to `FlightEconomics`, required with no default in the domain (`None` computes it from the served impressions; `priced_flights` passes `None`), with domain tests that a given gross is the flight's gross and the base of its flag; implement the freeze in `save`, the frozen read in `_margin_from_frozen` (frozen revenue as `reported_revenue`, frozen base as `gross_revenue`) and the check in `MarginClosingService` (design.md decisions 7 and 9); verify 11.3 and 11.4, `test_margin_closing_concurrency.py`, an end-to-end test in which Equativ restates a day of the closed month changing its impressions and its reported revenue and the closed flight keeps its revenue, gross and rebate while its gross flag may change, and a random comparison against `HEAD` in which committed flights and target flights that are not closed, with `gross_revenue=None`, give exactly the same results
- [x] 11.6 Write a failing API test in `backend/tests/api/test_margin_closings_endpoint.py` that the blocked closing answers 409 `{"code": "month_delivery_not_loaded", "message": …}`; map the error in `presentation/errors.py` and verify; verify the existing negative cases of `POST /margin/closings` (a user holding neither `operations` nor `finance` gets 403, no token gets 401) still pass

## 12. Daily Status

- [x] 12.1 Write failing tests in `backend/tests/domain/test_pacing.py` for `pacing_flag`: a target flight at +20 % is `over_delivering` and not flagged; at −15 % it is flagged; a committed flight at +20 % is flagged
- [x] 12.2 Write failing repository tests in `test_sqlalchemy_campaign_status_repository.py` that each figure carries its line's commitment, and service tests in `test_campaign_status_service.py` that the target row at +20 % has no `pacing_flag` and does not sort among the flagged rows
- [x] 12.3 Implement `pacing_flag` in `pacing.py`, the commitment in `FlightDeliveryFigures`, `CampaignStatusRow` and the repository, and verify 12.1 and 12.2

## 13. Response Schemas

- [x] 13.1 Write failing API tests in `test_campaign_status_endpoint.py` that every row carries `volume_commitment`, and that a user holding only `trading` receives it and, walking every key however nested, no cost, revenue, rebate, spend, gross or margin field
- [x] 13.2 Write failing API tests in `test_margin_endpoint.py` (or a new `test_margin_target_flights.py`): the worked example's flight carries `volume_commitment` `target`, `revenue` `"4400.00"`, `contracted_revenue` `"5000.00"`, `gross_revenue` `"5500.00"`, `margin` `"2750.00"` and `margin_pct` 62.50; a committed flight has `gross_revenue` null; line, campaign and totals carry the summed gross, the shared or null commitment and the two counts
- [x] 13.3 Add the fields to `schemas/campaign_status.py` and `schemas/margin.py`, and verify 13.1, 13.2 and that `test_route_protection.py` passes with `ACCESS_MATRIX` unchanged: no route is added, so no new negative case is needed beyond the existing ones of the three routes

## 14. Screens

- [x] 14.1 (Brought forward to group 1 as task 1.7: nothing left to do here.) Write failing Vitest tests in `frontend/tests/unit/app/campaigns/` that the form shows a commitment selector per line, proposes «Objetivo» when the channel is `Deal` and «Compromiso» otherwise, keeps the user's choice when the channel changes afterwards, and sends the value shown
- [x] 14.2 Write failing Vitest tests in `frontend/tests/unit/app/status/status-page.test.tsx` that a target row labels its volume «Objetivo» and shows no pacing tag above its target
- [x] 14.3 Write failing Vitest tests in `frontend/tests/unit/features/margin/` that a target flight shows «Venta objetivo», a «Bruto» column with the API's gross, and the tags «Bruto distinto del gasto» and «Coste de datos» where raised; a committed flight shows «Venta contratada» and an empty gross
- [x] 14.4 Write failing Vitest tests in `frontend/tests/unit/app/catalogue/` that, for a line on Equativ without a mapping, operations can write a package id, the request sends it as both identifiers, the screen shows the mapping as validated by the user, the Equativ packages of the catalogue are suggested by name and id, a package not suggested is still accepted, and `invalid_equativ_package` shows its Spanish message beside the field
- [x] 14.5 Write a failing test that the closing maps `month_delivery_not_loaded` to a Spanish message naming the month and the DSP
- [x] 14.6 Update (`campaigns.ts` and the form's commitment selector were done in task 1.7) `frontend/lib/api/campaigns.ts`, `status.ts`, `margin.ts` and `dsp-catalog.ts`, `CreateCampaignForm.tsx`, the catalogue screen, `StatusTable.tsx`, `MarginTree.tsx`, `Figures.tsx` and the closing messages; verify 14.1 to 14.5, the frontend suite and the no-arithmetic test

## 15. Demo Data and E2E

- [x] 15.1 (Brought forward to group 1 as task 1.8: nothing left to do here.) Update `e2e/support/campaigns.ts` and `campaign-form.ts` to send `volume_commitment`, with a check beside `campaigns.test.mjs`; verify the existing E2E helpers' checks pass
- [x] 15.2 Write failing tests in `backend/tests/scripts/test_seed_margin_demo.py` that the demo adds, idempotently, a Deal campaign with one target line on Equativ, a validated Equativ mapping on an invented package and invented deliveries with the four amounts, whose closed month reproduces the worked example and whose running month delivers above its target; implement in `scripts/seed_margin_demo.py` and verify with `test_seed_margin_demo_states.py`
- [x] 15.3 Write the E2E in `e2e/tests/campaign.spec.ts`, `status.spec.ts` and `margin.spec.ts`: choosing `Deal` proposes «Objetivo» and the campaign registers with it; the Deal demo's running row says «Objetivo» with no pacing tag although above target; its closed flight shows «Venta objetivo», «Bruto» and the margin of `GET /api/margin`

## 16. Review and Update Existing Unit Tests (MANDATORY)

- [x] 16.1 Review every backend and frontend test that builds a line, a delivery row, a flight, a margin response or a registration request (`tests/fixtures/*`, `frontend/tests/helpers/margin-data.ts`) so it carries the new fields; review the tests whose meaning changed (`test_margin_model_integrity.py:69`, `test_pacing.py` over-delivery cases, the margin-calculation scenario «Every platform type uses the same model»); verify with `git grep -n "volume_commitment" -- backend/tests frontend/tests e2e` that every registration path sends it

## 17. Run Unit Tests and Verify Database State (MANDATORY)

- [x] 17.1 Capture the pre-test baseline of the development database: row counts of `campaign_lines`, `daily_deliveries`, `dsp_catalog_lines`, `dsp_mappings`, `ingestion_batches`, `ingestion_exceptions` and `applied_rates`
- [x] 17.2 Run the targeted tests of tasks 1 to 15, then the whole backend suite (`pytest`), mypy on the touched files as `docs/base-standards.md` §4 says, and the frontend suite (`npm test`), recording totals, failures and runtime
- [x] 17.3 Re-check the baseline and restore any change the tests left
- [x] 17.4 Create `docs/reports/YYYY-MM-DD-step-17-unit-test-and-db-verification.md`; the step is complete only once it exists

## 18. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 18.1 With the stack running and a test-issuer token, `POST /api/campaigns` without `volume_commitment` and check 422; post a valid campaign with a target `Deal` line, check 201 and its `volume_commitment`, then delete it to restore the database
- [x] 18.2 `POST /api/campaign-lines/{id}/dsp-mappings` for a line on Equativ with `900000001` in both ids and check 201 with `validation` `user_validated`; with two different ids check 422 `invalid_equativ_package`; as `business` check 403; then delete the mapping to restore the database
- [x] 18.3 Call `GET /api/campaign-status` as `operations` and as `trading` and check `volume_commitment` on the Deal demo row, no pacing flag above target, and no money field for `trading`
- [x] 18.4 Call `GET /api/margin` as `operations` and check the Deal demo's revenue, gross, flags and counts; as `business` check 403
- [x] 18.5 `POST /api/margin/closings` for a month whose target flight lacks its last day and check 409 `month_delivery_not_loaded` with nothing written; as `trading` check 403
- [x] 18.6 Run `python -m scripts.run_ingestion --dsp Equativ` once against the real API with the configured credentials, check exit 0 and that the output shows only counts, then restore the development database to the baseline of 17.1 (delete the batch, its rows, catalogue rows and exceptions it created)
- [x] 18.7 Document every command and response in `docs/reports/YYYY-MM-DD-step-18-curl.md`, with no package name, package id, amount or token, and verify the database matches the baseline of 17.1

## 19. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [x] 19.1 Reset the E2E data with `e2e/scripts/reset-data.sh` and run the whole Playwright suite, including the cases of task 15
- [x] 19.2 Check in the browser the campaign form, the status and the margin of the Deal demo, restore the data, and document the run in `docs/reports/YYYY-MM-DD-step-19-e2e.md`

## 20. Update Technical Documentation (MANDATORY)

- [x] 20.1 Update `docs/deploy.md` (the Equativ credentials only in the instance's `.env` with `chmod 600`, never in the repository, optional for the API, required only by `--dsp Equativ`; mapping a Deal line by writing its package id, and that a wrong id surfaces as a line without delivery; the crontab line at 06:15 UTC with `--dsp Equativ`, the first history load with `--from/--to`, that each run leaves one report in the Equativ account, the EUR assumption of the company currency) and `.env.example` (`EQUATIV_CLIENT_ID`, `EQUATIV_CLIENT_SECRET` with no real value)
- [x] 20.2 Update `readme.md` (data model of `campaign_lines`, `daily_deliveries` and `applied_rates`; the ingestion criteria for Equativ; the margin criteria for target lines; the examples of the registration, status and margin responses; the error `month_delivery_not_loaded`; the figures and the E2E flows table of §2.6)
- [x] 20.3 Check that `openspec/config.yaml` and `docs/product-description.md`, both revised with this specification (the revenue invariant, §4, §5 and its introduction, §5.1, §5.3, §5.5, §6 and §8), still agree with the specs after the implementation; verify with a read-through against the specs of this change
