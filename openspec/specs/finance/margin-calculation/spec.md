# finance/margin-calculation Specification

## Purpose
The per-flight, per-line and per-campaign economics — what a campaign earned, what it cost and what it left — computed from explicit rules that can be read, tested and argued with, rather than reconstructed from chart expressions.

A **flight** is one campaign line in one calendar month: a row of `campaign_line_periods` with `flight_start`, `flight_end` and its own `contracted_impressions`. The flight is the unit of calculation.

## Requirements

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

### Requirement: Monetary calculation keeps exact precision

The system SHALL perform every monetary and rate calculation in exact decimal arithmetic.

#### Scenario: A rate applied across a year does not drift
- **WHEN** rebate amounts are accumulated across a year of flights
- **THEN** the total equals the sum of the individual amounts exactly

### Requirement: A flight with a negative margin is flagged

The system SHALL flag as `below_cost`, labelled "Margen negativo", a flight whose final margin is below zero, that is revenue less media cost, less rebate, less platform cost, each amount rounded before it is subtracted. It SHALL report on its line and its campaign how many of their flights are flagged, and SHALL NOT alter any total because of the flag.

#### Scenario: A negative final margin is surfaced
- **WHEN** a flight's revenue less media cost, rebate and platform cost, each rounded, is below zero
- **THEN** the flight is flagged `below_cost`
- **AND** its line and its campaign count it
- **AND** it still contributes its true value to every total

#### Scenario: A media cost above revenue is not the test
- **WHEN** a flight's media cost is below its revenue but the rebate and the platform cost take the final margin below zero
- **THEN** the flight is flagged `below_cost`

#### Scenario: A media cost above revenue is always flagged
- **WHEN** a flight's media cost exceeds its revenue
- **THEN** its final margin is negative, because the rebate and the platform cost are never negative
- **AND** the flight is flagged `below_cost`

#### Scenario: A margin of exactly zero is not flagged
- **WHEN** a flight's final margin is 0.00
- **THEN** it is not flagged

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

### Requirement: The margin percentage is over revenue and never divides by zero

The system SHALL express `margin_pct` of a flight, a line, a campaign and the totals as a decimal string with two decimals, half up, in percentage points of revenue, and SHALL give it as null when revenue is 0. No calculation divides by revenue without checking it.

#### Scenario: The percentage of the worked example
- **WHEN** a flight has revenue 3,631.01 € and margin 823.26 €
- **THEN** `margin_pct` is "22.67"

#### Scenario: A negative margin has a negative percentage
- **WHEN** a flight has revenue 1,000.00 € and margin -50.00 €
- **THEN** `margin_pct` is "-5.00"

#### Scenario: Revenue of zero has no percentage
- **WHEN** revenue is 0.00 €
- **THEN** `margin_pct` is null, at the flight and at every level above

#### Scenario: A half rounds up
- **WHEN** margin over revenue is exactly 12.345 percentage points
- **THEN** `margin_pct` is "12.35"

### Requirement: Contracted volume of zero is outside this cut

The system SHALL keep rejecting a line whose contracted impressions are 0 at registration, and a campaign with zero contracted volume (a zero sale with no purchase order) and delivery with no purchase cost (pixels) are **not part of the margin in this cut**: their delivery remains unmatched delivery in the exception queue.

#### Scenario: Registration refuses a volume of zero
- **WHEN** a line is registered with contracted impressions of 0
- **THEN** the request is rejected

### Requirement: Margin access is restricted to operations and finance

The system SHALL restrict every cost and margin figure to users holding the `operations` or the `finance` role, enforced at the endpoint.

#### Scenario: A user without the role is forbidden
- **WHEN** a user holding `business` or `trading`, and neither `operations` nor `finance`, requests a margin resource
- **THEN** the request is rejected as forbidden

#### Scenario: A missing or invalid token is unauthenticated
- **WHEN** a margin endpoint is called without a token or with an invalid one
- **THEN** the request is rejected as unauthenticated, a distinct outcome from forbidden

#### Scenario: The restriction holds against direct API access
- **WHEN** a margin endpoint is called directly rather than through the interface
- **THEN** the same restriction applies

### Requirement: A flight that has ended but is not closed is pending close

The system SHALL treat a flight whose `flight_end` is on or before `as_of` and which has no frozen rates as **pending close**: calculated on the fly with the rates in force, marked provisional, writing nothing, and using the same opening counter positions and the same domain function that closing the month will use.

