# finance/rebate-accrual Specification

## Purpose
The annual accumulation the brackets are measured against: which counter a flight's revenue feeds, in what order the year's euros are consumed, and how the rate is frozen when a month is closed.

## Requirements

### Requirement: Volume accumulates per counter, channel and year

The system SHALL accumulate annual revenue against a counter keyed on holding group, agency or none, channel and the calendar year of `flight_start`, and SHALL keep each channel's counter independent. The agency slot is filled only when the schedule that priced the flight is an agency exception, so that a flight accrues on the counter of the schedule that priced it. The key is derived from the resolved schedule; no state outside the inputs is read.

Platform type, as `rebate-schedule` calls the key of a schedule, and channel are the same value: the channel of the campaign line.

#### Scenario: Channels do not help each other reach a bracket
- **WHEN** an agency group spends in two channels
- **THEN** each channel has its own annual counter
- **AND** revenue in one does not advance the bracket of the other

#### Scenario: One group can sit in several brackets at once
- **WHEN** a group's channels have accumulated different revenue
- **THEN** each channel resolves to its own bracket independently

#### Scenario: An agency exception accrues on the agency's own counter
- **WHEN** a flight is priced by an agency exception
- **THEN** its revenue advances the counter of that agency, channel and year
- **AND** it does not advance the counter of the agency's group

#### Scenario: An exception without a channel has one counter per channel
- **WHEN** an agency exception covers every channel and the agency has flights in two channels
- **THEN** each channel advances its own counter of that agency

#### Scenario: Flights never cross years
- **WHEN** a flight is assigned to a counter
- **THEN** its year is the year of `flight_start`
- **AND** a flight cannot end in a different year, because it lies inside one calendar month

### Requirement: Attribution is chronological and marginal

The system SHALL apply the closed flights of a counter in chronological order of `flight_start`, breaking ties by flight id, SHALL charge each flight the marginal brackets that its own revenue falls into, and SHALL leave already-accrued flights untouched when a later flight crosses a threshold.

#### Scenario: A crossing is forward-only
- **WHEN** cumulative revenue crosses a bracket threshold
- **THEN** flights from that point onward accrue at the higher marginal rate
- **AND** flights already accrued keep the rate they were accrued at

#### Scenario: A flight straddling a threshold blends
- **WHEN** a flight's revenue spans a bracket boundary
- **THEN** each portion accrues at its own bracket's rate
- **AND** the flight's effective rate is the blend

#### Scenario: The order of the input does not matter
- **WHEN** the same closed flights are given in any order
- **THEN** the positions and rebates are identical

#### Scenario: Ties are broken by id
- **WHEN** two flights of the same counter have the same `flight_start`
- **THEN** the one with the lower id is applied first

### Requirement: A running flight reads the counter without advancing it

The system SHALL compute the rebate of a running flight whose line is `committed` on its full revenue, starting from the position given by all the closed flights of its counter, and SHALL NOT advance the counter; the margin calculation then pro-rates that rebate by elapsed days. A running flight whose line is `target` is priced from the same position on its gross up to `as_of`, does not advance the counter and is not pro-rated. A closed flight read before the month is closed takes its position from the closed flights only, which can differ from the position it will be frozen with when a running flight of the same counter started earlier; this is a documented limitation.

#### Scenario: A running flight does not advance the counter
- **WHEN** a running flight and a later closed flight belong to the same counter
- **THEN** the closed flight's position does not include the running flight's revenue

#### Scenario: The pro-rated rebate is the fraction of the full rebate
- **WHEN** a running flight's full rebate is 300.00 € and 10 of its 30 days have elapsed
- **THEN** the margin calculation pro-rates it to 100.00 €, the same fraction of the full rebate

#### Scenario: A running target flight is priced on its gross to date
- **WHEN** a running target flight has a gross of 2,000.00 € up to `as_of` and a flat rate of 10 %
- **THEN** its rebate is 200.00 €, not pro-rated, and its counter does not move

### Requirement: A closed month does not move

