## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/daily-campaign-delivery-status` from `final-project-LFMC` and verify `git status` reports it as current **(desviación: rama creada desde final-project-LFMC, no desde main)** (deviation: branch created from final-project-LFMC, not main)
- [x] 0.2 Verify `register-campaign-from-purchase-order` is applied: campaign lines and validated DSP mappings exist to ingest against

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

- [x] 4.1 Implement the Adform delivery client in `infrastructure/dsp/` behind the interface from 2.1, with authentication and pagination, verified against the sandbox **(verificado contra la cuenta real de Adform, solo lectura, con adform_smoke el 2026-10-24: 142 filas, operación succeeded)** (verified against the real Adform account, read-only, 2026-10-25: mapping, nightly command and idempotent re-run; stored delivery matches the interface export for impressions, clicks, cost, measurable and viewable)
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

- [ ] 5.1 Implement the spreadsheet parser in `infrastructure/spreadsheets/` behind an interface, and verify pandas and openpyxl are imported nowhere else **(deferred: the API route is verified against the real account; the format of the Adform export is recorded in design.md)**
- [ ] 5.2 Write failing tests asserting structure is validated before content and that a malformed file fails naming file, sheet and row **(deferred: the API route is verified against the real account; the format of the Adform export is recorded in design.md)**
- [ ] 5.3 Implement the upload endpoint validating file type and size before parsing, storing the file in S3, and verify the tests from 5.2 pass **(partial: almacenamiento en disco detrás de una interfaz, en lugar de S3)** **(deferred: the API route is verified against the real account; the format of the Adform export is recorded in design.md)**
- [ ] 5.4 Verify an uploaded file produces delivery records indistinguishable from the API route, asserted by a test comparing both paths **(deferred: the API route is verified against the real account; the format of the Adform export is recorded in design.md)**
- [ ] 5.5 Write a test asserting a user without `operations` receives 403 on the upload endpoint **(deferred: the API route is verified against the real account; the format of the Adform export is recorded in design.md)**

## 6. Backend: Exceptions and Status API

