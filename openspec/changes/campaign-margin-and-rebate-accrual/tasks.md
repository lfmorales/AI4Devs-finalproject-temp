## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/campaign-margin-and-rebate-accrual` from `main` and verify `git status` reports it as current (deviation: branch already existed; created from final-project-LFMC)
- [ ] 0.2 Verify the flights exist: every campaign line has `campaign_line_periods` rows with `flight_start`, `flight_end` and `contracted_impressions`, the line carries `sale_cpm`, and `daily_deliveries` carries impressions and media cost

## 1. Database: Rebate and Rate Schema

- [x] 1.1 Write failing tests for `rebate_schedules` asserting a nullable agency, channel and scope, a required `valid_from`, an inclusive nullable `valid_to`, and an exclusion constraint that refuses overlapping validity of the same key (an open-ended range included) while accepting back-to-back validity and different keys
- [x] 1.2 Define `rebate_schedules` and `rebate_brackets` with `Numeric` thresholds and rates, and verify the tests from 1.1 pass
- [ ] 1.3 ~~Define `rebate_accruals` keyed on holding group, nullable agency, channel and year, holding accrued and settled separately, verified by constraint tests~~ **Deferred**: nothing in this cut settles a rebate; the frozen rebate of the closed flights is the accrued amount, and the per-payment or per-year question stays open
- [x] 1.4 Define `platform_rate_settings` with its level (line, agency, campaign type, system), nullable scope keys, author, timestamp and the append-only latest-wins rule, with the system row inserted by the migration with no author, verified by tests rejecting a level whose scope key is absent and an author-less row at any other level, and by a test that a new system row changes the resolved rate without code
- [x] 1.5 Define `applied_rates` as append-only with one row per closed flight, unique on its foreign key to `campaign_line_periods`, holding schedule and step, source year, agency flag, zero reason, effective rate, counter key, position before and after, exact rebate, platform rate and closing time, and `applied_rate_brackets` for the breakdown, all `Numeric`; verify a second row for a flight is rejected and a breakdown round-trips without losing precision
- [x] 1.6 Generate the Alembic migration with `--autogenerate`, review it by hand (it creates `btree_gist` and fails with a clear message if it cannot, and its downgrade drops it only if it created it), and verify `test_migration_schema_sync`, and `upgrade head`, `downgrade -1` and `upgrade head` on a database holding data; write the requirement in `docs/deploy.md`

## 2. Domain: Margin Calculation (no database, no HTTP)

- [x] 2.1 Write failing tests for the closed-flight margin using the worked example — 726,202 contracted impressions at 5.00 € giving revenue 3,631.01 €, media cost 1,200.00 € (a placeholder), rebate 907.75 € (25 % of revenue, from 907.7525 rounded half up), platform cost 700.00 € (700,000 delivered), margin 823.26 € — and verify it fails
- [x] 2.2 Implement the flight margin in the domain layer, with each amount rounded to 2 decimals half up before the subtraction and line and campaign totals as exact sums of their flights, and verify the tests from 2.1 pass with no database involved
- [x] 2.3 Write a failing test asserting a flight's revenue uses its contracted volume when delivery falls short (726,202 contracted, 700,000 delivered, revenue still 3,631.01 €), then verify the implementation satisfies it
- [x] 2.4 Write failing tests for the running-flight pro-rating on the flight's own window — the 30-day flight with 10 elapsed days (revenue 500.00 €, rebate 100.00 €, platform 90.00 €, margin 160.00 €), a flight with zero delivery still accruing revenue, and the date of the last delivery having no effect — and implement it, asserting the result is provisional and nothing is written
- [x] 2.5 Write a failing test asserting a `Deal` line uses the identical model to a `Directo` line, and verify no channel-specific revenue branch exists
- [x] 2.6 Write a failing test asserting exact decimal arithmetic across an accumulated year, then verify no float appears in the calculation path
- [x] 2.8 Write failing tests that a flight never crosses a year (a line from 2026-12-15 to 2027-01-20 yields two flights, one per year, and none spans two months) and that a line with a closed flight and a running one sums both and is provisional; then verify they pass
- [x] 2.9 Write failing tests for the media cost of a flight as the sum of the line's deliveries between `flight_start` and `flight_end`, and for a delivery outside every flight counting nowhere; then implement it
- [x] 2.7 Write a failing test for a flight whose media cost exceeds its revenue, asserting the flight is flagged, its line and campaign count it, and no total changes, and implement the below-cost flag *(superseded by 2A.1: the flag now means a negative final margin)*

## 2A. Domain: Negative Margin, Zero Sale and Margin Percentage

