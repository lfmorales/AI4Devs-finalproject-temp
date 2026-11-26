## Purpose

Lets Operations and Finance set, before the closing, the billing of a committed flight that ended to something other than the rule of the lesser, with a reason, an author and a date that are kept, and freezes the adjustment in force with the month.

## ADDED Requirements

### Requirement: An ended, unfrozen committed flight can have its billing adjusted

The system SHALL expose `POST /billing/flights/{flight_id}/adjustments`, restricted to the `operations` and `finance` roles, taking a `basis` and a `reason`, and an `amount` only when the basis is `custom`. The bases SHALL be:

- `minimum`: the rule of the lesser of the delivered volume and the cap (`finance/margin-calculation`);
- `delivered`: the delivered volume of the flight's window, with no cap;
- `contracted`: the flight's billing cap, its contracted volume plus its carry-over when the carry-over is billable (`campaign/carryover`);
- `custom`: the `amount` given, a decimal string with at most two decimals, zero or above.

With the first three, the billing is the volume of the basis divided by 1000 times the line's sale CPM, rounded once to two decimals, and SHALL be computed again from the stored delivery on every read until the flight is closed. With `custom`, the billing is the amount, fixed. The `reason` is mandatory and SHALL NOT be blank. The system SHALL store the flight, the basis, the amount when `custom`, the reason, the user who made the request and the moment, and SHALL answer 201 with them and with the billing the flight has after it.

The system SHALL reject the adjustment, writing nothing, with:

- 404 `flight_not_found` when the flight does not exist;
- 409 `target_line_not_adjustable` when its line is `target`;
- 409 `flight_not_ended` when it has not ended by D-1;
- 409 `flight_closed` when it has frozen rates;
- 422 when the reason is missing or blank, the basis is unknown, the basis is `custom` without an amount, an amount is given with another basis, or the amount is negative or has more than two decimals.

#### Scenario: An under-delivered flight is billed at its contracted volume
- **WHEN** Finance adjusts the pending-close committed flight of 1,000,000 contracted impressions at 5.00 € that delivered 700,000, with a media cost of 1,200.00 €, a flat rebate of 25 % and a platform rate of 1.00 €, to the basis `contracted` with the reason «Acuerdo con la agencia: se factura la OC completa»
- **THEN** the response is 201 with the basis, the reason, the author, the moment and a billing of 5,000.00 €
- **AND** the flight's revenue is 5,000.00 €, its rebate 1,250.00 € and its margin 5,000.00 − 1,200.00 − 1,250.00 − 700.00, which is 1,850.00 €

#### Scenario: A custom amount is fixed
- **WHEN** the same flight is adjusted to `custom` with an amount of 4,200.00 € and a reason
- **THEN** its revenue is 4,200.00 €, its rebate 1,050.00 € and its margin 1,250.00 €
- **AND** a later ingestion that changes its delivered impressions does not change its revenue

#### Scenario: The delivered basis follows the delivery until the closing
- **WHEN** the same flight is adjusted to `delivered` and its window is ingested again with 720,000 impressions before its month is closed
- **THEN** its revenue goes from 3,500.00 € to 3,600.00 €

#### Scenario: The contracted basis bills the cap, with a billable carry-over
- **WHEN** a pending-close flight of 500,000 contracted impressions at 5.00 € with a carry-over of 100,000 delivered 450,000 and is adjusted to `contracted` with a reason
- **THEN** with the carry-over not billable its revenue is 500,000 / 1000 × 5.00, which is 2,500.00 €
- **AND** with the carry-over billable its revenue is 600,000 / 1000 × 5.00, which is 3,000.00 €

#### Scenario: The delivered basis bills an over-delivery
- **WHEN** a pending-close flight of 1,000,000 contracted impressions at 5.00 € that delivered 1,100,000 is adjusted to `delivered`
- **THEN** its revenue is 5,500.00 €

#### Scenario: A zero amount is accepted
- **WHEN** a flight is adjusted to `custom` with an amount of 0.00 and a reason
- **THEN** the response is 201 and its revenue and rebate are 0.00 €

#### Scenario: The reason is mandatory
- **WHEN** an adjustment is posted with no reason, or with a reason of only spaces
- **THEN** the response is 422 and nothing is written

#### Scenario: The amount belongs to the custom basis only
- **WHEN** an adjustment is posted with the basis `custom` and no amount, or with the basis `contracted` and an amount
- **THEN** the response is 422 and nothing is written

#### Scenario: A negative amount is refused
- **WHEN** an adjustment is posted with the basis `custom` and an amount of −1.00
- **THEN** the response is 422 and nothing is written

#### Scenario: A target flight is never adjusted
- **WHEN** an adjustment is posted for a flight of a `target` line
- **THEN** the response is 409 `target_line_not_adjustable` and nothing is written

#### Scenario: A running flight is not adjusted
- **WHEN** an adjustment is posted for a flight whose `flight_end` is after D-1
- **THEN** the response is 409 `flight_not_ended` and nothing is written

#### Scenario: A frozen flight is not adjusted
- **WHEN** an adjustment is posted for a flight whose month was closed with it
- **THEN** the response is 409 `flight_closed` and nothing is written

#### Scenario: An unknown flight
- **WHEN** an adjustment is posted for a flight id that does not exist
- **THEN** the response is 404 `flight_not_found`

### Requirement: Adjustments are only added and the latest is in force

The system SHALL never update or delete an adjustment. The adjustment in force on a flight SHALL be its latest one; a flight with none follows the rule of the lesser. An adjustment to `minimum` returns the flight to the rule and stays in the history. The system SHALL expose `GET /billing/flights/{flight_id}/adjustments`, restricted to the `operations` and `finance` roles, returning every adjustment of the flight, latest first, with its basis, amount, reason, author and moment, and which one is in force; 404 `flight_not_found` when the flight does not exist.

#### Scenario: The latest adjustment wins
- **WHEN** a flight is adjusted to `contracted` and then to `custom` with 4,200.00 €
- **THEN** its revenue is 4,200.00 € and the history lists both, the custom one first and in force

#### Scenario: Returning to the rule keeps the history
- **WHEN** a flight adjusted to `contracted` is then adjusted to `minimum`
- **THEN** its revenue is the billing of the rule and its history lists both adjustments

#### Scenario: The database refuses to change an adjustment
- **WHEN** an update or a delete of an adjustment row is attempted in the database
- **THEN** it is refused

### Requirement: The adjusted billing moves the rebate, the counter and the review

The system SHALL price the rebate of an adjusted flight on its adjusted billing, SHALL advance its counter by it when the flight is closed (`finance/rebate-accrual`), and SHALL return the flight's campaign to pending review in the flight's month when it was reviewed (`finance/monthly-review`). The adjustment in force when the month is closed SHALL be frozen in the flight's snapshot with its basis and its billing; an adjustment made after the closing is impossible.

#### Scenario: An adjustment reopens a reviewed campaign
- **WHEN** a campaign is reviewed in October 2026 and one of its October flights is adjusted
- **THEN** the campaign is pending review in October 2026

#### Scenario: The closing freezes the adjustment in force
- **WHEN** a flight adjusted to `custom` with 4,200.00 € is closed
- **THEN** its snapshot holds a revenue of 4,200.00 €, the basis `custom` and the adjustment
- **AND** a later read of the flight shows 4,200.00 € whatever its delivery
