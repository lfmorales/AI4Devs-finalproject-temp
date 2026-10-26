## Purpose

The per-flight, per-line and per-campaign economics — what a campaign earned, what it cost and what it left — computed from explicit rules that can be read, tested and argued with, rather than reconstructed from chart expressions.

A **flight** is one campaign line in one calendar month: a row of `campaign_line_periods` with `flight_start`, `flight_end` and its own `contracted_impressions`. The flight is the unit of calculation.

## ADDED Requirements

### Requirement: The flight is the unit of calculation

The system SHALL compute revenue, media cost, rebate, platform cost and margin per flight, SHALL define the margin of a line as the sum of the margins of its flights, and SHALL define the margin of a campaign as the sum of the margins of its lines.

#### Scenario: A line is the sum of its flights
- **WHEN** a line has three flights with margins of 100.00 €, 250.50 € and -40.25 €
- **THEN** the margin of the line is 310.25 €

#### Scenario: A campaign is the sum of its lines
- **WHEN** a campaign has two lines with margins of 310.25 € and 89.75 €
- **THEN** the margin of the campaign is 400.00 €

#### Scenario: A flight never crosses a year
- **WHEN** a line runs from 2026-12-15 to 2027-01-20
- **THEN** it has two flights, one ending on 2026-12-31 and one starting on 2027-01-01
- **AND** no flight spans two calendar months, and so none spans two years

### Requirement: Revenue derives from the flight's contracted volume

The system SHALL compute the revenue of a flight as its contracted impressions divided by 1000 times the sale CPM of its line, SHALL NOT use delivered impressions in any revenue figure, and SHALL NOT depend on the purchase order version, which may be absent.

#### Scenario: Revenue is volume times CPM
- **WHEN** a flight has 726,202 contracted impressions and its line has a sale CPM of 5.00 €
- **THEN** its revenue is 3,631.01 €

#### Scenario: Under-delivery does not reduce revenue
- **WHEN** a flight contracted for 726,202 impressions at 5.00 € delivers 700,000
- **THEN** revenue is computed on 726,202 impressions, which is 3,631.01 €
- **AND** the delivered figure does not appear in the revenue calculation

#### Scenario: A line without a purchase order still has revenue
- **WHEN** a flight belongs to a line with no purchase order version
- **THEN** its revenue is computed from its contracted impressions and the line's sale CPM

### Requirement: Media cost is the Adform cost over the flight's window

The system SHALL compute the media cost of a flight as the sum of the `media_cost` of the line's daily deliveries dated from `flight_start` to `flight_end`, both included, and SHALL treat that column as the whole media cost, because it already includes every additional cost Adform charges.

#### Scenario: Only the flight's window counts
- **WHEN** a line has flights in August and September and a delivery on 2026-09-02
- **THEN** that delivery's cost belongs to the September flight and not to the August one

#### Scenario: A delivery outside every flight counts nowhere
- **WHEN** a line has a delivery dated outside the window of all its flights
- **THEN** its cost belongs to no flight

### Requirement: The margin includes the platform cost

The system SHALL compute the margin of a flight as revenue less media cost, less agency rebate, less platform cost, each already rounded, and SHALL express the margin percentage as margin over revenue.

#### Scenario: All four terms are applied
- **WHEN** a closed flight has revenue of 3,631.01 €, a media cost of 1,200.00 €, a rebate of 907.75 € and a platform cost of 700.00 €
- **THEN** the margin is 823.26 €
- **AND** the margin percentage is that margin over revenue, 22.7 %
- **AND** the media cost of 1,200.00 € in this example is a placeholder, since real cost only exists in Adform

#### Scenario: The rebate is a percentage of the sale price
- **WHEN** the agency rebate of a flight is computed
- **THEN** its base is the flight's revenue, not media cost and not delivered volume

#### Scenario: The platform cost is computed on the delivered volume of the window
- **WHEN** the platform cost of a flight is computed
- **THEN** it is the line's delivered impressions between `flight_start` and `flight_end`, divided by 1000, times the platform rate in force
- **AND** 700,000 delivered impressions at 1.00 € per thousand give 700.00 €

#### Scenario: Every platform type uses the same model
- **WHEN** a flight of a line on the `Deal` channel is calculated
- **THEN** the same four terms apply as for any other channel
- **AND** no channel-specific revenue rule is applied

### Requirement: Every amount is rounded to two decimals, half up, before subtracting

The system SHALL round the revenue, media cost, rebate and platform cost of each flight to 2 decimals, half up, before they are subtracted, SHALL compute the margin of the flight from the rounded amounts, and SHALL compute every line or campaign total as the exact sum of the amounts of its flights.

#### Scenario: The rebate is rounded before the margin
- **WHEN** the rebate of a flight is 25 % of a revenue of 3,631.01 €, which is 907.7525 €
- **THEN** the rebate is 907.75 €
- **AND** the margin is computed from 907.75 €

