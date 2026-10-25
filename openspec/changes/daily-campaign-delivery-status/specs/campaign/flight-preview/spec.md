## Purpose

Show operations, before they register a campaign, the flights a line would get and the volume each would carry, so the split by days is seen before it is stored.

## ADDED Requirements

### Requirement: A preview computes the flights of a line without storing anything

The system SHALL offer `POST /api/flights/preview` (the backend route is `/flights/preview`, the proxy strips `/api`) to users holding the `operations` role, enforced at the endpoint. It takes the campaign's start and end dates, the line's start and end dates, both optional and defaulting to the campaign's, and the line's total contracted impressions, which must be positive. It answers the line's effective start and end dates and its flights, each with its year, month, start, end and contracted impressions, split in proportion to the days of each window exactly as a registration would split them. It SHALL NOT read or write the database.

#### Scenario: A line inheriting the campaign dates gets a flight per month
- **WHEN** a preview is requested for a campaign from 2026-08-01 to 2026-10-31, a line with no dates and 100 impressions
- **THEN** the line's effective dates are the campaign's
- **AND** the flights are August, September and October carrying 34, 32 and 34 impressions

#### Scenario: A line with its own dates only gets the months it touches
- **WHEN** a preview is requested for a line from 2026-09-10 to 2026-10-05 inside that campaign
- **THEN** the flights are September from the 10th to the 30th and October from the 1st to the 5th
- **AND** their impressions add up to the total

#### Scenario: A line in one month and a line of one day get one flight
- **WHEN** a preview is requested for a line inside a single month, or for a line starting and ending on the same date
- **THEN** it has a single flight carrying the whole total

#### Scenario: The preview stores nothing
- **WHEN** a preview is requested
- **THEN** no purchase order, campaign, period, line or flight is created

#### Scenario: The preview and the registration agree
- **WHEN** the same campaign dates, line dates and total are previewed and then registered
- **THEN** the flights of the preview are identical to the flights of the registered line

### Requirement: The preview rejects what a registration would reject

The system SHALL reject a preview with the same codes a registration uses, as an unprocessable request with `{"code","message"}`: `line_dates_outside_campaign` when the line's dates are not within the campaign's, `line_dates_invalid` when its start is after its end, and `volume_too_small_for_flights` when the split by days leaves a flight with zero impressions. A total that is zero or negative SHALL be rejected as an invalid request, like the total of a registered line. The preview does not validate the campaign on its own: campaign dates given in reverse order leave no valid line and are rejected through the line's codes.

#### Scenario: Line dates outside the campaign are rejected
- **WHEN** a preview is requested for a line that starts before the campaign or ends after it
- **THEN** it is rejected with the code `line_dates_outside_campaign`

#### Scenario: Inverted line dates are rejected
- **WHEN** a preview is requested for a line whose start is after its end
- **THEN** it is rejected with the code `line_dates_invalid`

#### Scenario: A total too small for its flights is rejected
- **WHEN** a preview is requested for a total that leaves a flight with zero impressions
- **THEN** it is rejected with the code `volume_too_small_for_flights`

#### Scenario: A volume that is not positive is rejected
- **WHEN** a preview is requested with a total of zero or less
- **THEN** it is rejected as an unprocessable request

#### Scenario: A user without the operations role is forbidden
- **WHEN** an authenticated user without `operations` requests a preview
- **THEN** the request is rejected as forbidden

#### Scenario: A request without a valid token is unauthenticated
- **WHEN** a preview is requested with no token or an invalid one
- **THEN** the request is rejected as unauthenticated
