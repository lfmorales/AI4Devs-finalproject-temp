## MODIFIED Requirements

### Requirement: Contracted and delivered volume are shown as distinct quantities

The system SHALL present, for each flight, contracted volume and delivered volume as separate figures together with their ratio, and SHALL NOT present a single combined impressions figure. The contracted volume is the flight's and the delivered volume is the line's delivery inside the flight's window up to D-1. Both are counted in the delivery metric of the line's channel, OTS for `DOOH` and impressions for every other channel, and the view SHALL label them with that unit, «OTS» or «impresiones».

#### Scenario: Both quantities are visible
- **WHEN** a flight of an active campaign is shown in the daily status
- **THEN** its contracted volume, its delivered volume and the ratio between them are all present

#### Scenario: A DOOH flight is shown in OTS
- **WHEN** a DOOH flight with 300,000 contracted OTS has delivered 95,000.75 OTS and 4,800 impressions up to D-1
- **THEN** its contracted and delivered volumes are shown as 300,000 and 95,000.75 labelled «OTS»
- **AND** its ratio is 95,000.75 / 300,000

#### Scenario: A CTV flight is shown in impressions
- **WHEN** a CTV flight with 200,000 contracted impressions has delivered 50,000 impressions up to D-1
- **THEN** its contracted and delivered volumes are shown as 200,000 and 50,000 labelled «impresiones»

### Requirement: An active campaign missing D-1 delivery is flagged

The system SHALL flag an active campaign whose most recent delivery predates D-1, evaluated after the nightly ingestion has run. For this flag a campaign is active when its status is `active` and D-1 falls within its dates. A delivery row counts as data received whatever its figures, including a row with zero impressions or zero OTS. The flag is not evaluated while D-1 is before the campaign's start; once D-1 is on or after the start, a campaign with no delivery at all is flagged. A campaign that receives rows but stalls is covered by the pacing deviation flag, not by this one: the two flags are distinct.

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

#### Scenario: A DOOH row with zero OTS counts as data received
- **WHEN** an active DOOH campaign's most recent delivery is dated D-1 and has 12 impressions and 0.0000 OTS
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

The system SHALL compare, for each flight, delivered volume inside its window against the volume expected by the current date within that window, and SHALL flag a deviation of more than ten percent in either direction. The flag belongs to the flight. Both volumes are counted in the delivery metric of the line's channel; the delivered volume SHALL be compared as an exact decimal, so that OTS decimals decide the ten percent boundary.

#### Scenario: Under-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent below what is expected to date
- **THEN** it is flagged as deviating, together with the days remaining in the flight

#### Scenario: Over-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent above what is expected to date
- **THEN** it is flagged as deviating

#### Scenario: Delivery within the threshold is not flagged
- **WHEN** a flight paces within ten percent of expectation
- **THEN** no deviation flag is raised

#### Scenario: A DOOH flight paces on its OTS
- **WHEN** a DOOH flight from 2026-09-01 to 2026-09-30 has 300,000 contracted OTS, D-1 is 2026-09-10 and it has delivered 95,000.75 OTS and 4,800 impressions
- **THEN** the expected volume is 100,000 OTS and the deviation is −4.99925 %
- **AND** no deviation flag is raised, although its impressions are far below 100,000

#### Scenario: Half an OTS crosses the boundary
- **WHEN** the same DOOH flight has delivered exactly 90,000.0000 OTS
- **THEN** the deviation is −10 % and no deviation flag is raised
- **AND** with 89,999.5000 OTS the deviation is −10.0005 % and the flight is flagged, with 20 days remaining

#### Scenario: A DOOH flight with impressions and no OTS is under-delivering
- **WHEN** the same DOOH flight has delivered 4,800 impressions and 0.0000 OTS
- **THEN** its delivered volume is 0 and it is flagged as under-delivering

### Requirement: The daily status is read through one endpoint for operations, business, finance and trading

The system SHALL expose the daily status at `GET /api/campaign-status` to users holding the `operations`, `business`, `finance` or `trading` role, with one row per flight whose window contains D-1 and whose campaign has status `active`, where D is the day the request is made. Each row SHALL carry the campaign (id and name), the agency (id and name), the line number, the flight (campaign period and window), the contracted volume of the flight (`contracted_impressions`, an integer in the line's delivery metric), `delivery_metric` (`impressions` or `ots`), the delivered volume (`delivered`, a decimal string with four decimals, the line's delivery in that metric from the flight's start to D-1), the delivered impressions (`delivered_impressions`, the line's impressions over the same days, whatever the metric), the ratio of the delivered to the contracted volume, the pacing (expected to date, deviation, days remaining until the flight's last day and the `pacing_flag`) and the `missing_data_flag`. Pacing SHALL be calculated by the pure pacing function from the delivered volume. The delivered volume and the delivered impressions SHALL be aggregated in the database, without bringing delivery rows into the application. OTS are not a cost or margin figure, so they are returned to all four roles.

#### Scenario: A running flight of an active campaign is listed with its figures
- **WHEN** a user with the `operations`, `business`, `finance` or `trading` role reads the daily status
- **THEN** a flight whose window contains D-1, of an `active` campaign, is listed once
- **AND** its contracted volume and its delivered volume are separate fields
- **AND** the delivered volume counts only the line's delivery from the flight's start to D-1

#### Scenario: A DOOH row carries OTS and impressions separately
- **WHEN** the DOOH flight of 300,000 contracted OTS that delivered 95,000.75 OTS and 4,800 impressions up to D-1 is read
- **THEN** its row carries `contracted_impressions` 300000, `delivery_metric` `ots`, `delivered` `"95000.7500"` and `delivered_impressions` 4800

#### Scenario: A CTV row carries impressions in both fields
- **WHEN** a CTV flight that delivered 50,000 impressions and 50,000 OTS up to D-1 is read
- **THEN** its row carries `delivery_metric` `impressions`, `delivered` `"50000.0000"` and `delivered_impressions` 50000

#### Scenario: A trading user reads OTS
- **WHEN** a user holding only `trading` reads the daily status of a DOOH flight
- **THEN** its row carries `delivered` and `delivery_metric` `ots`
- **AND** no cost or margin field is present

#### Scenario: A campaign that is not active is not listed
- **WHEN** a campaign has a status other than `active`
- **THEN** none of its flights is listed

#### Scenario: A line with no delivery in a running flight is flagged for pacing
- **WHEN** a running flight has no delivery or only rows of zeros in its delivery metric
- **THEN** it is listed with zero delivered and its `pacing_flag` raised

#### Scenario: Rows with any flag come first
- **WHEN** the daily status is read
- **THEN** rows with a pacing flag or a missing-data flag precede rows with none
- **AND** within each group the rows are ordered by agency name, campaign name and line number

#### Scenario: The response carries no cost field
- **WHEN** the daily status is read
- **THEN** no field of the response, however nested, is a cost or margin figure

#### Scenario: Reading the daily status requires one of the four roles
- **WHEN** a user holding none of the four roles reads the daily status
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated
