## MODIFIED Requirements

### Requirement: Contracted and delivered volume are shown as distinct quantities

The system SHALL present, for each flight, contracted volume, carry-over, delivery target and delivered volume as separate figures together with the ratio of the delivered volume to the delivery target, and SHALL NOT present a single combined impressions figure. The contracted volume is the flight's, the carry-over is the volume carried to it from the previous flight of its line (`campaign/carryover`, zero when none), the delivery target is the contracted volume plus the carry-over, and the delivered volume is the line's delivery inside the flight's window up to D-1. All four are counted in the delivery metric of the line's channel, OTS for `DOOH` and impressions for every other channel, and the view SHALL label them with that unit, «OTS» or «impresiones». The contracted volume never includes the carry-over.

#### Scenario: Both quantities are visible
- **WHEN** a flight of an active campaign is shown in the daily status
- **THEN** its contracted volume, its carry-over, its delivery target, its delivered volume and the ratio of the delivered volume to the delivery target are all present

#### Scenario: A DOOH flight is shown in OTS
- **WHEN** a DOOH flight with 300,000 contracted OTS and no carry-over has delivered 95,000.75 OTS and 4,800 impressions up to D-1
- **THEN** its contracted volume and its delivery target are shown as 300,000 and its delivered volume as 95,000.75, labelled «OTS»
- **AND** its ratio is 95,000.75 / 300,000

#### Scenario: A CTV flight is shown in impressions
- **WHEN** a CTV flight with 200,000 contracted impressions has delivered 50,000 impressions up to D-1
- **THEN** its contracted and delivered volumes are shown as 200,000 and 50,000 labelled «impresiones»

#### Scenario: A flight with a carry-over shows its delivery target
- **WHEN** a November flight with 500,000 contracted impressions received a carry-over of 100,000 from its October flight and has delivered 190,000 up to D-1
- **THEN** its contracted volume is 500,000, its carry-over 100,000, its delivery target 600,000 and its ratio 190,000 / 600,000

### Requirement: Pacing deviation beyond ten percent is flagged

The system SHALL compare, for each flight, delivered volume inside its window against the volume of its delivery target expected by the current date within that window, and SHALL flag a deviation of more than ten percent in either direction for a flight whose line is `committed`. For a flight whose line is `target`, it SHALL flag only a deviation of more than ten percent below the expected volume: delivering more than the target is never flagged, although the pacing still reports the status `over_delivering` and the deviation. The delivery target is the contracted volume plus the carry-over (`campaign/carryover`), whether or not the carry-over is billable. The flag belongs to the flight. Both volumes are counted in the delivery metric of the line's channel; the delivered volume SHALL be compared as an exact decimal, so that OTS decimals decide the ten percent boundary.

#### Scenario: Under-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent below what is expected to date
- **THEN** it is flagged as deviating, together with the days remaining in the flight

#### Scenario: Over-delivery beyond the threshold is flagged
- **WHEN** a flight has delivered more than ten percent above what is expected to date
- **THEN** it is flagged as deviating

#### Scenario: Delivery within the threshold is not flagged
- **WHEN** a flight paces within ten percent of expectation
- **THEN** no deviation flag is raised

#### Scenario: The carry-over raises the expected volume
- **WHEN** a committed flight from 2026-11-01 to 2026-11-30 has 500,000 contracted impressions and a carry-over of 100,000, D-1 is 2026-11-10 and it has delivered 190,000
- **THEN** the expected volume is 600,000 × 10 / 30, which is 200,000, the deviation is −5 % and no deviation flag is raised
- **AND** without the carry-over the expected volume would be 166,666.67, the deviation +14 % and the flight flagged

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

#### Scenario: A target flight above its target is not flagged
- **WHEN** a `target` flight from 2026-11-01 to 2026-11-30 has a target of 300,000 impressions, D-1 is 2026-11-10 and it has delivered 120,000
- **THEN** the expected volume is 100,000, the deviation is +20 % and the status is `over_delivering`
- **AND** its `pacing_flag` is not raised

#### Scenario: A target flight below its target is flagged
- **WHEN** the same `target` flight has delivered 85,000 impressions
- **THEN** the deviation is −15 % and its `pacing_flag` is raised, with 20 days remaining

#### Scenario: A committed flight above its volume is still flagged
- **WHEN** a `committed` flight with the same figures has delivered 120,000 impressions
- **THEN** its `pacing_flag` is raised

