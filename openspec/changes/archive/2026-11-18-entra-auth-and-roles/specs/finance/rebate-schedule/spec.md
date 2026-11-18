## REMOVED Requirements

### Requirement: Schedules and platform rates are created by finance through the API
**Reason**: Creating schedules and platform rates moves from finance to operations, so the name and the scenario titles are no longer true.
**Migration**: Read the replacement requirement of the same capability; finance keeps reading the margin and closing months, and no longer writes these two resources.

## ADDED Requirements

### Requirement: Schedules and platform rates are created by operations through the API

The system SHALL let a user with the `operations` role create a rebate schedule with its brackets (`POST /margin/rebate-schedules`) and set a platform rate at any level (`POST /margin/platform-rates`), SHALL take every amount as a decimal string and refuse a JSON number, SHALL answer a schedule that overlaps another of its key with 409 `schedule_overlaps_existing` and a reference to something that does not exist with 422 `reference_not_found`, and SHALL stamp each platform rate with its author and time.

#### Scenario: A schedule is created with its brackets
- **WHEN** operations posts a schedule with a valid bracket table
- **THEN** the response is 201 and the schedule and its brackets are stored

#### Scenario: An invalid table is refused with its own message
- **WHEN** a schedule is posted with an empty table, a table that does not start at zero, a table with a gap or a table whose last bracket is bounded
- **THEN** each is refused with a different code and a different message

#### Scenario: An overlapping schedule is a conflict
- **WHEN** a schedule is posted whose validity overlaps another of the same key
- **THEN** the response is 409 `schedule_overlaps_existing` and nothing is stored

#### Scenario: A number instead of a string is refused
- **WHEN** a rate is posted as the JSON number 0.15
- **THEN** the response is 422 `validation_error`

#### Scenario: A platform rate records who set it
- **WHEN** operations sets a platform rate
- **THEN** the response is 201 and the row holds the author and the time

#### Scenario: Only operations may create them
- **WHEN** a user without `operations`, finance included, posts either
- **THEN** the response is 403 and nothing is stored