#### Scenario: A half rounds up
- **WHEN** an amount is exactly 2.525 €
- **THEN** it is rounded to 2.53 €

#### Scenario: A total equals the sum of its detail
- **WHEN** the amounts of the flights of a line are rounded and then added
- **THEN** the line total equals that sum exactly, with no further rounding

### Requirement: A running flight is pro-rated by contract days and labelled provisional

The system SHALL receive a date `as_of`, the last day counted (D-1), and SHALL treat a flight as closed when `flight_end <= as_of`, as not started when `flight_start > as_of` and as running otherwise. It SHALL pro-rate the revenue and the rebate of a running flight by the days elapsed from `flight_start` to `min(as_of, flight_end)`, both included, over the total days of the flight's window, both ends included, SHALL NOT use the date of the last delivery, SHALL mark the result as provisional, and SHALL NOT write anything.

#### Scenario: An open flight is pro-rated by elapsed days
- **WHEN** a flight from 2026-09-01 to 2026-09-30 has 300,000 contracted impressions at 5.00 € and `as_of` is 2026-09-10
- **THEN** the elapsed days are 10 and the total days are 30
- **AND** revenue is 1,500.00 € × 10 / 30, which is 500.00 €
- **AND** with a flat rebate of 20 % the rebate is 100.00 €

#### Scenario: A running flight is a complete worked example
- **WHEN** the flight above has delivered 90,000 impressions at a media cost of 150.00 € (a placeholder) and the platform rate is 1.00 €
- **THEN** the platform cost is 90.00 €
- **AND** the margin is 500.00 − 150.00 − 100.00 − 90.00, which is 160.00 €
- **AND** the figure is marked provisional

#### Scenario: A flight with no delivery still accrues revenue
- **WHEN** a running flight has received no delivery
- **THEN** revenue is still recognised on elapsed contract days
- **AND** the figure is marked provisional

#### Scenario: A closed flight is not pro-rated
- **WHEN** a flight whose `flight_end` is on or before `as_of` is calculated
- **THEN** revenue is the full contracted volume times the sale CPM

#### Scenario: The last day of a flight is closed on the day it is counted
- **WHEN** a flight ends on 2026-09-30 and `as_of` is 2026-09-30
- **THEN** the flight is closed and not pro-rated

#### Scenario: The day before the end is still running
- **WHEN** a flight ends on 2026-09-30 and `as_of` is 2026-09-29
- **THEN** the flight is running, with 29 elapsed days over 30, and provisional

#### Scenario: A flight that has not started has no margin
- **WHEN** a flight starts on 2026-10-01 and `as_of` is 2026-09-30
- **THEN** its status is not started and it has no revenue, cost, rebate, platform cost or margin
- **AND** it contributes to no total, and its line counts it as not started

#### Scenario: A total is provisional when any flight is running
- **WHEN** a line has a closed flight, a running flight and a not-started flight
- **THEN** its totals add the closed and the running flights only
- **AND** the line is marked provisional

#### Scenario: A running flight writes nothing
- **WHEN** a running flight is read
- **THEN** no `applied_rates` row is written
- **AND** the rebate counter is not advanced

#### Scenario: A line with a closed flight and a running one
- **WHEN** a line has an August flight that has ended and a September flight still running
- **THEN** the August flight is calculated in full from its frozen rates and the September flight is pro-rated and marked provisional
- **AND** the line total is the sum of both and is itself marked provisional

### Requirement: Monetary calculation keeps exact precision

The system SHALL perform every monetary and rate calculation in exact decimal arithmetic.

#### Scenario: A rate applied across a year does not drift
- **WHEN** rebate amounts are accumulated across a year of flights
- **THEN** the total equals the sum of the individual amounts exactly

### Requirement: A flight sold below cost is flagged

The system SHALL flag a flight whose media cost exceeds its revenue as "below cost", SHALL report on its line and its campaign how many of their flights are below cost, and SHALL NOT alter any total because of the flag.

#### Scenario: A negative margin is surfaced
- **WHEN** a flight's media cost exceeds its revenue
- **THEN** the flight is flagged "below cost"
- **AND** its line and its campaign indicate it
- **AND** it still contributes its true value to every total

### Requirement: Margin access is restricted to finance

The system SHALL restrict every cost and margin figure to users holding the `finance` role, enforced at the endpoint.

#### Scenario: A user without the role is forbidden
- **WHEN** a user holding `business` or `operations` but not `finance` requests a margin resource
- **THEN** the request is rejected as forbidden

#### Scenario: A missing or invalid token is unauthenticated
- **WHEN** a margin endpoint is called without a token or with an invalid one
- **THEN** the request is rejected as unauthenticated, a distinct outcome from forbidden

#### Scenario: The restriction holds against direct API access
- **WHEN** a margin endpoint is called directly rather than through the interface
- **THEN** the same restriction applies