#### Scenario: A pending-close flight is calculated without being written
- **WHEN** a flight ended on 2026-08-31, `as_of` is 2026-09-05 and August has not been closed
- **THEN** its state is `pending_close` and it is marked provisional
- **AND** no `applied_rates` row exists afterwards

#### Scenario: The pending-close figure is the figure that closing freezes
- **WHEN** three flights of one counter are read as pending close and the month is then closed
- **THEN** the margin read afterwards from the frozen rows equals the pending-close margin to the cent, for every flight

#### Scenario: Closing and reading call the same function
- **WHEN** the closing and the pending-close read compute a flight's rebate
- **THEN** both go through one domain function over the same inputs, so they cannot diverge

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

### Requirement: A closed flight is read from its snapshot

The system SHALL take the revenue, contracted revenue, media cost, rebate, platform cost, margin, gross, delivered impressions, delivered volume, billable volume, billing basis, carry-over and its billable flag, the flags `gross_differs_from_buyer_spend` and `data_cost_reported`, the delivery metric, the contracted volume and the volume commitment of a closed flight from the snapshot its closing stored (`finance/rebate-accrual`), and SHALL NOT compute any of them again from the stored delivery, the line, the channel, the rates, the adjustments or the carry-over. A closed flight is never pro-rated and never provisional: its `accrued_days` equals its `window_days`, both counted from its own dates. Its `below_cost` SHALL be its frozen margin below zero, its `zero_sale` its frozen sale CPM equal to zero, and its `margin_pct` its frozen margin over its frozen revenue, with the rules of this specification. A snapshot stored before this change has no billable volume, billing basis or carry-over: its flight keeps the revenue it was closed with and reports those three as null. The rules of the other requirements of this specification give the figures a flight has until it is closed, and so the figures its closing freezes.

#### Scenario: A closed flight reads its frozen figures whatever the delivery says
- **WHEN** a closed flight's stored delivery is replaced after the closing with more impressions and a higher media cost
- **THEN** its revenue, billable volume, media cost, rebate, platform cost, margin, delivered impressions and delivered volume are those of its snapshot

#### Scenario: Closing and reading after the closing agree to the cent
- **WHEN** a flight is read as pending close, its month is closed, and it is read again with no change to its delivery
- **THEN** every amount, volume and flag read after the closing equals the one read before it

#### Scenario: An adjustment or a carry-over after closing does not move a closed flight
- **WHEN** a closed flight's line later receives an adjustment on another flight, or the next flight of its line receives a carry-over
- **THEN** its revenue, billable volume, billing basis and carry-over are those of its snapshot

#### Scenario: The flags of a closed flight are frozen
- **WHEN** the buyer's spend of a closed target flight is restated so that its gross differs from it by more than 1 %, and a data cost appears inside its window
- **THEN** its `gross_differs_from_buyer_spend` and `data_cost_reported` are those frozen at closing

#### Scenario: A negative frozen margin stays flagged
- **WHEN** a flight was closed with a margin of −20.00 € and its delivery is later restated so that its current margin would be positive
- **THEN** it is still flagged `below_cost` with a margin of −20.00 €

#### Scenario: A flight closed before this change keeps its revenue
- **WHEN** a committed flight closed before this change with a revenue of 5,000.00 € on 1,000,000 contracted impressions and 700,000 delivered is read
- **THEN** its revenue is still 5,000.00 € and its billable volume, billing basis and carry-over are null

### Requirement: A closed flight is checked against its current delivery

The system SHALL compare every closed flight with the delivery stored now inside its window, and SHALL flag it `delivery_changed` when its current margin differs from its frozen margin by 1.00 € or more, in either direction, or when its current delivered volume differs from its frozen delivered volume by 1 % or more of the frozen volume; a frozen delivered volume of zero is exceeded by any current volume that is not zero. The check SHALL change no amount, no volume, no flag and no total of the flight or of any level above it.

The check SHALL report, each as the current value less the frozen one: the difference of the delivered volume (four decimals), of the delivered impressions (an integer), of the media cost (both rounded to two decimals before subtracting); for a `target` flight only, of the reported revenue and of the buyer's spend (both rounded to two decimals before subtracting); and, for a `committed` flight closed with this change, of the billable volume (four decimals) and of the billing (two decimals). It SHALL also report the current margin and its difference from the frozen margin. The current margin is the frozen margin's formula with only the delivery changed:

