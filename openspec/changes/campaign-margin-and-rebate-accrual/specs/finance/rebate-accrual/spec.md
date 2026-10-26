## Purpose

The annual accumulation the brackets are measured against: which counter a flight's revenue feeds, in what order the year's euros are consumed, and how the rate is frozen when a month is closed.

## ADDED Requirements

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

The system SHALL compute the rebate of a running flight on its full revenue, starting from the position given by all the closed flights of its counter, and SHALL NOT advance the counter; the margin calculation then pro-rates that rebate by elapsed days. A closed flight read before the month is closed takes its position from the closed flights only, which can differ from the position it will be frozen with when a running flight of the same counter started earlier; this is a documented limitation.

#### Scenario: A running flight does not advance the counter
- **WHEN** a running flight and a later closed flight belong to the same counter
- **THEN** the closed flight's position does not include the running flight's revenue

#### Scenario: The pro-rated rebate is the fraction of the full rebate
- **WHEN** a running flight's full rebate is 300.00 € and 10 of its 30 days have elapsed
- **THEN** the margin calculation pro-rates it to 100.00 €, the same fraction of the full rebate

### Requirement: Closing a month freezes the rates of its flights

The system SHALL expose `POST /margin/closings`, restricted to the `finance` role, taking a year and a month, which SHALL resolve and freeze in `applied_rates` the rates of every flight that ended in that month, one row per flight with a foreign key to the flight, and SHALL be idempotent.

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
- **THEN** the request is rejected with 409 and nothing is written

#### Scenario: Only finance may close
- **WHEN** a user without the `finance` role requests a closing
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated

### Requirement: A closed month does not move

The system SHALL read a closed flight from its frozen `applied_rates` row, SHALL never update a row, and SHALL NOT let a later change of a schedule, a bracket or a platform rate alter a closed flight.

#### Scenario: Editing a master after closing leaves the margin unchanged
- **WHEN** a rebate schedule is edited after a month was closed
- **THEN** the margin of every flight of that month is unchanged

#### Scenario: A running flight is calculated on the fly
- **WHEN** a running flight is read
- **THEN** it is calculated from the rates in force and nothing is written
- **AND** its rebate is computed against the counter position given by the closed flights, without advancing it

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
