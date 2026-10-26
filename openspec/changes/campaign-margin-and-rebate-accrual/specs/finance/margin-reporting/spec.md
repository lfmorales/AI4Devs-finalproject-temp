## Purpose

How the calculated figures reach Finance: aggregated along the dimensions the business uses and labelled so that an accrual, an estimate and a settled result are never mistaken for one another.

## ADDED Requirements

### Requirement: Figures roll up along the business dimensions

The system SHALL aggregate margin and its component figures from flights by period, agency, advertiser and campaign type, where the period of a flight is the campaign period of its month.

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

### Requirement: Below-cost flights are flagged without altering totals

The system SHALL show a flagged flight as below cost, SHALL show on its line and its campaign the number of their flights below cost, and SHALL keep the flagged flight's true value in every total.

#### Scenario: A flagged flight is not blended away
- **WHEN** a line has one flight below cost
- **THEN** the line shows one flight below cost
- **AND** its total includes that flight's negative margin

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
