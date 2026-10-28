## Purpose

How the calculated figures reach Finance: aggregated along the dimensions the business uses and labelled so that an accrual, an estimate and a settled result are never mistaken for one another.

## ADDED Requirements

### Requirement: Figures roll up along the business dimensions

The system SHALL aggregate margin and its component figures from flights by period, agency, advertiser and campaign type, where the period of a flight is the campaign period of its month. **Deferred**: in this cut only the roll-up by campaign and line inside `GET /margin` exists; the period, agency, advertiser and campaign-type roll-ups wait for the roll-up view (task 7.4).

#### Scenario: A period roll-up aggregates its flights
- **WHEN** a period roll-up is requested
- **THEN** revenue, media cost, rebate, platform cost and margin are the exact sums of the amounts of the flights of that period

#### Scenario: Aggregation is consistent with the detail
- **WHEN** a roll-up and its underlying flight figures are compared
- **THEN** the roll-up equals the sum of the detail

#### Scenario: Deliveries are joined to the flight by date range
- **WHEN** a roll-up is computed
- **THEN** each delivery counts toward a flight only if its date lies between `flight_start` and `flight_end` of a flight of its line
- **AND** the aggregation is done in the database, without fetching delivery rows into the application

### Requirement: Roll-ups are exportable

The system SHALL export a roll-up to Excel or CSV. **Deferred** (task 6.6).

#### Scenario: An export matches what is displayed
- **WHEN** a roll-up is exported
- **THEN** the exported figures match those displayed

### Requirement: Provisional figures are labelled as provisional

The system SHALL label a running flight, and any line, campaign or roll-up that includes one, as provisional, distinctly from a closed figure.

#### Scenario: A running flight is marked
- **WHEN** a running flight's figure is displayed
- **THEN** it carries a label identifying it as an accrual rather than a result

#### Scenario: A closed figure is not marked
- **WHEN** a closed flight's figure is displayed
- **THEN** it carries no provisional label

#### Scenario: A line mixing closed and running flights is provisional
- **WHEN** a line has one closed flight and one running flight
- **THEN** the line is labelled provisional and the closed flight within it is not

### Requirement: Negative-margin and zero-sale flights are flagged without altering totals

The system SHALL show a flight with a negative final margin as "Margen negativo" (`below_cost`) and a flight without a price as "Sin venta" (`zero_sale`), SHALL show on its line and its campaign how many of their flights are each, and SHALL keep the true value of every flagged flight in every total.

#### Scenario: A flagged flight is not blended away
- **WHEN** a line has one flight with a negative margin
- **THEN** the line shows one flight with "Margen negativo"
- **AND** its total includes that flight's negative margin

#### Scenario: Zero-sale flights are counted
- **WHEN** a line has one flight without a price
- **THEN** the line, its campaign and the totals each count one `zero_sale` flight

### Requirement: Every level carries the margin percentage

The system SHALL return `margin_pct` on every flight, line, campaign and on the totals, as a decimal string with two decimals or null when revenue is 0.

#### Scenario: The percentage is present at every level
- **WHEN** the margin is read
- **THEN** each flight, line, campaign and the totals carry `margin_pct`

#### Scenario: A level without revenue has none
- **WHEN** a level has revenue 0.00
- **THEN** its `margin_pct` is null

### Requirement: Every level carries the contracted revenue and a flight its accrued days

