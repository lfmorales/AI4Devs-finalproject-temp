# Campaign Registration Specification

## Purpose

Registering an advertising campaign from the purchase order the client sends, expanding it into the monthly periods the business reports on and the lines that carry contracted volume and sale price, against validated master references rather than free text.

## Requirements

### Requirement: Campaign registration requires the operations role

The system SHALL restrict campaign registration to users holding the `operations` role, enforced at the endpoint and never only in the interface.

#### Scenario: A user without the role is forbidden
- **WHEN** an authenticated user holding only `finance` submits a campaign registration
- **THEN** the request is rejected as forbidden
- **AND** no campaign, period or line is created

#### Scenario: An authenticated user unknown to the application is forbidden
- **WHEN** a request carries a valid token whose email has no matching user record
- **THEN** the request is rejected as forbidden
- **AND** no user record is created for that email

#### Scenario: A missing or invalid token is unauthenticated
- **WHEN** a request carries no token, or one that fails signature, expiry, issuer or audience validation
- **THEN** the request is rejected as unauthenticated, which is a distinct outcome from forbidden

### Requirement: A campaign expands into one period per calendar month

The system SHALL create one campaign period for each calendar month the campaign spans, with the first and last period clipped to the campaign's own start and end dates. The periods are the campaign's calendar, the months billing and the monthly close work on. They no longer own lines: a line hangs from the campaign, and the months it runs in are its flights.

#### Scenario: A multi-month campaign expands
- **WHEN** a campaign is registered running from 2026-08-01 to 2026-12-31
- **THEN** five campaign periods are created, one per month from August to December
- **AND** each carries its own period start and end dates

#### Scenario: A campaign starting mid-month is clipped
- **WHEN** a campaign is registered running from 2026-08-15 to 2026-09-30
- **THEN** the August period starts on 2026-08-15, not on 2026-08-01
- **AND** the September period covers the whole month

#### Scenario: A campaign within a single month produces one period
- **WHEN** a campaign is registered running from 2026-08-05 to 2026-08-20
- **THEN** exactly one period is created, bounded by those two dates

#### Scenario: A period belongs to the campaign and not to a line
- **WHEN** a campaign with two lines is registered over three months
- **THEN** three campaign periods exist, not six
- **AND** each line reaches the months it runs in through its flights

### Requirement: Contracted volume and sale price live on the line

The system SHALL hold the line's total contracted impressions and its sale CPM on the campaign line, and SHALL allow two lines of the same campaign to carry different values. The CPM is the same in every flight of a line: a different CPM is a different line. The line's volume in each month is held on its flight.

#### Scenario: Lines of one campaign carry different CPMs
- **WHEN** a campaign is given one line at 5.00 € CPM and another at 25.00 € CPM
- **THEN** both are accepted and stored independently
- **AND** neither value is promoted to the campaign header

#### Scenario: Contracted volume is never conflated with delivered volume
- **WHEN** a campaign line is stored
- **THEN** its contracted impressions are held in a field distinct from any delivered figure
- **AND** no single combined impressions field exists

#### Scenario: Monetary values keep exact precision
- **WHEN** a sale CPM of 4.375 € is submitted
- **THEN** it is stored as an exact decimal value, not as binary floating point

#### Scenario: A flight carries no price of its own
- **WHEN** a line runs over several months
- **THEN** every flight takes the line's sale CPM
- **AND** a price that changes during the campaign is registered as another line

### Requirement: Scope is validated and separate from the descriptive market

The system SHALL record a validated scope of `national` or `international` on every campaign line, and SHALL hold any descriptive market text in a separate field that does not participate in pricing.

#### Scenario: Descriptive market text is preserved separately
- **WHEN** a line is registered with scope `national` and market text `Nacional (Vigo)`
- **THEN** the scope is stored as `national`
- **AND** `Nacional (Vigo)` is preserved as descriptive text

#### Scenario: Scope cannot be omitted
- **WHEN** a line is submitted without a scope
- **THEN** the request is rejected with a validation error naming the field

#### Scenario: An unrecognised scope is rejected
- **WHEN** a line is submitted with a scope outside the accepted set
- **THEN** the request is rejected, and the value is not coerced into either bucket

### Requirement: Master references are validated, never created on the fly

The system SHALL reject a registration naming an agency, advertiser, DSP, channel, format, campaign type, sector or sales rep that does not exist in the corresponding master, and SHALL NOT create the missing record automatically.

#### Scenario: An unknown agency is rejected
- **WHEN** a registration names an agency absent from the agency master
- **THEN** the request is rejected with a message naming the unresolved value
- **AND** no agency record is created

