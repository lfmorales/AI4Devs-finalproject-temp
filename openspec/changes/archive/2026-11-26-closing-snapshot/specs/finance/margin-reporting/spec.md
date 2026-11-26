## ADDED Requirements

### Requirement: Every level reports a delivery that changed after closing

The system SHALL return on every flight `delivery_changed`, true only for a closed flight flagged by the check of `finance/margin-calculation`, and `delivery_change`, null for a flight that is not closed and, for a closed flight, an object with:

- `delivered_difference`, a decimal string with four decimals, in the unit of the flight's `delivery_metric`;
- `delivered_impressions_difference`, an integer;
- `media_cost_difference`, a decimal string with two decimals;
- `reported_revenue_difference` and `buyer_spend_difference`, decimal strings with two decimals for a `target` flight and null for a `committed` one;
- `current_margin` and `margin_difference`, decimal strings with two decimals.

Every difference is the current value less the frozen one. The response SHALL describe these fields as informative: the current margin uses the closing's rebate and rates and only the delivery changes, and no amount or total adds it. A line, a campaign and the totals SHALL carry `delivery_changed_count`, the number of their flights flagged `delivery_changed`. No amount, volume, flag or other count of any level changes because of them.

#### Scenario: The restated committed flight of the example reports its change
- **WHEN** the committed flight closed at 1,850.00 € is read after 28 November was restated with 500,000 more impressions and 1,800.00 € more media cost
- **THEN** it carries `margin` `"1850.00"`, `media_cost` `"1200.00"`, `platform_cost` `"700.00"` and `delivered_impressions` 700000, as frozen
- **AND** it carries `delivery_changed` true and `delivery_change` with `delivered_impressions_difference` 500000, `delivered_difference` `"500000.0000"`, `media_cost_difference` `"1800.00"`, `reported_revenue_difference` and `buyer_spend_difference` null, `current_margin` `"-450.00"` and `margin_difference` `"-2300.00"`
- **AND** its line, its campaign and the totals carry `delivery_changed_count` 1 and add 1,850.00 € to their margin

#### Scenario: A closed flight whose delivery did not change
- **WHEN** a closed flight's stored delivery is the one it was closed with
- **THEN** it carries `delivery_changed` false and `delivery_change` with every difference zero and `current_margin` equal to its `margin`

#### Scenario: A flight that is not closed carries no change
- **WHEN** a running flight or a flight pending close is read
- **THEN** it carries `delivery_changed` false and `delivery_change` null

#### Scenario: A target flight reports its revenue and spend differences
- **WHEN** the restated Deal flight of `finance/margin-calculation` is read
- **THEN** its `delivery_change` carries `reported_revenue_difference` `"800.00"`, `buyer_spend_difference` `"1000.00"`, `current_margin` `"3350.00"` and `margin_difference` `"600.00"`

#### Scenario: The fields describe the current margin as informative
- **WHEN** the response schema of `GET /margin` is read
- **THEN** the description of `delivery_change` and of `current_margin` says that the current margin uses the closing's rebate and rates with today's delivery, and that no amount or total adds it

### Requirement: The margin screen labels a flight that changed after closing

The system SHALL show «Cambió tras el cierre» on a flight that carries `delivery_changed`, and on a line, a campaign or the period the number of their flights that carry it, like the other flags. Next to the flight's label it SHALL show the differences and the current margin as the response gives them, stating that this margin uses the rebate and the rates of the closing and that only the delivery changed. The screen SHALL compute no figure: every amount and every difference is the response's.

#### Scenario: A changed flight is labelled with its current margin
- **WHEN** the margin screen shows the restated committed flight of the example
- **THEN** it shows its margin 1.850,00 € and the label «Cambió tras el cierre» with the current margin −450,00 €, the differences of the response and the note that the rebate and the rates are the closing's

#### Scenario: The count reaches the line, the campaign and the period
- **WHEN** a line holds one flight that carries `delivery_changed`
- **THEN** the line, its campaign and the period show «Cambió tras el cierre» counting one flight

#### Scenario: An unchanged or open flight shows no label
- **WHEN** a flight carries `delivery_changed` false
- **THEN** no «Cambió tras el cierre» label is shown for it

## MODIFIED Requirements

### Requirement: Every level carries the delivered and the contracted impressions

The system SHALL return `delivered_impressions`, `contracted_impressions`, `delivered` and `delivery_metric` on every flight, line, campaign and on the totals.

- `delivered_impressions` is always the delivered impressions, an integer, whatever the channel. On a flight it is the sum of the line's daily deliveries inside the flight's window, the same figure the platform cost is computed from. A line, a campaign and the totals carry the exact sum of their flights.
- `delivery_metric` is the delivery metric of the line's channel, `impressions` or `ots`. Every line of a campaign shares one metric, so a flight, a line and a campaign each have exactly one.
- `contracted_impressions` is the contracted volume, an integer counted in that metric, and `delivered` the delivered volume in the same metric, a decimal string with four decimals. On a flight they are the flight's contracted volume and the line's delivery inside the flight's window; a line and a campaign carry the exact sums of their flights.
- On a closed flight the four are those its closing froze (`finance/margin-calculation`, requirement «A closed flight is read from its snapshot»), whatever the stored delivery, the line or the channel say afterwards; the levels above add the frozen figures.
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

#### Scenario: A restatement after closing leaves a closed flight's volumes
- **WHEN** a closed flight that delivered 700,000 impressions has 1,200,000 in its window after a restatement
- **THEN** it still carries `delivered_impressions` 700000 and `delivered` `"700000.0000"`, and so do the sums of its line and its campaign

### Requirement: The margin is read per campaign, line and flight

The system SHALL expose `GET /margin`, restricted to the `operations` and `finance` roles, returning campaigns, their lines and their flights with totals at every level, filtered by year, month and campaign, and SHALL include every campaign whatever its status. A closed flight's figures are those its closing froze; the delivery stored now only feeds its `delivery_change`.

#### Scenario: A closed flight reads what was frozen
- **WHEN** a flight with an `applied_rates` row is read
- **THEN** its state is `closed` and its rebate and platform rate are the frozen ones
- **AND** every amount, volume and flag it carries is the one frozen at closing, whatever was ingested afterwards

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

#### Scenario: A closed month reads the same after a reingestion
- **WHEN** a month is closed, its window is ingested again with different figures, and the margin is read
- **THEN** every flight, line, campaign and total of that month carries the same amounts, volumes, flags and counts as before the reingestion, except `delivery_changed`, `delivery_change` and `delivery_changed_count`