### Requirement: The daily status is read through one endpoint for operations, business, finance and trading

The system SHALL expose the daily status at `GET /api/campaign-status` to users holding the `operations`, `business`, `finance` or `trading` role, with one row per flight whose window contains D-1 and whose campaign has status `active`, where D is the day the request is made. Each row SHALL carry the campaign (id and name), the agency (id and name), the line number, the flight (its id, campaign period and window), the contracted volume of the flight (`contracted_impressions`, an integer in the line's delivery metric), the carry-over it received (`carryover`, an integer in the same metric, zero when none), its delivery target (`delivery_target`, the contracted volume plus the carry-over), `delivery_metric` (`impressions` or `ots`), the line's `volume_commitment` (`committed` or `target`), the delivered volume (`delivered`, a decimal string with four decimals, the line's delivery in that metric from the flight's start to D-1), the delivered impressions (`delivered_impressions`, the line's impressions over the same days, whatever the metric), the ratio of the delivered volume to the delivery target, the pacing (expected to date, deviation, days remaining until the flight's last day and the `pacing_flag`) and the `missing_data_flag`. Pacing SHALL be calculated by the pure pacing function from the delivered volume and the delivery target. The delivered volume and the delivered impressions SHALL be aggregated in the database, without bringing delivery rows into the application. OTS and carry-overs are not cost or margin figures, so they are returned to all four roles; the row SHALL NOT carry whether the carry-over is billable, its reason, or any amount.

#### Scenario: A running flight of an active campaign is listed with its figures
- **WHEN** a user with the `operations`, `business`, `finance` or `trading` role reads the daily status
- **THEN** a flight whose window contains D-1, of an `active` campaign, is listed once
- **AND** its contracted volume, its carry-over, its delivery target and its delivered volume are separate fields
- **AND** the delivered volume counts only the line's delivery from the flight's start to D-1

#### Scenario: A DOOH row carries OTS and impressions separately
- **WHEN** the DOOH flight of 300,000 contracted OTS that delivered 95,000.75 OTS and 4,800 impressions up to D-1 is read
- **THEN** its row carries `contracted_impressions` 300000, `carryover` 0, `delivery_target` 300000, `delivery_metric` `ots`, `delivered` `"95000.7500"` and `delivered_impressions` 4800

#### Scenario: A CTV row carries impressions in both fields
- **WHEN** a CTV flight that delivered 50,000 impressions and 50,000 OTS up to D-1 is read
- **THEN** its row carries `delivery_metric` `impressions`, `delivered` `"50000.0000"` and `delivered_impressions` 50000

#### Scenario: A row with a carry-over
- **WHEN** the November flight with 500,000 contracted impressions and a carry-over of 100,000 is read
- **THEN** its row carries `contracted_impressions` 500000, `carryover` 100000 and `delivery_target` 600000
- **AND** no field says whether the carry-over is billable

#### Scenario: A trading user reads OTS
- **WHEN** a user holding only `trading` reads the daily status of a DOOH flight with a carry-over
- **THEN** its row carries `delivered`, `delivery_metric` `ots`, `carryover` and `delivery_target`
- **AND** no cost, revenue, billing or margin field, no billable flag and no reason is present

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
- **THEN** no field of the response, however nested, is a cost, revenue, billing or margin figure

#### Scenario: Reading the daily status requires one of the four roles
- **WHEN** a user holding none of the four roles reads the daily status
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated

#### Scenario: A row names the commitment of its line
- **WHEN** the daily status lists a flight of a `target` line and one of a `committed` line
- **THEN** each row carries its line's `volume_commitment`
- **AND** a user holding only `trading` receives it too, because it is not a cost or margin figure

### Requirement: The status screen names a target volume as a target

The system SHALL label the contracted volume of a row whose line is `target` «Objetivo» instead of the label of a committed volume, SHALL show the delivered volume of such a row above its target without any warning, and SHALL show on every row the carry-over labelled «Arrastre» and the delivery target labelled «Objetivo de entrega».

#### Scenario: A target row says Objetivo
- **WHEN** the status screen shows a row of a `target` line that delivered 120,000 impressions against 100,000 expected
- **THEN** its contracted volume is labelled «Objetivo» and no pacing flag is shown

#### Scenario: A row shows its carry-over and its delivery target
- **WHEN** the status screen shows the November flight with a carry-over of 100,000
- **THEN** it shows «Arrastre» 100.000 and «Objetivo de entrega» 600.000, labelled «impresiones»
