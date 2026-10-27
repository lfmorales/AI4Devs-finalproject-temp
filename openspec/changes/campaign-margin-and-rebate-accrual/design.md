## Context

See `proposal.md` — Why. This is the change the product exists for: the margin calculation *is* the product, and every other change feeds it. It is also the one where a wrong number is invisible until someone reconciles a year of data, which is why `docs/backend-standards.md` requires the economic model to live in a domain layer with no infrastructure dependencies.

Two facts shape the design. The rebate is a **tiered annual accrual attributed chronologically**, so a flight's rate depends on everything accrued before it. And the model of campaign lines changed in `daily-campaign-delivery-status`: a line hangs from its campaign with its own dates, and its months are **flights** (`campaign_line_periods`). Every figure in this change is computed on a flight.

## Goals / Non-Goals

**Goals**

- The whole economic model unit-testable with no database, no HTTP server and no DSP.
- Every closed figure traceable to the rate that produced it and the reason that rate applied, and immune to later edits of a master.
- A running month visible as a provisional accrual without writing anything.

**Non-Goals**

- Immutable month-end snapshots and a Finance-facing rate editor — phase 2.
- Recalculating a closed month on purpose, restating a year after a schedule change, and replaying a counter chronologically. Deferred (see Cut).
- Performance work on delivery aggregation; that is owned by the delivery change.

## Decisions

