## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/campaign-margin-and-rebate-accrual` from `main` and verify `git status` reports it as current (deviation: branch already existed; created from final-project-LFMC)
- [ ] 0.2 Verify the flights exist: every campaign line has `campaign_line_periods` rows with `flight_start`, `flight_end` and `contracted_impressions`, the line carries `sale_cpm`, and `daily_deliveries` carries impressions and media cost

## 1. Database: Rebate and Rate Schema

- [ ] 1.1 Write failing tests for `rebate_schedules` asserting a nullable agency, a nullable platform type, a required validity start and non-overlapping validity for the same key
- [ ] 1.2 Define `rebate_schedules` and `rebate_brackets` with `Numeric` thresholds and rates, and verify the tests from 1.1 pass
- [ ] 1.3 ~~Define `rebate_accruals` keyed on holding group, nullable agency, channel and year, holding accrued and settled separately, verified by constraint tests~~ **Deferred**: nothing in this cut settles a rebate; the frozen rebate of the closed flights is the accrued amount, and the per-payment or per-year question stays open
- [ ] 1.4 Define `platform_rate_settings` with its level (line, agency, campaign type, system), nullable scope keys, author and timestamp, verified by a test rejecting a level whose scope key is absent
- [ ] 1.5 Define `applied_rates` as append-only with one row per closed flight and a foreign key to `campaign_line_periods`, unique per flight, holding the rebate schedule and resolution step, source year, agency-exception flag, effective rebate rate, counter position before the flight, platform rate and closing time; verify by tests that a second row for the same flight is rejected
- [ ] 1.6 Generate the Alembic migration with `--autogenerate`, review it by hand, and verify `upgrade head` then `downgrade base` runs clean

## 2. Domain: Margin Calculation (no database, no HTTP)

- [x] 2.1 Write failing tests for the closed-flight margin using the worked example — 726,202 contracted impressions at 5.00 € giving revenue 3,631.01 €, media cost 1,200.00 € (a placeholder), rebate 907.75 € (25 % of revenue, from 907.7525 rounded half up), platform cost 700.00 € (700,000 delivered), margin 823.26 € — and verify it fails
- [x] 2.2 Implement the flight margin in the domain layer, with each amount rounded to 2 decimals half up before the subtraction and line and campaign totals as exact sums of their flights, and verify the tests from 2.1 pass with no database involved
- [ ] 2.3 Write a failing test asserting a flight's revenue uses its contracted volume when delivery falls short (726,202 contracted, 700,000 delivered, revenue still 3,631.01 €), then verify the implementation satisfies it
- [ ] 2.4 Write failing tests for the running-flight pro-rating on the flight's own window — the 30-day flight with 10 elapsed days (revenue 500.00 €, rebate 100.00 €, platform 90.00 €, margin 160.00 €), a flight with zero delivery still accruing revenue, and the date of the last delivery having no effect — and implement it, asserting the result is provisional and nothing is written
- [ ] 2.5 Write a failing test asserting a `Deal` line uses the identical model to a `Directo` line, and verify no channel-specific revenue branch exists
- [ ] 2.6 Write a failing test asserting exact decimal arithmetic across an accumulated year, then verify no float appears in the calculation path
- [ ] 2.8 Write failing tests that a flight never crosses a year (a line from 2026-12-15 to 2027-01-20 yields two flights, one per year, and none spans two months) and that a line with a closed flight and a running one sums both and is provisional; then verify they pass
- [ ] 2.9 Write failing tests for the media cost of a flight as the sum of the line's deliveries between `flight_start` and `flight_end`, and for a delivery outside every flight counting nowhere; then implement it
- [ ] 2.7 Write a failing test for a flight whose media cost exceeds its revenue, asserting the flight is flagged, its line and campaign count it, and no total changes, and implement the below-cost flag

## 3. Domain: Rebate Resolution Ladder

