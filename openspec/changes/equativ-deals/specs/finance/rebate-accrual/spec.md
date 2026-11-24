## ADDED Requirements

### Requirement: The rebate base of a target flight is its served gross

The system SHALL price the rebate of a flight whose line is `target` on its served gross (served impressions inside its window / 1000 × the line's sale CPM, rounded to two decimals), never on its reported revenue or its target, and SHALL advance its counter by that gross when it is closed. Its counter is the one of its channel like any other flight's, so `Deal` flights accrue on the `Deal` counter.

#### Scenario: The worked example accrues on its gross
- **WHEN** the closed Deal flight with a gross of 5,500.00 € and a reported revenue of 4,400.00 € is priced at a flat 10 %
- **THEN** its rebate is 550.00 €
- **AND** closing its month advances its `Deal` counter by 5,500.00 €

#### Scenario: The gross, not the target, crosses a bracket
- **WHEN** a `Deal` counter stands at 95,000 €, the brackets are 10 % up to 100,000 € and 15 % above, and a closed target flight has a gross of 10,000 € against a target worth 8,000 €
- **THEN** 5,000 € accrue at 10 % and 5,000 € at 15 %, a rebate of 1,250 €

## MODIFIED Requirements

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

The system SHALL read a closed flight from its frozen `applied_rates` row, SHALL never update a row, and SHALL NOT let a later change of a schedule, a bracket or a platform rate alter a closed flight. The revenue and the rebate base of a closed `target` flight SHALL be read from that row, so that a later restatement of its DSP does not alter them.

#### Scenario: Editing a master after closing leaves the margin unchanged
- **WHEN** a rebate schedule is edited after a month was closed
- **THEN** the margin of every flight of that month is unchanged

#### Scenario: A running flight is calculated on the fly
- **WHEN** a running flight is read
- **THEN** it is calculated from the rates in force and nothing is written
- **AND** its rebate is computed against the counter position given by the closed flights, without advancing it

#### Scenario: A restated reported revenue does not move a closed target flight
- **WHEN** Equativ restates the reported revenue of a day of a target flight whose month is closed, and the window is ingested again
- **THEN** the flight's revenue, gross and rebate are those frozen at closing

### Requirement: Closing a month freezes the rates of every flight it covers

The system SHALL expose `POST /margin/closings`, restricted to the `operations` and `finance` roles, taking a year and a month, which SHALL resolve and freeze in `applied_rates` the rates of every flight that ended in that month, one row per flight with a foreign key to the flight, and SHALL be idempotent. For a flight whose line is `target`, the row SHALL also hold its revenue and its rebate base (its gross) as computed at closing. A month that holds a flight of a `target` line SHALL NOT be closed until a succeeded ingestion batch of that line's DSP has a window that includes the month's last day: until then the request SHALL be rejected with 409 `month_delivery_not_loaded`, naming the month and the DSP, and nothing SHALL be written.

#### Scenario: Closing writes one row per ended flight
- **WHEN** a month with 12 flights that have ended is closed
- **THEN** 12 `applied_rates` rows are created, one per flight
- **AND** each holds the schedule and step, the source year, the agency flag, the effective rebate rate, the counter position before the flight, the platform rate and the closing time

#### Scenario: Closing twice changes nothing
- **WHEN** a month that is already closed is closed again
- **THEN** no row is created, none is updated, and the response reports the flights as already closed

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

#### Scenario: The month's flights reach the engine in order
- **WHEN** a month is closed
- **THEN** its flights are passed to the rebate engine ordered by `flight_start` and then by flight id

#### Scenario: A closing is all or nothing
- **WHEN** a failure occurs after some rows of a closing were written
- **THEN** none of that closing's rows remains

#### Scenario: Two concurrent closings of one month do not duplicate
- **WHEN** two requests close the same month at the same time
- **THEN** each flight ends with exactly one `applied_rates` row and both requests succeed

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