- the revenue is the current billing for a `committed` flight closed with this change: its billable volume recomputed on the current delivered volume with the cap frozen in its snapshot (its contracted volume, plus its carry-over when the carry-over was billable), at the frozen sale CPM, rounded; with a frozen billing basis of `contracted` it is the billing of the frozen cap, with `delivered` the current delivered volume's, and with `custom` the frozen revenue;
- the revenue is the frozen one for a `committed` flight closed before this change, and the current reported revenue, rounded, for a `target` flight;
- the media cost is the current one, rounded; the rebate is the frozen one; the platform cost is the current delivered impressions divided by 1000 times the frozen platform rate, rounded; and the margin is revenue less media cost, less rebate, less platform cost.

No rebate, rate, adjustment, carry-over or master is resolved again for it. A flight that is not closed is not checked.

#### Scenario: The restated committed flight of the example is flagged
- **WHEN** the committed flight of 1,000,000 contracted impressions at 5.00 € closed with 700,000 delivered impressions, a revenue of 3,500.00 €, a media cost of 1,200.00 €, a rebate of 875.00 € (25 %), a platform cost of 700.00 € at 1.00 € and a margin of 725.00 € now has 1,200,000 delivered impressions and a media cost of 3,000.00 € in its window
- **THEN** its current billable volume is 1,000,000, its current billing 5,000.00 €, and its current margin 5,000.00 − 3,000.00 − 875.00 − 1,200.00, which is −75.00 €, a difference of −800.00 €
- **AND** its delivered impressions differ by 500,000, its billable volume by 300,000, its billing by 1,500.00 € and its media cost by 1,800.00 €, and it is flagged `delivery_changed`
- **AND** its revenue is still 3,500.00 € and its margin still 725.00 €

#### Scenario: A flight closed before this change keeps comparing with its frozen revenue
- **WHEN** a committed flight closed before this change with a revenue of 5,000.00 €, a media cost of 1,200.00 €, a rebate of 1,250.00 €, a platform cost of 700.00 € on 700,000 impressions at 1.00 € and a margin of 1,850.00 € now has 1,200,000 delivered impressions and a media cost of 3,000.00 €
- **THEN** its current margin is 5,000.00 − 3,000.00 − 1,250.00 − 1,200.00, which is −450.00 €, a difference of −2,300.00 €
- **AND** its billable volume and billing differences are null
- **AND** with its stored delivery equal to the one it was closed with, it is not flagged

#### Scenario: A custom billing does not move with the delivery
- **WHEN** a committed flight closed with a custom billing of 4,200.00 € has more delivered impressions in its window afterwards
- **THEN** its current billing is 4,200.00 € and its billing difference is 0.00

#### Scenario: A delivery equal to the frozen one raises nothing
- **WHEN** a closed flight's stored delivery is the one it was closed with
- **THEN** every difference is zero, its current margin equals its margin, and it is not flagged

#### Scenario: A margin difference of 1.00 € is flagged and 0.99 € is not
- **WHEN** a closed flight's current delivery differs from the frozen one only in its media cost, by 0.99 €
- **THEN** it is not flagged
- **AND** with a media cost changed by 1.00 € it is flagged

#### Scenario: A delivered volume 1 % away is flagged
- **WHEN** a closed DOOH flight with 300,000 contracted OTS, frozen with 300,000.0000 delivered OTS, now has 303,000.0000 OTS, so that its billing stays at its cap and its current margin differs by less than 1.00 €
- **THEN** it is flagged `delivery_changed`
- **AND** with 302,999.9999 OTS it is not

#### Scenario: Delivery appearing after a closing with none is flagged
- **WHEN** a flight was closed with no delivery and 10 impressions are stored in its window afterwards
- **THEN** it is flagged `delivery_changed`

#### Scenario: A restated target flight keeps the closing's rebate in its current margin
- **WHEN** the closed Deal flight of the worked example (revenue 4,400.00 €, gross 5,500.00 €, rebate 550.00 €, platform cost 1,100.00 € on 1,100,000 impressions at 1.00 €, margin 2,750.00 €) now has 1,300,000 served impressions, a reported revenue of 5,200.00 € and a buyer's spend of 6,500.00 € in its window
- **THEN** its current margin is 5,200.00 − 0.00 − 550.00 − 1,300.00, which is 3,350.00 €, a difference of 600.00 €
- **AND** its reported revenue differs by 800.00 € and its buyer's spend by 1,000.00 €, and its billable volume and billing differences are null
- **AND** it is flagged `delivery_changed`, and its revenue, gross, rebate and margin are still 4,400.00 €, 5,500.00 €, 550.00 € and 2,750.00 €

