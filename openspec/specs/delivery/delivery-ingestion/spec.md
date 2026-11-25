# delivery/delivery-ingestion Specification

## Purpose
Bringing delivery figures from a DSP or an uploaded export into one delivery model, repeatably and without duplication, so that what a campaign actually served is a stored fact with a recorded provenance rather than the residue of a manual download.

## Requirements

### Requirement: Delivery is stored per campaign line and day

The system SHALL store delivery at the grain of one campaign line and one calendar day, holding impressions, clicks, media cost, measurable impressions, viewable impressions, OTS, video completions, the buyer's spend, the reported revenue, the third-party data cost and the audience data cost. OTS SHALL be stored as an exact decimal with four decimals and video completions as a whole number; both SHALL be mandatory and SHALL default to zero, so that delivery stored before they existed reads zero OTS and zero completions. The four amounts SHALL be stored as exact decimals with six decimals, SHALL be mandatory and SHALL default to zero, so that Adform delivery, which reports none of them, and delivery stored before they existed read zero in all four.

#### Scenario: A day of delivery is recorded against its line
- **WHEN** an ingestion run retrieves a day of delivery for a mapped campaign line
- **THEN** one delivery record exists for that line and date
- **AND** its media cost is stored as an exact decimal value

#### Scenario: Delivered volume never overwrites contracted volume
- **WHEN** delivery is ingested for a campaign line
- **THEN** the line's contracted impressions are unchanged
- **AND** the two quantities remain separately readable

#### Scenario: A DOOH day keeps its OTS decimals
- **WHEN** a run stores a day of a DOOH line with 500 impressions and 8,999.75 OTS
- **THEN** the record holds 500 impressions and an OTS of exactly 8999.7500

#### Scenario: A CTV day keeps its video completions
- **WHEN** a run stores a day of a CTV line with 50,000 impressions and a video completion rate of 0.8123
- **THEN** the record holds 50,000 impressions and 40,615 video completions
- **AND** no rate is stored

#### Scenario: Delivery stored before the change reads zeros
- **WHEN** a delivery record stored before OTS and video completions existed is read
- **THEN** its OTS is 0.0000 and its video completions are 0

#### Scenario: An Equativ day keeps its four amounts
- **WHEN** a run stores a day of an Equativ line with 61,628 impressions, a buyer's spend of 338.954, a reported revenue of 271.1632 and no data costs
- **THEN** the record holds a buyer's spend of exactly 338.954000, a reported revenue of exactly 271.163200, both data costs at 0 and a media cost of 0

#### Scenario: An Adform day reads zero in the four amounts
- **WHEN** a run stores a day of an Adform line
- **THEN** its buyer's spend, reported revenue and both data costs are 0

### Requirement: Ingestion is idempotent over a rolling window

The system SHALL replace, not append, the delivery already held for the date range being ingested, so that re-running a range yields the same result as running it once.

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

### Requirement: Every ingestion run is recorded as a batch

The system SHALL record each ingestion run with its route, its source, its start and end times, its outcome, the number of rows read, the number of rows ignored for having no attributed line item and the number of unmatched rows ignored for having no impressions, no cost and no OTS, and SHALL associate every delivery record with the batch that produced it. The outcome SHALL be one of `running`, `succeeded` or `failed`.

#### Scenario: A successful run is traceable to its source
- **WHEN** an ingestion run completes
- **THEN** a batch record exists naming the route, the DSP and the source
- **AND** every delivery record it produced references that batch

#### Scenario: The batch counts the rows it read and the rows it ignored
- **WHEN** a run reads rows of which some have no attributed line item and some are unmatched with zero impressions, zero cost and zero OTS
- **THEN** the batch's row count is the number of rows read
- **AND** its ignored rows and its zero unmatched rows are counted separately

#### Scenario: A failed run is recorded, not silently dropped
- **WHEN** an ingestion run fails partway
- **THEN** a batch record exists with a failed outcome
- **AND** the run leaves no partially applied date range

### Requirement: Manual upload shares the ingestion contract

The system SHALL accept an uploaded delivery export through the same ingestion model as the API route, differing only in the recorded route and source.

#### Scenario: An uploaded file produces the same delivery model
- **WHEN** an operations user uploads a delivery export
- **THEN** the resulting delivery records are indistinguishable in shape from those ingested through the API
- **AND** the batch records the upload route and the source file name