The system SHALL read a closed flight only from what its closing froze: the rates and the rebate of its `applied_rates` row, and every amount, volume, flag and line attribute of its snapshot (requirement «Closing a month freezes the rates of every flight it covers»). It SHALL NOT recompute a closed flight's figures from the stored delivery, the masters or the campaign, SHALL never update or delete a row of `applied_rates`, of the snapshots or of the closing headers, and SHALL NOT let a later change of a schedule, a bracket, a platform rate, a channel's delivery metric or the stored delivery alter a closed flight, its line, its campaign or any total. The stored delivery of a closed month keeps being replaced by the ingestion and removed by unlinking a line (`delivery/delivery-ingestion`); it only feeds the warning that the delivery changed after closing (`finance/margin-calculation`).

#### Scenario: Editing a master after closing leaves the margin unchanged
- **WHEN** a rebate schedule is edited after a month was closed
- **THEN** the margin of every flight of that month is unchanged

#### Scenario: A running flight is calculated on the fly
- **WHEN** a running flight is read
- **THEN** it is calculated from the rates in force and nothing is written
- **AND** its rebate is computed against the counter position given by the closed flights, without advancing it

#### Scenario: A restated reported revenue does not move a closed target flight
- **WHEN** Equativ restates the impressions, the buyer's spend and the reported revenue of a day of a target flight whose month is closed, and the window is ingested again
- **THEN** the flight's revenue, gross, rebate, platform cost, margin, delivered volumes and flags are those frozen at closing
- **AND** the flight carries `delivery_changed`

#### Scenario: A restated cost does not move a closed committed flight
- **WHEN** a committed Adform flight of November with 1,000,000 contracted impressions at 5.00 €, a flat rebate of 25 % and a platform rate of 1.00 € was closed on 1 December with 700,000 delivered impressions and a media cost of 1,200.00 €, a margin of 1,850.00 €, and the run of 3 December restates 28 November with 500,000 more impressions and 1,800.00 € more media cost
- **THEN** the flight's media cost is still 1,200.00 €, its platform cost 700.00 € and its margin 1,850.00 €
- **AND** it carries `delivery_changed`, with a current margin of −450.00 € that no total adds

#### Scenario: Unlinking a line does not move its closed flights
- **WHEN** the only mapping of a line with a closed flight is removed with its delivery
- **THEN** the closed flight's figures are those frozen at closing

#### Scenario: A change of a channel's delivery metric does not move a closed flight
- **WHEN** the delivery metric of a channel changes after a flight of a line on that channel was closed
- **THEN** the closed flight still reports the metric, the contracted volume and the delivered volume frozen at closing

### Requirement: Accrued and settled are distinct quantities

The system SHALL hold what has been accrued separately from what has been settled with the agency, and SHALL report the difference. **Deferred**: storing the settled amount is outside this cut (task 1.3); the frozen rebate of the closed flights is the accrued amount.

#### Scenario: Accrual does not imply payment
- **WHEN** a flight is closed and accrues rebate
- **THEN** no settled amount is created or changed

### Requirement: Margin is provisional until the year closes

The system SHALL mark any running flight, and any total that includes one, as an estimate, because the rate applied depends on volume not yet delivered.

#### Scenario: A running figure is marked provisional
- **WHEN** a margin that includes a running flight is reported
- **THEN** it is presented as an estimate rather than a settled result

### Requirement: Restatement and replay are not part of this cut

The system SHALL, in this cut, leave a closed flight untouched when a schedule changes, when a campaign is added, revised or removed with an earlier date, or when an agency exception is created or removed. Restating the year, replaying a counter and recalculating a closed month on purpose are **deferred** (tasks 4.6 to 4.10), and so are the restatement of counters already frozen when an exception is created or removed mid-year and the tests of sibling agencies (tasks 4.4 and 4.8).

#### Scenario: A schedule change after closing does not restate
- **WHEN** a schedule changes in May after January to April were closed
- **THEN** the frozen rows of January to April are unchanged

### Requirement: The engine accepts opening positions

The system SHALL let the rebate engine take, as an optional input that is empty by default, the opening position of each counter, and SHALL return exactly the same results as before when it is empty.

#### Scenario: An empty opening is the previous behaviour
- **WHEN** the engine is called with no opening positions
- **THEN** every result is identical to the result of the engine without the parameter

