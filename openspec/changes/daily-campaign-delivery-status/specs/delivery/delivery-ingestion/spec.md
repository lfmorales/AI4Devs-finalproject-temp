## Purpose

Bringing delivery figures from a DSP or an uploaded export into one delivery model, repeatably and without duplication, so that what a campaign actually served is a stored fact with a recorded provenance rather than the residue of a manual download.

## ADDED Requirements

### Requirement: Delivery is stored per campaign line and day

The system SHALL store delivery at the grain of one campaign line and one calendar day, holding impressions, clicks, media cost, measurable impressions and viewable impressions.

#### Scenario: A day of delivery is recorded against its line
- **WHEN** an ingestion run retrieves a day of delivery for a mapped campaign line
- **THEN** one delivery record exists for that line and date
- **AND** its media cost is stored as an exact decimal value

#### Scenario: Delivered volume never overwrites contracted volume
- **WHEN** delivery is ingested for a campaign line
- **THEN** the line's contracted impressions are unchanged
- **AND** the two quantities remain separately readable

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

The system SHALL record each ingestion run with its route, its source, its start and end times, its outcome, the number of rows read, the number of rows ignored for having no attributed line item and the number of unmatched rows ignored for having no impressions and no cost, and SHALL associate every delivery record with the batch that produced it. The outcome SHALL be one of `running`, `succeeded` or `failed`.

#### Scenario: A successful run is traceable to its source
- **WHEN** an ingestion run completes
- **THEN** a batch record exists naming the route, the DSP and the source
- **AND** every delivery record it produced references that batch

#### Scenario: The batch counts the rows it read and the rows it ignored
- **WHEN** a run reads rows of which some have no attributed line item and some are unmatched with zero impressions and zero cost
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

### Requirement: Lines are ingested when their mapping is validated and their campaign overlaps the window

The system SHALL ingest delivery for every campaign line that runs on the DSP being ingested, carries a validated DSP mapping for that DSP and belongs to a campaign whose dates overlap the ingestion window, whatever the campaign's status, and SHALL NOT fail the run because other such lines lack a validated mapping.

#### Scenario: An unmapped line is skipped without failing the run
- **WHEN** an ingestion run encounters a line of an overlapping campaign with no DSP mapping
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

#### Scenario: A campaign that ended inside the window is still ingested
- **WHEN** a campaign ended three days before the run and its line has a validated mapping
- **THEN** its delivery is ingested, whatever the campaign's status
- **AND** figures the DSP restates for it are picked up

#### Scenario: A campaign that has not started is neither ingested nor skipped
- **WHEN** a campaign starts after the last day of the window
- **THEN** its lines are not ingested
- **AND** they are not counted among the skipped lines

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

The system SHALL combine the delivery of every external line item mapped to the same campaign line into one record per day, summing impressions, clicks, media cost, measurable impressions and viewable impressions.

#### Scenario: Two external line items of one line are summed
- **WHEN** two external line items mapped to the same campaign line report delivery for the same day
- **THEN** one delivery record exists for that line and date
- **AND** each of its figures is the sum of the two reported figures

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

The system SHALL check an external identifier pair with the DSP when a mapping is created, SHALL distinguish a pair that was found, one the DSP does not know and a DSP that could not be reached, SHALL create the mapping in all three cases, and SHALL set `validated_at` only when the pair was found.

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

