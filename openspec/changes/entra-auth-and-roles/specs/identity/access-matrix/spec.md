## Purpose

Fixes which roles each existing route accepts and keeps money figures away from the roles that must not see them, enforced at the endpoint and never only in the interface.

## ADDED Requirements

### Requirement: Routes are open to the roles of the access matrix

The system SHALL accept on each existing route the roles below and no others.

| Routes | Roles |
|---|---|
| Reads of campaigns and of the masters | operations, business, finance |
| Writes of campaigns and of the masters | operations |
| Delivery status | operations, business, finance, trading |
| Ingestion exceptions, DSP mappings, DSP catalogue, flight preview, unmapped lines | operations |
| `GET /margin` and `POST /margin/closings` | operations, finance |
| `POST /margin/rebate-schedules` and `POST /margin/platform-rates` | operations |
| `POST /users/activation` | operations |
| `GET /users/me` | operations, business, finance, trading |

#### Scenario: Finance reads the margin but cannot write the schedules
- **WHEN** a user with only `finance` reads the margin and posts a rebate schedule
- **THEN** the read succeeds and the write is rejected with 403

#### Scenario: Trading reads the delivery status and nothing else
- **WHEN** a user with only `trading` calls any route outside the delivery status
- **THEN** the request is rejected with 403

#### Scenario: Business and trading receive no money fields
- **WHEN** a user with only `business`, or only `trading`, reads the delivery status
- **THEN** no cost, revenue, rebate or margin field appears in the response