- [ ] 3.1 Write failing tests for each implemented ladder step (1 to 6 and 8, with the reference date `flight_start`), asserting the step that produced the rate is recorded
- [ ] 3.2 Implement the ladder as an ordered table of match keys rather than a conditional chain, and verify the tests from 3.1 pass
- [ ] 3.3 Write failing tests asserting an agency exception wins over its group's schedule, and that scope narrows before it widens
- [ ] 3.4 Write a failing test asserting a group with no schedule in any year resolves to an explicit zero carrying its reason, distinguishable from a negotiated zero
- [ ] 3.5 ~~Write a failing test asserting two scopes priced differently never resolve to the mean of the two~~ **Deferred**: the rebate tables are not loaded in this cut; the ladder keys on scope at steps 1 and 4 and never blends
- [ ] 3.6 ~~Write a failing test asserting a year with no schedule inherits the previous one and the result records it as inherited~~ **Deferred**: it implements ladder step 7 (the most recent earlier table), which waits for the migration of the rebate tables (8.1); until then a missing schedule falls from step 6 to the explicit 0 % of step 8

## 4. Domain: Bracket Engine and Accrual

- [ ] 4.1 Write a failing test for marginal bracket application using the worked example — a counter at 90,000 € receiving a flight of 30,000 € of revenue, 10,000 € at 15 % and 20,000 € at 20 %, a rebate of 5,500 € and an effective rate of 18.33 % — and the three-bracket year (600,000 € giving 120,000 €, 20.0 %), and verify they fail
- [ ] 4.2 Implement marginal bracket application on the flight's slice, applying a counter's closed flights in chronological order of `flight_start` with ties broken by flight id, and verify the tests from 4.1 pass
- [ ] 4.3 Write failing tests asserting each (group, channel, year of `flight_start`) runs an independent counter and that one channel's volume never advances another's bracket
- [ ] 4.4 ~~Write failing tests for the agency carve-out: an excepted agency accrues to itself, is excluded from its group's counter, and the carve-out applies per channel~~ **Deferred**: the exception replaces the group's schedule for that agency but the carve-out of the group's counter is a documented limitation of this cut
- [ ] 4.5 ~~Implement counter resolution keyed on group, optional agency, channel and year, and verify the tests from 4.3 and 4.4 pass~~ **Deferred**: it implements the agency slot of the counter, which depends on 4.4; this cut keys the counter on group, channel and year
- [ ] 4.6 ~~Write failing tests for chronological attribution: a bracket crossing is forward-only, already-accrued months keep their rate, and a straddling campaign blends~~ **Deferred**: the forward-only application at closing is covered by 4.1 to 4.3; the full chronological replay it was written for is deferred with 4.7
- [ ] 4.7 ~~Implement the counter-year replay with a stable ordering tiebreak, and verify two replays of the same inputs produce identical results~~ **Deferred**: this cut applies flights forward once, at closing, and never replays a counter-year
- [ ] 4.8 ~~Write failing tests asserting a schedule change restates the year to date, a backdated correction replays it, and creating or removing an agency exception restates both sides~~ **Deferred**: restatement is deferred: a closed month does not move in this cut
- [ ] 4.9 ~~Implement restatement triggers and verify the restatement is recorded rather than applied silently~~ **Deferred**: depends on 4.8
- [ ] 4.10 ~~Measure a replay against the largest real combination (1,159,752 € in one group and channel) and record the timing~~ **Deferred**: there is no replay to measure

## 5. Domain: Platform Rate

- [ ] 5.1 Write failing tests for most-specific-first resolution across line, then agency, then campaign type, then system default (1.00 €/CPM read from data), and implement it
- [ ] 5.2 Write a failing test asserting the resolved rate is frozen in the flight's `applied_rates` row at closing and that changing the default afterwards does not move a closed flight

## 6. Backend: Persistence, Freezing and API