#### Scenario: A known agency resolves to its holding group
- **WHEN** a registration names an agency present in the master
- **THEN** the campaign is linked to that agency
- **AND** the agency's holding group is reachable from it without further input

### Requirement: Purchase order and offer references are optional

The system SHALL allow a campaign to be registered without a purchase order reference, because most campaigns in the existing corpus carry none.

#### Scenario: A campaign without a purchase order is accepted
- **WHEN** a campaign is registered with no purchase order reference
- **THEN** the campaign is created with no purchase order linked
- **AND** its lines still carry their contracted volume and sale CPM, and their flights their monthly volume

#### Scenario: A campaign with a purchase order links to its version in force
- **WHEN** a campaign is registered with a purchase order reference
- **THEN** each line is linked to the purchase order version in force
- **AND** its flights are not linked to a version of their own

### Requirement: A line hangs from the campaign with its own dates

The system SHALL attach every campaign line to the campaign, number the lines of a campaign from 1 in the order the purchase order lists them with no repeated number, and give each line a start and an end date. The dates are optional in the purchase order and default to the campaign's. A line's dates SHALL fall within the campaign's; otherwise the registration is rejected with the code `line_dates_outside_campaign` as an unprocessable request. A line whose start is after its end, whether both dates are given or one of them is completed from the campaign's, is rejected with the code `line_dates_invalid` as an unprocessable request.

#### Scenario: Lines are numbered in purchase order sequence
- **WHEN** a campaign is registered with three lines
- **THEN** they are numbered 1, 2 and 3 in the order submitted
- **AND** two lines of one campaign never share a number

#### Scenario: A line without dates takes the campaign's
- **WHEN** a line is submitted with no start and no end date
- **THEN** it starts and ends on the campaign's start and end dates

#### Scenario: A line inside the campaign dates is accepted
- **WHEN** a line starts after the campaign starts and ends before the campaign ends
- **THEN** it keeps those dates

#### Scenario: A line ending before it starts is rejected
- **WHEN** a line is submitted with a start date after its end date
- **THEN** the request is rejected with the code `line_dates_invalid`
- **AND** no campaign, period or line is created

#### Scenario: A line outside the campaign dates is rejected
- **WHEN** a line starts before the campaign starts or ends after it ends
- **THEN** the request is rejected with the code `line_dates_outside_campaign`
- **AND** no campaign, period or line is created

### Requirement: A line's volume is split into one flight per month it runs in

The system SHALL give every line one flight for each calendar month its dates intersect, and none for any other month. A flight carries the window that month shares with the line, from `flight_start` to `flight_end`, and the line's contracted impressions in that month. There SHALL be at most one flight per line and month. The flights' volumes SHALL add up exactly to the line's total. A line running in a single month has a single flight carrying the whole total.

#### Scenario: A line spanning three months has three flights
- **WHEN** a line runs from 2026-08-15 to 2026-10-10
- **THEN** it has flights in August (15 to 31), September (1 to 30) and October (1 to 10)

#### Scenario: A line ending before the campaign has no flight afterwards
- **WHEN** a campaign runs from August to December and a line ends on 2026-09-20
- **THEN** the line has flights in August and September only

#### Scenario: A line in one month has one flight with the total
- **WHEN** a line runs inside a single month
- **THEN** it has one flight whose volume equals the line's total

#### Scenario: A line of a single day has one flight of one day
- **WHEN** a line starts and ends on the same date
- **THEN** it has one flight whose start and end are that date

### Requirement: Volume is split by days unless the purchase order states it

The system SHALL split a line's total across its flights in proportion to the number of days of each window, both ends included, in whole impressions. The remainder goes to the windows with the largest fractional share and, on a tie, to the earliest month, so the parts always add up to the total. If any flight would come out with zero impressions, the registration is rejected with the code `volume_too_small_for_flights` as an unprocessable request. When the purchase order carries `monthly_volumes` (year, month and volume), those volumes SHALL be used instead, and they SHALL cover exactly the months the line intersects, each with a positive volume, adding up exactly to the line's total. Otherwise the registration is rejected as an unprocessable request with one of these codes:

- `flight_volumes_incomplete`: a month the line intersects is missing, one it does not intersect is present, or a month is repeated.
- `flight_volumes_mismatch`: the volumes do not add up to the line's total.
- `flight_volume_not_positive`: a volume is zero or negative.

#### Scenario: Volume follows the days of each window
- **WHEN** a line of 100 impressions has flights of 31, 30 and 31 days
- **THEN** the flights carry 34, 32 and 34 impressions
- **AND** they add up to 100

