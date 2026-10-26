## Purpose

The agency rebate as a bracket schedule with temporal validity, resolved by date through an explicit ladder, so that a rate can be traced to what was negotiated and when — instead of being averaged out of a spreadsheet whose key schema changes every year.

## ADDED Requirements

### Requirement: A schedule is a set of marginal brackets, not a single rate

The system SHALL express a rebate schedule as an ordered set of brackets, each with a lower threshold, an optional upper threshold and a rate, applied to the slice of volume falling within it. Brackets are half-open: a bracket covers its lower threshold and every euro below its upper threshold. The system SHALL reject, with a domain error carrying a code, a schedule whose first bracket does not start at 0 (`bracket_table_must_start_at_zero`), whose brackets leave a gap or overlap (`bracket_table_not_contiguous`), or whose last bracket has an upper threshold (`last_bracket_must_be_open`).

#### Scenario: Brackets apply to the slice, not the total
- **WHEN** a counter standing at 90,000 € receives a flight of 30,000 € of revenue, with brackets of 15 % up to 100,000 € and 20 % from 100,000 € upward
- **THEN** 10,000 € accrues at 15 % and 20,000 € at 20 %
- **AND** the rebate is 1,500 € + 4,000 € = 5,500 €
- **AND** the effective rate is 5,500 / 30,000 = 18.33 %, the blend of the two, not the higher rate applied to the whole

#### Scenario: Three brackets over a year
- **WHEN** a counter receives 600,000 € in a year, with brackets of 15 % up to 100,000 €, 20 % from 100,000 to 500,000 € and 25 % above 500,000 €
- **THEN** the rebate is 15,000 + 80,000 + 25,000 = 120,000 €
- **AND** the effective rate is 20.0 %, not 25 %

#### Scenario: A flight crossing a threshold by cents is split between two brackets
- **WHEN** a counter standing at 99,999.50 € receives a flight of 10.00 €, with brackets of 15 % up to 100,000 € and 20 % from 100,000 € upward
- **THEN** 0.50 € accrues at 15 % and 9.50 € at 20 %
- **AND** the rebate is 0.075 € + 1.90 € = 1.975 €, unrounded

#### Scenario: A counter exactly on a threshold starts the next bracket
- **WHEN** a counter standing at exactly 100,000 € receives a flight of 1,000 €
- **THEN** all of it accrues at the rate of the bracket starting at 100,000 €

#### Scenario: A table that does not start at zero is rejected
- **WHEN** a schedule's first bracket starts at 1,000 €
- **THEN** it is rejected with `bracket_table_must_start_at_zero`

#### Scenario: A table with a gap is rejected
- **WHEN** a schedule has a bracket up to 100,000 € and the next starts at 120,000 €
- **THEN** it is rejected with `bracket_table_not_contiguous`

#### Scenario: A table whose last bracket is bounded is rejected
- **WHEN** a schedule's last bracket has an upper threshold of 500,000 €
- **THEN** it is rejected with `last_bracket_must_be_open`

#### Scenario: The rebate can be reproduced from its breakdown
- **WHEN** a flight's rebate is computed
- **THEN** the amount charged in each bracket, times that bracket's rate, summed, equals the rebate exactly

#### Scenario: A schedule with one open bracket behaves as a flat rate
- **WHEN** a schedule holds a single bracket covering all volume
- **THEN** every euro accrues at that bracket's rate

### Requirement: Schedules carry temporal validity

The system SHALL record a validity period on every schedule and SHALL resolve the rate of a flight from the schedule in force on the flight's `flight_start`.

#### Scenario: A rate change applies from its validity date
- **WHEN** a group's schedule changes mid-year
- **THEN** the rate resolved for a flight depends on which schedule was in force on its `flight_start`
- **AND** no schedule is applied outside its validity period

#### Scenario: Two schedules of one key never overlap
- **WHEN** a schedule is stored whose validity overlaps another for the same key
- **THEN** it is rejected

#### Scenario: An overlap met by the ladder is a domain error
- **WHEN** two schedules match at the same step on `flight_start`
- **THEN** the resolution fails with the domain error `overlapping_schedules` instead of choosing one

### Requirement: The rate is resolved by an ordered ladder

The system SHALL resolve the rebate rate of a flight by walking the following eight steps from the first to the last, in the schedule table in force on `flight_start`, SHALL stop at the first match, and SHALL record which step produced the rate:

1. agency, channel and scope;
2. agency and channel, any scope;
3. agency alone;
4. holding group, channel and scope;
5. holding group and channel, any scope;
6. holding group alone;
7. the most recent earlier table, restarting at step 1;
8. an explicit 0 % recorded with its reason.

Step 7 is **deferred**: until it is implemented the walk goes from step 6 to step 8.

#### Scenario: An agency exception wins over its group
- **WHEN** a flight's agency has a schedule of its own matching at step 1, 2 or 3
- **THEN** the agency's schedule is used
- **AND** the group's schedule is not consulted

#### Scenario: Scope narrows before it widens
- **WHEN** a schedule exists for the group and channel both with and without a scope
- **THEN** the one matching the line's scope (step 4) is used in preference to the scopeless one (step 5)

#### Scenario: A channel-less schedule applies to every channel
- **WHEN** only a group-level schedule with no channel exists
- **THEN** it applies at step 6 to a flight of any channel

#### Scenario: Each step is recorded
- **WHEN** a rate is resolved at any of the steps
- **THEN** the number of the step that produced it is recorded

#### Scenario: No schedule anywhere resolves to zero, explicitly
- **WHEN** no schedule is found at any implemented step for a flight's group
- **THEN** the rate is zero, resolved at step 8
- **AND** it is recorded as an explicit zero with its reason, distinguishable from a negotiated zero
- **AND** the reason is `no_schedule_for_year` when no schedule of any group is in force on `flight_start`, and `no_schedule` when schedules are in force but none matches the flight's group

#### Scenario: A negotiated zero is not a defaulted zero
- **WHEN** the schedule that matches has a single bracket at 0 %
- **THEN** the rate is zero, resolved at the step that matched (1 to 6), with no zero reason

#### Scenario: The resolution is traceable
- **WHEN** any rate is resolved
- **THEN** the step that produced it, the source year and whether it came from an agency exception are all recorded
- **AND** the source year is the year of `valid_from` of the schedule that matched, and none at step 8

#### Scenario: A schedule in force on the first of January belongs to the new year
- **WHEN** a flight starts on 1 January
- **THEN** the schedule in force on that day is the one used, and the year of the flight is the new year

### Requirement: An agency exception replaces its group's schedule for that agency

The system SHALL price the flights of an agency holding a schedule of its own with that schedule instead of its group's, and SHALL accrue their volume on the agency's own counter, as the rebate-accrual capability defines. An exception without a channel covers every channel.

#### Scenario: The agency's own schedule prices its flights
- **WHEN** an agency has an exception and its group has a different schedule
- **THEN** the agency's flights are priced by the agency's schedule
- **AND** the agency flag is recorded as true

#### Scenario: An exception without a channel covers every channel
- **WHEN** an agency's schedule has no channel
- **THEN** it prices the agency's flights in every channel, at step 3

### Requirement: The scope is a validated attribute, never averaged

The system SHALL resolve the rebate against the campaign line's validated scope, and SHALL NOT average the rates of two scopes together. The dedicated test is deferred; the ladder keys on scope at steps 1 and 4 and never blends two scopes.

#### Scenario: Two scopes priced differently stay distinct
- **WHEN** a group is priced at one rate nationally and another internationally
- **THEN** a national line resolves to the national rate and an international line to the international rate
- **AND** neither receives the mean of the two

### Requirement: The database refuses overlapping schedules

The system SHALL guarantee in the database that two schedules of the same key (group, agency or none, channel or none, scope or none) never have overlapping validity, SHALL treat `valid_to` as inclusive and an absent `valid_to` as open-ended, and SHALL create schedules only through an endpoint restricted to the `finance` role.

#### Scenario: Overlapping validity of one key is refused by the database
- **WHEN** a schedule is stored whose validity overlaps another of the same key
- **THEN** the database rejects it

#### Scenario: Back-to-back validity is accepted
- **WHEN** one schedule ends on 2026-04-30 and the next of the same key starts on 2026-05-01
- **THEN** both are accepted

#### Scenario: An open-ended schedule overlaps a later one
- **WHEN** a schedule with no `valid_to` exists and another of the same key starts later
- **THEN** the second is rejected

#### Scenario: Different keys never conflict
- **WHEN** two schedules differ in channel, scope or agency
- **THEN** their validity may overlap