#### Scenario: An uploaded file is validated before parsing
- **WHEN** a file is uploaded whose type or size is not accepted
- **THEN** it is rejected before any parsing occurs

#### Scenario: A malformed file fails with a precise message
- **WHEN** an uploaded file has an unexpected structure
- **THEN** the failure names the file, the sheet and the row
- **AND** no partial delivery is stored

### Requirement: The configured channel is authoritative over the DSP's

The system SHALL take the channel from the campaign line's configuration, SHALL store the DSP's reported line format only as contrast data, and SHALL flag a disagreement for review rather than reclassifying.

#### Scenario: A disagreement is flagged, never applied
- **WHEN** ingested delivery reports a line format that differs from the campaign line's configured channel
- **THEN** the line's channel is unchanged
- **AND** the reported value is stored as contrast data
- **AND** the row is flagged for review

### Requirement: Lines are ingested when their mapping is validated and their own dates overlap the window

The system SHALL ingest delivery for every campaign line that runs on the DSP being ingested, carries a validated DSP mapping for that DSP and whose own start and end dates overlap the ingestion window, whatever the campaign's status, and SHALL NOT fail the run because other such lines lack a validated mapping.

#### Scenario: An unmapped line is skipped without failing the run
- **WHEN** an ingestion run encounters a line whose dates overlap the window and that has no DSP mapping
- **THEN** that line is skipped and reported
- **AND** the run completes for every mapped line

#### Scenario: A mapping that is not validated does not make a line ingestable
- **WHEN** the only mapping of a line has no validation timestamp
- **THEN** the line is not ingested
- **AND** it is counted among the skipped lines

#### Scenario: A mapping for another DSP does not make a line ingestable
- **WHEN** a line's mapping belongs to a DSP other than the one being ingested
- **THEN** the line is not ingested
- **AND** it is counted among the skipped lines

#### Scenario: A line that ended inside the window is still ingested
- **WHEN** a line ended three days before the run and has a validated mapping
- **THEN** its delivery is ingested, whatever the campaign's status
- **AND** figures the DSP restates for it are picked up

#### Scenario: A line that ended before its campaign is judged by its own dates
- **WHEN** a line ended before the window while its campaign is still running
- **THEN** the line is neither ingested nor counted among the skipped lines

#### Scenario: A line that starts mid-campaign is ingested from its own start
- **WHEN** a line starts inside the window while its campaign started earlier
- **THEN** the line is ingested

#### Scenario: A line that has not started is neither ingested nor skipped
- **WHEN** a line starts after the last day of the window
- **THEN** it is not ingested
- **AND** it is not counted among the skipped lines

#### Scenario: Delivery outside every flight of its line is stored
- **WHEN** a delivery row of a mapped line is dated outside all the flights of that line
- **THEN** it is stored all the same
- **AND** it counts toward a flight only if it lies inside that flight's window

#### Scenario: A line with several external pairs is ingested through all its validated pairs
- **WHEN** a line holds several validated pairs
- **THEN** every validated pair is ingested
- **AND** the line is not counted among the skipped lines

### Requirement: Media cost keeps the precision the DSP reports

The system SHALL store media cost without losing any of the up to six decimals a DSP reports.

#### Scenario: A six-decimal cost is stored and read back unchanged
- **WHEN** a day of delivery with a media cost of six decimals is stored
- **THEN** reading it back returns exactly the same value

### Requirement: External identifiers are compared as text

The system SHALL compare a DSP's external campaign and line item identifiers with a mapping as text, whatever type the DSP reports them in.

#### Scenario: A numeric identifier matches its textual mapping
- **WHEN** the DSP reports a line item identifier as a number and a mapping holds the same digits as text
- **THEN** the delivery row resolves to the mapped campaign line

### Requirement: An external identifier pair maps to at most one campaign line per DSP

The system SHALL NOT allow two campaign lines to carry the same external campaign identifier and external line item identifier for the same DSP.

#### Scenario: A second mapping to the same pair is rejected
- **WHEN** a mapping is created for a pair already mapped to another campaign line of the same DSP
- **THEN** the creation is rejected as a conflict
- **AND** the existing mapping is unchanged

### Requirement: Several external line items on one campaign line are combined per day

