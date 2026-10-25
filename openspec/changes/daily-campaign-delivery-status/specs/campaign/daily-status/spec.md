## Purpose

The view operations opens every morning: which active campaigns are delivering, how their flights pace against what was contracted, and which ones have stopped — replacing a per-DSP download routine with a page that already knows.

## ADDED Requirements

### Requirement: Contracted and delivered volume are shown as distinct quantities

The system SHALL present, for each flight, contracted volume and delivered volume as separate figures together with their ratio, and SHALL NOT present a single combined impressions figure. The contracted volume is the flight's and the delivered volume is the line's delivery inside the flight's window up to D-1.

#### Scenario: Both quantities are visible
- **WHEN** a flight of an active campaign is shown in the daily status
- **THEN** its contracted volume, its delivered volume and the ratio between them are all present

### Requirement: An active campaign missing D-1 delivery is flagged

The system SHALL flag an active campaign whose most recent delivery predates D-1, evaluated after the nightly ingestion has run. For this flag a campaign is active when its status is `active` and D-1 falls within its dates. A delivery row with zero impressions counts as data received. The flag is not evaluated while D-1 is before the campaign's start; once D-1 is on or after the start, a campaign with no delivery at all is flagged. A campaign that receives rows but stalls is covered by the pacing deviation flag, not by this one: the two flags are distinct.

#### Scenario: A campaign with no delivery for D-1 is flagged
- **WHEN** the nightly ingestion completes and an active campaign's most recent delivery is older than D-1
- **THEN** the campaign is flagged as having received no data

#### Scenario: A campaign delivering through D-1 is not flagged
- **WHEN** an active campaign has delivery dated D-1
- **THEN** it carries no missing-data flag

#### Scenario: A campaign that has not started is not flagged
- **WHEN** a campaign's start date is after D-1
- **THEN** it carries no missing-data flag

#### Scenario: A row with zero impressions counts as data received
- **WHEN** an active campaign's most recent delivery is dated D-1 and has zero impressions
- **THEN** it carries no missing-data flag

#### Scenario: A campaign with no delivery at all is flagged once D-1 reaches its start
- **WHEN** D-1 is on or after an active campaign's start and the campaign has no delivery
- **THEN** it is flagged as having received no data

#### Scenario: A campaign that has ended is not flagged
- **WHEN** a campaign ended before D-1, even if it was ingested because its dates overlap the window
- **THEN** it carries no missing-data flag

#### Scenario: The flag clears on the next successful ingestion
- **WHEN** a previously flagged campaign receives delivery for the latest day
- **THEN** the flag is no longer raised

### Requirement: Pacing deviation beyond ten percent is flagged

The system SHALL compare, for each flight, delivered volume inside its window against the volume expected by the current date within that window, and SHALL flag a deviation of more than ten percent in either direction. The flag belongs to the flight.

#### Scenario: Under-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent below what is expected to date
- **THEN** it is flagged as deviating, together with the days remaining in the flight

#### Scenario: Over-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent above what is expected to date
- **THEN** it is flagged as deviating

#### Scenario: Delivery within the threshold is not flagged
- **WHEN** a flight paces within ten percent of expectation
- **THEN** no deviation flag is raised

### Requirement: Pacing, the status view and absence are separate responsibilities

The system SHALL calculate pacing for a flight from its contracted volume, its window bounds, a date and the volume delivered inside the window, without regard to whether the flight is shown. Which flights and campaigns the daily status lists is decided by the status view, and delivery that never arrived in a finished flight is surfaced by the absence exception, not by the pacing flag.

#### Scenario: The pacing calculation does not hide a finished flight
- **WHEN** pacing is calculated for a flight that has ended with nothing delivered against a contracted volume
- **THEN** it reports under-delivery

#### Scenario: The status view lists one row per running flight of an active campaign
- **WHEN** the daily status is read
- **THEN** it has one row for each flight whose window contains D-1 and whose campaign has status `active`
- **AND** a flight that has ended is not listed
- **AND** a flight that has not started is not listed
- **AND** a campaign that has not started is not listed

#### Scenario: A line in two months shows only the month in course
- **WHEN** a line has flights in August and September and D-1 falls in September
- **THEN** only the September flight is listed, with its own contracted volume and the delivery inside its window

#### Scenario: The missing-data flag belongs to the campaign and repeats on each row
- **WHEN** a campaign has several rows in the daily status
- **THEN** each carries the campaign's missing-data flag, calculated from the latest delivery of any of its lines

### Requirement: The daily status is read through one endpoint for operations and business

The system SHALL expose the daily status at `GET /api/campaign-status` to users holding the `operations` or the `business` role, with one row per flight whose window contains D-1 and whose campaign has status `active`, where D is the day the request is made. Each row SHALL carry the campaign (id and name), the agency (id and name), the line number, the flight (campaign period and window), the contracted volume of the flight, the delivered volume (the line's impressions from the flight's start to D-1), their ratio, the pacing (expected to date, deviation, days remaining until the flight's last day and the `pacing_flag`) and the `missing_data_flag`. Pacing SHALL be calculated by the pure pacing function. The delivered volume SHALL be aggregated in the database, without bringing delivery rows into the application.

#### Scenario: A running flight of an active campaign is listed with its figures
- **WHEN** a user with the `operations` or the `business` role reads the daily status
- **THEN** a flight whose window contains D-1, of an `active` campaign, is listed once
- **AND** its contracted volume and its delivered volume are separate fields
- **AND** the delivered volume counts only impressions from the flight's start to D-1

#### Scenario: A campaign that is not active is not listed
- **WHEN** a campaign has a status other than `active`
- **THEN** none of its flights is listed

#### Scenario: A line with no delivery in a running flight is flagged for pacing
- **WHEN** a running flight has no delivery or only rows of zeros
- **THEN** it is listed with zero delivered and its `pacing_flag` raised

#### Scenario: Rows with any flag come first
- **WHEN** the daily status is read
- **THEN** rows with a pacing flag or a missing-data flag precede rows with none
- **AND** within each group the rows are ordered by agency name, campaign name and line number

#### Scenario: The response carries no cost field
- **WHEN** the daily status is read
- **THEN** no field of the response, however nested, is a cost or margin figure

#### Scenario: Reading the daily status requires operations or business
- **WHEN** a user holding neither role reads the daily status
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated

### Requirement: The daily status takes its day from the configured time zone

The system SHALL take D, and from it D-1, for the pacing and the missing-data flag of the daily status from the same time zone as the ingestion, `Europe/Madrid` unless configured otherwise, and not from UTC.

#### Scenario: Just after midnight in Madrid the status already looks at the new day
- **WHEN** the status is read at 00:30 in Madrid on 11 August, which is 22:30 UTC on the 10th
- **THEN** D-1 is 10 August

### Requirement: Cost and margin figures are restricted to finance

The system SHALL withhold cost and margin figures from users who do not hold the `finance` role, in the API response and not only in the interface.

#### Scenario: A business user sees delivery but not cost
- **WHEN** a user holding `business` and not `finance` reads the daily status
- **THEN** campaigns and their delivery are returned
- **AND** no cost or margin field is present in the response

#### Scenario: Calling the API directly does not bypass the restriction
- **WHEN** a user without `finance` requests a cost or margin resource directly
- **THEN** the request is rejected as forbidden

### Requirement: Loading and empty states are distinguishable

The system SHALL render a list that has not yet loaded differently from a list that loaded and is empty.

#### Scenario: An empty result is not mistaken for a pending one
- **WHEN** the daily status returns no campaigns
- **THEN** the view states that there are none
- **AND** that state is visually distinct from the pending state
