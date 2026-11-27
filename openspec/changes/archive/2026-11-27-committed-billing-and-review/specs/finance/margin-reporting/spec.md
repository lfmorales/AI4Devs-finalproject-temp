## MODIFIED Requirements

### Requirement: Every level carries the contracted revenue and a flight its accrued days

The system SHALL return `contracted_revenue` on every flight, line, campaign and on the totals: the sale contracted for the whole flight (contracted volume / 1000 × the line's CPM; for a `target` line, the sale of its target), as a decimal string with two decimals, rounded half up once, exactly like `revenue`. A carry-over never enters it. A line, a campaign and the totals carry the exact sum of the `contracted_revenue` of their flights. A flight SHALL also return `accrued_days` and `window_days` as integers: the contract days counted up to `as_of` and the days of its whole window, both ends included; they drive no amount. In a closed or pending-close flight `accrued_days` equals `window_days`; when its line is `committed`, its `revenue` is its billing (`finance/margin-calculation`), which equals `contracted_revenue` when it delivered at least its contracted volume and has no adjustment, is below it when it under-delivered, and may be above it with a billable carry-over or an adjustment; a `target` flight's `revenue` is its reported revenue, which may be above or below `contracted_revenue`. In a running flight `accrued_days` is below `window_days`. A flight that has not started does not appear, so it carries none.

#### Scenario: A closed flight accrues all its contracted revenue
- **WHEN** a closed or pending-close flight of a `committed` line that delivered its whole contracted volume and has no adjustment is read
- **THEN** its `revenue` equals its `contracted_revenue` and its `accrued_days` equals its `window_days`

#### Scenario: A closed flight that under-delivered bills less than it contracted
- **WHEN** a closed flight of a `committed` line with 1,000,000 contracted impressions at 5.00 € that delivered 700,000 is read
- **THEN** its `contracted_revenue` is "5000.00" and its `revenue` is "3500.00"

#### Scenario: A running flight shows how much of the sale it has accrued
- **WHEN** a running committed flight of 31 days with 9 elapsed days, a contracted revenue of 3100.00 at 5.00 € and 180,000 impressions delivered to date is read
- **THEN** `contracted_revenue` is "3100.00", `revenue` is "900.00", `accrued_days` is 9 and `window_days` is 31

#### Scenario: A line without a price has a contracted revenue of zero
- **WHEN** a flight of a line with a sale CPM of 0.00 is read
- **THEN** its `contracted_revenue` is "0.00" and so is its `revenue`

#### Scenario: Higher levels add the flights
- **WHEN** a line, a campaign or the totals are read
- **THEN** their `contracted_revenue` is the exact sum of the `contracted_revenue` of the flights below, with no further rounding

#### Scenario: Reading and closing agree
- **WHEN** the same flight is read before and after its month is closed
- **THEN** its `contracted_revenue`, `revenue`, `accrued_days` and `window_days` are the same

#### Scenario: A closed target flight earns what was reported, not its target
- **WHEN** the closed Deal flight with a target of 1,000,000 impressions at 5.00 € and a reported revenue of 4,400.00 € is read
- **THEN** its `contracted_revenue` is "5000.00", its `revenue` is "4400.00" and its `accrued_days` equals its `window_days`

### Requirement: Every level reports a delivery that changed after closing

The system SHALL return on every flight `delivery_changed`, true only for a closed flight flagged by the check of `finance/margin-calculation`, and `delivery_change`, null for a flight that is not closed and, for a closed flight, an object with:

- `delivered_difference`, a decimal string with four decimals, in the unit of the flight's `delivery_metric`;
- `delivered_impressions_difference`, an integer;
- `media_cost_difference`, a decimal string with two decimals;
- `reported_revenue_difference` and `buyer_spend_difference`, decimal strings with two decimals for a `target` flight and null for a `committed` one;
- `billable_difference`, a decimal string with four decimals, and `billing_difference`, a decimal string with two decimals, for a `committed` flight closed with this change, and null for a `target` flight and for a flight closed before it;
- `current_margin` and `margin_difference`, decimal strings with two decimals.

Every difference is the current value less the frozen one. The response SHALL describe these fields as informative: the current margin uses the closing's rebate and rates, the cap and billing basis frozen at closing, and only the delivery changes; no amount or total adds it. A line, a campaign and the totals SHALL carry `delivery_changed_count`, the number of their flights flagged `delivery_changed`. No amount, volume, flag or other count of any level changes because of them.

#### Scenario: The restated committed flight of the example reports its change
- **WHEN** the committed flight of 1,000,000 contracted impressions closed at a revenue of 3,500.00 € and a margin of 725.00 € is read after 28 November was restated with 500,000 more impressions and 1,800.00 € more media cost
- **THEN** it carries `revenue` `"3500.00"`, `margin` `"725.00"`, `media_cost` `"1200.00"`, `platform_cost` `"700.00"`, `billable` `"700000.0000"` and `delivered_impressions` 700000, as frozen
- **AND** it carries `delivery_changed` true and `delivery_change` with `delivered_impressions_difference` 500000, `delivered_difference` `"500000.0000"`, `billable_difference` `"300000.0000"`, `billing_difference` `"1500.00"`, `media_cost_difference` `"1800.00"`, `reported_revenue_difference` and `buyer_spend_difference` null, `current_margin` `"-75.00"` and `margin_difference` `"-800.00"`
- **AND** its line, its campaign and the totals carry `delivery_changed_count` 1 and add 725.00 € to their margin

#### Scenario: A closed flight whose delivery did not change
- **WHEN** a closed flight's stored delivery is the one it was closed with
- **THEN** it carries `delivery_changed` false and `delivery_change` with every difference zero and `current_margin` equal to its `margin`

#### Scenario: A flight that is not closed carries no change
- **WHEN** a running flight or a flight pending close is read
- **THEN** it carries `delivery_changed` false and `delivery_change` null

#### Scenario: A target flight reports its revenue and spend differences
- **WHEN** the restated Deal flight of `finance/margin-calculation` is read
- **THEN** its `delivery_change` carries `reported_revenue_difference` `"800.00"`, `buyer_spend_difference` `"1000.00"`, `billable_difference` and `billing_difference` null, `current_margin` `"3350.00"` and `margin_difference` `"600.00"`

#### Scenario: A flight closed before this change has no billing difference
- **WHEN** a committed flight closed before this change is read
- **THEN** its `billable_difference` and `billing_difference` are null and its current margin keeps its frozen revenue

#### Scenario: The fields describe the current margin as informative
- **WHEN** the response schema of `GET /margin` is read
- **THEN** the description of `delivery_change` and of `current_margin` says that the current margin uses the closing's rebate, rates, cap and billing basis with today's delivery, and that no amount or total adds it

### Requirement: The margin screen labels a flight that changed after closing

The system SHALL show «Cambió tras el cierre» on a flight that carries `delivery_changed`, and on a line, a campaign or the period the number of their flights that carry it, like the other flags. Next to the flight's label it SHALL show the differences and the current margin as the response gives them, stating that this margin uses the rebate and the rates of the closing and that only the delivery changed. The screen SHALL compute no figure: every amount and every difference is the response's.

#### Scenario: A changed flight is labelled with its current margin
- **WHEN** the margin screen shows the restated committed flight of the example
- **THEN** it shows its margin 725,00 € and the label «Cambió tras el cierre» with the current margin −75,00 €, the differences of the response and the note that the rebate and the rates are the closing's

#### Scenario: The count reaches the line, the campaign and the period
- **WHEN** a line holds one flight that carries `delivery_changed`
- **THEN** the line, its campaign and the period show «Cambió tras el cierre» counting one flight

#### Scenario: An unchanged or open flight shows no label
- **WHEN** a flight carries `delivery_changed` false
- **THEN** no «Cambió tras el cierre» label is shown for it

## ADDED Requirements

### Requirement: Every flight carries its billable volume and its billing basis

The system SHALL return on every flight of `GET /margin`:

- `billable`, a decimal string with four decimals in the unit of its `delivery_metric`: the billable volume its revenue was computed on (`finance/margin-calculation`), to date for a running flight; null for a `target` flight, for a flight whose billing is a custom amount, and for a flight closed before this change;
- `billing_basis`: `minimum` when the rule of the lesser applies, `delivered`, `contracted` or `custom` when an adjustment is in force (`finance/billing-adjustment`), `reported` for a `target` flight, and null for a flight closed before this change.

A line, a campaign and the totals SHALL NOT sum `billable`. No amount changes because of these fields.

#### Scenario: An under-delivered flight reports its billable volume
- **WHEN** the closed committed flight of 1,000,000 contracted impressions that delivered 700,000, with no adjustment, is read
- **THEN** it carries `billable` `"700000.0000"` and `billing_basis` `minimum`

#### Scenario: An adjusted flight names its basis
- **WHEN** a pending-close committed flight with an adjustment to its contracted volume is read
- **THEN** it carries `billing_basis` `contracted` and `billable` equal to its cap: its contracted volume, plus its carry-over when the carry-over is billable

#### Scenario: A target flight bills what was reported
- **WHEN** the closed Deal flight of the worked example is read
- **THEN** it carries `billable` null and `billing_basis` `reported`

### Requirement: The margin screen names the billing

The system SHALL label the revenue of a flight that has ended, closed or pending close, «Facturable», and the revenue of a running flight «Facturable a la fecha», instead of «Devengado», whatever its commitment. A line, a campaign or the period that includes a running flight SHALL label its revenue «Facturable a la fecha», and «Facturable» otherwise. The screen SHALL show the billing basis of an adjusted flight, labelled «Ajustado», and SHALL compute no figure.

#### Scenario: An ended flight says Facturable
- **WHEN** the margin screen shows a pending-close committed flight with a revenue of 3,500.00 €
- **THEN** its revenue is labelled «Facturable» 3.500,00 €

#### Scenario: A running flight says Facturable a la fecha
- **WHEN** the margin screen shows a running flight and its line
- **THEN** the flight's revenue and the line's are labelled «Facturable a la fecha»

#### Scenario: An adjusted flight is labelled
- **WHEN** a flight carries `billing_basis` `custom`
- **THEN** the screen labels it «Ajustado»
