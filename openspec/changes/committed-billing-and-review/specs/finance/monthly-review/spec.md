## Purpose

Records, per campaign and calendar month, that Operations or Finance looked at the campaign's billing once its flights ended, returns it to pending when its billing is edited afterwards, and keeps a month from being closed until every campaign in it was reviewed.

## ADDED Requirements

### Requirement: A campaign has a review state in each month

The system SHALL give each campaign, in each calendar month in which it has flights (the flights whose campaign period is that month), one of four states, as of D-1:

- `closed` when every one of those flights has frozen rates;
- otherwise `in_progress` when one of them has not ended by D-1;
- otherwise `reviewed` when its latest review event in that month is a review;
- otherwise `pending_review`.

Only the review events are stored; `in_progress` and `closed` are derived from the flights. A campaign without flights in a month has no state in it. An ingestion and a change of a master, a schedule or a platform rate SHALL NOT change a state; only the review events and the flights (their ends and their freezing) do.

#### Scenario: A campaign whose flights are running is in progress
- **WHEN** a campaign has two October 2026 flights, one ended on 2026-10-15 and one ending on 2026-10-31, and D-1 is 2026-10-20
- **THEN** its state in October 2026 is `in_progress`

#### Scenario: A campaign whose flights have all ended is pending review
- **WHEN** D-1 is 2026-11-02 and the same campaign has no review event in October
- **THEN** its state in October 2026 is `pending_review`

#### Scenario: A reviewed campaign is closed with its month
- **WHEN** the campaign is reviewed in October and October is closed with its flights
- **THEN** its state in October 2026 is `closed`

#### Scenario: An ingestion does not reopen a review
- **WHEN** a reviewed campaign's October window is ingested again with other figures before the closing
- **THEN** its state is still `reviewed`

### Requirement: Operations and Finance mark a campaign reviewed

The system SHALL expose `POST /billing/reviews`, restricted to the `operations` and `finance` roles, taking `campaign_id`, `year` and `month`, which SHALL record a review event of that campaign and month with the user who made the request and the moment, and answer 201 with the campaign, the month, its state `reviewed`, the author and the moment. A campaign already reviewed in that month SHALL be answered 200 with its current review and nothing written. The system SHALL reject the request, writing nothing, with 404 `campaign_not_found` when the campaign does not exist, 404 `campaign_month_not_found` when it has no flights in that month, 409 `campaign_month_in_progress` when its state is `in_progress`, and 409 `campaign_month_closed` when its state is `closed`.

#### Scenario: Finance reviews a campaign whose flights have ended
- **WHEN** a user holding `finance` reviews a campaign in October 2026 whose October flights have all ended
- **THEN** the response is 201 with the state `reviewed`, the author and the moment
- **AND** the campaign's state in October is `reviewed`

#### Scenario: A campaign in progress cannot be reviewed
- **WHEN** a campaign with an October flight that has not ended is reviewed for October
- **THEN** the response is 409 `campaign_month_in_progress` and nothing is written

#### Scenario: A closed campaign-month cannot be reviewed
- **WHEN** a campaign whose October flights are all frozen is reviewed for October
- **THEN** the response is 409 `campaign_month_closed`

#### Scenario: Reviewing twice writes once
- **WHEN** a campaign already reviewed in October is reviewed again
- **THEN** the response is 200 with the first review's author and moment and no event is added

### Requirement: The review can be withdrawn

The system SHALL expose `POST /billing/reviews/withdrawals`, restricted to the `operations` and `finance` roles, taking `campaign_id`, `year` and `month`, which SHALL record a reopening event caused by a withdrawal, with the user and the moment, and answer 201 with the state `pending_review`. It SHALL reject the request, writing nothing, with 404 `campaign_not_found`, 404 `campaign_month_not_found`, 409 `not_reviewed` when the state is not `reviewed`, and 409 `campaign_month_closed` when it is `closed`.

#### Scenario: A review is withdrawn
- **WHEN** a user holding `operations` withdraws the October review of a reviewed campaign
- **THEN** the response is 201 with the state `pending_review` and the campaign's state in October is `pending_review`

#### Scenario: Only a reviewed campaign can be withdrawn
- **WHEN** a withdrawal is posted for a campaign pending review
- **THEN** the response is 409 `not_reviewed`

### Requirement: An edit of the billing returns the campaign to pending review

The system SHALL record a reopening event of a campaign and month, naming its cause (an adjustment, a carry-over or a carry-over's billable flag), the flight and the user, in the same transaction as the edit, whenever a billing adjustment is written on one of its flights of that month (`finance/billing-adjustment`) or a carry-over or its flag is written on one of them (`campaign/carryover`), and only when the campaign was `reviewed` in that month. No other change reopens a review.

#### Scenario: An adjustment reopens the review with its cause
- **WHEN** a campaign reviewed in October has one of its October flights adjusted
- **THEN** a reopening event names the adjustment, the flight and the user, and the state is `pending_review`

#### Scenario: An edit of a campaign pending review records nothing
- **WHEN** a campaign pending review in October has one of its October flights adjusted
- **THEN** no reopening event is written and the state is still `pending_review`

#### Scenario: A failed edit does not reopen
- **WHEN** an adjustment of a flight of a reviewed campaign is rejected with 409
- **THEN** no reopening event is written and the state is still `reviewed`

### Requirement: Review events are only added

The system SHALL never update or delete a review or reopening event; the state is read from the latest event of the campaign and month.

#### Scenario: The database refuses to change a review event
- **WHEN** an update or a delete of a review event row is attempted in the database
- **THEN** it is refused

### Requirement: The closing waits for every campaign of the month

The system SHALL refuse to close a month while a campaign with flights in it is `in_progress` or `pending_review`, with 409 `month_not_reviewed` whose message names the month and each such campaign with its state (`finance/rebate-accrual`). A `closed` campaign does not block a later closing of the same month.

#### Scenario: The closing names the campaigns that block it
- **WHEN** October 2026 is closed while campaign A is `reviewed`, campaign B is `pending_review` and campaign C is `in_progress`
- **THEN** the response is 409 `month_not_reviewed` and its message names October 2026, B as pending review and C as in progress

#### Scenario: A late campaign is reviewed before a second closing
- **WHEN** October was closed and a campaign registered afterwards has October flights that have ended
- **THEN** a new closing of October is refused with `month_not_reviewed` until that campaign is reviewed

### Requirement: The billing screen shows and changes the review

The system SHALL show, on the billing screen of a month, each campaign's state labelled «En curso», «Pendiente de revisión», «Revisada» or «Cerrada», with the author and the moment of its review, and SHALL offer to a user holding `operations` or `finance` «Marcar como revisada» on a campaign pending review and «Quitar revisión» on a reviewed one. The margin screen SHALL turn the closing control off, stating the reason «Hay campañas pendientes de revisión», while the billing read reports a campaign of the month in progress or pending review.

#### Scenario: A campaign is marked reviewed from the screen
- **WHEN** a user holding `finance` presses «Marcar como revisada» on a campaign pending review
- **THEN** the campaign shows «Revisada» with the user and the moment

#### Scenario: The closing is off while a campaign is pending
- **WHEN** the margin screen shows a month with a campaign pending review
- **THEN** the closing control is off with the reason «Hay campañas pendientes de revisión»
