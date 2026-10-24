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

## 4. Backend: Adform Connector and Ingestion Service

- [x] 4.1 Implement the Adform delivery client in `infrastructure/dsp/` behind the interface from 2.1, with authentication and pagination, verified against the sandbox **(partial: sin sandbox: se verifica contra la cuenta real, solo lectura; los tests usan HTTP simulado y la verificación contra la cuenta real queda pendiente)**
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
- [ ] 4.14 Write a test with simulated HTTP asserting that the Adform smoke script prints no value, name, identifier or amount from a synthetic response, and makes a single request
- [ ] 4.15 Implement `scripts/adform_smoke.py` (`python -m scripts.adform_smoke`), printing only the final operation status, row count, ignored rows, EUR rows, distinct pair count and the type of each column, writing nothing to the database or disk; the PO runs it against the real account
- [ ] 4.16 Mark the 1 M-row memory test as `slow`, register the marker, exclude it by default with `-m "not slow"`, and note that it runs with `pytest -m slow` and that the full verification of section 10 must include it

## 5. Backend: Manual Upload Route

- [ ] 5.1 Implement the spreadsheet parser in `infrastructure/spreadsheets/` behind an interface, and verify pandas and openpyxl are imported nowhere else
- [ ] 5.2 Write failing tests asserting structure is validated before content and that a malformed file fails naming file, sheet and row
- [ ] 5.3 Implement the upload endpoint validating file type and size before parsing, storing the file in S3, and verify the tests from 5.2 pass **(partial: almacenamiento en disco detrás de una interfaz, en lugar de S3)**
- [ ] 5.4 Verify an uploaded file produces delivery records indistinguishable from the API route, asserted by a test comparing both paths
- [ ] 5.5 Write a test asserting a user without `operations` receives 403 on the upload endpoint

## 6. Backend: Exceptions and Status API

- [ ] 6.1 Write failing tests for unmatched delivery: an exception is recorded with its external key, figures are retained, and the run still stores matched rows
- [ ] 6.2 Implement unmatched-delivery exception recording and verify the tests from 6.1 pass
- [ ] 6.3 Write failing tests for absence: a line with no delivery in an ended period raises an exception, a running period does not
- [ ] 6.4 Implement absence detection and exception resolution, and verify a resolved exception leaves the outstanding queue while remaining readable
- [ ] 6.5 Implement the daily status endpoint returning contracted, delivered, ratio, pacing and both flags, aggregated in the database
- [ ] 6.6 Implement the finance restriction so cost fields are absent from the response for a user without the role, and write a test asserting the field is missing rather than null **(deferred: el endpoint de estado del corte no devuelve campos de coste)**
- [ ] 6.7 Write tests asserting 403 for a user without `operations` on the exception queue, and 401 for a missing or invalid token on every endpoint of this change

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
