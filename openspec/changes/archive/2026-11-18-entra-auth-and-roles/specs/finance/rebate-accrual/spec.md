## REMOVED Requirements

### Requirement: Closing a month freezes the rates of its flights
**Reason**: The scenario title "Only finance may close" is no longer true: operations may also close a month.
**Migration**: Read the replacement requirement `Closing a month freezes the rates of every flight it covers`; the closing behaviour is unchanged.

## ADDED Requirements

### Requirement: Closing a month freezes the rates of every flight it covers

The system SHALL expose `POST /margin/closings`, restricted to the `operations` and `finance` roles, taking a year and a month, which SHALL resolve and freeze in `applied_rates` the rates of every flight that ended in that month, one row per flight with a foreign key to the flight, and SHALL be idempotent.

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
