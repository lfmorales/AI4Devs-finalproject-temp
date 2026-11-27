## ADDED Requirements

### Requirement: Each route accepts only the roles of the access matrix

The system SHALL accept on each existing route the roles below and no others.

| Routes | Roles |
|---|---|
| Reads of campaigns and of the masters | operations, business, finance |
| Writes of campaigns and of the masters | operations |
| Delivery status | operations, business, finance, trading |
| Ingestion exceptions, DSP mappings, DSP catalogue, flight preview, unmapped lines | operations |
| `GET /margin` and `POST /margin/closings` | operations, finance |
| `POST /margin/rebate-schedules` and `POST /margin/platform-rates` | operations |
| `GET /billing`, `POST /billing/flights/{flight_id}/adjustments`, `GET /billing/flights/{flight_id}/adjustments`, `POST /billing/reviews`, `POST /billing/reviews/withdrawals`, `PUT /billing/flights/{flight_id}/carryover/billable` and `GET /billing/export` | operations, finance |
| `PUT /flights/{flight_id}/carryover` | operations, trading |
| `POST /users/activation` | operations |
| `GET /users/me` | operations, business, finance, trading |

A response to a user holding `trading` SHALL carry no cost, revenue, billing, rebate or margin amount, no billing adjustment or its reason, and no billable flag of a carry-over, whatever the route.

#### Scenario: Finance reads the margin but cannot write the schedules
- **WHEN** a user with only `finance` reads the margin and posts a rebate schedule
- **THEN** the read succeeds and the write is rejected with 403

#### Scenario: Trading reads the delivery status, writes a carry-over and reads its own roles, and nothing else
- **WHEN** a user with only `trading` calls each route
- **THEN** the delivery status, `PUT /flights/{flight_id}/carryover` and `GET /users/me` are let through
- **AND** any other route is rejected with 403

#### Scenario: Finance adjusts and reviews but does not carry over
- **WHEN** a user with only `finance` adjusts a flight's billing, marks a campaign reviewed, sets a carry-over's billable flag and writes a carry-over
- **THEN** the first three are let through and the carry-over is rejected with 403

#### Scenario: Trading cannot see or set the billing
- **WHEN** a user with only `trading` reads `GET /billing`, downloads `GET /billing/export`, posts an adjustment or sets a carry-over's billable flag
- **THEN** each request is rejected with 403 and the body carries no amount

#### Scenario: Business and trading receive no money fields
- **WHEN** a user with only `business`, or only `trading`, reads the delivery status
- **THEN** no cost, revenue, billing, rebate or margin field appears in the response

#### Scenario: The carry-over response to trading carries volumes only
- **WHEN** a user with only `trading` writes a carry-over
- **THEN** the response carries volumes, the carry-over's reason, author and date, and no amount, no billable flag, no adjustment and no adjustment reason

## REMOVED Requirements

### Requirement: Routes are open to the roles of the access matrix
**Reason**: Seven billing routes are added and trading may now write a carry-over, so the scenario that trading reaches nothing beyond the delivery status and its own roles no longer holds.
**Migration**: Replaced by «Each route accepts only the roles of the access matrix», with the same routes and roles plus the eight new ones.
