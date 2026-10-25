## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Create feature branch `feature/daily-campaign-delivery-status` from `final-project-LFMC` and verify `git status` reports it as current **(desviación: rama creada desde final-project-LFMC, no desde main)**
- [ ] 0.2 Verify `register-campaign-from-purchase-order` is applied: campaign lines and validated DSP mappings exist to ingest against

## 1. Database: Delivery Schema

- [x] 1.1 Write failing tests for the delivery model asserting exact-decimal media cost and that delivered and contracted volumes are separate fields
- [x] 1.2 Define the `daily_deliveries` model at the line-and-day grain with impressions, clicks, media cost, measurable and viewable impressions, banner size, screen and contrast `line_format`, and verify the tests from 1.1 pass
- [x] 1.3 Define `ingestion_batches` with route, source, timings, outcome and row count, and `ingestion_exceptions` with its type and external key, verified by constraint tests
- [x] 1.4 Add indexes on the DSP mapping, campaign period and delivery date, and verify with `EXPLAIN` that a period roll-up uses them rather than scanning **(partial: índice sin EXPLAIN)**
- [x] 1.5 Generate the Alembic migration with `--autogenerate`, review it by hand, and verify `upgrade head` then `downgrade base` runs clean
- [ ] 1.6 Load a synthetic set of at least 1 M delivery rows and verify a period roll-up returns within an acceptable time, recording the measurement **(deferred: carga sintética de 1 M de filas; rendimiento sin medir)**
- [x] 1.7 Widen `daily_deliveries.media_cost` to `Numeric(18,6)` with a migration, and verify with a test that a six-decimal value is stored and read back unchanged
- [x] 1.8 Add the ignored-row count to `ingestion_batches` with a migration, verified by a constraint test

## 2. Backend: Ingestion Contract (domain layer)

- [x] 2.1 Define the DSP delivery-client interface in `domain/` alongside the existing identifier-resolution method, and build an in-memory double in `tests/fixtures/`
- [x] 2.2 Write failing tests for the idempotency rule: running a range twice yields one set of rows, a restated figure supersedes, and rows outside the range are untouched
- [x] 2.3 Implement the delete-then-insert replace strategy for a line and date range inside one transaction, and verify the tests from 2.2 pass
- [x] 2.4 Write a failing test asserting a run that fails partway leaves no partially applied range, then implement the transactional boundary
- [x] 2.5 Write failing tests for the channel-authority rule: a differing `line_format` leaves the configured channel unchanged, is stored as contrast, and raises a mismatch flag
- [x] 2.6 Implement the channel-authority rule in the domain layer and verify the tests from 2.5 pass with no database involved

## 3. Backend: Pacing Calculation (domain layer)

- [x] 3.1 Write failing tests for pacing covering under-delivery beyond ten percent, over-delivery beyond ten percent, and delivery inside the threshold at the exact boundary
- [x] 3.2 Implement pacing as a pure function of contracted volume, period bounds, date and delivered volume, and verify the tests from 3.1 pass without a database
- [x] 3.3 Write failing tests for the missing-data rule: flagged when the latest delivery predates D-1, not flagged at D-1, cleared on the next ingestion
- [x] 3.4 Implement the missing-data rule and verify the tests from 3.3 pass
- [x] 3.5 Add a test documenting that the pacing function reports under-delivery for a period that has ended with nothing delivered, and keep the test for a period that has not started

## 4. Backend: Adform Connector and Ingestion Service

