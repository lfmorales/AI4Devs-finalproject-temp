## MODIFIED Requirements

### Requirement: Every override records who set it and when

The system SHALL stamp each platform rate override with its author and the time it was created, because the value moves the margin.

#### Scenario: An override is attributable
- **WHEN** a platform rate override is created
- **THEN** the author and creation time are stored with it

#### Scenario: Only finance may configure the rate
- **WHEN** a user without the `operations` role, finance included, attempts to create or change an override
- **THEN** the request is rejected as forbidden
