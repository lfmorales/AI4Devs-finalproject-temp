## RENAMED Requirements

- FROM: `### Requirement: Reporting access is restricted to finance`
- TO: `### Requirement: Reporting access is restricted to operations and finance`

## MODIFIED Requirements

### Requirement: Reporting access is restricted to operations and finance

The system SHALL restrict margin reporting to users holding the `operations` or the `finance` role.

#### Scenario: A user without the role is forbidden
- **WHEN** a user holding neither `operations` nor `finance` requests a roll-up
- **THEN** the request is rejected as forbidden

### Requirement: The margin is read per campaign, line and flight

The system SHALL expose `GET /margin`, restricted to the `operations` and `finance` roles, returning campaigns, their lines and their flights with totals at every level, filtered by year, month and campaign, and SHALL include every campaign whatever its status.

#### Scenario: A closed flight reads what was frozen
- **WHEN** a flight with an `applied_rates` row is read
- **THEN** its state is `closed` and its rebate and platform rate are the frozen ones

#### Scenario: A running flight is calculated and provisional
- **WHEN** a flight that has started and not ended is read
- **THEN** its state is `running` and it is provisional

#### Scenario: A flight that has ended and is not frozen is pending close
- **WHEN** a flight that has ended but has no frozen rates is read
- **THEN** its state is `pending_close` and it is provisional

#### Scenario: A flight that has not started is absent
- **WHEN** a flight starts after `as_of`
- **THEN** it does not appear

#### Scenario: A line with flights in different states
- **WHEN** a line has a closed flight and a running one
- **THEN** both appear, the line total is their sum and the line is provisional

#### Scenario: Filters narrow the result
- **WHEN** a year, a month or a campaign is given
- **THEN** only the matching flights appear

#### Scenario: An unknown campaign is not found
- **WHEN** the campaign filter names a campaign that does not exist
- **THEN** the response is 404 `campaign_not_found`

#### Scenario: Inactive campaigns are included
- **WHEN** a campaign is `inactive`
- **THEN** its flights appear

#### Scenario: Amounts are decimal strings
- **WHEN** any amount is serialised
- **THEN** it is a string such as `"3631.01"`, never a floating-point number

#### Scenario: Reading writes nothing
- **WHEN** `GET /margin` is called
- **THEN** no row of any table is created or changed

#### Scenario: Negative-margin flights are counted at every level
- **WHEN** a line or the totals include a flight with a negative final margin
- **THEN** the count of such flights is present at that level as `below_cost_count`
