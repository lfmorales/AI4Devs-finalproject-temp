## ADDED Requirements

### Requirement: Every level carries the gross, the commitment and the counts of the two flags

The system SHALL return on every flight `volume_commitment`, `gross_revenue` (a decimal string with two decimals, null for a `committed` flight), `gross_differs_from_buyer_spend` and `data_cost_reported`. A line SHALL carry the `volume_commitment` of its line; a campaign and the totals SHALL carry the one commitment of their lines when they share it, and null otherwise. A line, a campaign and the totals SHALL carry `gross_revenue` as the exact sum of the gross of their target flights, null when they have none, and `gross_differs_count` and `data_cost_count` as the number of their flights carrying each flag. No amount changes because of them.

#### Scenario: The worked example reports its gross
- **WHEN** the closed Deal flight of 1,100,000 served impressions at 5.00 € is read
- **THEN** it carries `volume_commitment` `target`, `revenue` `"4400.00"`, `gross_revenue` `"5500.00"` and `margin` `"2750.00"`

#### Scenario: A committed flight has no gross
- **WHEN** a `committed` flight is read
- **THEN** its `gross_revenue` is null and neither flag is raised by the gross

#### Scenario: A campaign of both commitments
- **WHEN** a campaign has a `target` line and a `committed` line
- **THEN** its `volume_commitment` is null and its `gross_revenue` is the gross of the target line's flights

#### Scenario: The flags are counted at every level
- **WHEN** a line has one flight flagged `gross_differs_from_buyer_spend` and one flagged `data_cost_reported`
- **THEN** the line, its campaign and the totals carry `gross_differs_count` 1 and `data_cost_count` 1

### Requirement: The margin screen names a target line's sale and shows its gross

The system SHALL label the contracted revenue of a flight or a line whose commitment is `target` «Venta objetivo» instead of «Venta contratada», SHALL show its gross labelled «Bruto» next to its revenue, and SHALL show the two flags where the response raises them, labelled «Bruto distinto del gasto» and «Coste de datos». The margin percentage shown SHALL be the one the response carries, over revenue.

#### Scenario: A target line says Venta objetivo and shows its gross
- **WHEN** the margin screen shows the closed Deal flight of the worked example
- **THEN** it shows «Venta objetivo» 5.000,00 €, «Bruto» 5.500,00 € and the revenue 4.400,00 €

#### Scenario: The flags are labelled where raised
- **WHEN** a flight carries `gross_differs_from_buyer_spend` and `data_cost_reported`
- **THEN** the screen labels it «Bruto distinto del gasto» and «Coste de datos»

## MODIFIED Requirements

### Requirement: Every level carries the contracted revenue and a flight its accrued days

The system SHALL return `contracted_revenue` on every flight, line, campaign and on the totals: the sale contracted for the whole flight (contracted volume / 1000 × the line's CPM; for a `target` line, the sale of its target), as a decimal string with two decimals, rounded half up once, exactly like `revenue`. A line, a campaign and the totals carry the exact sum of the `contracted_revenue` of their flights. A flight SHALL also return `accrued_days` and `window_days` as integers: the contract days counted up to `as_of` and the days of its whole window, both ends included. In a closed or pending-close flight `accrued_days` equals `window_days` and, when its line is `committed`, `revenue` equals `contracted_revenue`; a `target` flight's `revenue` is its reported revenue, which may be above or below `contracted_revenue`; in a running flight `accrued_days` is below `window_days`. A flight that has not started does not appear, so it carries none. No existing amount changes.

#### Scenario: A closed flight accrues all its contracted revenue
- **WHEN** a closed or pending-close flight of a `committed` line is read
- **THEN** its `revenue` equals its `contracted_revenue` and its `accrued_days` equals its `window_days`

#### Scenario: A running flight shows how much of the sale it has accrued
- **WHEN** a running flight of 31 days with 9 elapsed days and a contracted revenue of 3100.00 is read
- **THEN** `contracted_revenue` is "3100.00", `revenue` is "900.00", `accrued_days` is 9 and `window_days` is 31

#### Scenario: A line without a price has a contracted revenue of zero
- **WHEN** a flight of a line with a sale CPM of 0.00 is read
- **THEN** its `contracted_revenue` is "0.00" and so is its `revenue`

#### Scenario: Higher levels add the flights
- **WHEN** a line, a campaign or the totals are read
- **THEN** their `contracted_revenue` is the exact sum of the `contracted_revenue` of the flights below, with no further rounding

#### Scenario: Reading and closing agree
- **WHEN** the same flight is read before and after its month is closed
- **THEN** its `contracted_revenue`, `accrued_days` and `window_days` are the same

#### Scenario: A closed target flight earns what was reported, not its target
- **WHEN** the closed Deal flight with a target of 1,000,000 impressions at 5.00 € and a reported revenue of 4,400.00 € is read
- **THEN** its `contracted_revenue` is "5000.00", its `revenue` is "4400.00" and its `accrued_days` equals its `window_days`
