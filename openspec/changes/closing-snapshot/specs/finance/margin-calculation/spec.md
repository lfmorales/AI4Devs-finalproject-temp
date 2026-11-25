## ADDED Requirements

### Requirement: A closed flight is read from its snapshot

The system SHALL take the revenue, contracted revenue, media cost, rebate, platform cost, margin, gross, delivered impressions, delivered volume, the flags `gross_differs_from_buyer_spend` and `data_cost_reported`, the delivery metric, the contracted volume and the volume commitment of a closed flight from the snapshot its closing stored (`finance/rebate-accrual`), and SHALL NOT compute any of them again from the stored delivery, the line, the channel or the rates. A closed flight is never pro-rated and never provisional: its `accrued_days` equals its `window_days`, both counted from its own dates. Its `below_cost` SHALL be its frozen margin below zero, its `zero_sale` its frozen sale CPM equal to zero, and its `margin_pct` its frozen margin over its frozen revenue, with the rules of this specification. The rules of the other requirements of this specification give the figures a flight has until it is closed, and so the figures its closing freezes.

#### Scenario: A closed flight reads its frozen figures whatever the delivery says
- **WHEN** a closed flight's stored delivery is replaced after the closing with more impressions and a higher media cost
- **THEN** its revenue, media cost, rebate, platform cost, margin, delivered impressions and delivered volume are those of its snapshot

#### Scenario: Closing and reading after the closing agree to the cent
- **WHEN** a flight is read as pending close, its month is closed, and it is read again with no change to its delivery
- **THEN** every amount, volume and flag read after the closing equals the one read before it

#### Scenario: The flags of a closed flight are frozen
- **WHEN** the buyer's spend of a closed target flight is restated so that its gross differs from it by more than 1 %, and a data cost appears inside its window
- **THEN** its `gross_differs_from_buyer_spend` and `data_cost_reported` are those frozen at closing

#### Scenario: A negative frozen margin stays flagged
- **WHEN** a flight was closed with a margin of −20.00 € and its delivery is later restated so that its current margin would be positive
- **THEN** it is still flagged `below_cost` with a margin of −20.00 €

### Requirement: A closed flight is checked against its current delivery

The system SHALL compare every closed flight with the delivery stored now inside its window, and SHALL flag it `delivery_changed` when its current margin differs from its frozen margin by 1.00 € or more, in either direction, or when its current delivered volume differs from its frozen delivered volume by 1 % or more of the frozen volume; a frozen delivered volume of zero is exceeded by any current volume that is not zero. The check SHALL change no amount, no volume, no flag and no total of the flight or of any level above it.

The check SHALL report, each as the current value less the frozen one: the difference of the delivered volume (four decimals), of the delivered impressions (an integer), of the media cost (both rounded to two decimals before subtracting) and, for a `target` flight only, of the reported revenue and of the buyer's spend (both rounded to two decimals before subtracting); a `committed` flight has neither. It SHALL also report the current margin and its difference from the frozen margin. The current margin is the frozen margin's formula with only the delivery changed: the revenue is the frozen one for a `committed` flight and the current reported revenue, rounded, for a `target` flight; the media cost is the current one, rounded; the rebate is the frozen one; the platform cost is the current delivered impressions divided by 1000 times the frozen platform rate, rounded; and the margin is revenue less media cost, less rebate, less platform cost. No rebate, rate or master is resolved again for it. A flight that is not closed is not checked.

#### Scenario: The restated committed flight of the example is flagged
- **WHEN** the committed flight closed with a revenue of 5,000.00 €, a media cost of 1,200.00 €, a rebate of 1,250.00 €, a platform cost of 700.00 € on 700,000 impressions at 1.00 € and a margin of 1,850.00 € now has 1,200,000 delivered impressions and a media cost of 3,000.00 € in its window
- **THEN** its current margin is 5,000.00 − 3,000.00 − 1,250.00 − 1,200.00, which is −450.00 €, a difference of −2,300.00 €
- **AND** its delivered impressions differ by 500,000, its media cost by 1,800.00 €, and it is flagged `delivery_changed`
- **AND** its margin is still 1,850.00 €

#### Scenario: A delivery equal to the frozen one raises nothing
- **WHEN** a closed flight's stored delivery is the one it was closed with
- **THEN** every difference is zero, its current margin equals its margin, and it is not flagged

#### Scenario: A margin difference of 1.00 € is flagged and 0.99 € is not
- **WHEN** a closed flight's current delivery differs from the frozen one only in its media cost, by 0.99 €
- **THEN** it is not flagged
- **AND** with a media cost changed by 1.00 € it is flagged

#### Scenario: A delivered volume 1 % away is flagged
- **WHEN** a closed flight frozen with 300,000.0000 delivered OTS now has 303,000.0000 OTS and its current margin differs by less than 1.00 €
- **THEN** it is flagged `delivery_changed`
- **AND** with 302,999.9999 OTS it is not

#### Scenario: Delivery appearing after a closing with none is flagged
- **WHEN** a flight was closed with no delivery and 10 impressions are stored in its window afterwards
- **THEN** it is flagged `delivery_changed`