**The flight is the unit of calculation.** A flight is `campaign_line_periods`: line × calendar month, with `flight_start`, `flight_end` (the intersection of the month with the line's dates) and its own `contracted_impressions`. The margin of a line is the sum of its flights; the margin of a campaign is the sum of its lines. A flight lies inside one calendar month, so it can never cross a year; a test proves it. The spec says "flight" wherever the earlier text said "period". `campaign_periods` stays the campaign's calendar for billing and monthly close and takes no part in the calculation, except as the grouping key of the period roll-up.

**Revenue is the flight's contracted volume times the line's CPM.** `revenue = flight.contracted_impressions / 1000 × line.sale_cpm`. It does not read the purchase order version, which may be null, and never reads delivery.

**A running flight is pro-rated on its own window and writes nothing.** The calculation receives a date `as_of`, which is D-1: the last day whose delivery is complete, and the last day counted. It is a parameter of the domain, never read from the clock inside it. A flight is **closed** when `flight_end <= as_of`, **not started** when `flight_start > as_of` and **running** otherwise. A running flight has `elapsed_days = min(as_of, flight_end) − flight_start + 1` and `total_days = flight_end − flight_start + 1`, both ends included; revenue and rebate are multiplied by `elapsed_days / total_days` and rounded afterwards. A not-started flight has no margin: no amount is computed and it contributes to no total. It does not use the date of the last delivery. A running figure is labelled provisional, writes no `applied_rates` row and does not advance the counter: its rebate is computed against the counter position given by the frozen flights, as a read.

**Media cost is the sum of `daily_deliveries.media_cost` of the line between `flight_start` and `flight_end`.** It is the Adform `Cost` column, which already includes Adform's additional costs; no other media cost exists. A delivery outside every flight of its line is stored by ingestion but counts toward no flight.

**Platform cost is the line's delivered impressions in the flight window, divided by 1000, times the rate in force.** The rate resolves line, then agency, then campaign type, then system. The system value is 1.00 €/CPM and is a row of `platform_rate_settings`, never a constant in code.

**Rounding is per amount, half up, before subtracting.** Revenue, media cost, rebate and platform cost of a flight are each rounded to 2 decimals with `ROUND_HALF_UP`. The margin of the flight is the subtraction of the rounded amounts. A line or campaign total is the exact sum of its flights' rounded amounts, so a total never differs from its detail. Intermediate values (a pro-rated amount before its rounding, a bracket slice) stay unrounded.

**The rebate counter is per (holding group, agency or none, channel, year of `flight_start`).** The agency slot is filled only when the resolved schedule is an agency exception, so a flight accrues on the counter of the schedule that priced it; the key is derived from the resolution and nothing else, which keeps the function pure. An exception without a channel covers every channel and has one counter of that agency per channel. The year is always the year of `flight_start`. Closed flights are applied to a counter in chronological order of `flight_start`, ties broken by flight id; the result does not depend on the order of the input. The tiebreak makes the result reproducible; marginal brackets are order-invariant in aggregate, so only an individual flight's rate depends on it. `applied_rates` stores the counter position before the flight, so the bracket slice can be reproduced from the frozen row alone. A running flight computes its rebate on its **full** revenue from the position after all closed flights, without advancing the counter; the margin calculation pro-rates that rebate by elapsed days. Consequence, accepted: a closed flight read before its month is closed takes its position from the closed flights only, so it can differ from the position it is frozen with if a running flight of the same counter started earlier.

**The agency exception replaces the group's schedule for that agency and moves its volume to the agency's own counter.** The deferred part is the restatement: creating or removing an exception mid-year does not rewrite counters already frozen, and the sibling-agency behaviour is not tested in this cut (4.4, 4.8). That is the documented limitation.

**`applied_rates` is one append-only row per closed flight.** It has a foreign key to the flight and holds the rebate schedule and step, the source year, the agency-exception flag, the effective rebate rate, the counter position before the flight, the platform rate and the closing time. A row is never updated. `POST /margin/closings` (year and month, `finance` only) resolves and freezes the rates of every flight that ended in that month, and is idempotent: a flight that already has a row is not touched, and the response says how many were created and how many already existed. Closing a month while an earlier month of the same year has ended flights without a row is rejected with 409, so the counter is never applied out of order. A flight is closed when its `flight_end` is on or before `as_of` (D-1).

**Reads follow the state of the flight.** The GET of a closed flight reads the frozen row and recomputes the amounts from it; the GET of a running flight computes on the fly and writes nothing. Changing a schedule, a bracket or a platform rate afterwards does not move a closed month. This resolves the earlier tension between "frozen" and "computed on demand": the margin is never stored, its frozen inputs are.

**The counter measures the group's annual volume, with or without a schedule.** *To be confirmed with Finance.* A flight that resolves to the explicit zero of step 8 still advances the counter of its group, channel and year, so a schedule that starts mid-year finds the volume already there, as it would find it in the invoicing. Reason: the counter is a measure of volume, and volume exists whether or not a rate was loaded for it. Risk: a group with no schedule in force at all accumulates volume that can push the first flights priced by a table that appears later into a higher bracket than Finance expects; if Finance reads the brackets as counting only from the table's `valid_from`, the counter must start from that date instead. Pinned by a test, so changing it is a deliberate act.

**Platform type and channel are one value.** `rebate-schedule` keys a schedule on "platform type" (`docs/product-description.md` §5.9) and `rebate-accrual` keys a counter on "channel"; both are the channel of the campaign line (§5.10). The domain uses the word `channel` in both keys.

**Bracket tables are validated, half-open and end open.** The first bracket starts at 0, brackets are contiguous and the last has no upper threshold; each bracket covers its lower threshold and every euro below its upper one. A table breaking this is a domain error with a code (`bracket_table_empty`, `bracket_table_must_start_at_zero`, `bracket_table_not_contiguous`, `last_bracket_must_be_open`). Two schedules matching at the same step on `flight_start` is the domain error `overlapping_schedules`.

**The rebate engine is a pure function over received values.** It takes the schedules, the closed flights of a counter-year and the flight to price (group, agency, channel, scope, `flight_start`, id, revenue) and returns, per flight, the resolved rate (the effective rate: rebate over revenue, zero when revenue is zero), the step, the agency-exception flag, the source year (`valid_from.year` of the matched schedule, none at step 8), the counter position before and after, the amount charged in each bracket and the exact rebate, unrounded. The revenue is given by the caller, who passes the flight's rounded revenue so the counter equals the roll-up. The zero reason is `no_schedule_for_year` when no schedule of any group is in force on `flight_start` and `no_schedule` otherwise.

**The resolution ladder is data-driven, not a chain of conditionals.** The eight steps are a table of progressively wider match keys, walked in order, with the reference date `flight_start`. Step 7 (the most recent earlier table) is deferred with task 3.6; without it a combination missing from the table in force falls through to step 8.

**A missing schedule resolves to an explicit zero, written to the flight's `applied_rates` with its reason.** Never a null, and never an error. A group negotiated at zero and a group whose rate was never loaded produce the same number but different provenance, and Finance must be able to tell them apart.

**A flight with a negative margin is flagged, not blended away.** `below_cost` means the final margin is below zero: rounded revenue less rounded media cost, rebate and platform cost. It supersedes the earlier test of media cost above revenue, which missed a flight that only the rebate and the platform cost pushed under zero. The view labels it "Margen negativo". The line and the campaign count their flagged flights, and a flagged flight still contributes its true value to every total.

**A line without a price is a case of the model, not an error.** A sale CPM of 0.00 is accepted when the contracted impressions are above zero and a negative CPM never is, so a price exception (a line sold at no charge that still costs money) is represented. Revenue and rebate are 0, the margin is minus the media cost and the platform cost, and the flights, the split of the volume and the pacing do not change because the volume stays positive. The flight carries `zero_sale` ("Sin venta"); a line carries it when it has a flight that does, and a campaign when it has a line that does; every total counts the flights. Its revenue adds 0 to the counter.

**The margin percentage is points of revenue, guarded.** `margin_pct` is margin over revenue times 100, two decimals, half up, as a string, at flight, line, campaign and totals, and null when revenue is 0. Rounding is applied once, to the final ratio.

**Limitation: zero contracted volume and cost-free delivery are outside this cut.** A campaign with contracted volume 0 (a zero sale with no purchase order) and pixels with no purchase cost do not enter the margin. Registration keeps refusing `contracted_impressions` of 0, so their delivery stays as unmatched delivery in the exception queue.

**`CuratorMargin` is computed, never ingested.** Verified as `OC revenue − purchase cost` on 404 of 408 rows of the supplied reports. It never enters the margin; its own `% Margin` excludes the platform cost. Implementation deferred (6.9).

## Backend decisions of the closing and reading cut

**Roles.** Margin is for `finance` only. `operations` and `business` get 403 on every margin route. The development seed gives the test user `finance` in addition to `operations` and removes nothing.

**Schema.** `rebate_schedules` and `rebate_brackets` (with `valid_from`, `valid_to` inclusive and nullable, group, optional agency, optional channel, optional scope), `platform_rate_settings`, `applied_rates` and its child `applied_rate_brackets`. Money and rates are `Numeric(18,6)` or wider, never float. The overlap rule is a PostgreSQL exclusion constraint over the key, with `COALESCE` for the optional columns, and `daterange(valid_from, valid_to, '[]')`; it needs the `btree_gist` extension. The migration fails with a clear message if it cannot create the extension, and its downgrade drops the extension only if the migration created it. The requirement is written in `docs/deploy.md`.

**`applied_rates`** holds one row per closed flight, with a unique foreign key to `campaign_line_periods`: schedule and step, source year, agency flag, zero reason, effective rate, the counter key (group, agency or none, channel, year), the position before and after, the exact unrounded rebate, the platform rate and the closing time. Its per-bracket breakdown is `applied_rate_brackets` (lower, upper, rate, amount, rebate, all `Numeric`), not JSON, so no precision is lost; a test round-trips a breakdown.

**Platform rate.** Overrides are rows that are only added; the latest by id wins. The system value is a row inserted by the migration with no author; a check constraint allows an absent author only at the system level.

**Closing.** `POST /margin/closings` takes a year and month, is a plain `def`, runs in one transaction and takes a transaction-level advisory lock for the year and month, so two concurrent closings of one month produce one row per flight. It closes the flights of that month with `flight_end <= as_of`, `as_of` being D-1 from the configured zone. The flights go to the rebate engine ordered by `flight_start` and then by id, with the opening position of each counter taken from the latest frozen row of that counter; the frozen flights are not priced again. `previous_month_open` (409) names the earliest earlier month of the same year with ended flights and no frozen row. A month with no ended flights answers 200 with zero closed.

**One function for closing and reading.** A single domain function takes the schedules, the platform rates, the flights, the opening positions and `as_of`, and returns the per-flight rebate, platform rate and margin. The closing writes its output; the read of a pending-close or running flight only returns it. They cannot diverge, and a test with three flights proves the pending-close margin equals the frozen one to the cent. `calculate_rebates` gains an optional `opening_positions`, empty by default; a test proves an empty value changes no result.

**Reading.** `GET /margin` returns campaigns, lines and flights with totals at each level and the count of below-cost flights. States: `closed` (frozen, read from `applied_rates`), `pending_close` and `running` (calculated on the fly, provisional, writing nothing); a flight that has not started does not appear. Every campaign is included, `inactive` too; the campaign filter is by id and answers 404 `campaign_not_found`. Aggregation is done in the database; no delivery row reaches the application. Amounts are decimal strings.

**Errors.** A handler returns `{"code","message"}` for validation errors on routes under `/margin` only, because the campaign registration tests and clients rely on `detail`. Domain rule codes (`bracket_table_must_start_at_zero`, `bracket_table_not_contiguous`, `last_bracket_must_be_open`, `overlapping_schedules`, ...) each map to their own message.

**Masters.** `POST /margin/rebate-schedules` and `POST /margin/platform-rates`, both `finance` only, answering 201. Every amount is a decimal string; a JSON number is refused. A schedule that overlaps another of its key is 409 `schedule_overlaps_existing` (the database's exclusion constraint, translated), a missing group, agency or channel is 422 `reference_not_found`, and a bad bracket table is 422 with the code of its rule. A platform rate setting records its author and time. The development seed leaves one fictitious schedule and one fictitious rate.

**Deferred in this cut.** The period, agency, advertiser and campaign-type roll-ups (their endpoints and 6.5 beyond the sum of `GET /margin`'s own detail) wait for the roll-up view. The frontend (section 7) is not touched.

**Known differences with the source sheets.** The running-month sheet accrues by the days a line *served* (`days_served / days_oc`); the domain accrues by the contract days elapsed up to `as_of` (D-1), whether or not the line delivered on them, which is the deliberate revenue-recognition choice of this change (a line that stopped delivering keeps accruing revenue). The acceptance test sets `as_of` from `days_served`, so the two coincide there; a real line that delivered fewer days than have elapsed would accrue more here than in the sheet. The sheet's `margin_pct_full_month` subtracts partial costs from the revenue of the whole month and is not replicated. Its `rebate_cost` column is the rebate on the whole month's sale, not the accrued one, and is not compared.

## Cut

Deferred, each with its reason in `tasks.md`:

- Accrued versus settled storage (1.3): nothing in this cut settles a rebate.
- Scope-mean test and carry-forward (3.5, 3.6) and so ladder step 7: the rebate tables are not loaded in this cut.
- Restating counters already frozen when an agency exception is created or removed, the sibling tests, and every replay and recalculation (4.4, 4.6–4.10): they need the counter replay, which this cut replaces with a single forward application at closing.
- Export (6.6), `CuratorMargin` (6.9), the roll-up view (7.4), the masters view (7.7), the migration and reconciliation (8.1, 8.3–8.5).

## Risks / Trade-offs

- **Margins will appear to fall by roughly 16 points the day the new figures are published**, and Deal revenue will more than quadruple, both by design. → A communications risk before a technical one; the reconciliation (deferred) attributes every difference to a named defect.
- **Creating or removing an agency exception mid-year does not restate the counters already frozen.** → The agency's volume before the exception stays on the group's counter. Documented limitation; it matters once real bracket thresholds exist.
- **Without restatement, a schedule change after a closing leaves the closed months at the old rate.** → Intended in this cut: a closed month does not move. Restating is the deferred mechanism.
- **Chronological attribution makes two comparable flights in a crossing month carry different rates.** → Real, documented, and read as an artefact of the method rather than a performance difference.
- **Closing must be run in month order.** → Enforced by the 409 rule above.

## Migration Plan

1. Alembic migration creates `rebate_schedules`, `rebate_brackets`, `platform_rate_settings` and `applied_rates`.
2. The platform rate is seeded at the system default of 1.00 €/CPM as a row of `platform_rate_settings`.
3. Loading the rebate spreadsheets is deferred (8.1); schedules are created through the application and the tests until then.
4. Rollback drops the four tables; the campaign and delivery data they read are untouched.

## Open Questions

- Whether a settled rebate should be recorded per payment or as a single annual figure per counter. Deferred with 1.3.
