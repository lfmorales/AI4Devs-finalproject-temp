# campaign/carryover Specification

## Purpose
Lets Operations and Trading carry, case by case, the volume a flight did not deliver to the next flight of the same line, raising that flight's delivery target without touching the contracted volume or the purchase order, and lets Operations and Finance decide whether the carried volume can be billed.

## Requirements

### Requirement: A carry-over is written on the flight that receives it

The system SHALL expose `PUT /flights/{flight_id}/carryover`, restricted to the `operations` and `trading` roles, where `flight_id` is the flight that receives the volume, taking `volume`, a whole number zero or above in the delivery metric of the line's channel, and a mandatory `reason`. It SHALL store on that flight the volume, the reason, the user who made the request and the moment, replacing the carry-over it had; a volume of zero removes it. The flight's contracted volume, its line's volume and its purchase order SHALL NOT change. The system SHALL answer 200 with the flight's id, its `delivery_metric`, its contracted volume, its carry-over, its delivery target (the contracted volume plus the carry-over), the reason, the author and the moment, and with no amount, no billable flag and nothing of a billing adjustment.

The previous flight is the flight of the same line with the latest window before the receiving flight's. The system SHALL reject the carry-over, writing nothing, with:

- 404 `flight_not_found` when the flight does not exist;
- 409 `no_previous_flight` when the flight is the first of its line;
- 409 `previous_flight_not_ended` when the previous flight has not ended by D-1;
- 409 `carryover_exceeds_shortfall` when the volume is above the previous flight's shortfall: its own delivery target less the volume its line delivered inside its window as stored now, or zero when it delivered its target; the message names the shortfall;
- 409 `month_closed` when the receiving flight's month holds a closing header;
- 422 when the volume is missing, negative or not a whole number, or the reason is missing or blank.

#### Scenario: Undelivered October volume is carried to November
- **WHEN** a committed line at 5.00 € has an October 2026 flight of 500,000 contracted impressions that delivered 400,000 and a November flight of 500,000, and Trading puts a carry-over of 100,000 on the November flight with the reason «Recuperar lo no entregado en octubre»
- **THEN** the response is 200 with `contracted_impressions` 500000, `carryover` 100000 and `delivery_target` 600000, the reason, the author and the moment
- **AND** the November flight's contracted volume is still 500,000 and the purchase order is unchanged

#### Scenario: The carry-over cannot exceed the shortfall
- **WHEN** the same carry-over is put with a volume of 100,001
- **THEN** the response is 409 `carryover_exceeds_shortfall` naming a shortfall of 100,000, and nothing is written

#### Scenario: A previous flight that delivered its target leaves nothing to carry
- **WHEN** the October flight delivered 520,000 impressions and a carry-over of 1 is put on November
- **THEN** the response is 409 `carryover_exceeds_shortfall` naming a shortfall of 0

#### Scenario: The shortfall counts the previous flight's own carry-over
- **WHEN** an October flight of 500,000 contracted impressions with a carry-over of 50,000 from September delivered 480,000
- **THEN** the November flight can receive at most 70,000

#### Scenario: December carries to January
- **WHEN** a line's December 2026 flight fell 50,000 impressions short and its January 2027 flight receives a carry-over of 50,000
- **THEN** the response is 200 and the January flight's delivery target is its contracted volume plus 50,000

#### Scenario: The first flight of a line has nothing to receive
- **WHEN** a carry-over is put on the first flight of a line
- **THEN** the response is 409 `no_previous_flight`

#### Scenario: The previous flight must have ended
- **WHEN** a carry-over is put on a flight whose previous flight ends after D-1
- **THEN** the response is 409 `previous_flight_not_ended`

#### Scenario: A closed month receives no carry-over
- **WHEN** a carry-over is put on a flight whose month holds a closing header
- **THEN** the response is 409 `month_closed` and nothing is written

#### Scenario: The reason is mandatory
- **WHEN** a carry-over is put with no reason, or with a reason of only spaces
- **THEN** the response is 422 and nothing is written

#### Scenario: A volume of zero removes the carry-over
- **WHEN** a carry-over of 0 is put on the November flight with a reason
- **THEN** its carry-over is 0 and its delivery target is its contracted volume

### Requirement: Operations and Finance decide whether a carry-over is billable

