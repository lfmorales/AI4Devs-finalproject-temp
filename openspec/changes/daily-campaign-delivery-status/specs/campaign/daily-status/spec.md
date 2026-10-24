## Purpose

The view operations opens every morning: which active campaigns are delivering, how they pace against what was contracted, and which ones have stopped — replacing a per-DSP download routine with a page that already knows.

## ADDED Requirements

### Requirement: Contracted and delivered volume are shown as distinct quantities

The system SHALL present contracted volume and delivered volume as separate figures together with their ratio, and SHALL NOT present a single combined impressions figure.

#### Scenario: Both quantities are visible
- **WHEN** an active campaign is shown in the daily status
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

The system SHALL compare delivered volume against the volume expected by the current date within the period, and SHALL flag a deviation of more than ten percent in either direction.

#### Scenario: Under-delivery beyond the threshold is flagged
- **WHEN** a campaign line has delivered more than ten percent below what is expected to date
- **THEN** it is flagged as deviating, together with the days remaining in the period

#### Scenario: Over-delivery beyond the threshold is flagged
- **WHEN** a campaign line has delivered more than ten percent above what is expected to date
- **THEN** it is flagged as deviating

#### Scenario: Delivery within the threshold is not flagged
- **WHEN** a campaign line paces within ten percent of expectation
- **THEN** no deviation flag is raised

### Requirement: Pacing, the status view and absence are separate responsibilities

The system SHALL calculate pacing for a campaign line from its contracted volume, its period bounds, a date and its delivered volume, without regard to whether the period is shown. Which periods and campaigns the daily status lists is decided by the status view, and delivery that never arrived in a finished period is surfaced by the absence exception, not by the pacing flag.

#### Scenario: The pacing calculation does not hide a finished period
- **WHEN** pacing is calculated for a period that has ended with nothing delivered against a contracted volume
- **THEN** it reports under-delivery

#### Scenario: The status view lists neither finished periods nor campaigns that have not started
- **WHEN** the daily status is read
- **THEN** a period that has ended is not listed
- **AND** a campaign that has not started is not listed

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
