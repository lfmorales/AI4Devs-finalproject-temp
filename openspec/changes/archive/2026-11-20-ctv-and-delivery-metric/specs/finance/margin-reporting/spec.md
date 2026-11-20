## MODIFIED Requirements

### Requirement: Every level carries the delivered and the contracted impressions

The system SHALL return `delivered_impressions`, `contracted_impressions`, `delivered` and `delivery_metric` on every flight, line, campaign and on the totals.

- `delivered_impressions` is always the delivered impressions, an integer, whatever the channel. On a flight it is the sum of the line's daily deliveries inside the flight's window, the same figure the platform cost is computed from. A line, a campaign and the totals carry the exact sum of their flights.
- `delivery_metric` is the delivery metric of the line's channel, `impressions` or `ots`. Every line of a campaign shares one metric, so a flight, a line and a campaign each have exactly one.
- `contracted_impressions` is the contracted volume, an integer counted in that metric, and `delivered` the delivered volume in the same metric, a decimal string with four decimals. On a flight they are the flight's contracted volume and the line's delivery inside the flight's window; a line and a campaign carry the exact sums of their flights.
- The totals mix campaigns. When every campaign below them shares one metric, they carry that metric and the exact sums of `contracted_impressions` and `delivered`. When they include more than one metric, their `delivery_metric`, `contracted_impressions` and `delivered` are null.

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
