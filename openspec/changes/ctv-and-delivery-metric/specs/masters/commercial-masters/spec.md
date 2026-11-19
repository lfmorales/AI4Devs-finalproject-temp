## MODIFIED Requirements

### Requirement: Channels are a closed, maintained catalogue

The system SHALL hold the channel catalogue covering exactly `Directo`, `Deal`, `DOOH` and `CTV`, and SHALL treat the channel as the rebate accumulation key, so that each of the four channels keeps its own annual rebate counter. The development seed, the test fixtures and the example masters file SHALL carry these four channels and no `OOH` or `Digital` channel. The development seed SHALL carry a fictitious rebate schedule that applies to `CTV` only, so that a CTV line resolves a channel-specific schedule in development. As an exception of the demonstration data only, a channel whose name starts with `DEMO`, such as `DEMO Channel`, SHALL be accepted when a demonstration seed adds it; such channels exist only in development and E2E databases, are counted in impressions unless they state otherwise, and are not part of the catalogue a real deployment loads.

#### Scenario: CTV is available from the start
- **WHEN** the channel catalogue is read
- **THEN** `CTV` is present and selectable, even though no historical campaign uses it
- **AND** no historical campaign is retroactively reclassified into it

#### Scenario: The seeds carry the four channels and nothing else
- **WHEN** the development seed, the test fixtures or the example masters file are loaded into an empty database
- **THEN** the channel catalogue holds `Directo`, `Deal`, `DOOH` and `CTV`
- **AND** it holds no `OOH` and no `Digital` channel

#### Scenario: The demonstration channel is an exception of the demo data
- **WHEN** the development seed and then the margin demo are loaded into an empty database
- **THEN** the channels are `Directo`, `Deal`, `DOOH`, `CTV` and `DEMO Channel`
- **AND** `DEMO Channel` is counted in impressions
- **AND** a database loaded only from the masters file has no `DEMO` channel

#### Scenario: Each channel accrues on its own counter
- **WHEN** a holding group has accrued 90,000.00 € on `Directo` in 2026 and a CTV campaign of the same group accrues 30,000.00 € in 2026
- **THEN** the group's `CTV` counter for 2026 stands at 30,000.00 €
- **AND** its `Directo` counter for 2026 stays at 90,000.00 €

#### Scenario: A CTV line resolves the CTV schedule of the development seed
- **WHEN** a CTV line of the seed's holding group is priced in the development database
- **THEN** its rebate comes from the fictitious schedule for `CTV`, at the group-and-channel step
- **AND** a `Directo` line of the same group still resolves the group's schedule for any channel

## ADDED Requirements

### Requirement: A channel carries its delivery metric

The system SHALL hold on every channel a delivery metric, `impressions` or `ots`, which names the unit in which the contracted and the delivered volume of its lines are counted. A channel created without one SHALL take `impressions`. `DOOH` SHALL be `ots`; `Directo`, `Deal` and `CTV` SHALL be `impressions`. Upgrading a database that already holds a channel named `DOOH` SHALL set that channel to `ots`. The masters load SHALL accept an optional `delivery_metric` on a channel it creates; it SHALL NOT change the metric of a channel that already exists, and SHALL reject the whole file, writing nothing, when it names an existing channel with a metric different from the stored one, reporting the problem by section and position and never by content.

#### Scenario: DOOH is counted in OTS and the others in impressions
- **WHEN** the channel catalogue of the development seed is read
- **THEN** `DOOH` has the delivery metric `ots`
- **AND** `Directo`, `Deal` and `CTV` have the delivery metric `impressions`

#### Scenario: A channel created without a metric counts impressions
- **WHEN** a channel is created without a delivery metric, such as the `DEMO Channel` of the margin demo
- **THEN** its delivery metric is `impressions`

#### Scenario: Upgrading a database fixes the metric of an existing DOOH channel
- **WHEN** a database holding a `DOOH` channel created before this change is upgraded
- **THEN** that channel's delivery metric is `ots`
- **AND** every other existing channel's delivery metric is `impressions`

#### Scenario: The masters load creates a channel with its metric
- **WHEN** the masters file lists `{"name": "DOOH", "delivery_metric": "ots"}` and no `DOOH` channel exists
- **THEN** the `DOOH` channel is created with the delivery metric `ots`

#### Scenario: The masters load does not change an existing channel's metric
- **WHEN** the masters file lists the third channel with the delivery metric `impressions` and that channel already exists with `ots`
- **THEN** the load is rejected as an invalid file, reporting `channels[2]`, and nothing is written
- **AND** the stored channel keeps `ots`

#### Scenario: An unknown metric is rejected
- **WHEN** the masters file gives a channel the delivery metric `views`
- **THEN** the load is rejected as an invalid file and nothing is written
