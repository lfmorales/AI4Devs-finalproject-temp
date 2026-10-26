## Purpose

The infrastructure rate charged per thousand delivered impressions, held as configurable and audited data rather than a constant inside a chart expression, so that the second-largest cost line in the business can be seen and changed deliberately.

## ADDED Requirements

### Requirement: The platform rate is stored data with a system default

The system SHALL hold the platform rate as data, with a system-wide default of 1.00 € per thousand impressions that applies when nothing more specific is configured, and SHALL NOT hold any rate as a constant in code.

#### Scenario: The default applies with no override
- **WHEN** a flight's line has no rate configured at any level
- **THEN** the system default rate of 1.00 € per thousand impressions is used
- **AND** the value used is recorded when the flight is closed

#### Scenario: The default is a row, not a constant
- **WHEN** the platform rate settings are read on a freshly migrated database
- **THEN** the system level holds one row with the value 1.00

### Requirement: The rate resolves most-specific-first

The system SHALL resolve the platform rate by taking the most specific configured level in this order: campaign line, then agency, then campaign type, then system default.

#### Scenario: A line override beats an agency override
- **WHEN** both an agency-level and a line-level rate are configured for a line
- **THEN** the line-level rate is used

#### Scenario: An agency override beats a campaign-type override
- **WHEN** an agency-level and a campaign-type rate are configured and no line-level rate exists
- **THEN** the agency-level rate is used

#### Scenario: A campaign-type override beats the system default
- **WHEN** a campaign-type rate is configured and nothing more specific exists
- **THEN** the campaign-type rate is used

#### Scenario: A level without its key is rejected
- **WHEN** a setting is stored for a level whose scope key is absent
- **THEN** it is rejected

### Requirement: Every override records who set it and when

The system SHALL stamp each platform rate override with its author and the time it was created, because the value moves the margin.

#### Scenario: An override is attributable
- **WHEN** a platform rate override is created
- **THEN** the author and creation time are stored with it

#### Scenario: Only finance may configure the rate
- **WHEN** a user without the `finance` role attempts to create or change an override
- **THEN** the request is rejected as forbidden

### Requirement: The rate used is frozen on the closed flight

The system SHALL record the platform rate actually applied in the `applied_rates` row of a closed flight, and SHALL NOT re-resolve it at read time for a closed flight.

#### Scenario: Changing the default does not move a closed flight
- **WHEN** the system default rate is changed after a flight has been closed
- **THEN** that flight's margin is unchanged

#### Scenario: A running flight uses the rate in force
- **WHEN** a running flight is read after the default changed
- **THEN** it is calculated with the new rate and nothing is written

### Requirement: Overrides are append-only and the latest wins

The system SHALL store each platform rate setting as a new row and SHALL resolve a level by its most recent row, so that the history of a rate stays in the data.

#### Scenario: A second setting does not erase the first
- **WHEN** a rate is set twice for the same agency
- **THEN** both rows exist and the later one is the one resolved

### Requirement: The system rate is data inserted by the migration

The system SHALL hold the system rate as a row inserted by the migration with no author, and SHALL allow an absent author only at the system level.

#### Scenario: The system rate changes without touching code
- **WHEN** a new system row is stored with the value 1.25
- **THEN** a flight with no other configured level is calculated with 1.25

#### Scenario: Only the system level may have no author
- **WHEN** a row at the agency level is stored without an author
- **THEN** it is rejected
