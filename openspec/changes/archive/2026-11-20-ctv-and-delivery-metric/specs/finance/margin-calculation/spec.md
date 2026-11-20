## MODIFIED Requirements

### Requirement: Revenue derives from the flight's contracted volume

The system SHALL compute the revenue of a flight as its contracted volume divided by 1000 times the sale CPM of its line, SHALL NOT use the delivered volume or the delivered impressions in any revenue figure, and SHALL NOT depend on the purchase order version, which may be absent. The contracted volume is a whole number counted in the delivery metric of the line's channel: OTS for `DOOH`, impressions for every other channel. It is held in `contracted_impressions` whatever the metric.

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

### Requirement: The margin includes the platform cost

The system SHALL compute the margin of a flight as revenue less media cost, less agency rebate, less platform cost, each already rounded, and SHALL express the margin percentage as margin over revenue. The platform cost SHALL be computed on the delivered impressions for every channel, including a channel whose delivery metric is OTS.

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

#### Scenario: A DOOH flight pays the platform on impressions, not on OTS
- **WHEN** the closed DOOH flight above, with 280,000.50 delivered OTS and 12,000 delivered impressions, is calculated with a platform rate of 1.00 € per thousand
- **THEN** its platform cost is 12.00 €, not 280.00 €
- **AND** closing its month freezes the same platform rate and gives the same platform cost

#### Scenario: Every platform type uses the same model
- **WHEN** a flight of a line on the `Deal` channel is calculated
- **THEN** the same four terms apply as for any other channel
- **AND** no channel-specific revenue rule is applied
