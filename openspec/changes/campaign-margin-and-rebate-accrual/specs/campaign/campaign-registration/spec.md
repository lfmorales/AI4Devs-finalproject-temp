## ADDED Requirements

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