- [x] 6.1 Write failing tests for unmatched delivery: an `unmatched_delivery` exception is recorded with its DSP and external pair, figures are retained per date, running the same window twice neither duplicates the exception nor its days, a resolved pair that delivers again is not reopened but its new delivery is kept, unmatched rows of zeros are counted and not recorded, and the run still stores matched rows
- [x] 6.2 Implement unmatched-delivery exception recording in the ingestion service, shared by the API and upload routes, and verify the tests from 6.1 pass
- [x] 6.3 Write failing tests against PostgreSQL for absence by flight: a mapped line with no delivery row inside the window of a flight that ended inside the D-7 to D-1 window raises a `missing_delivery` exception identified by line and period, so does one whose rows inside the window sum to zero, delivery outside the flight's window does not count for it and is stored, a flight whose last day is after D-1 or before D-7 does not, a flight that ended before the mapping was validated does not, a line without a validated mapping does not, and evaluating twice does not duplicate it **(implementado por periodo en 8e96021; rehecho por flight en 6A.14)**
- [x] 6.4 Implement absence detection as a service method not wired to a scheduler, and the endpoints `GET /ingestion-exceptions?status=open|resolved` and `POST /ingestion-exceptions/{id}/resolve` for the `operations` role as plain `def` routes, with 404 `exception_not_found` and 409 `exception_already_resolved`, with the queue showing first and last dates, number of days and impressions and clicks totals but no cost, and verify a resolved exception leaves the open queue while remaining readable
- [x] 6.5 Implement `GET /api/campaign-status` for the `operations` and `business` roles as a plain `def` route: one row per flight whose window contains D-1, of a campaign with status `active`, with contracted, delivered inside the window up to D-1, ratio, and pacing (expected to date, deviation, days remaining) from the pure function of 3.2; the `pacing_flag` per flight and the `missing_data_flag` per campaign repeated on each of its rows (a row of zeros counts as data received); aggregated in the database in one query; no cost field in the response, asserted by a test walking every field name; ordered by rows with any flag first, then agency, campaign and line; verified by tests listing neither finished flights, nor flights not yet started, nor campaigns that have not started **(depende de 6A.15; el orden y los campos están en la spec `daily-status`)**
- [ ] 6.6 Implement the finance restriction so cost fields are absent from the response for a user without the role, and write a test asserting the field is missing rather than null **(deferred: el endpoint de estado del corte no devuelve campos de coste)**
- [x] 6.7 Write a parametrized test built from the routes registered in the application, not from a hand-written list, asserting 401 without a token and 403 without the required role for every route of this change (mappings, exceptions, status and flight preview), so that a new unprotected route fails the suite
- [x] 6.8 Generate the exceptions migration with `--autogenerate`: the types `unmatched_delivery`, `missing_delivery` and `channel_mismatch`, uniqueness per type, DSP and external pair and per line and period, `first_date`, `last_date`, `resolved_at`, `resolved_by` and the note, the child table `ingestion_exception_deliveries` unique on exception and date, and `zero_unmatched_row_count` on the batches, reviewed by hand with `test_migration_schema_sync` green and `downgrade base` clean
- [x] 6.9 Order the exception queue by `last_date` descending and then `id` descending, test first, and verify the queue spec scenario passes

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
- [x] 6A.11 Write API tests for registration over several months: a line over three months, two lines over two months, a one-month line, lines starting mid-campaign and ending early, two formats in one month, valid and invalid explicit volumes, dates outside and inverted, a total too small, and a partial failure leaving nothing stored
- [x] 6A.12 Write the final migration with `--autogenerate`: `campaign_id`, `line_number`, `start_date` and `end_date` mandatory and `campaign_lines.campaign_period_id`, its foreign key and its index dropped, failing with a message asking to recreate the development database when a line lacks `campaign_id`, with a downgrade that restores `campaign_period_id` from each line's earliest flight and fails clearly when a line has no flights; verified on a throwaway database holding a campaign with two flights, with `test_migration_schema_sync` green and the registration repository and the line entity no longer filling or holding the period
- [x] 6A.13 Write failing tests against PostgreSQL and move the ingestion-target query onto the line's own dates, with no join through periods, covering a line that ended before its campaign, one that starts mid-campaign, one outside the window, one with an unvalidated mapping and one of another DSP; the watched-campaign query depends on the campaign alone
- [x] 6A.14 Write failing tests against PostgreSQL and rework absence (task 6.3) by flight: a finished flight whose rows are zeros or missing is flagged, delivery outside its window does not count even inside another flight of the same line, a mapping validated after the flight ended and a flight still running are not evaluated, and two runs do not duplicate the exception, which stays identified by line and period
- [x] 6A.15 Provide the flight-level aggregate the status endpoint (6.5) reads: contracted per flight and delivery summed inside its window, in one query
- [x] 6A.16 Move the shared test fixtures to the new model: `insert_campaign_line` creates the campaign, a period, the line with `campaign_id`, number and dates, and its flight, and `campaign_id_of` reads it from the line, keeping their signatures

## 6B. Backend: Flight Preview

- [x] 6B.1 Write failing tests and define the request and response schemas of `POST /api/flights/preview`: campaign dates, optional line dates and a positive total in; effective line dates and flights (`period_year`, `period_month`, `flight_start`, `flight_end`, `contracted_impressions`) out
- [x] 6B.2 Write failing tests and implement the endpoint for the `operations` role as a plain `def` route that reads and writes no database, moving the line-window planning and the strict split by days into domain functions that the registration service also uses, so the rule exists once
- [x] 6B.3 Write API tests for the preview: a line inheriting three months, a line with its own dates, one month, one day, a total too small, dates outside and inverted, a zero or negative total, 401 without a token and 403 without `operations`, and that nothing is stored
- [x] 6B.4 Write a consistency test asserting that for the same input the preview's flights are identical to those returned by the registration

