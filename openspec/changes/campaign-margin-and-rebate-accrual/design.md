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

**A running flight is pro-rated on its own window and writes nothing.** `elapsed_days` is the number of days from `flight_start` to the reference date, both ends included, capped at the window; `total_days` is `flight_end − flight_start + 1`. Revenue and rebate are multiplied by `elapsed_days / total_days`. The reference date is an input of the calculation, never read from the clock inside the domain. It does not use the date of the last delivery. A running figure is labelled provisional, writes no `applied_rates` row and does not advance the counter: its rebate is computed against the counter position given by the frozen flights, as a read.

**Media cost is the sum of `daily_deliveries.media_cost` of the line between `flight_start` and `flight_end`.** It is the Adform `Cost` column, which already includes Adform's additional costs; no other media cost exists. A delivery outside every flight of its line is stored by ingestion but counts toward no flight.

**Platform cost is the line's delivered impressions in the flight window, divided by 1000, times the rate in force.** The rate resolves line, then agency, then campaign type, then system. The system value is 1.00 €/CPM and is a row of `platform_rate_settings`, never a constant in code.

**Rounding is per amount, half up, before subtracting.** Revenue, media cost, rebate and platform cost of a flight are each rounded to 2 decimals with `ROUND_HALF_UP`. The margin of the flight is the subtraction of the rounded amounts. A line or campaign total is the exact sum of its flights' rounded amounts, so a total never differs from its detail. Intermediate values (a pro-rated amount before its rounding, a bracket slice) stay unrounded.

**The rebate counter is per (holding group, channel, year of `flight_start`).** Closed flights are applied to it in chronological order of `flight_start`, ties broken by flight id. The tiebreak makes the result reproducible; marginal brackets are order-invariant in aggregate, so only an individual flight's rate depends on it. `applied_rates` stores the counter position before the flight, so the bracket slice can be reproduced from the frozen row alone.

**The agency exception replaces the group's schedule for that agency.** The carve-out of the group's counter (volume accrues to the agency and leaves the group's counter) is **deferred** and documented as a limitation: in this cut an excepted agency is priced by its own schedule but its volume still advances its group's counter.

**`applied_rates` is one append-only row per closed flight.** It has a foreign key to the flight and holds the rebate schedule and step, the source year, the agency-exception flag, the effective rebate rate, the counter position before the flight, the platform rate and the closing time. A row is never updated. `POST /margin/closings` (year and month, `finance` only) resolves and freezes the rates of every flight that ended in that month, and is idempotent: a flight that already has a row is not touched, and the response says how many were created and how many already existed. Closing a month while an earlier month of the same year has ended flights without a row is rejected with 409, so the counter is never applied out of order. A flight is closed when its `flight_end` is before the reference date.

**Reads follow the state of the flight.** The GET of a closed flight reads the frozen row and recomputes the amounts from it; the GET of a running flight computes on the fly and writes nothing. Changing a schedule, a bracket or a platform rate afterwards does not move a closed month. This resolves the earlier tension between "frozen" and "computed on demand": the margin is never stored, its frozen inputs are.

**The resolution ladder is data-driven, not a chain of conditionals.** The eight steps are a table of progressively wider match keys, walked in order, with the reference date `flight_start`. Step 7 (the most recent earlier table) is deferred with task 3.6; without it a combination missing from the table in force falls through to step 8.

**A missing schedule resolves to an explicit zero, written to the flight's `applied_rates` with its reason.** Never a null, and never an error. A group negotiated at zero and a group whose rate was never loaded produce the same number but different provenance, and Finance must be able to tell them apart.

**A flight sold below cost is flagged, not blended away.** A flight whose rounded media cost exceeds its rounded revenue is flagged "below cost". The line and the campaign report how many of their flights are below cost. The flagged flight still contributes its true value to every total.

**`CuratorMargin` is computed, never ingested.** Verified as `OC revenue − purchase cost` on 404 of 408 rows of the supplied reports. It never enters the margin; its own `% Margin` excludes the platform cost. Implementation deferred (6.9).

## Cut

Deferred, each with its reason in `tasks.md`:

- Accrued versus settled storage (1.3): nothing in this cut settles a rebate.
- Scope-mean test and carry-forward (3.5, 3.6) and so ladder step 7: the rebate tables are not loaded in this cut.
- Agency carve-out and every restatement, replay and recalculation (4.4–4.10): they need the counter replay, which this cut replaces with a single forward application at closing.
- Export (6.6), `CuratorMargin` (6.9), the roll-up view (7.4), the masters view (7.7), the migration and reconciliation (8.1, 8.3–8.5).

## Risks / Trade-offs

- **Margins will appear to fall by roughly 16 points the day the new figures are published**, and Deal revenue will more than quadruple, both by design. → A communications risk before a technical one; the reconciliation (deferred) attributes every difference to a named defect.
- **Without the carve-out, an excepted agency's volume advances its group's counter**, so the group's other agencies cross brackets earlier than the business defines. → Documented limitation; the exception only matters once real bracket thresholds exist.
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