#### Scenario: A committed flight reports no revenue or spend difference
- **WHEN** a committed closed flight is checked
- **THEN** its reported revenue and buyer's spend differences are absent

#### Scenario: A running or pending-close flight is not checked
- **WHEN** a running flight or a flight pending close is read
- **THEN** it is not flagged `delivery_changed` and carries no check

### Requirement: The revenue of a committed flight is its billing

The system SHALL compute the revenue of a flight whose line is `committed` as its billing: its billable volume divided by 1000 times the sale CPM of its line, rounded once to two decimals, half up. The billable volume SHALL be the lesser of the flight's delivered volume and its cap, both in the delivery metric of the line's channel (OTS for `DOOH`, impressions for every other channel), the delivered volume with its decimals. The cap SHALL be the flight's contracted volume, held in `contracted_impressions` whatever the metric, or its contracted volume plus its carry-over when the carry-over is billable (`campaign/carryover`). A manual adjustment in force replaces this billing (`finance/billing-adjustment`). The revenue SHALL NOT depend on the purchase order version, which may be absent, and SHALL NOT read the delivered impressions of a channel counted in OTS. The revenue of a flight whose line is `target` is the revenue its DSP reports (requirement «A target flight earns the revenue its DSP reports»), with no cap and no adjustment.

#### Scenario: A flight that delivered its volume bills its contracted volume
- **WHEN** a closed flight has 726,202 contracted impressions, delivered 726,202 or more, and its line has a sale CPM of 5.00 €
- **THEN** its billable volume is 726,202 and its revenue is 3,631.01 €

#### Scenario: Under-delivery reduces revenue
- **WHEN** a closed flight contracted for 1,000,000 impressions at 5.00 € delivered 700,000
- **THEN** its billable volume is 700,000 and its revenue is 3,500.00 €, not 5,000.00 €
- **AND** its contracted revenue is still 5,000.00 €

#### Scenario: Over-delivery does not raise revenue
- **WHEN** a closed flight contracted for 291,610 impressions at 6.00 € delivered 296,052
- **THEN** its billable volume is 291,610 and its revenue is 1,749.66 €

#### Scenario: A line without a purchase order still has revenue
- **WHEN** a flight belongs to a line with no purchase order version
- **THEN** its revenue is computed from its billable volume and the line's sale CPM

#### Scenario: A DOOH flight bills its delivered OTS
- **WHEN** a closed DOOH flight has 300,000 contracted OTS at a sale CPM of 5.00 € and delivered 280,000.50 OTS and 12,000 impressions
- **THEN** its billable volume is 280,000.5000 OTS and its revenue is 280,000.50 / 1000 × 5.00, which is 1,400.0025 €, rounded once to 1,400.00 €
- **AND** the delivered impressions do not appear in the revenue calculation

#### Scenario: A billable carry-over raises the cap
- **WHEN** a closed flight with 500,000 contracted impressions at 5.00 € received a carry-over of 100,000 impressions and delivered 580,000
- **THEN** with the carry-over not billable its billable volume is 500,000 and its revenue 2,500.00 €
- **AND** with the carry-over billable its billable volume is 580,000 and its revenue 2,900.00 €

#### Scenario: The rebate and the counter follow the billing
- **WHEN** the closed flight of 1,000,000 contracted impressions at 5.00 € that delivered 700,000 is priced at a flat rebate of 25 %
- **THEN** its rebate is 875.00 € and closing its month advances its counter by 3,500.00 €

