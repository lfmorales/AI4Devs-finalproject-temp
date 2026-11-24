## ADDED Requirements

### Requirement: Lines on Equativ are checked for absence after each Equativ ingestion

The system SHALL run the check for lines without delivery after every Equativ ingestion of the rolling window that started at or after 06:00 UTC, with that batch's identifier, under the same rule as for Adform: a line that runs on Equativ with a validated Equativ mapping is a candidate for a flight whose last day falls inside the window, on or after the day the mapping was validated, when its delivered volume inside the flight's window is zero or it has no row there. The commitment of the line does not change the rule: a target line that delivered nothing is missing delivery. A mapping operations wrote for an Equativ package is validated by the user when it is created, whether or not the package is in the catalogue, so the line is evaluated for every flight that ends on or after that day, its delivery counted from the flight's first day; a package id written wrong is surfaced this way. An Equativ run SHALL evaluate only Equativ lines, and an Adform run only Adform lines.

#### Scenario: A target Deal line that delivered nothing is an exception
- **WHEN** an Equativ run started at 06:15 UTC and a target line on Equativ, with a validated Equativ mapping, has a flight that ended inside the window with no delivery row in it
- **THEN** a `missing_delivery` exception is recorded against that line and period with the Equativ batch

#### Scenario: Equativ does not report a day without delivery
- **WHEN** a package delivered nothing on some days of a finished flight but delivered on others
- **THEN** no absence exception is raised, because the flight's delivered volume is above zero

#### Scenario: Each DSP checks its own lines
- **WHEN** an Equativ run detects absence
- **THEN** no line that runs on Adform is evaluated
- **AND** an Adform run evaluates no line that runs on Equativ

#### Scenario: A Deal that never receives bids is a line without delivery
- **WHEN** operations wrote the package `900000001` for a target `Deal` line on 2026-11-01, the package never appears in any Equativ report nor in the catalogue, and the line's flight from 2026-11-01 to 2026-11-15 ends inside the window of an Equativ run started at 06:15 UTC on 2026-11-18
- **THEN** a `missing_delivery` exception is recorded against that line and period
- **AND** the same happens when the id written is well formed but names no package of Equativ, such as `900000009`: it passes the check at creation and is surfaced here
