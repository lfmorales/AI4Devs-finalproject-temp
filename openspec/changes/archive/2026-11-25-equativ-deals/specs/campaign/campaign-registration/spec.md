## ADDED Requirements

### Requirement: Every line declares its volume commitment

The system SHALL require on every line of a registration a `volume_commitment` of `committed` or `target`, SHALL store it on the line and SHALL NOT derive it from the channel, the DSP or any other field. A `committed` line's volume is what the buyer committed to; a `target` line's volume is an objective the buyer may miss or exceed. A registration with a line that lacks it, or that carries any other value, SHALL be rejected as an invalid request (422) and SHALL create nothing. Lines stored before the attribute existed SHALL read `committed`. The registration form SHALL propose `target` for a line whose channel is `Deal` and `committed` for any other channel, and SHALL let the user change it before submitting; the proposal is a convenience of the form, never a rule of the server.

#### Scenario: A Deal line is registered as a target
- **WHEN** a registration has one `Deal` line with `volume_commitment` `target`
- **THEN** the line is stored as `target`

#### Scenario: The commitment is not derived from the channel
- **WHEN** a registration has a `Deal` line with `volume_commitment` `committed` and a `Directo` line with `target`
- **THEN** both lines are stored with the commitment they declare

#### Scenario: A line without a commitment is refused
- **WHEN** a registration has a line with no `volume_commitment`, or with `volume_commitment` `maybe`
- **THEN** the request is rejected with 422
- **AND** no purchase order, campaign, period, line or flight is created

#### Scenario: Existing lines are committed
- **WHEN** a line stored before the attribute existed is read
- **THEN** its `volume_commitment` is `committed`

#### Scenario: The form proposes the commitment from the channel
- **WHEN** the user picks the `Deal` channel for a line in the registration form
- **THEN** the form proposes `target` for that line
- **AND** picking `Directo`, `DOOH` or `CTV` proposes `committed`
- **AND** the user can change the proposal and the value sent is the one shown

## MODIFIED Requirements

### Requirement: The registration answers with each line and its flights

The system SHALL answer a registration with the campaign, its periods as the campaign's calendar, and its lines. Each line SHALL carry its number, its start and end dates, its total contracted impressions, its `volume_commitment` and a list of its flights, and each flight SHALL carry the identifier of its campaign period, the year and month, its start and end dates and its contracted impressions. A line SHALL NOT carry a campaign period of its own.

#### Scenario: A line over three months is answered with three flights
- **WHEN** a campaign with one line over three months is registered
- **THEN** the response has one line with three flights
- **AND** the flights' impressions add up to the line's total
- **AND** each flight's campaign period identifier is the identifier of one of the periods listed

#### Scenario: Two lines over two months are not duplicated
- **WHEN** a campaign with two lines over two months is registered
- **THEN** the response has two lines of two flights each, and two periods

#### Scenario: A failure leaves nothing stored
- **WHEN** any line of the registration is rejected, or storing the campaign fails halfway
- **THEN** no purchase order, campaign, period, line or flight remains

#### Scenario: A line answers with its commitment
- **WHEN** a campaign with a `target` line and a `committed` line is registered
- **THEN** each line of the response carries the `volume_commitment` it was registered with