#### Scenario: An opening position shifts the counter
- **WHEN** a counter opens at 90,000 € and a flight of 30,000 € follows, with brackets of 15 % up to 100,000 € and 20 % above
- **THEN** the flight's position before is 90,000 € and its rebate is 5,500 €

### Requirement: Closing a month freezes the rates of every flight it covers

The system SHALL expose `POST /margin/closings`, restricted to the `operations` and `finance` roles, taking a year and a month, which SHALL resolve and freeze in `applied_rates` the rates of every flight that ended in that month, one row per flight with a foreign key to the flight, and SHALL be idempotent. For a flight whose line is `target`, the row SHALL also hold its revenue and its rebate base (its gross) as computed at closing. A month that holds a flight of a `target` line SHALL NOT be closed until a succeeded ingestion batch of that line's DSP has a window that includes the month's last day: until then the request SHALL be rejected with 409 `month_delivery_not_loaded`, naming the month and the DSP, and nothing SHALL be written.

For every flight it freezes, the closing SHALL also store one snapshot, tied one to one to its `applied_rates` row, holding the figures the closing computed for it, which are the figures its pending-close read showed: its revenue, contracted revenue, media cost, rebate, platform cost and margin, each rounded to two decimals as the margin rounds them, and its gross when its line is `target` and none when it is `committed`; the delivery they were computed on, which is its delivered impressions, its delivered volume in the unit of its metric, and the sums of its media cost, reported revenue, buyer's spend and data costs inside its window; its flags `gross_differs_from_buyer_spend` and `data_cost_reported`; and its line's delivery metric, sale CPM, contracted volume and volume commitment.

Every closing that freezes at least one flight SHALL record one closing header naming the month, the moment of the closing, the user who requested it, its `as_of` and, for each DSP of the lines of the flights it froze, the latest succeeded ingestion batch of that DSP at that moment; a DSP without a succeeded batch is not named. Each snapshot SHALL name the header of the closing that wrote it. A closing that freezes no flight SHALL write no header. A month is closed when it holds at least one header; a month may hold several, when a flight is registered in it after it was closed and a later closing freezes it. The response SHALL carry `year`, `month`, `closed` (the flights frozen by this request), `already_closed` (the flights of the month frozen before it) and `closings` (the headers the month holds after it), all integers. Rates, snapshots and header of one closing SHALL be written together or not at all.

#### Scenario: Closing writes one row per ended flight
- **WHEN** a month with 12 flights that have ended is closed
- **THEN** 12 `applied_rates` rows are created, one per flight
- **AND** each holds the schedule and step, the source year, the agency flag, the effective rebate rate, the counter position before the flight, the platform rate and the closing time

#### Scenario: Closing writes one snapshot per frozen flight and one header
- **WHEN** a month with 12 flights that have ended is closed
- **THEN** 12 snapshots are created, one per `applied_rates` row, and one closing header names the month, the moment, the user and the `as_of`
- **AND** the response is `closed` 12, `already_closed` 0 and `closings` 1

#### Scenario: The snapshot holds what the pending-close read showed
- **WHEN** a month's flights are read as pending close and the month is then closed
- **THEN** each snapshot holds the revenue, contracted revenue, media cost, rebate, platform cost, margin, gross, delivered impressions, delivered volume, flags, delivery metric, sale CPM, contracted volume and commitment that the pending-close read showed for its flight

#### Scenario: A committed flight's snapshot has no gross
- **WHEN** a month holding a committed flight is closed
- **THEN** that flight's snapshot holds no gross, and a target flight's snapshot of the same month holds its gross

#### Scenario: The header names the latest succeeded batch of each DSP
- **WHEN** a month whose ended flights are on Adform and on Equativ is closed, and each DSP has failed and succeeded batches
- **THEN** its header names, for Adform and for Equativ, the latest succeeded batch of that DSP at the moment of the closing
- **AND** a failed batch is never named

#### Scenario: Closing twice changes nothing
- **WHEN** a month that is already closed is closed again
- **THEN** no row is created, none is updated, and the response reports the flights as already closed
- **AND** no header is added and `closings` is still 1

