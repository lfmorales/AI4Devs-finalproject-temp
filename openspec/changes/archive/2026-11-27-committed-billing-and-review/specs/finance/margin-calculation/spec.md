## MODIFIED Requirements

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

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Revenue derives from the flight's contracted volume
**Reason**: Confirmed by the business on 2026-11-26: a committed flight is invoiced at the lesser of what it delivered and what it contracted, so its revenue is its billing, no longer its contracted volume.
**Migration**: Replaced by «The revenue of a committed flight is its billing». Flights closed before this change keep the revenue frozen in their snapshot.

### Requirement: A running flight is pro-rated by contract days and labelled provisional
**Reason**: Confirmed by the business on 2026-11-26: a running committed flight earns its billing to date, with no pro-rating of its revenue or its rebate, like a target flight.
**Migration**: Replaced by «A running flight bills its delivery to date and is labelled provisional».
