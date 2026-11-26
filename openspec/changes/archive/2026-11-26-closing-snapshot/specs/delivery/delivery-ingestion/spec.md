## MODIFIED Requirements

### Requirement: Ingestion is idempotent over a rolling window

The system SHALL replace, not append, the delivery already held for the date range being ingested, so that re-running a range yields the same result as running it once. The replacement SHALL apply whether or not the days of the range fall in a closed month: the stored delivery is the DSP's latest figure, kept as information, while the margin of a closed month is read from what its closing froze (`finance/rebate-accrual`) and the difference only raises the warning that the delivery changed after closing (`finance/margin-reporting`).

#### Scenario: Re-running a range replaces it
- **WHEN** an ingestion run for a date range is executed a second time
- **THEN** the delivery held for that range reflects the second run only
- **AND** no duplicate record exists for any line and date in that range

#### Scenario: A restated figure supersedes the earlier one
- **WHEN** the DSP reports a different figure for a day already ingested and that day falls inside the reprocessing window
- **THEN** the stored figure is updated to the restated value

#### Scenario: Delivery outside the window is untouched
- **WHEN** an ingestion run covers a date range
- **THEN** delivery held for dates outside that range is left unchanged

#### Scenario: A restated day of a closed month supersedes the delivery and not the closed margin
- **WHEN** November is closed on 1 December and the run of 3 December receives a restated figure for 28 November
- **THEN** the stored delivery of 28 November is updated to the restated value
- **AND** the margin of the closed November flights is the one frozen at closing, and the flights whose delivery changed beyond the tolerance carry `delivery_changed`

### Requirement: A line's mapping can be removed with its delivery

The system SHALL expose `DELETE /api/campaign-lines/{id}/dsp-mappings`. When the line has exactly one mapping, it deletes the mapping and the line's ingested delivery in one transaction and returns how many days of delivery it removes; with several mappings it answers 409 `ambiguous_mapping`; with none, 404. The delivery of a line only comes from its mapping while the API is the only ingestion route; this assumption must be revisited when the manual upload exists. Reopening the exception is out of scope: the delivery reappears as unmatched at the next ingestion. The days of a closed month are deleted like any other; the figures of the line's closed flights are those frozen at closing.

#### Scenario: The only mapping is removed with its delivery
- **WHEN** a line with exactly one mapping is unlinked
- **THEN** the mapping and the line's ingested delivery are deleted in one transaction
- **AND** the response carries the number of days of delivery removed

#### Scenario: Several mappings are ambiguous
- **WHEN** a line with several mappings is unlinked
- **THEN** the answer is 409 `ambiguous_mapping` and nothing is deleted

#### Scenario: A line without a mapping is not found
- **WHEN** a line with no mapping is unlinked
- **THEN** the answer is 404 `mapping_not_found`

#### Scenario: An unknown line is not found
- **WHEN** a line that does not exist is unlinked
- **THEN** the answer is 404 `line_not_found`

#### Scenario: Unlinking a line with a closed flight keeps its closed figures
- **WHEN** a line whose August flight is closed is unlinked, and its delivery of August is deleted with the mapping
- **THEN** the August flight still reports the amounts and volumes frozen at closing
- **AND** it carries `delivery_changed`

### Requirement: The nightly ingestion is one command that uses the same service as every other route

The system SHALL provide the command `python -m scripts.run_ingestion`, to be invoked by the host scheduler once per DSP, that calculates the window, ingests the lines with a validated mapping with one request to the DSP, records the batch, and then runs the absence detection with the identifier of that batch, through the same service as any other entry route. An optional `--date YYYY-MM-DD` SHALL replace today so a window can be repeated. An optional `--dsp NAME` SHALL name the DSP to ingest, `Adform` when absent; only a DSP with a connector, `Adform` or `Equativ`, is accepted. Two runs of the same DSP SHALL never overlap; runs of different DSPs may. The absence detection of an Equativ run SHALL run only when the run started at or after 06:00 UTC; an earlier Equativ run SHALL skip it and print `absences: skipped, before 06:00 UTC`. There SHALL be no dry-run option. A succeeded run, with the rolling window or a custom range, SHALL print `closed_month_days`: how many calendar days of its window fall in a month that holds at least one closing header (`finance/rebate-accrual`) at the end of the run. It never refuses or skips those days.

#### Scenario: A successful run ingests and then detects absence
- **WHEN** the command runs and the DSP answers
- **THEN** the batch succeeds, absence is detected with that batch's identifier, and the exit code is 0

#### Scenario: A failed run leaves a failed batch and no partial rows
- **WHEN** the DSP client fails
- **THEN** a batch with a failed outcome exists, the window holds no partial rows, absence is not detected and the exit code is 1

#### Scenario: Two runs never overlap
- **WHEN** the command starts while another run of the same DSP holds the lock
- **THEN** it does nothing and exits with code 2

#### Scenario: Missing configuration stops the run before it starts
- **WHEN** the DSP credentials, the database or the time zone are not configured, or `--dsp` names a DSP without a connector
- **THEN** no batch is created and the exit code is 3

#### Scenario: Repeating a window changes nothing
- **WHEN** the command runs twice for the same date and the DSP reports the same figures
- **THEN** the delivery rows and the exceptions are the same as after the first run

#### Scenario: The output states counts and never values
- **WHEN** the command prints its result
- **THEN** it shows only states and counts: rows read, ignored, unmatched zeros, new exceptions, skipped lines, absences and days in closed months
- **AND** it never prints an identifier, a name, an amount, a token or the text of a DSP error
- **AND** a failure is summarised by the name of its error class

#### Scenario: Equativ is ingested by its own run
- **WHEN** the command runs with `--dsp Equativ`
- **THEN** only the lines that run on Equativ with a validated Equativ mapping are ingested, from one Equativ report
- **AND** the batch records the DSP Equativ

#### Scenario: Without --dsp the command ingests Adform
- **WHEN** the command runs with no `--dsp`
- **THEN** it ingests Adform exactly as before

#### Scenario: Runs of two DSPs may overlap
- **WHEN** an Equativ run starts while an Adform run holds its lock
- **THEN** the Equativ run proceeds

#### Scenario: An early Equativ run skips the absence detection
- **WHEN** an Equativ run starts at 05:59 UTC
- **THEN** the batch is ingested and the output says `absences: skipped, before 06:00 UTC`
- **AND** a run started at 06:00 UTC detects absence with its batch's identifier

#### Scenario: The run counts the days of its window in closed months
- **WHEN** the nightly run of 2026-12-03 ingests 2026-11-26 to 2026-12-02 and November is closed
- **THEN** it ingests the seven days and prints `closed_month_days: 5`
- **AND** with November open it prints `closed_month_days: 0`

#### Scenario: A custom range over closed months counts their days
- **WHEN** a custom range from 2026-10-15 to 2026-11-14 runs with October closed and November open
- **THEN** the range is replaced as one and the output prints `closed_month_days: 17`

#### Scenario: A failed run prints no count of closed days
- **WHEN** the DSP client fails
- **THEN** the output shows `status: failed` and the name of the error class, and no `closed_month_days`