- [x] 2A.1 Write failing tests for `below_cost` as a negative final margin (rounded amounts, a media cost under revenue that the rebate and the platform cost push below zero, a margin of exactly zero not flagged), adapt the tests of 2.7 that assumed media cost above revenue, and implement it in the flight and in the totals
- [x] 2A.2 Write failing tests that registration accepts a sale CPM of 0.00 with positive contracted impressions, rejects a negative CPM, and keeps rejecting contracted impressions of 0, and implement the validation
- [x] 2A.3 Write failing tests for a flight with revenue 0 (a synthetic line without a price with volume and cost: margin minus the cost, no rebate, no counter advance, `zero_sale` at flight, line and campaign, counted in the totals) and implement it
- [x] 2A.4 Write failing tests for `margin_pct` (two decimals half up, in points, null with revenue 0, at flight, line, campaign and totals, no division by zero) and implement it in the domain and the API
- [ ] 2A.5 ~~A campaign with contracted volume 0 (a zero sale with no purchase order) and delivery with no purchase cost (pixels) in the margin~~ **Deferred**: they have no contracted volume to hang a flight from; registration still refuses a volume of 0 and their delivery stays as unmatched delivery in the exception queue

## 3. Domain: Rebate Resolution Ladder

- [x] 3.1 Write failing tests for each implemented ladder step (1 to 6 and 8, with the reference date `flight_start`), asserting the step that produced the rate is recorded and that the source year is the `valid_from` year of the matched schedule
- [x] 3.2 Implement the ladder as an ordered table of match keys rather than a conditional chain, and verify the tests from 3.1 pass
- [x] 3.3 Write failing tests asserting an agency exception wins over its group's schedule, and that scope narrows before it widens
- [x] 3.4 Write failing tests asserting that a flight whose group has no schedule resolves to an explicit zero at step 8 carrying its reason (`no_schedule`, or `no_schedule_for_year` when no schedule of any group is in force on `flight_start`), distinguishable from a negotiated zero that resolves at steps 1 to 6
- [ ] 3.5 ~~Write a failing test asserting two scopes priced differently never resolve to the mean of the two~~ **Deferred**: the rebate tables are not loaded in this cut; the ladder keys on scope at steps 1 and 4 and never blends
- [ ] 3.6 ~~Write a failing test asserting a year with no schedule inherits the previous one and the result records it as inherited~~ **Deferred**: it implements ladder step 7 (the most recent earlier table), which waits for the migration of the rebate tables (8.1); until then a missing schedule falls from step 6 to the explicit 0 % of step 8

## 4. Domain: Bracket Engine and Accrual

- [x] 4.1 Write failing tests for marginal bracket application: a counter at 90,000 € receiving a flight of 30,000 € (10,000 € at 15 % and 20,000 € at 20 %, rebate 5,500 €, effective rate 18.33 %), 600,000 € over 15/20/25 % brackets cut at 100,000 and 500,000 € (120,000 €, 20.0 %), a flat 25 % on 3,631.01 € (907.7525 € exact), a flight crossing a cut by cents (counter at 99,999.50 € and a flight of 10 €), a counter exactly on a cut, the rebate reproducible from the breakdown by bracket, and the rejection of tables that do not start at 0, leave a gap or end bounded; and verify they fail
- [x] 4.2 Implement marginal bracket application on the flight's slice, applying a counter's closed flights in chronological order of `flight_start` with ties broken by flight id, and verify the tests from 4.1 pass
- [x] 4.3 Write failing tests asserting each (group, agency or none, channel, year of `flight_start`) runs an independent counter, one channel's volume never advances another's bracket, an agency exception accrues on its own counter (one per channel when it has no channel), the result does not depend on the order of the input, ties break by id, a running flight does not advance the counter and its full rebate pro-rated by the margin calculation equals the same fraction, and a flight starting on 1 January belongs to the new year
- [ ] 4.4 ~~Write failing tests for the agency carve-out: an excepted agency accrues to itself, is excluded from its group's counter, and the carve-out applies per channel~~ **Partly deferred**: the engine puts an exception's volume on the agency's own counter (4.3); deferred are the tests of sibling agencies and the restatement of counters already frozen when an exception is created or removed
- [ ] 4.5 ~~Implement counter resolution keyed on group, optional agency, channel and year, and verify the tests from 4.3 and 4.4 pass~~ **Deferred**: the counter key with its agency slot is built in 4.3; what remains is the verification against the sibling tests of 4.4
- [ ] 4.6 ~~Write failing tests for chronological attribution: a bracket crossing is forward-only, already-accrued months keep their rate, and a straddling campaign blends~~ **Deferred**: the forward-only application at closing is covered by 4.1 to 4.3; the full chronological replay it was written for is deferred with 4.7
- [ ] 4.7 ~~Implement the counter-year replay with a stable ordering tiebreak, and verify two replays of the same inputs produce identical results~~ **Deferred**: this cut applies flights forward once, at closing, and never replays a counter-year
- [ ] 4.8 ~~Write failing tests asserting a schedule change restates the year to date, a backdated correction replays it, and creating or removing an agency exception restates both sides~~ **Deferred**: restatement is deferred: a closed month does not move in this cut
- [ ] 4.9 ~~Implement restatement triggers and verify the restatement is recorded rather than applied silently~~ **Deferred**: depends on 4.8
- [ ] 4.10 ~~Measure a replay against the largest real combination (1,159,752 € in one group and channel) and record the timing~~ **Deferred**: there is no replay to measure