- [ ] 6.1 Implement the SQLAlchemy repositories behind the domain interfaces and verify no module under `domain/` imports SQLAlchemy
- [ ] 6.2 Implement `applied_rates` as append-only, one row per closed flight, and verify that closing an already closed month neither adds nor updates a row
- [ ] 6.3 Write an API test asserting that editing a rebate master after the month was closed leaves the margin of its flights unchanged
- [ ] 6.4 Implement the margin and roll-up endpoints aggregating in the database, joining `daily_deliveries` to the flight by date range (`delivery_date` between `flight_start` and `flight_end` of a flight of the same line), reading closed flights from `applied_rates` and calculating running flights on the fly, and verify with `EXPLAIN` that they do not fetch delivery rows into the application
- [ ] 6.5 Verify a roll-up equals the sum of its underlying flight figures, asserted by a test
- [ ] 6.6 ~~Implement Excel and CSV export and verify the exported figures match those returned by the API~~ **Deferred**: no view consumes an export in this cut and the roll-up view (7.4) is deferred
- [ ] 6.7 Implement `require_roles("finance")` on every cost and margin endpoint, including the platform rate configuration endpoints
- [ ] 6.8 Write tests asserting a user holding `business` or `operations` but not `finance` receives 403 on every endpoint of this change, and 401 for a missing or invalid token
- [ ] 6.9 ~~Implement the `CuratorMargin` figure as computed on demand for Deal lines, and verify it is never stored and never enters the margin~~ **Deferred**: it serves Equativ billing, not the margin Finance reads

## 6A. Backend: Monthly Closing

- [ ] 6A.1 Write failing API tests for `POST /margin/closings` (year and month): it creates one `applied_rates` row per flight that ended in the month, a flight still running gets none, and the response reports created and already-closed counts
- [ ] 6A.2 Write failing tests that closing the same month twice neither creates nor updates a row, and that closing a month while an earlier month of the same year has ended flights without a row is rejected with 409 and writes nothing
- [ ] 6A.3 Implement the closing: resolve the ladder at `flight_start`, apply the month's flights to their counters in chronological order of `flight_start` with ties by id, resolve the platform rate and write the rows; verify 6A.1 and 6A.2 pass
- [ ] 6A.4 Implement `require_roles("finance")` on the closing endpoint and write tests asserting 403 for `business` or `operations` without `finance` and 401 for a missing or invalid token
- [ ] 6A.5 Write a failing test asserting that the GET of a closed flight reads the frozen row, that the GET of a running flight writes nothing and does not advance the counter, and that a line with one closed and one running flight returns both

## 7. Frontend: Margin and Roll-up Views

- [ ] 7.1 Implement the typed API client for margin and roll-ups in `lib/api/` and verify no component calls `fetch` directly
- [ ] 7.2 Write failing Vitest tests asserting a running-flight figure, and a line or campaign that includes one, renders with its provisional label and a closed figure does not
- [ ] 7.3 Implement the margin view and verify the tests from 7.2 pass, with no monetary value recomputed client-side
- [ ] 7.4 ~~Implement the roll-up view with filtering by period, agency, advertiser and campaign type, and verify sorting and filtering work on each~~ **Deferred**: the margin view is the only view of this cut; the roll-up endpoints stay available through the API (6.4)
- [ ] 7.5 Implement the `finance` route guard and write a test asserting what a user without the role sees
- [ ] 7.6 Verify a below-cost flight renders flagged, that its line and campaign show the count of their flights below cost, and that the totals still include its true value, asserted by a test
- [ ] 7.7 ~~Verify the masters view distinguishes a group negotiated at zero from one whose rate was never loaded~~ **Deferred**: there is no masters view in this cut; the distinction is recorded in `applied_rates` (step 8 with its reason) and read from there

## 8. Data: Rebate Migration and Reconciliation

- [ ] 8.1 ~~Normalise `extraprimas 2023/2024/2026.xlsx` into `rebate_schedules` with validity ranges, each rate as a single open bracket, and verify 2025 resolves through the ladder rather than a hardcoded label~~ **Deferred**: 2025 resolves through ladder step 7, which is deferred with 3.6; schedules are created through the application and the tests
- [ ] 8.2 Seed the platform rate at the system default of 1.00 €/CPM as a `platform_rate_settings` row and verify no rate is hardcoded anywhere
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