The system SHALL combine the delivery of every external line item mapped to the same campaign line into one record per day, summing impressions, clicks, media cost, measurable impressions, viewable impressions, OTS, video completions, the buyer's spend, the reported revenue and the two data costs. It SHALL never sum, average or store a video completion rate: each row's completions are computed from its own rate before the rows are summed.

#### Scenario: Two external line items of one line are summed
- **WHEN** two external line items mapped to the same campaign line report delivery for the same day
- **THEN** one delivery record exists for that line and date
- **AND** each of its figures is the sum of the two reported figures

#### Scenario: Two DOOH line items sum their OTS decimals
- **WHEN** two line items of one DOOH line report, for the same day, 410 impressions with 7,500.50 OTS and 90 impressions with 1,499.25 OTS
- **THEN** the day holds 500 impressions and 8,999.7500 OTS

#### Scenario: Completions are summed, not rates
- **WHEN** two line items of one CTV line report, for the same day, 1,000 impressions at a completion rate of 0.75 and 3 impressions at a completion rate of 0.50
- **THEN** the day holds 1,003 impressions and 752 video completions (750 plus 2)
- **AND** no averaged rate is stored

#### Scenario: Two Equativ packages of one line sum their amounts
- **WHEN** two packages mapped to one line report, for the same day, a reported revenue of 271.1632 and 50.30080
- **THEN** the day holds a reported revenue of exactly 321.464000

### Requirement: Delivery the DSP does not attribute to a line item is ignored and counted

The system SHALL ignore delivery rows the DSP reports without an attributed line item, SHALL count them on the batch as ignored, and SHALL NOT turn them into exceptions.

#### Scenario: An unattributed row is counted, not worked
- **WHEN** a run retrieves a row with no attributed line item
- **THEN** the batch records it among its ignored rows
- **AND** no exception is recorded for it

#### Scenario: A currency other than EUR fails the run
- **WHEN** a run retrieves a delivery row reported in a currency other than EUR that is not an unattributed row
- **THEN** the run fails with a failed batch
- **AND** nothing is converted and no part of the range is stored

### Requirement: A DSP mapping is created against an identifier pair checked with the DSP

The system SHALL check an external identifier pair with the DSP when a mapping is created, SHALL distinguish a pair that was found, one the DSP does not know and a DSP that could not be reached, SHALL create the mapping in all three cases, and SHALL set `validated_at` only when the pair was found. Equativ is the exception: its mapping is created from the `auctionPackageDealId` operations writes, SHALL count as validated by the user, SHALL set `validated_at` at creation with the outcome `user_validated`, and SHALL ask Equativ nothing and require nothing of the catalogue. Its pair SHALL carry the same `auctionPackageDealId` in both identifiers, written as a positive integer of ASCII digits with no leading zero (`^[1-9][0-9]*$`): `0` is not a package, and `0900000001` would never match the `900000001` the report carries; any other pair for a line on Equativ SHALL be rejected with 422 `invalid_equativ_package` and nothing stored. A wrong id is not detected at creation: it is surfaced by the check for lines without delivery (`delivery/ingestion-exceptions`).

#### Scenario: A found pair is validated
- **WHEN** a mapping is created for a pair the DSP knows
- **THEN** the mapping carries a validation timestamp

#### Scenario: An unknown pair and an unreachable DSP are different outcomes
- **WHEN** the DSP does not know the pair, or cannot be reached
- **THEN** the two outcomes are distinguishable from each other and from a found pair
- **AND** the mapping is created without a validation timestamp

#### Scenario: A DSP that fails for another reason does not create a mapping
- **WHEN** the DSP answers the check with a failure that is not an unreachable DSP, such as refused credentials
- **THEN** the request fails and no mapping is created

#### Scenario: An Equativ package written by operations is validated by the user
- **WHEN** operations creates a mapping for a line on Equativ with the package `900000001` in both identifiers
- **THEN** the mapping carries a validation timestamp and the outcome `user_validated`
- **AND** no request is sent to Equativ

#### Scenario: An Equativ package not yet in the catalogue is validated all the same
- **WHEN** the package written is not in the Equativ catalogue
- **THEN** the mapping is created validated by the user, and its `last_impressions_date` is null

#### Scenario: A malformed Equativ pair is refused
- **WHEN** a mapping for a line on Equativ carries two different identifiers, or an identifier with characters other than digits
- **THEN** the request is rejected with 422 `invalid_equativ_package` and no mapping is stored

