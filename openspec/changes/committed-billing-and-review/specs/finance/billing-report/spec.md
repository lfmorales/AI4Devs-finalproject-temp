## Purpose

Gives Operations and Finance the billing of a month: per campaign its review state and per flight how its billing was reached, and, once the month is closed, a CSV built from the closing's snapshot for Finance to invoice from.

## ADDED Requirements

### Requirement: The billing of a month is read per campaign, line and flight

The system SHALL expose `GET /billing`, restricted to the `operations` and `finance` roles, taking a mandatory `year` and `month` and an optional `campaign_id`, returning every campaign with flights in that month (`finance/monthly-review`) with its id, name, agency, advertiser, review state and the author and moment of its latest review event, its lines, and each flight of the month with:

- its id, window and state: `not_started`, `running`, `pending_close` or `closed`;
- its `delivery_metric`, its contracted volume, its carry-over, whether the carry-over is billable, its delivery target and its delivered volume;
- its `billable` volume, its `billing` and its `billing_basis`, exactly as `GET /margin` gives its `billable`, `revenue` and `billing_basis` (`finance/margin-reporting`), and the line's sale CPM;
- the adjustment in force, with its basis, amount, reason, author and moment, or null.

A closed flight SHALL be read from its snapshot. A flight that has not started carries no billing. Amounts SHALL be decimal strings with two decimals, volumes as `GET /margin` gives them. The read SHALL write nothing. An unknown campaign is 404 `campaign_not_found`; a missing or invalid year or month is 422.

#### Scenario: A month with an adjusted flight and a carry-over
- **WHEN** November 2026 is read and its line holds the November flight of 500,000 contracted impressions with a billable carry-over of 100,000 that delivered 580,000, and an ended flight adjusted to `custom` with 4,200.00 €
- **THEN** the first carries `carryover` 100000, `carryover_billable` true, `delivery_target` 600000, `billable` `"580000.0000"`, `billing` `"2900.00"` and `billing_basis` `minimum`
- **AND** the second carries `billing` `"4200.00"`, `billing_basis` `custom` and its adjustment with the reason, the author and the moment

#### Scenario: Each campaign carries its review state
- **WHEN** a month holds a reviewed campaign, one pending review and one in progress
- **THEN** each carries its state, and the reviewed one the author and the moment of its review

#### Scenario: The billing read and the margin read agree
- **WHEN** a flight is read with `GET /billing` and with `GET /margin`
- **THEN** its `billing` equals its `revenue`, and its `billable` and `billing_basis` are the same

#### Scenario: Reading writes nothing
- **WHEN** `GET /billing` is called
- **THEN** no row of any table is created or changed

### Requirement: A closed month's billing is exported as a CSV

The system SHALL expose `GET /billing/export`, restricted to the `operations` and `finance` roles, taking a mandatory `year` and `month`, returning a CSV file named `facturacion-YYYY-MM.csv` with one row per flight frozen in that month, by every closing of it, ordered by agency, campaign, line number and flight start. Every figure SHALL come from the flight's snapshot and the adjustment it froze; the names come from the campaign as stored now. The columns, with this header row, SHALL be:

| Column | Value |
|---|---|
| `cliente` | the campaign's advertiser |
| `agencia` | the campaign's agency |
| `campaña` | the campaign's name |
| `línea` | the line number |
| `orden de compra` | the reference of the line's purchase order, empty when it has none |
| `entregado` | the frozen delivered volume, four decimals |
| `contratado` | the frozen contracted volume, a whole number |
| `arrastre` | the frozen carry-over, a whole number |
| `facturable` | the frozen billable volume, four decimals; empty for a target flight, a custom billing or a flight closed before this change |
| `CPM` | the frozen sale CPM, two decimals |
| `importe` | the frozen revenue, two decimals |
| `ajustado` | «sí» when the frozen billing basis is `delivered`, `contracted` or `custom`, «no» otherwise |
| `motivo` | the reason of the frozen adjustment when `ajustado` is «sí», empty otherwise |

The file SHALL be UTF-8 starting with a byte order mark, with `;` as the field separator, a comma as the decimal separator and no thousands separator, quoted as RFC 4180 quotes, with `;` in place of its comma, so that Excel set to Spanish opens it in columns. A flight closed before this change has `arrastre` and `facturable` empty and `ajustado` «no». A month that holds no closing header SHALL be answered 409 `month_not_closed`. The export SHALL write nothing.

#### Scenario: The CSV of a closed month
- **WHEN** October 2026 was closed with the committed flight of 1,000,000 contracted impressions at 5.00 € that delivered 700,000, with no adjustment, and the same line's November flight is still open
- **THEN** the CSV holds one row for the October flight with `entregado` `700000,0000`, `contratado` `1000000`, `arrastre` `0`, `facturable` `700000,0000`, `CPM` `5,00`, `importe` `3500,00`, `ajustado` «no» and `motivo` empty
- **AND** no row for the November flight