- [x] 4.1 Implement the Adform delivery client in `infrastructure/dsp/` behind the interface from 2.1, with authentication and pagination, verified against the sandbox **(verificado contra la cuenta real de Adform, solo lectura, con adform_smoke el 2026-10-24: 142 filas, operación succeeded)**
- [x] 4.2 Verify no credential reaches the logs or an error response, asserted by a test on the log output
- [x] 4.3 Implement the ingestion application service over the D-7 to D-1 window, writing through a bulk path rather than materialising entities, and verify memory stays bounded on a 1 M-row run **(partial: memoria verificada en el servicio con 1 M de filas y un destino contador; la escritura a PostgreSQL se verifica por trozos, no con 1 M de filas)**
- [x] 4.4 Implement batch recording for success and failure and verify a failed run leaves a batch with a failed outcome and no partial range
- [x] 4.5 Implement skipping of unmapped active lines and verify the run completes for every mapped line while reporting the skipped ones
- [x] 4.6 Create the DSP mapping from a campaign line to a real Adform identifier, checking the pair with `resolve_identifiers` and distinguishing found, unknown and unreachable, creating the mapping in all three cases, setting `validated_at` only when found, exposing it to the `operations` role only (403 without it, 401 without a token), and documenting that the stats API cannot tell a line with no delivery in 30 days from an unknown one
- [x] 4.7 Enforce one campaign line per external identifier pair and DSP with a unique constraint, and verify a second mapping to the same pair is rejected as a conflict
- [x] 4.8 Compare external identifiers as text and combine several external line items mapped to one campaign line into one record per day, verified by tests
- [x] 4.9 Ignore delivery rows without an attributed line item, counting them on the batch and not as exceptions, and fail the batch on a currency other than EUR, verified by tests
- [x] 4.10 Write failing tests against PostgreSQL for the ingestion-target query: a campaign ended three days ago is ingested, one starting tomorrow is neither ingested nor skipped, an unvalidated mapping and a mapping of another DSP are skipped and counted, and a line with several external pairs is ingested through all of them
- [x] 4.11 Implement the ingestion-target query with SQLAlchemy behind `IngestionTargetRepository` and verify the tests from 4.10 pass
- [x] 4.12 Write failing tests against PostgreSQL for the watched-campaign query: only a campaign with status `active` whose dates include D-1 is returned
- [x] 4.13 Implement the watched-campaign query behind `IngestionTargetRepository` and verify the tests from 4.12 pass
- [x] 4.14 Write a test with simulated HTTP asserting that the Adform smoke script prints no value, name, identifier or amount from a synthetic response, and makes a single request
- [x] 4.15 Implement `scripts/adform_smoke.py` (`python -m scripts.adform_smoke`), printing only the final operation status, row count, ignored rows, EUR rows, distinct pair count, the zero-impression rows with and without an attributed line item (line item above 0, EUR) and the type of each column, writing nothing to the database or disk; the PO runs it against the real account
- [x] 4.16 Mark the 1 M-row memory test as `slow`, register the marker, exclude it by default with `-m "not slow"`, and note that it runs with `pytest -m slow` and that the full verification of section 10 must include it **(run it with `pytest -m slow`; the full verification of section 10, task 10.3, includes it)**
- [x] 4.17 Make a batch's `row_count` the number of rows read from the DSP, keeping `ignored_row_count` for rows without an attributed line item and adding `zero_unmatched_row_count` for unmatched rows of zeros, verified by tests on the ingestion service

## 5. Backend: Manual Upload Route

- [ ] 5.1 Implement the spreadsheet parser in `infrastructure/spreadsheets/` behind an interface, and verify pandas and openpyxl are imported nowhere else
- [ ] 5.2 Write failing tests asserting structure is validated before content and that a malformed file fails naming file, sheet and row
- [ ] 5.3 Implement the upload endpoint validating file type and size before parsing, storing the file in S3, and verify the tests from 5.2 pass **(partial: almacenamiento en disco detrás de una interfaz, en lugar de S3)**
- [ ] 5.4 Verify an uploaded file produces delivery records indistinguishable from the API route, asserted by a test comparing both paths
- [ ] 5.5 Write a test asserting a user without `operations` receives 403 on the upload endpoint

## 6. Backend: Exceptions and Status API