## 7. Backend: Scheduled Run

- [x] 7.1 Implement the nightly ingestion as `python -m scripts.run_ingestion [--date YYYY-MM-DD]`, a container command invoked by the host scheduler, using the same service as every other route, with an advisory lock and the exit codes 0 (succeeded), 1 (failed), 2 (another run holds the lock) and 3 (missing configuration), and tests for success, client failure, busy lock, missing configuration and a repeated window **(la línea de crontab de ejemplo está en el design)** (verified against the real Adform account, read-only, 2026-10-25: mapping, nightly command and idempotent re-run; stored delivery matches the interface export for impressions, clicks, cost, measurable and viewable)
- [ ] 7.2 Verify the status view reads the last successful batch so a stale page is visibly stale, asserted by a test with a failed most-recent run **(deferred: indicador de página desactualizada)**
- [x] 7.3 Calculate today and the ingestion window in the configured time zone (`Europe/Madrid` by default) in one function used by the command, the API's `get_today` and the Adform client, with tests for the change of day between 22:00 and 02:00 in Madrid and for the daylight saving changes
- [x] 7.4 Write a test with synthetic data asserting that no value, identifier, name, amount, token or DSP error text appears in what the command prints

## 8. Frontend: Daily Status and Exception Queue

- [x] 8.1 Implement the typed API client for status and exceptions in `lib/api/` (`getCampaignStatus`, `listIngestionExceptions(status)`, `resolveIngestionException(id, note)`), typed from the real OpenAPI schemas (`CampaignStatusResponse`, `IngestionExceptionResponse`, `ResolveExceptionRequest`) with `contracted_impressions` and `delivered_impressions` as distinct fields and no cost field, and verify no component calls `fetch` directly
- [x] 8.2 Write failing Vitest tests for the status page at `/status` (operations and business), over the real API client with a simulated `fetch`, covering both flags shown as text («Sin datos recibidos», «Desviación de ritmo») and not only as colour, the contracted-versus-delivered columns, ratio and deviation shown as the API returns them with percentage format and never recomputed in the browser, the server order by default and client sorting by period and by agency, a 401 leading to the session-expired page and a 403 to the access-denied page
- [x] 8.3 Implement the status table, one row per running flight (campaign, agency, line, period and window, contracted, delivered, ratio, expected, deviation, days remaining and the two flags), with accessible column headers and sort controls, and verify the tests from 8.2 pass
- [x] 8.4 Verify the loading («Cargando…»), empty («No hay campañas en curso») and error states of the status page render distinctly from each other, asserted by a test for each
- [x] 8.5 Implement the exception queue at `/exceptions` with the tabs «Abiertas» and «Resueltas», each row showing type, DSP, external pair, first and last date, days, impressions and clicks and never cost, and «Resolver» asking for an optional note and a confirmation so the row leaves «Abiertas» without reloading, with `exception_already_resolved` and `exception_not_found` shown in Spanish, an empty state distinct from loading, and write tests for success, 409, 404, 401 and what a user without the `operations` role sees (the access-denied page)
- [x] 8.7 Implement the navigation of the authenticated layout (campaigns, status, exceptions, and the existing sign-out button, moved there from the campaigns page) without decoding roles in the browser: every link is shown until a page reports a 403 from the backend, which is the source of truth, and from then on the link to that page is hidden, with tests for both behaviours
- [ ] 8.6 Verify no cost or margin column renders for a user without `finance`, asserted by a test **(deferred: el endpoint de estado del corte no devuelve campos de coste)**

## 8A. Frontend: Line Dates and Flights in the New Campaign Form

The form lets each line have its own dates and shows the monthly split (flights). The types of the preview and of the line come from the real OpenAPI schema (`/api/openapi.json`). Behaviour:

