## ADDED Requirements

### Requirement: Every line of a campaign shares one delivery metric

The system SHALL reject a registration whose lines name channels with different delivery metrics, as an unprocessable request with `{"code","message"}` and the code `mixed_delivery_metrics`, and SHALL create nothing: no campaign, period, line, flight or purchase order. Lines on different channels that share a delivery metric SHALL be accepted. This check SHALL run after the master references are validated, so that a registration naming an unknown channel is rejected for that channel.

#### Scenario: A DOOH line and a Directo line cannot share a campaign
- **WHEN** a registration has line 1 on `DOOH` (OTS) and line 2 on `Directo` (impressions)
- **THEN** the request is rejected with 422 and the code `mixed_delivery_metrics`
- **AND** no campaign, period, line, flight or purchase order is created

#### Scenario: Channels of the same metric share a campaign
- **WHEN** a registration has line 1 on `Directo`, line 2 on `Deal` and line 3 on `CTV`, all counted in impressions
- **THEN** the campaign is registered with its three lines

#### Scenario: A DOOH campaign registers its lines in OTS
- **WHEN** a registration has two lines on `DOOH` with 300,000 and 150,000 contracted volume
- **THEN** the campaign is registered and both volumes are OTS

#### Scenario: An unknown channel is reported before the metric
- **WHEN** a registration has line 1 on `Directo` and line 2 on a channel that does not exist
- **THEN** the request is rejected for the unknown channel, not with `mixed_delivery_metrics`