The system SHALL return `contracted_revenue` on every flight, line, campaign and on the totals: the sale contracted for the whole flight (contracted volume / 1000 × the line's CPM), as a decimal string with two decimals, rounded half up once, exactly like `revenue`. A line, a campaign and the totals carry the exact sum of the `contracted_revenue` of their flights. A flight SHALL also return `accrued_days` and `window_days` as integers: the contract days counted up to `as_of` and the days of its whole window, both ends included. In a closed or pending-close flight `revenue` equals `contracted_revenue` and `accrued_days` equals `window_days`; in a running flight `accrued_days` is below `window_days`. A flight that has not started does not appear, so it carries none. No existing amount changes.

#### Scenario: A closed flight accrues all its contracted revenue
- **WHEN** a closed or pending-close flight is read
- **THEN** its `revenue` equals its `contracted_revenue` and its `accrued_days` equals its `window_days`

#### Scenario: A running flight shows how much of the sale it has accrued
- **WHEN** a running flight of 31 days with 9 elapsed days and a contracted revenue of 3100.00 is read
- **THEN** `contracted_revenue` is "3100.00", `revenue` is "900.00", `accrued_days` is 9 and `window_days` is 31

#### Scenario: A line without a price has a contracted revenue of zero
- **WHEN** a flight of a line with a sale CPM of 0.00 is read
- **THEN** its `contracted_revenue` is "0.00" and so is its `revenue`

#### Scenario: Higher levels add the flights
- **WHEN** a line, a campaign or the totals are read
- **THEN** their `contracted_revenue` is the exact sum of the `contracted_revenue` of the flights below, with no further rounding

#### Scenario: Reading and closing agree
- **WHEN** the same flight is read before and after its month is closed
- **THEN** its `contracted_revenue`, `accrued_days` and `window_days` are the same

### Requirement: Divergence from the legacy application is classified

The system SHALL support comparing a recalculated closed month line by line against the legacy figures, and SHALL require every difference to be attributed either to a known defect or to an implementation error. **Deferred** (tasks 8.3 to 8.5).

#### Scenario: Each difference is attributable
- **WHEN** a closed month is reconciled against the legacy application
- **THEN** every differing line is attributed to a named known defect or raised as an implementation error
- **AND** no difference is accepted as merely close enough

### Requirement: Reporting access is restricted to finance

The system SHALL restrict margin reporting to users holding the `finance` role.

#### Scenario: A user without the role is forbidden
- **WHEN** a user without `finance` requests a roll-up
- **THEN** the request is rejected as forbidden

### Requirement: The margin is read per campaign, line and flight

The system SHALL expose `GET /margin`, restricted to the `finance` role, returning campaigns, their lines and their flights with totals at every level, filtered by year, month and campaign, and SHALL include every campaign whatever its status.

#### Scenario: A closed flight reads what was frozen
- **WHEN** a flight with an `applied_rates` row is read
- **THEN** its state is `closed` and its rebate and platform rate are the frozen ones

#### Scenario: A running flight is calculated and provisional
- **WHEN** a flight that has started and not ended is read
- **THEN** its state is `running` and it is provisional

#### Scenario: A flight that has ended and is not frozen is pending close
- **WHEN** a flight that has ended but has no frozen rates is read
- **THEN** its state is `pending_close` and it is provisional

#### Scenario: A flight that has not started is absent
- **WHEN** a flight starts after `as_of`
- **THEN** it does not appear

#### Scenario: A line with flights in different states
- **WHEN** a line has a closed flight and a running one
- **THEN** both appear, the line total is their sum and the line is provisional

#### Scenario: Filters narrow the result
- **WHEN** a year, a month or a campaign is given
- **THEN** only the matching flights appear

#### Scenario: An unknown campaign is not found
- **WHEN** the campaign filter names a campaign that does not exist
- **THEN** the response is 404 `campaign_not_found`

#### Scenario: Inactive campaigns are included
- **WHEN** a campaign is `inactive`
- **THEN** its flights appear

#### Scenario: Amounts are decimal strings
- **WHEN** any amount is serialised
- **THEN** it is a string such as `"3631.01"`, never a floating-point number

#### Scenario: Reading writes nothing
- **WHEN** `GET /margin` is called
- **THEN** no row of any table is created or changed

#### Scenario: Negative-margin flights are counted at every level
- **WHEN** a line or the totals include a flight with a negative final margin
- **THEN** the count of such flights is present at that level as `below_cost_count`

### Requirement: Errors under the margin routes are code and message

The system SHALL answer every error of a route under `/margin`, including a validation error, with a body of exactly `code` and `message`, and SHALL leave the error format of the other routes unchanged.

#### Scenario: A validation error under /margin
- **WHEN** a margin route receives an invalid month
- **THEN** the body has only `code` and `message`

#### Scenario: Other routes keep their format
- **WHEN** campaign registration receives an invalid body
- **THEN** the body still has `detail`

#### Scenario: Domain rule codes have distinct messages
- **WHEN** a bracket table is rejected for being empty and another for not starting at zero
- **THEN** the two messages differ
