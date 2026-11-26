## MODIFIED Requirements

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