#### Scenario: A flight registered in a closed month is closed by a second closing
- **WHEN** a flight of a month already closed is registered afterwards, has ended, and the month is closed again
- **THEN** that flight gets its `applied_rates` row and its snapshot under a second header
- **AND** the response is `closed` 1, the earlier flights are `already_closed`, and `closings` is 2
- **AND** the flights frozen by the first closing are unchanged

#### Scenario: A running flight is not closed
- **WHEN** a month is closed and one of its flights has not ended
- **THEN** that flight gets no row

#### Scenario: Months close in order
- **WHEN** a month is closed while an earlier month of the same year has ended flights without a row
- **THEN** the request is rejected with 409 `previous_month_open` and nothing is written
- **AND** the message names the earliest month that blocks it

#### Scenario: A month with no ended flights closes nothing
- **WHEN** a month with no flight that has ended is closed
- **THEN** the response is 200 with zero flights closed and nothing is written
- **AND** no header is written and `closings` is 0

#### Scenario: The month's flights reach the engine in order
- **WHEN** a month is closed
- **THEN** its flights are passed to the rebate engine ordered by `flight_start` and then by flight id

#### Scenario: A closing is all or nothing
- **WHEN** a failure occurs after some rows of a closing were written
- **THEN** none of that closing's rates, snapshots or header remains

#### Scenario: Two concurrent closings of one month do not duplicate
- **WHEN** two requests close the same month at the same time
- **THEN** each flight ends with exactly one `applied_rates` row and one snapshot, and both requests succeed
- **AND** the month holds one header

#### Scenario: The opening position comes from the frozen rows
- **WHEN** flights are closed after earlier flights of the same counter were frozen
- **THEN** the counter's position before the first new flight is the `position_after` of the latest frozen flight of that counter
- **AND** the frozen flights are not priced again

#### Scenario: Only operations and finance may close
- **WHEN** a user holding neither `operations` nor `finance` requests a closing
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated

#### Scenario: A target flight freezes its revenue and its gross
- **WHEN** the month of the closed Deal flight of the worked example is closed
- **THEN** its `applied_rates` row holds a revenue of 4,400.00 € and a rebate base of 5,500.00 € beside its rebate and platform rate
- **AND** its snapshot holds a revenue of 4,400.00 €, a gross of 5,500.00 €, a rebate of 550.00 €, a platform cost of 1,100.00 € and a margin of 2,750.00 €

#### Scenario: A month with a target flight waits for its last day
- **WHEN** November 2026 holds a target flight on Equativ and the latest succeeded Equativ batch covers up to 2026-11-29
- **THEN** closing November is rejected with 409 `month_delivery_not_loaded` and nothing is written
- **AND** once a succeeded Equativ batch whose window includes 2026-11-30 exists, the month closes

#### Scenario: A failed batch or another DSP's batch does not unblock
- **WHEN** the only batches whose window includes 2026-11-30 are a failed Equativ batch and a succeeded Adform batch
- **THEN** closing November is still rejected with 409 `month_delivery_not_loaded`

#### Scenario: A month of committed flights only is not blocked
- **WHEN** a month holds no flight of a `target` line
- **THEN** it closes as before, whatever the batches

### Requirement: The rebate base of a target flight is its served gross

The system SHALL price the rebate of a flight whose line is `target` on its served gross (served impressions inside its window / 1000 × the line's sale CPM, rounded to two decimals), never on its reported revenue or its target, and SHALL advance its counter by that gross when it is closed. Its counter is the one of its channel like any other flight's, so `Deal` flights accrue on the `Deal` counter.

#### Scenario: The worked example accrues on its gross
- **WHEN** the closed Deal flight with a gross of 5,500.00 € and a reported revenue of 4,400.00 € is priced at a flat 10 %
- **THEN** its rebate is 550.00 €
- **AND** closing its month advances its `Deal` counter by 5,500.00 €

#### Scenario: The gross, not the target, crosses a bracket
- **WHEN** a `Deal` counter stands at 95,000 €, the brackets are 10 % up to 100,000 € and 15 % above, and a closed target flight has a gross of 10,000 € against a target worth 8,000 €
- **THEN** 5,000 € accrue at 10 % and 5,000 € at 15 %, a rebate of 1,250 €