## 5. Domain: Platform Rate

- [x] 5.1 Write failing tests for most-specific-first resolution across line, then agency, then campaign type, then system default (1.00 €/CPM read from data), and implement it
- [x] 5.2 Write a failing test asserting the resolved rate is frozen in the flight's `applied_rates` row at closing and that changing the default afterwards does not move a closed flight *(partial: the pure part is covered in `test_platform_rate.py` — resolution is a function over received values and its result is a frozen value; freezing in `applied_rates` at closing and the closed-flight check wait for 6A, so this stays unmarked)*

## 6. Backend: Persistence, Freezing and API

- [x] 6.1 Implement the SQLAlchemy repositories behind the domain interfaces (schedules, platform rates, applied rates, the margin read) and verify no module under `domain/` imports SQLAlchemy
- [x] 6.2 Implement `applied_rates` as append-only, one row per closed flight, and verify that closing an already closed month neither adds nor updates a row
- [x] 6.3 Write an API test asserting that editing a rebate master after the month was closed leaves the margin of its flights unchanged
- [x] 6.4 Implement the margin endpoint aggregating in the database, joining `daily_deliveries` to the flight by date range, reading closed flights from `applied_rates` and calculating the others on the fly, and verify no delivery row reaches the application. The period, agency, advertiser and campaign-type roll-up endpoints are **deferred** with the roll-up view (7.4)
- [x] 6.5 Verify the total of `GET /margin` at campaign and report level is the sum of its detail, asserted by a test (the dimension roll-ups are deferred with 6.4)
- [ ] 6.6 ~~Implement Excel and CSV export and verify the exported figures match those returned by the API~~ **Deferred**: no view consumes an export in this cut and the roll-up view (7.4) is deferred
- [x] 6.7 Implement `require_roles("finance")` on every cost and margin endpoint, including the platform rate configuration endpoints
- [x] 6.8 Write tests asserting a user holding `business` or `operations` but not `finance` receives 403 on every endpoint of this change, and 401 for a missing or invalid token
- [ ] 6.9 ~~Implement the `CuratorMargin` figure as computed on demand for Deal lines, and verify it is never stored and never enters the margin~~ **Deferred**: it serves Equativ billing, not the margin Finance reads

## 6A. Backend: Monthly Closing

- [x] 6A.1 Write failing API tests for `POST /margin/closings` (year and month): it creates one `applied_rates` row per flight that ended in the month, a flight still running gets none, a month with no ended flights answers 200 with zero closed, and the response reports created and already-closed counts
- [x] 6A.2 Write failing tests that closing the same month twice neither creates nor updates a row, that closing while an earlier month of the same year has ended flights without a row is rejected with 409 `previous_month_open` naming the blocking month and writes nothing, and that a failure forced halfway through a closing leaves no row
- [x] 6A.3 Implement the closing: pass the month's flights to the engine ordered by `flight_start` then id, with opening positions from the latest frozen rows, resolve the platform rate and write the rows in one transaction under an advisory lock; verify 6A.1 and 6A.2 pass
- [x] 6A.4 Implement `require_roles("finance")` on the closing endpoint and write tests asserting 403 for `business` or `operations` without `finance` and 401 for a missing or invalid token
- [x] 6A.5 Write failing tests that the read of a closed flight returns the frozen row, that the read of a running or pending-close flight writes nothing and does not advance the counter, and that a line with one closed and one running flight returns both