The system SHALL hold on the receiving flight a billable flag, false by default, and SHALL expose `PUT /billing/flights/{flight_id}/carryover/billable`, restricted to the `operations` and `finance` roles, taking `billable` true or false and storing it with the user who made the request and the moment. With the flag false, the cap of the flight's billing is its contracted volume; with the flag true, it is its contracted volume plus its carry-over (`finance/margin-calculation`). The flag SHALL keep its value when the carry-over's volume changes. The system SHALL answer 200 with the flight's id, its carry-over, the flag, the author and the moment, and SHALL reject the request, writing nothing, with 404 `flight_not_found`, 409 `target_line_not_adjustable` for a flight of a `target` line, 409 `no_carryover` when setting true on a flight without a carry-over, and 409 `month_closed` when the flight's month holds a closing header.

#### Scenario: Not billable, the carry-over only moves the delivery target
- **WHEN** the November flight of 500,000 contracted impressions with a carry-over of 100,000, not billable, closes having delivered 580,000 at 5.00 € with a flat rebate of 25 %
- **THEN** its delivery target is 600,000, its billable volume 500,000, its revenue 2,500.00 € and its rebate 625.00 €
- **AND** the line bills 2,000.00 € in October and 2,500.00 € in November, 4,500.00 € in all

#### Scenario: Billable, the carry-over raises the cap
- **WHEN** Finance sets the November carry-over billable and the flight closes with the same delivery
- **THEN** its billable volume is 580,000, its revenue 2,900.00 € and its rebate 725.00 €, and its counter advances by 2,900.00 €
- **AND** the line bills 4,900.00 € in all, within the 5,000.00 € of its purchase order, which is unchanged

#### Scenario: A billable carry-over into January bills on the new year
- **WHEN** the January 2027 flight with a billable carry-over of 50,000 from December 2026 is closed
- **THEN** its billing, cap included, advances the 2027 counter

#### Scenario: A target flight has no billable carry-over
- **WHEN** the flag is set on a flight of a `target` line
- **THEN** the response is 409 `target_line_not_adjustable`

#### Scenario: There must be something to bill
- **WHEN** the flag is set true on a flight with no carry-over
- **THEN** the response is 409 `no_carryover`

### Requirement: Changing a carry-over or its flag returns the campaign to pending review

The system SHALL return the receiving flight's campaign to pending review in the receiving flight's month, when it was reviewed (`finance/monthly-review`), every time the carry-over's volume, its reason or its billable flag is written.

#### Scenario: A carry-over reopens the campaign
- **WHEN** a campaign is reviewed in November 2026 and Trading writes a carry-over on one of its November flights
- **THEN** the campaign is pending review in November 2026

#### Scenario: The flag reopens the campaign
- **WHEN** a campaign is reviewed in November 2026 and Finance sets a carry-over of one of its November flights billable
- **THEN** the campaign is pending review in November 2026

### Requirement: Errors of the carry-over route are code and message

The system SHALL answer every error of `PUT /flights/{flight_id}/carryover`, including a validation error, with a body of exactly `code` and `message`, and no error of it SHALL carry an amount.

#### Scenario: A validation error of the carry-over
- **WHEN** a carry-over is put with a negative volume
- **THEN** the response is 422 with only `code` and `message`

### Requirement: The status screen writes a carry-over

The system SHALL offer, on each row of the status screen, to a user holding `operations` or `trading`, an action «Arrastre» that asks for the volume and the reason and puts the carry-over, and SHALL show the error of the response in Spanish when it is refused, naming the shortfall when it is exceeded. The billing screen SHALL offer the billable flag, labelled «Arrastre facturable», only to a user holding `operations` or `finance`. Neither screen SHALL compute a shortfall or a delivery target: both come from the responses.

#### Scenario: Trading writes a carry-over from the status screen
- **WHEN** a user holding only `trading` writes a carry-over of 100,000 on the November row with a reason
- **THEN** the row shows «Arrastre» 100.000 and «Objetivo de entrega» 600.000

#### Scenario: A refused carry-over names the shortfall
- **WHEN** the carry-over is refused with `carryover_exceeds_shortfall`
- **THEN** the screen shows the message with the shortfall of the response

#### Scenario: Trading never sees the billable flag
- **WHEN** a user holding only `trading` opens the status screen
- **THEN** no «Arrastre facturable» control or value is shown