#### Scenario: A zero Equativ package is refused
- **WHEN** a mapping for a line on Equativ carries `0` in both identifiers
- **THEN** the request is rejected with 422 `invalid_equativ_package` and no mapping is stored

#### Scenario: An Equativ package with a leading zero is refused
- **WHEN** a mapping for a line on Equativ carries `0900000001` in both identifiers
- **THEN** the request is rejected with 422 `invalid_equativ_package` and no mapping is stored

### Requirement: Creating a DSP mapping requires the operations role

The system SHALL accept the creation of a DSP mapping only from a user holding the `operations` role.

#### Scenario: A user without the operations role is forbidden
- **WHEN** a user without the `operations` role creates a DSP mapping
- **THEN** the request is rejected as forbidden

#### Scenario: A request without a valid token is unauthenticated
- **WHEN** a DSP mapping is created without a valid token
- **THEN** the request is rejected as unauthenticated

#### Scenario: A pair the DSP is not asked about twice
- **WHEN** a mapping is created for a pair already mapped for that DSP
- **THEN** it is rejected as a conflict without asking the DSP

### Requirement: Today and the ingestion window are calendar days in a configured time zone

The system SHALL calculate "today", and from it the D-1 and the D-7 to D-1 window, as a calendar date in the time zone `Europe/Madrid`, configurable by an environment variable, and SHALL use that same zone for the ingestion, the pacing and the missing-data flag of the daily status, whatever the zone of the server. Equativ is asked for the dates of the window as days of `Etc/UTC`, the zone in which it bills: the delivery stored for a date of an Equativ line is the delivery of that UTC day.

#### Scenario: Late evening in Madrid is already the next day
- **WHEN** it is 23:30 in Madrid on 10 August, which is 21:30 UTC
- **THEN** today is 10 August and D-1 is 9 August
- **AND** at 00:30 in Madrid on 11 August, 22:30 UTC on the 10th, today is 11 August

#### Scenario: A change of daylight saving time does not move the day
- **WHEN** the clocks change in Madrid
- **THEN** every instant still belongs to exactly one calendar day of Madrid
- **AND** today is the date shown on a clock in Madrid at that instant

#### Scenario: The API and the nightly command agree on the day
- **WHEN** the daily status and the nightly run are evaluated at the same instant
- **THEN** both use the same today

#### Scenario: An Equativ date is a UTC day
- **WHEN** an Equativ run ingests 2026-11-19
- **THEN** the delivery stored for that date is what Equativ reports for 2026-11-19 from 00:00 to 24:00 UTC

### Requirement: The nightly ingestion is one command that uses the same service as every other route

The system SHALL provide the command `python -m scripts.run_ingestion`, to be invoked by the host scheduler once per DSP, that calculates the window, ingests the lines with a validated mapping with one request to the DSP, records the batch, and then runs the absence detection with the identifier of that batch, through the same service as any other entry route. An optional `--date YYYY-MM-DD` SHALL replace today so a window can be repeated. An optional `--dsp NAME` SHALL name the DSP to ingest, `Adform` when absent; only a DSP with a connector, `Adform` or `Equativ`, is accepted. Two runs of the same DSP SHALL never overlap; runs of different DSPs may. The absence detection of an Equativ run SHALL run only when the run started at or after 06:00 UTC; an earlier Equativ run SHALL skip it and print `absences: skipped, before 06:00 UTC`. There SHALL be no dry-run option.

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
- **THEN** it shows only states and counts: rows read, ignored, unmatched zeros, new exceptions, skipped lines and absences
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

### Requirement: The Adform line catalogue is filled by the ingestion

The system SHALL ask Adform, in the one nightly request, for `date`, `campaignID`, `campaign`, `lineItemID`, `lineItem`, `lineItemStartDate`, `lineItemEndDate` and `campaignCurrency` with the seven metrics `impressions`, `clicks`, `cost`, `measurableImpressions`, `viewImpressionsIAB`, `ots` and `videoCompletionRate`, and SHALL keep one catalogue row per DSP and identifier pair (`dsp_catalog_lines`) with the campaign and line item names, the line's dates, `first_seen_date`, `last_seen_date` and `last_impressions_date`. The catalogue SHALL be updated, in the same transaction as the batch, with every attributed row of the window (line item greater than 0 and currency EUR), mapped or not and with zeros or not. Rows without an attributed line item SHALL NOT enter. The dates arrive as `YYYY-MM-DDTHH:MM:SS` and only the date is kept. `first_seen_date` and `last_seen_date` are the oldest and the latest delivery date seen for the pair, and `last_impressions_date` the latest one with impressions greater than 0 (null if none), whatever the pair's OTS; `last_seen_date` is the last date with a row in Adform, not real activity. The request SHALL be made even when no line has a validated mapping, so that the catalogue can be filled before the first mapping exists.