- [x] 6.1 Write failing tests for unmatched delivery: an `unmatched_delivery` exception is recorded with its DSP and external pair, figures are retained per date, running the same window twice neither duplicates the exception nor its days, a resolved pair that delivers again is not reopened but its new delivery is kept, unmatched rows of zeros are counted and not recorded, and the run still stores matched rows
- [x] 6.2 Implement unmatched-delivery exception recording in the ingestion service, shared by the API and upload routes, and verify the tests from 6.1 pass
- [ ] 6.3 Write failing tests against PostgreSQL for absence by flight: a mapped line with no delivery row inside the window of a flight that ended inside the D-7 to D-1 window raises a `missing_delivery` exception identified by line and period, so does one whose rows inside the window sum to zero, delivery outside the flight's window does not count for it and is stored, a flight whose last day is after D-1 or before D-7 does not, a flight that ended before the mapping was validated does not, a line without a validated mapping does not, and evaluating twice does not duplicate it **(implementado por periodo en 8e96021; se rehace por flight en 6A.14)**
- [x] 6.4 Implement absence detection as a service method not wired to a scheduler, and the endpoints `GET /ingestion-exceptions?status=open|resolved` and `POST /ingestion-exceptions/{id}/resolve` for the `operations` role as plain `def` routes, with 404 `exception_not_found` and 409 `exception_already_resolved`, with the queue showing first and last dates, number of days and impressions and clicks totals but no cost, and verify a resolved exception leaves the open queue while remaining readable
- [ ] 6.5 Implement `GET /api/campaign-status` for the `operations` and `business` roles as a plain `def` route: one row per flight whose window contains D-1, of a campaign with status `active`, with contracted, delivered inside the window up to D-1, ratio, and pacing (expected to date, deviation, days remaining) from the pure function of 3.2; the `pacing_flag` per flight and the `missing_data_flag` per campaign repeated on each of its rows (a row of zeros counts as data received); aggregated in the database in one query; no cost field in the response, asserted by a test walking every field name; ordered by rows with any flag first, then agency, campaign and line; verified by tests listing neither finished flights, nor flights not yet started, nor campaigns that have not started **(depende de 6A.15)**
- [ ] 6.6 Implement the finance restriction so cost fields are absent from the response for a user without the role, and write a test asserting the field is missing rather than null **(deferred: el endpoint de estado del corte no devuelve campos de coste)**
- [ ] 6.7 Write tests asserting 403 for a user without `operations` on the exception queue, and 401 for a missing or invalid token on every endpoint of this change
- [x] 6.8 Generate the exceptions migration with `--autogenerate`: the types `unmatched_delivery`, `missing_delivery` and `channel_mismatch`, uniqueness per type, DSP and external pair and per line and period, `first_date`, `last_date`, `resolved_at`, `resolved_by` and the note, the child table `ingestion_exception_deliveries` unique on exception and date, and `zero_unmatched_row_count` on the batches, reviewed by hand with `test_migration_schema_sync` green and `downgrade base` clean

## 6A. Backend: Campaign Line and Flight Model