#### Scenario: An adjusted flight carries its reason
- **WHEN** a flight was closed with an adjustment to `custom` of 4,200.00 € and the reason «Acuerdo con la agencia»
- **THEN** its row carries `importe` `4200,00`, `facturable` empty, `ajustado` «sí» and `motivo` «Acuerdo con la agencia»

#### Scenario: A target flight carries what was reported
- **WHEN** the closed Deal flight of the worked example is exported
- **THEN** its row carries `importe` `4400,00`, `facturable` empty and `ajustado` «no»

#### Scenario: The file opens in columns in Excel set to Spanish
- **WHEN** the CSV of a closed month whose adjusted flight has the reason «Acuerdo; se factura la OC» is downloaded
- **THEN** its first three bytes are the UTF-8 byte order mark `EF BB BF`
- **AND** its header row is `cliente;agencia;campaña;línea;orden de compra;entregado;contratado;arrastre;facturable;CPM;importe;ajustado;motivo`
- **AND** its amounts are written with a decimal comma and no thousands separator, such as `3500,00` and `700000,0000`, never `3500.00` or `3.500,00`
- **AND** that row's reason is quoted, `"Acuerdo; se factura la OC"`, because it holds the separator

#### Scenario: A later delivery does not change the CSV
- **WHEN** the CSV of a closed month is downloaded, the stored delivery of the month changes, and it is downloaded again
- **THEN** both files are identical

#### Scenario: An open month has no CSV
- **WHEN** the CSV of a month that holds no closing header is requested
- **THEN** the response is 409 `month_not_closed`

### Requirement: Errors under the billing routes are code and message

The system SHALL answer every error of a route under `/billing`, including a validation error, with a body of exactly `code` and `message`, and no error body SHALL carry an amount.

#### Scenario: A validation error under /billing
- **WHEN** `GET /billing` receives a month of 13
- **THEN** the body has only `code` and `message`

### Requirement: The author of every billing event is named

Wherever a response of a route under `/billing`, or of `PUT /flights/{flight_id}/carryover`, names the user who wrote an event (a review or a withdrawal, an adjustment, a carry-over or its billable flag), the system SHALL return the user's id and, beside it, the user's name as stored, or the user's email when the name is blank. The billing screen SHALL show that name and never the bare id. Naming the author SHALL add no amount, no billable flag and no adjustment to the response of `PUT /flights/{flight_id}/carryover`, which `trading` may call.

#### Scenario: A review names its author
- **WHEN** «Ana Pérez» reviews a campaign for October 2026
- **THEN** the response carries her id in `set_by` and «Ana Pérez» in `set_by_name`, and `GET /billing` carries the same in `review_set_by` and `review_set_by_name`

#### Scenario: An adjustment names its author in the read and in the history
- **WHEN** a flight is adjusted by a user and read with `GET /billing` and with its history
- **THEN** its adjustment in force and each item of the history carry `created_by` and `created_by_name`

#### Scenario: A user with a blank name is named by the email
- **WHEN** a user whose name is blank sets the billable flag of a carry-over
- **THEN** the response carries the user's email in `set_by_name`

#### Scenario: The carry-over names its author and still carries no amount
- **WHEN** a user holding only `trading` writes a carry-over
- **THEN** the response carries `set_by` and `set_by_name`, and no amount, no billable flag, no adjustment and no adjustment reason

#### Scenario: The screen shows who reviewed and who adjusted
- **WHEN** the billing screen shows a campaign reviewed and a flight adjusted by «Ana Pérez»
- **THEN** it names «Ana Pérez» for both, and no «usuario» followed by a number

### Requirement: The billing screen shows a month's billing

The system SHALL offer, to users holding `operations` or `finance`, a billing screen for a month that shows each campaign with its review state, and each flight with its contracted volume, carry-over, delivery target, delivered volume, billable volume, sale CPM, billing labelled «Facturable» or «Facturable a la fecha» as in the margin screen, and the adjustment in force with its reason, the name of its author and its moment, as each campaign's review shows the name of whoever reviewed it. It SHALL let them adjust an ended, unfrozen committed flight (basis, amount when custom, mandatory reason), set the billable flag of a carry-over, mark and withdraw the review, and download the CSV of a closed month. It SHALL show the response's error in Spanish when an action is refused, and SHALL compute no figure. The screen and its entry in the navigation SHALL be hidden from a user holding neither role.

#### Scenario: Finance adjusts a flight from the billing screen
- **WHEN** a user holding `finance` adjusts a pending-close flight to its contracted volume with a reason
- **THEN** the flight shows the billing of the response, «Ajustado» with the reason, and its campaign «Pendiente de revisión»

#### Scenario: The CSV is downloaded from the screen
- **WHEN** a user holding `operations` downloads the CSV of a closed month
- **THEN** the file `facturacion-YYYY-MM.csv` of `GET /billing/export` is saved

#### Scenario: Trading has no billing screen
- **WHEN** a user holding only `trading` signs in
- **THEN** no billing screen or navigation entry is shown