#### Scenario: The request asks for the seven metrics
- **WHEN** the nightly request is sent to Adform
- **THEN** its metrics are `impressions`, `clicks`, `cost`, `measurableImpressions`, `viewImpressionsIAB`, `ots` and `videoCompletionRate`

#### Scenario: A new pair enters the catalogue
- **WHEN** a run reads an attributed row whose pair is not in the catalogue
- **THEN** a catalogue row is created with its names, dates and seen dates

#### Scenario: A known pair is updated
- **WHEN** a later run reads rows of a pair already in the catalogue
- **THEN** names and dates take the latest values and the seen dates only widen

#### Scenario: A pair that only delivers zeros enters with no impressions date
- **WHEN** every row of a pair has zero impressions
- **THEN** the pair is in the catalogue and `last_impressions_date` is null

#### Scenario: Unattributed rows do not enter
- **WHEN** a row has no attributed line item
- **THEN** the catalogue does not change

#### Scenario: A failed batch leaves the catalogue untouched
- **WHEN** the batch fails after the catalogue was prepared
- **THEN** the catalogue is as it was before the run

#### Scenario: A run without mapped lines still fills the catalogue
- **WHEN** no line has a validated mapping
- **THEN** one request is made, the catalogue is filled, the batch is recorded and the output shows `mapped_lines: 0`

### Requirement: The catalogue can be listed by operations

The system SHALL expose `GET /api/dsp-catalog` to the `operations` role, with the filters `dsp_id`, `q` (case-insensitive text in either name), `mapped` (true, false or absent) and `active_since` (`last_seen_date >= active_since`), paginated (50 by default, 200 at most). Each item SHALL carry the names, the pair, the dates, `last_impressions_date` and `mapped_line_id` when a mapping exists. It SHALL carry no cost.

#### Scenario: Filtering and paging
- **WHEN** the catalogue is requested with filters and a page size
- **THEN** only matching rows are returned, at most the page size, and a page size above 200 is rejected

#### Scenario: Reading the catalogue requires the operations role
- **WHEN** a user without the `operations` role requests it
- **THEN** the request is rejected as forbidden

### Requirement: Lines without a mapping can be listed

The system SHALL expose `GET /api/campaign-lines/unmapped` to the `operations` role, listing the lines with no DSP mapping with their id, campaign name, line number, dates and DSP.

#### Scenario: A line without a mapping is listed
- **WHEN** operations requests the unmapped lines and a line has no DSP mapping
- **THEN** the line appears with its campaign name, line number, dates and DSP

#### Scenario: A mapped line is not listed
- **WHEN** a line has a DSP mapping, validated or not
- **THEN** it does not appear in the list

#### Scenario: Listing requires the operations role
- **WHEN** a user without the `operations` role requests the unmapped lines
- **THEN** the request is rejected as forbidden

### Requirement: An exception is linked to a campaign line

The system SHALL expose `POST /api/ingestion-exceptions/{id}/link` with `{"campaign_line_id": N}`, which in one transaction creates a validated mapping from the pair of an `unmatched_delivery` exception to that line and resolves the exception with the note `linked to line N`. The mapping is validated because the exception proves the pair exists in its DSP; the pair need not be in the catalogue and the DSP is not asked. The retained delivery SHALL NOT move to the daily deliveries: the seven-day window will bring it. The errors are 404 `exception_not_found` and `line_not_found`, and 409 `exception_already_resolved`, `mapping_pair_taken` and `exception_not_linkable` (any type other than `unmatched_delivery`). The line must run on the DSP of the exception's pair; otherwise the answer is 422 `line_dsp_mismatch`, because a mapping to another DSP's line would never be ingested. The response carries the mapping, the resolved exception and `needs_history_load`. Nothing is stored when any error occurs.

#### Scenario: Linking succeeds
- **WHEN** an open unmatched exception is linked to an existing line
- **THEN** the mapping exists and is validated, and the exception is resolved with the automatic note

