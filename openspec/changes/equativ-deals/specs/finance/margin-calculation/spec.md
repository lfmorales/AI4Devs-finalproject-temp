## ADDED Requirements

### Requirement: A target flight earns the revenue its DSP reports

The system SHALL compute the revenue of a flight whose line is `target` as the exact sum of the reported revenue of the line's daily deliveries dated from `flight_start` to `flight_end`, both included, up to `as_of`, rounded once to two decimals, half up. It SHALL NOT read the flight's target volume, the sale CPM or the buyer's spend for that revenue, SHALL NOT pro-rate it, and SHALL NOT apply the rule of the lesser of contracted and served, nor any manual adjustment. Its media cost is the stored media cost, which is zero for Equativ; its platform cost is on the served impressions; its rebate is computed on its served gross (`finance/rebate-accrual`); and its margin is revenue less media cost, less rebate, less platform cost, each rounded, with the margin percentage over that revenue.

#### Scenario: The worked example of a closed Deal flight
- **WHEN** a closed `target` flight has a target of 1,000,000 impressions, a sale CPM of 5.00 € and served 1,100,000 impressions, Equativ reports a buyer's spend of 5,500.00 € and a reported revenue of 4,400.00 €, its rebate rate is a flat 10 % and the platform rate is 1.00 € per thousand
- **THEN** its revenue is 4,400.00 €, its media cost 0.00 €, its gross 5,500.00 €, its rebate 550.00 € and its platform cost 1,100.00 €
- **AND** its margin is 2,750.00 € and its margin percentage 62.50 %

#### Scenario: A running target flight is not pro-rated
- **WHEN** a `target` flight from 2026-11-01 to 2026-11-30 at 5.00 € with a target of 1,000,000 impressions has, up to `as_of` 2026-11-10, served 400,000 impressions with a reported revenue of 1,600.00 €, with a flat rebate of 10 % and a platform rate of 1.00 €
- **THEN** its revenue is 1,600.00 €, its rebate 200.00 € and its platform cost 400.00 €, none pro-rated by the 10 of 30 days
- **AND** its margin is 1,000.00 € and it is provisional

#### Scenario: Serving more than the target earns what is reported
- **WHEN** a closed `target` flight served 1,100,000 impressions against a target of 1,000,000
- **THEN** its revenue is the reported revenue, not 1,000,000 / 1000 × the CPM

#### Scenario: A target flight that served nothing earns nothing
- **WHEN** a closed `target` flight has no delivery in its window
- **THEN** its revenue, gross, rebate and platform cost are 0.00 € and its margin is 0.00 €

### Requirement: The gross and the data costs of a flight are reported and flagged

The system SHALL compute, for a flight whose line is `target`, its gross as the served impressions inside its window divided by 1000 times the line's sale CPM, rounded once to two decimals, half up; a `committed` flight has no gross. It SHALL flag a target flight `gross_differs_from_buyer_spend` when its gross differs from the sum of the buyer's spend inside its window, rounded to two decimals, by more than 1 % of that spend, or when the spend is zero and the gross is not. It SHALL flag any flight `data_cost_reported` when the sum of its third-party data cost or of its audience data cost inside its window is above zero. Neither flag nor the data costs SHALL change any amount: the data costs are never subtracted from the margin.

#### Scenario: A gross equal to the spend is not flagged
- **WHEN** the closed Deal flight of the worked example has a gross of 5,500.00 € and a buyer's spend of 5,500.00 €
- **THEN** it is not flagged `gross_differs_from_buyer_spend`

#### Scenario: A buyer paying above the CPM is flagged
- **WHEN** the same flight has a buyer's spend of 6,050.00 €
- **THEN** it is flagged `gross_differs_from_buyer_spend` and every amount is unchanged

#### Scenario: Exactly one percent is inside the tolerance
- **WHEN** a target flight has a buyer's spend of 5,000.00 € and a gross of 5,050.00 €
- **THEN** it is not flagged
- **AND** with a gross of 5,050.01 € it is flagged

#### Scenario: A data cost is flagged and not subtracted
- **WHEN** a flight's audience data cost inside its window adds up to 1.25 €
- **THEN** it is flagged `data_cost_reported`
- **AND** its margin is the same as with no data cost

## MODIFIED Requirements

### Requirement: Revenue derives from the flight's contracted volume

The system SHALL compute the revenue of a flight whose line is `committed` as its contracted volume divided by 1000 times the sale CPM of its line, SHALL NOT use the delivered volume or the delivered impressions in any revenue figure, and SHALL NOT depend on the purchase order version, which may be absent. The contracted volume is a whole number counted in the delivery metric of the line's channel: OTS for `DOOH`, impressions for every other channel. It is held in `contracted_impressions` whatever the metric. The revenue of a flight whose line is `target` is the revenue its DSP reports (requirement «A target flight earns the revenue its DSP reports»).

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

#### Scenario: A DOOH flight earns on its contracted OTS
- **WHEN** a closed DOOH flight has 300,000 contracted OTS at a sale CPM of 5.00 € and delivered 280,000.50 OTS and 12,000 impressions
- **THEN** its revenue is 1,500.00 €
- **AND** neither the delivered OTS nor the delivered impressions appear in the revenue calculation

### Requirement: Media cost is the Adform cost over the flight's window