#### Scenario: A clipped window carries a smaller share
- **WHEN** a line's first window covers half of its month
- **THEN** that flight carries a proportionally smaller volume than a whole month

#### Scenario: A total too small for its flights is rejected
- **WHEN** a line's total split by days leaves a flight with zero impressions
- **THEN** the request is rejected with the code `volume_too_small_for_flights`
- **AND** no campaign, period, line or flight is created

#### Scenario: Explicit monthly volumes are used as given
- **WHEN** a purchase order lists a volume for each month a line intersects and they add up to the line's total
- **THEN** each flight carries the volume listed for its month

#### Scenario: A month the line intersects has no volume
- **WHEN** `monthly_volumes` omits a month the line intersects
- **THEN** the request is rejected with the code `flight_volumes_incomplete`

#### Scenario: A month is listed twice or outside the line
- **WHEN** `monthly_volumes` repeats a month, or lists one the line does not intersect
- **THEN** the request is rejected with the code `flight_volumes_incomplete`

#### Scenario: The explicit volumes do not add up
- **WHEN** `monthly_volumes` adds up to one impression more or less than the line's total
- **THEN** the request is rejected with the code `flight_volumes_mismatch`

#### Scenario: A volume that is not positive is rejected
- **WHEN** `monthly_volumes` gives a month zero or a negative volume
- **THEN** the request is rejected with the code `flight_volume_not_positive`

### Requirement: The registration answers with each line and its flights

The system SHALL answer a registration with the campaign, its periods as the campaign's calendar, and its lines. Each line SHALL carry its number, its start and end dates, its total contracted impressions and a list of its flights, and each flight SHALL carry the identifier of its campaign period, the year and month, its start and end dates and its contracted impressions. A line SHALL NOT carry a campaign period of its own.

#### Scenario: A line over three months is answered with three flights
- **WHEN** a campaign with one line over three months is registered
- **THEN** the response has one line with three flights
- **AND** the flights' impressions add up to the line's total
- **AND** each flight's campaign period identifier is the identifier of one of the periods listed

#### Scenario: Two lines over two months are not duplicated
- **WHEN** a campaign with two lines over two months is registered
- **THEN** the response has two lines of two flights each, and two periods

#### Scenario: A failure leaves nothing stored
- **WHEN** any line of the registration is rejected, or storing the campaign fails halfway
- **THEN** no purchase order, campaign, period, line or flight remains

### Requirement: A line may have no sale price but never a negative one

The system SHALL accept a campaign line whose sale CPM is 0.00 when its contracted impressions are greater than zero, SHALL reject a negative sale CPM with a validation error naming the field, and SHALL keep rejecting contracted impressions of zero.

#### Scenario: A line without a price is registered
- **WHEN** a line is submitted with a sale CPM of 0.00 and contracted impressions of 500,000
- **THEN** the line is created with its flights and its volume split as for any other line

#### Scenario: A negative price is rejected
- **WHEN** a line is submitted with a sale CPM of -1.00
- **THEN** the request is rejected with a validation error naming `sale_cpm`
- **AND** nothing is created

#### Scenario: A volume of zero is still rejected
- **WHEN** a line is submitted with contracted impressions of 0, whatever its CPM
- **THEN** the request is rejected with a validation error naming `contracted_impressions`

### Requirement: Every line of a campaign shares one delivery metric

The system SHALL reject a registration whose lines name channels with different delivery metrics, as an unprocessable request with `{"code","message"}` and the code `mixed_delivery_metrics`, and SHALL create nothing: no campaign, period, line, flight or purchase order. Lines on different channels that share a delivery metric SHALL be accepted. This check SHALL run after the master references are validated, so that a registration naming an unknown channel is rejected for that channel.

#### Scenario: A DOOH line and a Directo line cannot share a campaign
- **WHEN** a registration has line 1 on `DOOH` (OTS) and line 2 on `Directo` (impressions)
- **THEN** the request is rejected with 422 and the code `mixed_delivery_metrics`
- **AND** no campaign, period, line, flight or purchase order is created

#### Scenario: Channels of the same metric share a campaign
- **WHEN** a registration has line 1 on `Directo`, line 2 on `Deal` and line 3 on `CTV`, all counted in impressions
- **THEN** the campaign is registered with its three lines

#### Scenario: A DOOH campaign registers its lines in OTS
- **WHEN** a registration has two lines on `DOOH` with 300,000 and 150,000 contracted volume
- **THEN** the campaign is registered and both volumes are OTS

#### Scenario: An unknown channel is reported before the metric
- **WHEN** a registration has line 1 on `Directo` and line 2 on a channel that does not exist
- **THEN** the request is rejected for the unknown channel, not with `mixed_delivery_metrics`