#### Scenario: A line of another DSP is refused
- **WHEN** the line runs on a different DSP than the exception's pair
- **THEN** the answer is 422 `line_dsp_mismatch` and nothing is stored

#### Scenario: Linking fails whole
- **WHEN** the exception is resolved, the pair is taken, the type is not linkable or a line or exception does not exist
- **THEN** the matching error is returned and no mapping is created and no exception changes

#### Scenario: An Equativ package is linked to a Deal line
- **WHEN** an open unmatched exception of an Equativ package is linked to a line that runs on Equativ
- **THEN** the mapping exists and is validated, the exception is resolved, and Equativ is not asked

### Requirement: A line's mapping can be removed with its delivery

The system SHALL expose `DELETE /api/campaign-lines/{id}/dsp-mappings`. When the line has exactly one mapping, it deletes the mapping and the line's ingested delivery in one transaction and returns how many days of delivery it removes; with several mappings it answers 409 `ambiguous_mapping`; with none, 404. The delivery of a line only comes from its mapping while the API is the only ingestion route; this assumption must be revisited when the manual upload exists. Reopening the exception is out of scope: the delivery reappears as unmatched at the next ingestion.

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

### Requirement: Mapping responses warn about idle pairs and missing history

The response of the mapping creation SHALL include `last_impressions_date` (optional, null when the pair is not in the catalogue) and, with that of the link, `needs_history_load`: true when the mapped line started before the start of the normal window (today minus 7 days, in the Madrid zone). A line starting exactly on that day does not need it.

#### Scenario: A catalogue pair without impressions has no impressions date
- **WHEN** a mapping is created for a pair that is in the catalogue and never delivered impressions
- **THEN** `last_impressions_date` is null

#### Scenario: A line that started before the start of the window needs a history load
- **WHEN** a mapped line started before today minus 7 days
- **THEN** `needs_history_load` is true

#### Scenario: A line that started exactly at the limit does not
- **WHEN** a mapped line started exactly on today minus 7 days
- **THEN** `needs_history_load` is false

### Requirement: A custom range can be loaded

`python -m scripts.run_ingestion --from YYYY-MM-DD --to YYYY-MM-DD`, with or without `--dsp`, SHALL accept both arguments together, never with `--date`, for at most 31 days and with `--to` not after D-1 in the Madrid zone; anything else exits with 3. It SHALL make one request for the whole range, select the lines whose dates overlap it, and use the same service and the same idempotent replacement. Every batch SHALL record its window in `window_start` and `window_end` (both null or both set, start not after end; legacy batches have none). Absence detection SHALL NOT run with a custom range and the output says `absences: skipped, custom range`. The output always shows `mapped_lines` and only counts.

#### Scenario: Range rules
- **WHEN** the range exceeds 31 days, ends after D-1, lacks one bound or is combined with `--date`
- **THEN** the exit code is 3 and nothing is requested

#### Scenario: Repeating a range changes nothing
- **WHEN** the same range runs twice with the same figures
- **THEN** the stored delivery is the same

#### Scenario: A custom range of Equativ
- **WHEN** the command runs with `--dsp Equativ --from 2026-11-01 --to 2026-11-23`
- **THEN** one Equativ report covers 2026-11-01 00:00 UTC to 2026-11-24 00:00 UTC and the range is replaced as one
- **AND** absence detection is skipped

### Requirement: Adform OTS and video completions are read per row

The system SHALL read, from each Adform row, the `ots` metric as a decimal rounded to four decimals, half to even, and the video completions as the row's `videoCompletionRate` times its impressions, rounded to a whole number, half to even. Both cells SHALL be read as exact decimals from their textual value and rounded in decimal arithmetic; neither value SHALL pass through a binary floating-point number before it is rounded. An empty cell (`null`, `""` or `"-"`) in either metric SHALL count as zero. A non-empty value that cannot be read as a number SHALL fail the run as a format error, as SHALL a report that lacks the `ots` or the `videoCompletionRate` column. OTS SHALL NEVER be replaced by the row's impressions.

#### Scenario: OTS keep four decimals
- **WHEN** a row reports 7,500.12345 OTS
- **THEN** its OTS are read as 7500.1234

#### Scenario: Completions are the rate times the impressions of the row
- **WHEN** a row reports 50,000 impressions and a completion rate of 0.8123
- **THEN** its video completions are 40,615

