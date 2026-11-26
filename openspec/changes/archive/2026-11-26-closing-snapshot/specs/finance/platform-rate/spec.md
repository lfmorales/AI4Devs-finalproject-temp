## MODIFIED Requirements

### Requirement: The rate used is frozen on the closed flight

The system SHALL record the platform rate actually applied in the `applied_rates` row of a closed flight, and SHALL NOT re-resolve it at read time for a closed flight. It SHALL also freeze, in the flight's snapshot, the platform cost that rate gave on the delivered impressions of the moment of the closing, and SHALL NOT compute a closed flight's platform cost again from the delivery stored afterwards.

#### Scenario: Changing the default does not move a closed flight
- **WHEN** the system default rate is changed after a flight has been closed
- **THEN** that flight's margin is unchanged

#### Scenario: A running flight uses the rate in force
- **WHEN** a running flight is read after the default changed
- **THEN** it is calculated with the new rate and nothing is written

#### Scenario: A restatement does not move a closed flight's platform cost
- **WHEN** a flight was closed with 700,000 delivered impressions and a platform rate of 1.00 € per thousand, and its window holds 1,200,000 impressions after a restatement
- **THEN** its platform cost is still 700.00 € and its platform rate 1.00 €