- [x] 6A.1 Write failing tests and implement the proportional split of a line's volume across flight windows in `domain/`: 100 impressions over windows of 31, 30 and 31 days, a window clipped to half a month, a single window, the tie going to the earliest month, and the property that the parts always add up to the total
- [x] 6A.2 Write failing tests and implement the generation of a line's flights from the line's dates and the campaign's periods, each window clipped to the intersection: a line starting mid-month, one ending before the campaign, one inside a single month and one of a single day
- [x] 6A.3 Write failing tests and implement the validation that a line's dates fall inside the campaign's, with its domain error mapped to 422 `line_dates_outside_campaign` by the global handlers
- [x] 6A.4 Write failing tests and implement the validation of explicit monthly volumes against the generated flights, with the errors `flight_volumes_incomplete`, `flight_volumes_mismatch` and `flight_volume_not_positive` mapped to 422 by the global handlers: matching months adding up to the total, a missing month, a repeated month, a month outside the line, a sum off by one, and a zero or negative volume
- [x] 6A.5 Generate the additive migration with `--autogenerate`: `campaign_line_periods` unique per line and period with a check of `flight_start <= flight_end`, and the nullable `campaign_id`, `line_number`, `start_date` and `end_date` on `campaign_lines` with the partial unique index on `(campaign_id, line_number)`, reviewed by hand with `test_migration_schema_sync` green and `downgrade -1` clean
- [x] 6A.6 Move the domain line to the new model: `CampaignLine` with campaign, number, dates and a list of `CampaignLineFlight` **(el `campaign_period_id` de la entidad queda como campo transitorio opcional hasta 6A.10, que lo elimina con el último código que lo lee)**
- [x] 6A.7 Write failing tests and extend the registration request schema: per line optional `start_date`, `end_date` and `monthly_volumes` (year, month, volume), with inverted dates rejected as 422 `line_dates_invalid` through the global handlers and the existing `flight_volumes_*` and `line_dates_outside_campaign` errors reused
- [x] 6A.8 Write failing tests and rewrite the registration service: one campaign line per line of the purchase order with its number, its dates (the campaign's by default) and its flights generated by the domain functions, the explicit split when `monthly_volumes` is given and the proportional one otherwise, rejecting with 422 `volume_too_small_for_flights` any split that leaves a flight at zero, validating every line before anything is written, and dropping the per-period copy loop and the placeholder period identifier
- [x] 6A.9 Write failing tests and rewrite the campaign repository to save campaign, periods, lines and flights in one transaction, resolving periods by year and month, filling the transitional `campaign_period_id` of each line with its first flight's period, and dropping the first-period `break` **(el campo transitorio de la entidad sigue hasta 6A.10, que es lo último que lo lee)**
- [x] 6A.10 Write failing tests and change the registration response and its schemas: each line with `line_number`, `start_date`, `end_date`, total volume and `flights`, without `campaign_period_id`, keeping the campaign's `periods`, and drop the line entity's transitional period field
- [ ] 6A.11 Write API tests for registration over several months: a line over three months, two lines over two months, a one-month line, lines starting mid-campaign and ending early, two formats in one month, valid and invalid explicit volumes, dates outside and inverted, a total too small, and a partial failure leaving nothing stored
- [ ] 6A.12 Write the cleanup migration that makes `campaign_id`, `line_number`, `start_date` and `end_date` mandatory and drops `campaign_lines.campaign_period_id`, failing with a clear message when a line has no `campaign_id`, verified against an empty and a dirty database
- [ ] 6A.13 Move the ingestion-target query off the line-to-period join and onto the line's campaign
- [ ] 6A.14 Rework absence by flight (task 6.3) over `campaign_line_periods`, keeping the exception identified by line and period
- [ ] 6A.15 Provide the flight-level aggregate the status endpoint (6.5) reads: contracted per flight and delivery summed inside its window, in one query

## 7. Backend: Scheduled Run

- [ ] 7.1 Implement the nightly ingestion as a container command invoked by the host scheduler, and verify a manual invocation uses the same code path
- [ ] 7.2 Verify the status view reads the last successful batch so a stale page is visibly stale, asserted by a test with a failed most-recent run **(deferred: indicador de página desactualizada)**

## 8. Frontend: Daily Status and Exception Queue

- [ ] 8.1 Implement the typed API client for status and exceptions in `lib/api/` and verify no component calls `fetch` directly
- [ ] 8.2 Write failing Vitest tests for the status table covering both flags, the contracted-versus-delivered columns and sorting by period and agency
- [ ] 8.3 Implement the status table and verify the tests from 8.2 pass
- [ ] 8.4 Verify a loaded-but-empty list renders distinctly from a pending one, asserted by a test
- [ ] 8.5 Implement the exception queue with resolution, guarded by the `operations` role, and write a test asserting what a user without the role sees
- [ ] 8.6 Verify no cost or margin column renders for a user without `finance`, asserted by a test **(deferred: el endpoint de estado del corte no devuelve campos de coste)**

## 9. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 9.1 Review every test touched by this change and update any asserting superseded behaviour
- [ ] 9.2 Verify each role-guarded endpoint added here has its negative authorisation case covered

## 10. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 10.1 Capture the pre-test database baseline for delivery, batches and exceptions
- [ ] 10.2 Run targeted unit tests for the changed modules and record passed, failed and skipped counts
- [ ] 10.3 Run the full backend and frontend suites and record totals and runtime, including the slow tests with `pytest -m slow`
- [ ] 10.4 Verify post-test database state against the baseline and restore it if anything changed
- [ ] 10.5 Create the report at `specs/daily-campaign-delivery-status/reports/YYYY-MM-DD-step-10-unit-test-and-db-verification.md`
- [ ] 10.6 Mark this step complete only once the tests pass and that report exists

## 11. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 11.1 Start the backend and verify the database connection is active
- [ ] 11.2 Trigger an ingestion run with curl, verify the batch record and the delivery written, then restore database state
- [ ] 11.3 Trigger the same range twice with curl and verify no duplicate rows result, then restore database state
- [ ] 11.4 Upload a delivery export with curl, verify the records match the API route, then restore database state
- [ ] 11.5 Test the status endpoint with curl and verify both flags appear on the campaigns that should carry them
- [ ] 11.6 Test error cases: malformed upload, unsupported file type, unreachable DSP
- [ ] 11.7 Test authorisation: no token (401), token without `operations` on upload and exceptions (403), token without `finance` receiving no cost fields
- [ ] 11.8 Verify the database matches its pre-test state and document every command and response in a report in the change folder

## 12. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 12.1 Start frontend and backend and verify the database is in a known state
- [ ] 12.2 Execute the operations flow: open the daily status, identify a flagged campaign and work an ingestion exception to resolution
- [ ] 12.3 Execute the business flow and verify no cost or margin figure is visible anywhere in it
- [ ] 12.4 Verify the loading and empty states render distinctly in the browser
- [ ] 12.5 Execute the flow as a user holding several roles and verify the interface composes from all of them
- [ ] 12.6 Clean up test data, restore database state and document the scenarios in a report in the change folder

## 13. Update Technical Documentation (MANDATORY)

- [ ] 13.1 Update `readme.md` §3 if the delivery schema diverged from the documented model
- [ ] 13.2 Record the measured roll-up timing and the indexing decision in `docs/backend-standards.md`
- [ ] 13.3 Update `.env.example` with the Adform and ingestion-window variables and verify no real value is committed
- [ ] 13.4 Verify `openspec validate daily-campaign-delivery-status` passes before archiving