#### Scenario: A half completion rounds to the even number
- **WHEN** one row reports 5 impressions and another 3 impressions, both at a completion rate of 0.5
- **THEN** the first row's completions are 2 (2.5 rounded half to even) and the second's are 2 (1.5 rounded half to even)

#### Scenario: Rounding is decimal, not binary floating point
- **WHEN** a row reports 100 impressions at a completion rate of 0.575 and 100.00035 OTS
- **THEN** its video completions are 58, because 0.575 × 100 is exactly 57.5 and rounds half to even to 58, not the 57 that a binary float (57.49999…) would give
- **AND** its OTS are 100.0004, because 100.00035 rounds half to even to 100.0004, not the 100.0003 that a binary float would give

#### Scenario: An empty cell is zero
- **WHEN** a row reports 1,200 impressions with an empty `ots` cell and a `videoCompletionRate` cell holding `"-"`
- **THEN** its OTS are 0.0000 and its video completions are 0
- **AND** its OTS are not replaced by its 1,200 impressions
- **AND** the run succeeds

#### Scenario: An unreadable value fails the run
- **WHEN** a row reports `"n/a"` in its `ots` cell
- **THEN** the run fails as a format error with a failed batch
- **AND** no part of the range is stored

#### Scenario: A report without the new columns fails the run
- **WHEN** Adform returns a report that lacks the `ots` column, or the `videoCompletionRate` column
- **THEN** the run fails as a format error naming the missing column

### Requirement: Equativ delivery is read from one asynchronous report per run

The system SHALL read the delivery of Equativ, for the window of a run, from one asynchronous report created with `POST /async-report` on the Equativ demand API, authenticated with the client-credentials token of the configured Equativ application. The report SHALL ask, with the time zone `Etc/UTC` and the use case `RTB`, for the dimensions `day`, `auctionPackageDealId` and `auctionPackageDealName` and the metrics `impressions`, `companyCurrencySpend`, `paidBuyerConnectCompanyVendorCostCompanyCurrency`, `paidBuyerConnectThirdPartyVendorCostCompanyCurrency`, `paidBuyerConnectAudienceVendorCostCompanyCurrency`, `clicks`, `viewableImpressions` and `videoComplete`, with no filter, from the window's first day at 00:00 UTC to the day after its last day at 00:00 UTC, because Equativ's end date is exclusive. It SHALL carry no scheduling and no post-processing configuration, so that Equativ sends no email and writes no file. The run SHALL wait for the report's execution, asking every 30 seconds for at most 15 minutes, until its status is `PostProcessingSuccessful`; any other final status, or no final status within 15 minutes, SHALL fail the run. The rows SHALL be read from the report's preview, in pages of 100, until as many rows as the preview's `totalRows` have been read; a preview that is not ready or that yields a different number of rows SHALL fail the run. The download link SHALL NOT be fetched, and the report SHALL NOT be deleted. The batch SHALL record the report's identifier as its source as soon as the report is created, in a transaction of its own, so that a run that fails afterwards still names its report.

#### Scenario: One report covers the window
- **WHEN** an Equativ run ingests the window from 2026-11-17 to 2026-11-23
- **THEN** one report is created with `startDate` `2026-11-17T00:00:00.000Z`, `endDate` `2026-11-24T00:00:00.000Z` and `timezone` `Etc/UTC`
- **AND** it has no scheduling and no post-processing configuration

#### Scenario: The run waits for the report
- **WHEN** the report's execution reads `PubSubPublishSuccessful` and, 30 seconds later, `PostProcessingSuccessful`
- **THEN** the run reads the preview after the second answer

#### Scenario: A report that never finishes fails the run
- **WHEN** the execution has no final status 15 minutes after the report was created
- **THEN** the run fails with a failed batch and no part of the window is stored

#### Scenario: The preview is read page by page
- **WHEN** the preview reports 238 rows in total
- **THEN** the run reads three pages of 100, 100 and 38 rows and ingests the 238

#### Scenario: A short preview fails the run
- **WHEN** the pages of the preview yield fewer rows than its `totalRows`
- **THEN** the run fails as a format error and no part of the window is stored

#### Scenario: The report is traceable from the batch
- **WHEN** an Equativ run succeeds
- **THEN** its batch records the route `api`, the DSP Equativ, the window and the report's identifier as its source