- [x] 6A.6 Write a failing test with two concurrent closings of the same month and verify each flight ends with exactly one `applied_rates` row and both requests succeed
- [x] 6A.7 Write failing tests for `opening_positions` on the rebate engine: empty gives results identical to the engine without it, and an opening of 90,000 € shifts a following flight of 30,000 € to a rebate of 5,500 €
- [x] 6A.8 Write a failing test with three flights of one counter asserting that the pending-close margin equals the margin frozen by closing the month, to the cent, and that closing and reading call the same domain function

## 6B. Backend: Margin Read, Masters and Roles

- [x] 6B.1 Write failing API tests for `GET /margin`: closed, running provisional, pending close, a not-started flight absent, a line with mixed states, the year, month and campaign filters, 404 `campaign_not_found`, inactive campaigns included, decimal-string amounts, no float anywhere, the below-cost counts, and that the read writes nothing; then implement it
- [x] 6B.2 Write a failing test that changing a rebate schedule or a platform rate after a closing does not move the closed month through `GET /margin`
- [x] 6B.3 Implement the `{"code","message"}` handler for validation errors under `/margin` only, with a test that campaign registration keeps `{"detail": ...}`, and map each rebate rule code to its own message (an empty table has its own code, `bracket_table_empty`)
- [x] 6B.4 Implement `POST /margin/rebate-schedules` and `POST /margin/platform-rates`, `finance` only, the latter recording its author and time
- [x] 6B.5 Make the development seed give the test user `finance` in addition to `operations`, remove nothing, and seed one fictitious schedule and one fictitious rate (deferred: the loading of real schedules, 8.1)
- [x] 6B.6 Verify the route protection test, built from the registered routes, covers every route of this change with 401 and 403, and that an `operations` user receives no margin field
- [x] 6B.7 Write an end-to-end calculation test with the spec's examples: a closed month of 3,631.01 € revenue, 1,200.00 € media cost, 907.75 € rebate and 700.00 € platform cost gives a margin of 823.26 €

## 6C. Acceptance with the private closed-month sheet

- [x] 6C.1 Write the acceptance test of a closed month from `tests/private/mes_cerrado_directo.csv` (skipped with a clear reason if the file is absent), one line and one whole-month flight per row in its own holding group, using the same domain functions as the closing and the reads, with the per-row, aggregate and negative-margin assertions
- [x] 6C.2 Write a test that the rows left out of the comparison are exactly those with no contracted volume, and that computes their cost from the sheet's own columns to make the difference with the sheet explicit
- [x] 6C.3 Write the database case: four real rows and the synthetic line without a price are created in the test database, the month is closed with `POST /margin/closings` and `GET /margin` returns the same amounts as decimal strings, with `zero_sale` and a null `margin_pct` for the synthetic line

## 6D. Acceptance with the private in-progress-month sheet

- [x] 6D.1 Write the acceptance test of a month still running from `tests/private/mes_en_curso.csv` (skipped with a clear reason if absent): each compared row is one line with one flight of `days_oc` days from 1 October 2026, `as_of` set to the start plus `days_served` minus one, priced with the same domain functions as the closing and the reads, with the per-row (revenue, rebate and margin accrued by `days_served / days_oc`, media and platform cost as served, `margin_pct_actual`, provisional or closed) and the aggregate assertions
- [x] 6D.2 Write the test that the rows left out are exactly those with no contracted volume (pixels included) and Campaign 38 (a manual adjustment of 37.50 € in the source sheet), each with its reason, and that makes the cost and the share of the month's cost of the first group explicit from the sheet's own columns
- [ ] 6D.3 Write the database case: five lines (one running with sale, one closed, one running without a rebate schedule, one over-delivered and the line without a price), the month closed for what has ended, and `GET /margin` returning the same amounts as decimal strings, provisional where it applies and `zero_sale` on the line without a price

## 7. Frontend: Margin and Roll-up Views

- [ ] 7.1 Implement the typed API client for margin and roll-ups in `lib/api/` and verify no component calls `fetch` directly
- [ ] 7.2 Write failing Vitest tests asserting a running-flight figure, and a line or campaign that includes one, renders with its provisional label and a closed figure does not
- [ ] 7.3 Implement the margin view and verify the tests from 7.2 pass, with no monetary value recomputed client-side
- [ ] 7.4 ~~Implement the roll-up view with filtering by period, agency, advertiser and campaign type, and verify sorting and filtering work on each~~ **Deferred**: the margin view is the only view of this cut; the roll-up endpoints stay available through the API (6.4)
- [ ] 7.5 Implement the `finance` route guard and write a test asserting what a user without the role sees
- [ ] 7.6 Verify a flight with a negative margin renders as "Margen negativo" and a flight without a price as "Sin venta", that its line and campaign show the counts, and that the totals still include their true value, asserted by a test
- [ ] 7.7 ~~Verify the masters view distinguishes a group negotiated at zero from one whose rate was never loaded~~ **Deferred**: there is no masters view in this cut; the distinction is recorded in `applied_rates` (step 8 with its reason) and read from there