The system SHALL compute the media cost of a flight as the sum of the `media_cost` of the line's daily deliveries dated from `flight_start` to `flight_end`, both included, and SHALL treat that column as the whole media cost, because it already includes every additional cost Adform charges. Equativ reports no media cost, so the media cost of a line on Equativ is zero; the buyer's spend is never a media cost.

#### Scenario: Only the flight's window counts
- **WHEN** a line has flights in August and September and a delivery on 2026-09-02
- **THEN** that delivery's cost belongs to the September flight and not to the August one

#### Scenario: A delivery outside every flight counts nowhere
- **WHEN** a line has a delivery dated outside the window of all its flights
- **THEN** its cost belongs to no flight

#### Scenario: An Equativ line has no media cost
- **WHEN** a flight of a line on Equativ is calculated and its deliveries carry a buyer's spend of 5,500.00 €
- **THEN** its media cost is 0.00 €

### Requirement: The margin includes the platform cost

The system SHALL compute the margin of a flight as revenue less media cost, less agency rebate, less platform cost, each already rounded, and SHALL express the margin percentage as margin over revenue. The platform cost SHALL be computed on the delivered impressions for every channel, including a channel whose delivery metric is OTS.

#### Scenario: All four terms are applied
- **WHEN** a closed flight has revenue of 3,631.01 €, a media cost of 1,200.00 €, a rebate of 907.75 € and a platform cost of 700.00 €
- **THEN** the margin is 823.26 €
- **AND** the margin percentage is that margin over revenue, 22.7 %
- **AND** the media cost of 1,200.00 € in this example is a placeholder, since real cost only exists in Adform

#### Scenario: The rebate is a percentage of the sale price
- **WHEN** the agency rebate of a `committed` flight is computed
- **THEN** its base is the flight's revenue, not media cost and not delivered volume
- **AND** the base of a `target` flight is its served gross, not its reported revenue

#### Scenario: The platform cost is computed on the delivered volume of the window
- **WHEN** the platform cost of a flight is computed
- **THEN** it is the line's delivered impressions between `flight_start` and `flight_end`, divided by 1000, times the platform rate in force
- **AND** 700,000 delivered impressions at 1.00 € per thousand give 700.00 €

#### Scenario: A DOOH flight pays the platform on impressions, not on OTS
- **WHEN** the closed DOOH flight above, with 280,000.50 delivered OTS and 12,000 delivered impressions, is calculated with a platform rate of 1.00 € per thousand
- **THEN** its platform cost is 12.00 €, not 280.00 €
- **AND** closing its month freezes the same platform rate and gives the same platform cost

#### Scenario: Every platform type uses the same model
- **WHEN** a `Deal` flight and a `Directo` flight with the same commitment and the same figures are calculated
- **THEN** they have the same margin
- **AND** the same four terms apply to both, and no rule reads the channel

### Requirement: A running flight is pro-rated by contract days and labelled provisional

The system SHALL receive a date `as_of`, the last day counted (D-1), and SHALL treat a flight as closed when `flight_end <= as_of`, as not started when `flight_start > as_of` and as running otherwise. It SHALL pro-rate the revenue and the rebate of a running flight whose line is `committed` by the days elapsed from `flight_start` to `min(as_of, flight_end)`, both included, over the total days of the flight's window, both ends included, SHALL NOT use the date of the last delivery, SHALL mark the result as provisional, and SHALL NOT write anything. A running flight whose line is `target` is not pro-rated: its revenue and its rebate are those of its delivery up to `as_of`, and it is still provisional.

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

### Requirement: A line without a price has no revenue and no rebate

The system SHALL accept a line whose sale CPM is 0.00 when its contracted impressions are above zero and SHALL never accept a negative CPM. For such a flight whose line is `committed`, revenue SHALL be 0, the rebate SHALL be 0 and the margin SHALL be minus the sum of the media cost and the platform cost. For such a flight whose line is `target`, the gross and the rebate SHALL be 0 and the revenue SHALL still be the reported revenue. Flights, the split of the volume and the pacing do not change, because the volume is still positive. The flight, its line and its campaign SHALL carry `zero_sale`, labelled "Sin venta", and every total SHALL count how many flights are `zero_sale`.

#### Scenario: A line without a price still has cost
- **WHEN** a flight with contracted impressions above zero, a CPM of 0.00, a media cost of 120.00 € and a platform cost of 30.00 € is calculated
- **THEN** revenue is 0.00 € and the rebate is 0.00 €
- **AND** the margin is -150.00 €
- **AND** the flight is `zero_sale` and `below_cost`

#### Scenario: Zero sale reaches the line and the campaign
- **WHEN** a campaign has one line without a price and one with a price
- **THEN** the flight and the line without a price carry `zero_sale`, and so does the campaign
- **AND** each total counts one `zero_sale` flight

#### Scenario: Zero sale advances no counter
- **WHEN** a flight has `zero_sale`
- **THEN** its revenue adds 0 to its rebate counter

#### Scenario: A target line without a price keeps its reported revenue
- **WHEN** a closed `target` flight with a CPM of 0.00 served 10,000 impressions and its DSP reports a revenue of 40.00 €, with a platform rate of 1.00 €
- **THEN** its gross and its rebate are 0.00 €, its revenue is 40.00 € and its margin is 30.00 €
- **AND** it carries `zero_sale`