#### Scenario: A failed run still names its report
- **WHEN** an Equativ run fails after its report was created, while waiting for it or reading its preview
- **THEN** its batch has a failed outcome and records the report's identifier as its source

### Requirement: Equativ rows are read with their amounts and keyed by the auction package

The system SHALL read each row of the Equativ report as one day of delivery of one auction package. The pair that identifies it SHALL be the `auctionPackageDealId` as text in both the external campaign and the external line item identifier. A row whose `auctionPackageDealId` is empty or `0` SHALL be treated as delivery without an attributed line item. The day SHALL be read from `day`, which arrives as `YYYY-MM-DDTHH:MM:SS`, keeping only the date. Impressions, clicks, viewable impressions and video completions SHALL be read as whole numbers from `impressions`, `clicks`, `viewableImpressions` and `videoComplete`. The buyer's spend, the reported revenue, the third-party data cost and the audience data cost SHALL be read as exact decimals from the text of `companyCurrencySpend`, `paidBuyerConnectCompanyVendorCostCompanyCurrency` (Equativ's «Total Curator Margin»), `paidBuyerConnectThirdPartyVendorCostCompanyCurrency` and `paidBuyerConnectAudienceVendorCostCompanyCurrency`, never through a binary floating-point number. Equativ reports no media cost, so the media cost SHALL be zero; measurable impressions and OTS SHALL be zero and the banner size, screen and line format empty. A missing column, an empty cell or a value that cannot be read SHALL fail the run as a format error.

#### Scenario: A row becomes one day of one package
- **WHEN** a row reports `day` `2026-11-19T00:00:00`, package `900000001`, 61,628 impressions, a spend of 338.954 and a total curator margin of 271.1632
- **THEN** it is one day of delivery dated 2026-11-19 for the pair (`900000001`, `900000001`)
- **AND** it carries 61,628 impressions, a buyer's spend of exactly 338.954000, a reported revenue of exactly 271.163200 and a media cost of zero

#### Scenario: The data costs are read separately
- **WHEN** a row reports a third-party data cost of 0 and an audience data cost of 1.25
- **THEN** its third-party data cost is 0 and its audience data cost is exactly 1.250000

#### Scenario: A row without a package is unattributed
- **WHEN** a row reports `auctionPackageDealId` `0`
- **THEN** it is counted on the batch among the ignored rows and no exception is recorded for it

#### Scenario: An unreadable amount fails the run
- **WHEN** a row reports `n/a` as its spend, or the report lacks the `videoComplete` column
- **THEN** the run fails as a format error and no part of the window is stored

### Requirement: The Equativ catalogue is filled by the ingestion

The system SHALL keep, in the same catalogue as Adform, one row per Equativ pair with the package name as reported in both the campaign and the line item name, no line dates, `first_seen_date`, `last_seen_date` and `last_impressions_date`, updated in the same transaction as the batch with every attributed row of the window, mapped or not. The name SHALL be kept as Equativ reports it, invisible characters included; the pair, not the name, identifies the package. The report SHALL be requested even when no line has a validated Equativ mapping. The Equativ catalogue SHALL serve to suggest packages to operations and to resolve unmatched exceptions; a mapping SHALL NOT require its package to be in the catalogue.

#### Scenario: A package enters the catalogue
- **WHEN** an Equativ run reads a package that is not in the catalogue
- **THEN** a catalogue row is created for Equativ with the package name in both names, no line dates and its seen dates

#### Scenario: A name with zero-width spaces keeps them
- **WHEN** a package name arrives with a zero-width space
- **THEN** the catalogue keeps the name as received and the pair still identifies the package

### Requirement: Operations can write an Equativ package to map a line

The system SHALL let a user with the `operations` role map a line that runs on Equativ by writing its `auctionPackageDealId` in the screen, which sends it as both identifiers of the pair, and SHALL offer the Equativ packages of the catalogue as suggestions for that same field without requiring the choice of one.

#### Scenario: Operations writes the package of a Deal line
- **WHEN** operations writes `900000001` for a line on Equativ that has no mapping
- **THEN** the mapping is created validated by the user and the screen says so
- **AND** the line is no longer listed among the lines without a mapping

#### Scenario: The catalogue suggests packages
- **WHEN** operations starts writing the package of a line on Equativ and the catalogue holds Equativ packages
- **THEN** the screen suggests them by name and id, and a package written that is not suggested is still accepted