## 8. Data: Rebate Migration and Reconciliation

- [ ] 8.1 ~~Normalise `extraprimas 2023/2024/2026.xlsx` into `rebate_schedules` with validity ranges, each rate as a single open bracket, and verify 2025 resolves through the ladder rather than a hardcoded label~~ **Deferred**: 2025 resolves through ladder step 7, which is deferred with 3.6; schedules are created through the application and the tests
- [x] 8.2 Seed the platform rate at the system default of 1.00 €/CPM as a `platform_rate_settings` row and verify no rate is hardcoded anywhere
- [ ] 8.3 ~~Recalculate a set of closed months and reconcile line by line against Qlik Sense~~ **Deferred**: the reconciliation needs the rebate tables loaded (8.1) and a recalculation of closed months, which is itself deferred
- [ ] 8.4 ~~Classify every difference as a named known defect or an implementation error, and verify none is accepted as merely close enough~~ **Deferred**: the reconciliation needs the rebate tables loaded (8.1) and a recalculation of closed months, which is itself deferred
- [ ] 8.5 ~~Produce the reconciliation summary for Finance and Business before any figure is published~~ **Deferred**: the reconciliation needs the rebate tables loaded (8.1) and a recalculation of closed months, which is itself deferred

## 9. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 9.1 Review every test touched by this change and update any asserting superseded behaviour
- [ ] 9.2 Verify every worked example from `docs/product-description.md` §5 is encoded as a test
- [ ] 9.3 Verify each role-guarded endpoint added here has its negative authorisation case covered

## 10. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 10.1 Capture the pre-test database baseline for schedules, brackets, accruals and applied rates
- [ ] 10.2 Run targeted unit tests for the domain modules and record passed, failed and skipped counts
- [ ] 10.3 Run the full backend and frontend suites and record totals and runtime
- [ ] 10.4 Verify post-test database state against the baseline and restore it if anything changed
- [ ] 10.5 Create the report at `specs/campaign-margin-and-rebate-accrual/reports/YYYY-MM-DD-step-10-unit-test-and-db-verification.md`
- [ ] 10.6 Mark this step complete only once the tests pass and that report exists

## 11. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 11.1 Start the backend and verify the database connection is active
- [ ] 11.2 Close a month with `POST /margin/closings`, request a closed flight's margin with curl and verify the four terms against a hand-computed figure, then close it again and verify nothing changed
- [ ] 11.3 Request a running flight's margin with curl and verify it is pro-rated on its window, marked provisional and that no `applied_rates` row was written
- [ ] 11.4 Create a platform rate override with curl, verify the resolution changes, then delete it to restore database state
- [ ] 11.5 Create an agency rebate exception with curl, verify the agency's flights are priced by its own schedule, then remove it and restore database state (the counter carve-out and the restatement are deferred with 4.4 and 4.8)
- [ ] 11.6 Request a roll-up with curl and verify it agrees with the detail (export is deferred with 6.6)
- [ ] 11.7 Test authorisation: no token (401), token without `finance` on every cost and margin endpoint, including the closing endpoint (403)
- [ ] 11.8 Verify the database matches its pre-test state and document every command and response in a report in the change folder

## 12. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 12.1 Start frontend and backend and verify the database is in a known state
- [ ] 12.2 Execute the finance flow: read a campaign margin, drill down to its lines and flights (the roll-up view and export are deferred with 7.4 and 6.6)
- [ ] 12.3 Verify a running-flight figure, and its line, display the provisional label in the browser
- [ ] 12.4 Verify a user without `finance` cannot reach the margin views and sees no cost figure anywhere
- [ ] 12.5 Execute the flow as a user holding several roles and verify the interface composes from all of them
- [ ] 12.6 Clean up test data, restore database state and document the scenarios in a report in the change folder

## 13. Update Technical Documentation (MANDATORY)

- [ ] 13.1 Update `readme.md` §3 if the rebate or rate schema diverged from the documented model
- [ ] 13.2 Record the bracket thresholds actually supplied (the replay timing is deferred with 4.10) in `docs/product-description.md`
- [ ] 13.3 Resolve or restate pending item 1 of `readme.md` §3.3 once real bracket thresholds exist
- [ ] 13.4 Verify `openspec validate campaign-margin-and-rebate-accrual` passes before archiving
