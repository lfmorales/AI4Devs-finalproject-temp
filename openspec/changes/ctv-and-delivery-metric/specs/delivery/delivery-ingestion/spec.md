## MODIFIED Requirements

### Requirement: Delivery is stored per campaign line and day

The system SHALL store delivery at the grain of one campaign line and one calendar day, holding impressions, clicks, media cost, measurable impressions, viewable impressions, OTS and video completions. OTS SHALL be stored as an exact decimal with four decimals and video completions as a whole number; both SHALL be mandatory and SHALL default to zero, so that delivery stored before they existed reads zero OTS and zero completions.

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

### Requirement: Several external line items on one campaign line are combined per day

The system SHALL combine the delivery of every external line item mapped to the same campaign line into one record per day, summing impressions, clicks, media cost, measurable impressions, viewable impressions, OTS and video completions. It SHALL never sum, average or store a video completion rate: each row's completions are computed from its own rate before the rows are summed.

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

## ADDED Requirements

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
