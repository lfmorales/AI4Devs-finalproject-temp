## MODIFIED Requirements

### Requirement: Margin access is restricted to finance

The system SHALL restrict every cost and margin figure to users holding the `operations` or the `finance` role, enforced at the endpoint.

#### Scenario: A user without the role is forbidden
- **WHEN** a user holding `business` or `trading`, and neither `operations` nor `finance`, requests a margin resource
- **THEN** the request is rejected as forbidden

#### Scenario: A missing or invalid token is unauthenticated
- **WHEN** a margin endpoint is called without a token or with an invalid one
- **THEN** the request is rejected as unauthenticated, a distinct outcome from forbidden

#### Scenario: The restriction holds against direct API access
- **WHEN** a margin endpoint is called directly rather than through the interface
- **THEN** the same restriction applies