#### Scenario: The closed month of the Finance sheet bills ten campaigns less
- **WHEN** the 51 compared rows of the closed-month sheet are priced as closed flights of `Directo` with the new rule, each with its own contracted volume, served impressions, CPM, rebate rate and platform rate, and rounded as this specification says
- **THEN** exactly these ten rows change, each because it served less than it contracted, and every other row keeps its revenue, rebate and margin:

  | Row | Served | Contracted | CPM | Rebate rate | Revenue before → after | Rebate before → after | Margin before → after |
  |---|---:|---:|---:|---:|---|---|---|
  | Campaign 8 | 956,014 | 999,999 | 4.50 | 40 % | 4,500.00 → 4,302.06 | 1,800.00 → 1,720.82 | 629.28 → 510.52 |
  | Campaign 10 | 54,599 | 60,000 | 9.00 | 40 % | 540.00 → 491.39 | 216.00 → 196.56 | 207.42 → 178.25 |
  | Campaign 28 | 177,466 | 195,000 | 9.00 | 40 % | 1,755.00 → 1,597.19 | 702.00 → 638.88 | 748.56 → 653.87 |
  | Campaign 37 | 172,539 | 178,294 | 6.00 | 25 % | 1,069.76 → 1,035.23 | 267.44 → 258.81 | 529.93 → 504.03 |
  | Campaign 42 | 22,000 | 41,143 | 4.50 | 35 % | 185.14 → 99.00 | 64.80 → 34.65 | 86.86 → 30.87 |
  | Campaign 47 | 163,678 | 164,950 | 10.00 | 25 % | 1,649.50 → 1,636.78 | 412.38 → 409.20 | 1,002.38 → 992.84 |
  | Campaign 50 | 295,590 | 396,821 | 6.76 | none | 2,682.51 → 1,998.19 | 0.00 → 0.00 | 2,277.79 → 1,593.47 |
  | Campaign 51 | 13,648 | 15,000 | 9.00 | 40 % | 135.00 → 122.83 | 54.00 → 49.13 | 63.87 → 56.57 |
  | Campaign 52 | 13,666 | 15,000 | 9.00 | 40 % | 135.00 → 122.99 | 54.00 → 49.20 | 63.91 → 56.70 |
  | Campaign 53 | 13,649 | 15,000 | 9.00 | 40 % | 135.00 → 122.84 | 54.00 → 49.14 | 63.94 → 56.64 |

- **AND** the revenue of the compared rows goes from 171,771.61 € to 170,513.20 €, 1,258.41 € less, and their margin from 64,506.31 € to 63,466.13 €, 1,040.18 € less, so the margin over total revenue goes from 37.55 % to 37.22 %
- **AND** the number of rows with a negative margin stays 1

### Requirement: A running flight bills its delivery to date and is labelled provisional

The system SHALL receive a date `as_of`, the last day counted (D-1), and SHALL treat a flight as closed when `flight_end <= as_of`, as not started when `flight_start > as_of` and as running otherwise. A running flight whose line is `committed` SHALL earn its billing to date: the lesser of its delivered volume from `flight_start` to `as_of` and its cap, divided by 1000 times the sale CPM, rounded once, with the cap and the rules of requirement «The revenue of a committed flight is its billing». Neither its revenue nor its rebate SHALL be pro-rated by elapsed days: its rebate is computed on its billing to date. A running flight whose line is `target` earns the revenue its DSP reported up to `as_of`, not pro-rated either. A running flight SHALL be marked provisional and SHALL NOT write anything. `accrued_days` and `window_days` are still reported (`finance/margin-reporting`) and drive no amount.

#### Scenario: A running committed flight bills what it delivered to date
- **WHEN** a flight from 2026-09-01 to 2026-09-30 has 300,000 contracted impressions at 5.00 €, `as_of` is 2026-09-10 and it has delivered 90,000 impressions
- **THEN** its revenue is 90,000 / 1000 × 5.00, which is 450.00 €, and not 300,000 × 10 / 30 at 5.00 €
- **AND** with a flat rebate of 20 % its rebate is 90.00 €

#### Scenario: A running flight is a complete worked example
- **WHEN** the flight above has a media cost of 150.00 € (a placeholder) and the platform rate is 1.00 €
- **THEN** the platform cost is 90.00 €
- **AND** the margin is 450.00 − 150.00 − 90.00 − 90.00, which is 120.00 €
- **AND** the figure is marked provisional

#### Scenario: A running flight ahead of its volume is capped
- **WHEN** the same flight has delivered 310,000 impressions by 2026-09-10
- **THEN** its revenue is 300,000 / 1000 × 5.00, which is 1,500.00 €

#### Scenario: A running flight with no delivery earns nothing
- **WHEN** a running committed flight has received no delivery
- **THEN** its revenue and its rebate are 0.00 €
- **AND** the figure is marked provisional

#### Scenario: The last day of a flight is closed on the day it is counted
- **WHEN** a flight ends on 2026-09-30 and `as_of` is 2026-09-30
- **THEN** the flight is closed and bills its whole window

#### Scenario: The day before the end is still running
- **WHEN** a flight ends on 2026-09-30 and `as_of` is 2026-09-29
- **THEN** the flight is running, with 29 accrued days over 30, and provisional

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
- **THEN** the August flight is read from its snapshot and the September flight bills its delivery to date and is marked provisional
- **AND** the line total is the sum of both and is itself marked provisional
