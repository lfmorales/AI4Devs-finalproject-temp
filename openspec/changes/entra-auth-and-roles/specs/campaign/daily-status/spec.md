## MODIFIED Requirements

### Requirement: The daily status is read through one endpoint for operations and business

The system SHALL expose the daily status at `GET /api/campaign-status` to users holding the `operations`, `business`, `finance` or `trading` role, with one row per flight whose window contains D-1 and whose campaign has status `active`, where D is the day the request is made. Each row SHALL carry the campaign (id and name), the agency (id and name), the line number, the flight (campaign period and window), the contracted volume of the flight, the delivered volume (the line's impressions from the flight's start to D-1), their ratio, the pacing (expected to date, deviation, days remaining until the flight's last day and the `pacing_flag`) and the `missing_data_flag`. Pacing SHALL be calculated by the pure pacing function. The delivered volume SHALL be aggregated in the database, without bringing delivery rows into the application.

#### Scenario: A running flight of an active campaign is listed with its figures
- **WHEN** a user with the `operations`, `business`, `finance` or `trading` role reads the daily status
- **THEN** a flight whose window contains D-1, of an `active` campaign, is listed once
- **AND** its contracted volume and its delivered volume are separate fields
- **AND** the delivered volume counts only impressions from the flight's start to D-1

#### Scenario: A campaign that is not active is not listed
- **WHEN** a campaign has a status other than `active`
- **THEN** none of its flights is listed

#### Scenario: A line with no delivery in a running flight is flagged for pacing
- **WHEN** a running flight has no delivery or only rows of zeros
- **THEN** it is listed with zero delivered and its `pacing_flag` raised

#### Scenario: Rows with any flag come first
- **WHEN** the daily status is read
- **THEN** rows with a pacing flag or a missing-data flag precede rows with none
- **AND** within each group the rows are ordered by agency name, campaign name and line number

#### Scenario: The response carries no cost field
- **WHEN** the daily status is read
- **THEN** no field of the response, however nested, is a cost or margin figure

#### Scenario: Reading the daily status requires operations or business
- **WHEN** a user holding none of the four roles reads the daily status
- **THEN** the request is rejected as forbidden
- **AND** a request without a valid token is rejected as unauthenticated

### Requirement: Cost and margin figures are restricted to finance

The system SHALL withhold cost and margin figures from users who hold neither the `operations` nor the `finance` role, in the API response and not only in the interface.

#### Scenario: A business user sees delivery but not cost
- **WHEN** a user holding `business`, and neither `operations` nor `finance`, reads the daily status
- **THEN** campaigns and their delivery are returned
- **AND** no cost or margin field is present in the response

#### Scenario: Calling the API directly does not bypass the restriction
- **WHEN** a user holding neither `operations` nor `finance` requests a cost or margin resource directly
- **THEN** the request is rejected as forbidden