- Each line has the box «Heredar las fechas de la campaña», checked by default. Checked, neither `start_date` nor `end_date` is sent. Unchecked, a start and an end appear, validated in the Zod schema: inside the campaign's dates, with the end not before the start.
- Each line has a button «Calcular reparto», enabled only when the campaign's dates, the line's dates (own or inherited) and the total volume are valid. It calls the preview and shows a table with month, window and volume, editable, plus «Suma X de Y».
- Editing any volume turns the line into «reparto manual», with a button «Restablecer reparto proporcional». Only then is `monthly_volumes` sent. Submitting is blocked if the sum differs from the total, a volume is not positive, or the months are not exactly those of the preview.
- If, after calculating, the campaign's dates, the line's dates or the total volume change, that line's preview is invalidated and a recalculation is asked for: a stale split is never sent.
- Before registering, the preview of every line that has none is calculated silently; its `line_dates_*` and `volume_too_small_for_flights` errors are shown on that line (exact, the request is per line), and the registration is sent only if all pass.
- The registration's own 422 codes `line_dates_*`, `flight_volumes_*` and `volume_too_small_for_flights` carry no line number, so they are shown on the candidate lines (own dates for `line_dates_*`, manual split for `flight_volumes_*`, proportional split for `volume_too_small_for_flights`), saying «en alguna de estas líneas» when there are several, and at form level when there is none. Messages come from the Zod schema or a code-to-Spanish table, never from searching library text.

- [x] 8A.1 Extend the Zod schema with the optional line dates, `monthly_volumes` and the manual split rules (coverage of the preview months, positive volumes, sum equal to the total), with the Spanish messages shared with the backend codes, tests first
- [x] 8A.2 Add a typed `previewFlights` function in `lib/api/` over the real client, tests first with a simulated `fetch` (200, 422 with each code, 401 and 403), and verify no component calls `fetch`
- [x] 8A.3 Add the line date control with the inherit box, tests first
- [x] 8A.4 Add the flight editor: calculate, table, «Suma X de Y», manual mode, reset and invalidation when the inputs change, tests first
- [x] 8A.5 Submit with the two rules (dates and `monthly_volumes` only when not inherited or manual) and the silent preview of lines that have none, tests first
- [x] 8A.6 Map the backend codes to Spanish messages on the exact line (preview) or the candidate lines (registration), and at form level when there is no candidate, tests first

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

## 11A. Production Images and Composition

- [x] 11A.1 Write failing tests for `scripts/grant_roles.py` against PostgreSQL (creates the user and the requested role rows when missing, is idempotent, assigns several roles, rejects an unknown role and an empty email with exit code 2 without writing, prints no email or other value) and implement it
- [x] 11A.2 Add `backend/Dockerfile.prod`: `uv sync --frozen --no-dev`, no `tests/`, no `scripts/seed_dev_data.py`, non-root user, `run_ingestion.py` and the migrations kept, migrations never run at start
- [x] 11A.3 Add the production nginx template (80 redirects to HTTPS and leaves `/.well-known/acme-challenge/` open; 443 with certificates from a volume and `SERVER_NAME` as variable)
- [x] 11A.4 Add `docker-compose.prod.yml`: only nginx publishes ports, restart policy, health checks, log rotation, `env_file: .env`, named PostgreSQL volume, the frontend build arguments with the public server URL
- [x] 11A.5 Ignore certificates and keys in `.gitignore` and verify nothing of the kind is versioned
- [x] 11A.6 Write `docs/deploy.md` with the steps that cannot be run here: instance, security group, DNS, Certbot, `.env` with `chmod 600`, Cognito callback and sign-out URLs over HTTPS, the explicit migration step and the first user
- [x] 11A.7 Write `scripts/verify_prod_images.sh` and run it: builds the images, brings the production composition up with a temporary database and a self-signed certificate, and checks `/api/health` answers 200 over HTTPS, port 80 redirects, the backend image has no pytest, `tests/` or `seed_dev_data.py` but has `run_ingestion.py`, the container is not root, the database publishes no port, and `alembic upgrade head` applies as a separate step; ends with one `OK` or `FALLO` line

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