#### Scenario: A restated target flight keeps the closing's rebate in its current margin
- **WHEN** the closed Deal flight of the worked example (revenue 4,400.00 €, gross 5,500.00 €, rebate 550.00 €, platform cost 1,100.00 € on 1,100,000 impressions at 1.00 €, margin 2,750.00 €) now has 1,300,000 served impressions, a reported revenue of 5,200.00 € and a buyer's spend of 6,500.00 € in its window
- **THEN** its current margin is 5,200.00 − 0.00 − 550.00 − 1,300.00, which is 3,350.00 €, a difference of 600.00 €
- **AND** its reported revenue differs by 800.00 € and its buyer's spend by 1,000.00 €
- **AND** it is flagged `delivery_changed`, and its revenue, gross, rebate and margin are still 4,400.00 €, 5,500.00 €, 550.00 € and 2,750.00 €

#### Scenario: A committed flight reports no revenue or spend difference
- **WHEN** a committed closed flight is checked
- **THEN** its reported revenue and buyer's spend differences are absent, and its current margin keeps its frozen revenue

#### Scenario: A running or pending-close flight is not checked
- **WHEN** a running flight or a flight pending close is read
- **THEN** it is not flagged `delivery_changed` and carries no check

## MODIFIED Requirements

### Requirement: Media cost is the Adform cost over the flight's window

The system SHALL compute the media cost of a flight as the sum of the `media_cost` of the line's daily deliveries dated from `flight_start` to `flight_end`, both included, and SHALL treat that column as the whole media cost, because it already includes every additional cost Adform charges. Equativ reports no media cost, so the media cost of a line on Equativ is zero; the buyer's spend is never a media cost. The media cost of a closed flight is the one its closing froze (requirement «A closed flight is read from its snapshot»): a later replacement of its days does not change it.

#### Scenario: Only the flight's window counts
- **WHEN** a line has flights in August and September and a delivery on 2026-09-02
- **THEN** that delivery's cost belongs to the September flight and not to the August one

#### Scenario: A delivery outside every flight counts nowhere
- **WHEN** a line has a delivery dated outside the window of all its flights
- **THEN** its cost belongs to no flight

#### Scenario: An Equativ line has no media cost
- **WHEN** a flight of a line on Equativ is calculated and its deliveries carry a buyer's spend of 5,500.00 €
- **THEN** its media cost is 0.00 €

#### Scenario: A restated cost after closing does not change a closed flight's media cost
- **WHEN** a closed flight's media cost was 1,200.00 € and a day of its window is restated after the closing to add 1,800.00 €
- **THEN** its media cost is still 1,200.00 €

### Requirement: The margin includes the platform cost

The system SHALL compute the margin of a flight as revenue less media cost, less agency rebate, less platform cost, each already rounded, and SHALL express the margin percentage as margin over revenue. The platform cost SHALL be computed on the delivered impressions for every channel, including a channel whose delivery metric is OTS. The platform cost of a closed flight is the one its closing froze, on the delivered impressions of that moment and the platform rate frozen with it.

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

#### Scenario: A restatement after closing does not change a closed flight's platform cost
- **WHEN** a flight closed with 700,000 delivered impressions at 1.00 € per thousand has 1,200,000 impressions in its window after a restatement
- **THEN** its platform cost is still 700.00 €

### Requirement: A target flight earns the revenue its DSP reports

The system SHALL compute the revenue of a flight whose line is `target` as the exact sum of the reported revenue of the line's daily deliveries dated from `flight_start` to `flight_end`, both included, up to `as_of`, rounded once to two decimals, half up. It SHALL NOT read the flight's target volume, the sale CPM or the buyer's spend for that revenue, SHALL NOT pro-rate it, and SHALL NOT apply the rule of the lesser of contracted and served, nor any manual adjustment. Its media cost is the stored media cost, which is zero for Equativ; its platform cost is on the served impressions; its rebate is computed on its served gross (`finance/rebate-accrual`); and its margin is revenue less media cost, less rebate, less platform cost, each rounded, with the margin percentage over that revenue. Once its month is closed, all of these are the ones its closing froze (requirement «A closed flight is read from its snapshot»).

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

The system SHALL compute, for a flight whose line is `target`, its gross as the served impressions inside its window divided by 1000 times the line's sale CPM, rounded once to two decimals, half up; a `committed` flight has no gross. It SHALL flag a target flight `gross_differs_from_buyer_spend` when its gross differs from the sum of the buyer's spend inside its window, rounded to two decimals, by more than 1 % of that spend, or when the spend is zero and the gross is not. It SHALL flag any flight `data_cost_reported` when the sum of its third-party data cost or of its audience data cost inside its window is above zero. Neither flag nor the data costs SHALL change any amount: the data costs are never subtracted from the margin. A closed flight's gross and both flags are the ones its closing froze; a later restatement of its spend or its data costs does not change them.

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

#### Scenario: A spend restated after closing does not raise the flag
- **WHEN** the Deal flight of the worked example was closed with a buyer's spend of 5,500.00 € and its spend is restated to 6,500.00 € afterwards
- **THEN** it is still not flagged `gross_differs_from_buyer_spend`, and its gross is still 5,500.00 €
