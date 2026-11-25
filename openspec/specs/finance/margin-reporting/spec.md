# finance/margin-reporting Specification

## Purpose
How the calculated figures reach Finance: aggregated along the dimensions the business uses and labelled so that an accrual, an estimate and a settled result are never mistaken for one another.

## Requirements

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

The system SHALL return `contracted_revenue` on every flight, line, campaign and on the totals: the sale contracted for the whole flight (contracted volume / 1000 × the line's CPM; for a `target` line, the sale of its target), as a decimal string with two decimals, rounded half up once, exactly like `revenue`. A line, a campaign and the totals carry the exact sum of the `contracted_revenue` of their flights. A flight SHALL also return `accrued_days` and `window_days` as integers: the contract days counted up to `as_of` and the days of its whole window, both ends included. In a closed or pending-close flight `accrued_days` equals `window_days` and, when its line is `committed`, `revenue` equals `contracted_revenue`; a `target` flight's `revenue` is its reported revenue, which may be above or below `contracted_revenue`; in a running flight `accrued_days` is below `window_days`. A flight that has not started does not appear, so it carries none. No existing amount changes.

#### Scenario: A closed flight accrues all its contracted revenue
- **WHEN** a closed or pending-close flight of a `committed` line is read
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

#### Scenario: A closed target flight earns what was reported, not its target
- **WHEN** the closed Deal flight with a target of 1,000,000 impressions at 5.00 € and a reported revenue of 4,400.00 € is read
- **THEN** its `contracted_revenue` is "5000.00", its `revenue` is "4400.00" and its `accrued_days` equals its `window_days`

### Requirement: Every level carries the delivered and the contracted impressions

The system SHALL return `delivered_impressions`, `contracted_impressions`, `delivered` and `delivery_metric` on every flight, line, campaign and on the totals.

- `delivered_impressions` is always the delivered impressions, an integer, whatever the channel. On a flight it is the sum of the line's daily deliveries inside the flight's window, the same figure the platform cost is computed from. A line, a campaign and the totals carry the exact sum of their flights.
- `delivery_metric` is the delivery metric of the line's channel, `impressions` or `ots`. Every line of a campaign shares one metric, so a flight, a line and a campaign each have exactly one.
- `contracted_impressions` is the contracted volume, an integer counted in that metric, and `delivered` the delivered volume in the same metric, a decimal string with four decimals. On a flight they are the flight's contracted volume and the line's delivery inside the flight's window; a line and a campaign carry the exact sums of their flights.
- The totals mix campaigns. When every campaign below them shares one metric, they carry that metric and the exact sums of `contracted_impressions` and `delivered`. When they include more than one metric, their `delivery_metric`, `contracted_impressions` and `delivered` are null. A level below with flights whose own `delivery_metric` is null already mixes metrics, so a total that includes it is null in the same three fields; a level below with no flights does not count. This corrects the totals of change `2026-11-20-ctv-and-delivery-metric`, which took such a null for the absence of flights and carried the metric of the other campaigns with partial sums, so that they meet this requirement.

A delivery outside the flight's window is not counted. A flight that has not started does not appear, so it adds nothing. No amount changes.

#### Scenario: A flight returns what the line delivered inside its window
- **WHEN** a flight is read and its line also delivered on days before `flight_start` or after `flight_end`
- **THEN** its `delivered_impressions` and its `delivered` count only the days inside the window and its `contracted_impressions` is the flight's volume

#### Scenario: A line without a price still reports its volumes
- **WHEN** a flight of a line with a sale CPM of 0.00 is read
- **THEN** it carries its delivered and contracted volumes and its delivered impressions like any other

#### Scenario: A DOOH flight reports OTS and impressions separately
- **WHEN** a closed DOOH flight with 300,000 contracted OTS that delivered 280,000.50 OTS and 12,000 impressions is read
- **THEN** it carries `delivery_metric` `ots`, `contracted_impressions` 300000, `delivered` `"280000.5000"` and `delivered_impressions` 12000

#### Scenario: A CTV flight reports impressions in both fields
- **WHEN** a CTV flight with 200,000 contracted impressions that delivered 198,500 impressions is read
- **THEN** it carries `delivery_metric` `impressions`, `delivered` `"198500.0000"` and `delivered_impressions` 198500

#### Scenario: Higher levels add the flights exactly
- **WHEN** a line has several flights, or a campaign several lines
- **THEN** their `delivered_impressions`, `contracted_impressions` and `delivered` are the exact sums of the levels below
- **AND** they carry the one `delivery_metric` of their lines

#### Scenario: A DOOH campaign adds its OTS decimals
- **WHEN** a DOOH campaign has two lines whose flights delivered 280,000.50 OTS with 12,000 impressions and 1,499.25 OTS with 300 impressions
- **THEN** the campaign's `delivered` is `"281499.7500"`, its `delivered_impressions` is 12300 and its `delivery_metric` is `ots`

#### Scenario: Totals of one metric are summed
- **WHEN** the response holds only campaigns counted in impressions
- **THEN** the totals carry `delivery_metric` `impressions` and the exact sums of `contracted_impressions`, `delivered` and `delivered_impressions`

#### Scenario: Totals that mix metrics null the volumes
- **WHEN** the response holds the DOOH campaign above and a CTV campaign with 200,000 contracted and 198,500 delivered impressions
- **THEN** the totals carry `delivery_metric`, `contracted_impressions` and `delivered` as null
- **AND** their `delivered_impressions` is still summed: 12,300 plus 198,500, which is 210,800
- **AND** every amount of the totals is summed as before

#### Scenario: Reading and closing agree
- **WHEN** the same flight is read before and after its month is closed
- **THEN** its `delivered_impressions`, `contracted_impressions`, `delivered` and `delivery_metric` are the same

#### Scenario: Totals over a campaign that already mixes metrics are null
- **WHEN** the totals are computed over a campaign whose `delivery_metric` is null because its lines count in OTS and in impressions (a state registration refuses with `mixed_delivery_metrics`, but the totals do not assume), with 300,000 contracted OTS and 200,000 contracted impressions, and over a campaign counted in OTS with 5,000 contracted OTS that delivered 1,000 OTS
- **THEN** the totals carry `delivery_metric`, `contracted_impressions` and `delivered` as null, not `ots`, 5000 and `"1000.0000"`
- **AND** their `delivered_impressions` and every amount are still summed

### Requirement: Divergence from the legacy application is classified

The system SHALL support comparing a recalculated closed month line by line against the legacy figures, and SHALL require every difference to be attributed either to a known defect or to an implementation error. **Deferred** (tasks 8.3 to 8.5).

#### Scenario: Each difference is attributable
- **WHEN** a closed month is reconciled against the legacy application
- **THEN** every differing line is attributed to a named known defect or raised as an implementation error
- **AND** no difference is accepted as merely close enough

### Requirement: Reporting access is restricted to operations and finance

The system SHALL restrict margin reporting to users holding the `operations` or the `finance` role.

#### Scenario: A user without the role is forbidden
- **WHEN** a user holding neither `operations` nor `finance` requests a roll-up
- **THEN** the request is rejected as forbidden

### Requirement: The margin is read per campaign, line and flight

The system SHALL expose `GET /margin`, restricted to the `operations` and `finance` roles, returning campaigns, their lines and their flights with totals at every level, filtered by year, month and campaign, and SHALL include every campaign whatever its status.

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

### Requirement: Every level carries the gross, the commitment and the counts of the two flags

The system SHALL return on every flight `volume_commitment`, `gross_revenue` (a decimal string with two decimals, null for a `committed` flight), `gross_differs_from_buyer_spend` and `data_cost_reported`. A line SHALL carry the `volume_commitment` of its line; a campaign and the totals SHALL carry the one commitment of their lines when they share it, and null otherwise. A line, a campaign and the totals SHALL carry `gross_revenue` as the exact sum of the gross of their target flights, null when they have none, and `gross_differs_count` and `data_cost_count` as the number of their flights carrying each flag. No amount changes because of them.

#### Scenario: The worked example reports its gross
- **WHEN** the closed Deal flight of 1,100,000 served impressions at 5.00 € is read
- **THEN** it carries `volume_commitment` `target`, `revenue` `"4400.00"`, `gross_revenue` `"5500.00"` and `margin` `"2750.00"`

#### Scenario: A committed flight has no gross
- **WHEN** a `committed` flight is read
- **THEN** its `gross_revenue` is null and neither flag is raised by the gross

#### Scenario: A campaign of both commitments
- **WHEN** a campaign has a `target` line and a `committed` line
- **THEN** its `volume_commitment` is null and its `gross_revenue` is the gross of the target line's flights

#### Scenario: The flags are counted at every level
- **WHEN** a line has one flight flagged `gross_differs_from_buyer_spend` and one flagged `data_cost_reported`
- **THEN** the line, its campaign and the totals carry `gross_differs_count` 1 and `data_cost_count` 1

### Requirement: The margin screen names a target line's sale and shows its gross

The system SHALL label the contracted revenue of a flight or a line whose commitment is `target` «Venta objetivo» instead of «Venta contratada», SHALL show its gross labelled «Bruto» next to its revenue, and SHALL show the two flags where the response raises them, labelled «Bruto distinto del gasto» and «Coste de datos». The margin percentage shown SHALL be the one the response carries, over revenue.

#### Scenario: A target line says Venta objetivo and shows its gross
- **WHEN** the margin screen shows the closed Deal flight of the worked example
- **THEN** it shows «Venta objetivo» 5.000,00 €, «Bruto» 5.500,00 € and the revenue 4.400,00 €

#### Scenario: The flags are labelled where raised
- **WHEN** a flight carries `gross_differs_from_buyer_spend` and `data_cost_reported`
- **THEN** the screen labels it «Bruto distinto del gasto» and «Coste de datos»
