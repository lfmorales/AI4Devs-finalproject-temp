## Context

See `proposal.md` (Why). The current state that shapes the approach:

- **The closing already computes every figure it needs, and stores only the rates.** `MarginClosingService._close` prices the month's ended flights with `price_flights`, the same function as the pending-close read (`backend/app/application/services/margin_closing_service.py:56-62`), so each `PricedFlight` carries the whole `FlightMargin` and the `FlightFacts` it came from. `SqlAlchemyAppliedRateRepository.save` keeps only the rates, the counter positions, the unrounded rebate and, for a target flight, `revenue_amount` and `rebate_base_amount` (`sqlalchemy_margin_repositories.py:397-431`).
- **A closed flight is recomputed on every read.** `MarginQueryService._report` calls `_margin_from_frozen`, which runs `calculate_flight_margin` on the frozen rebate and platform rate and on the live window sums: media cost, delivered impressions, delivered volume, buyer's spend and data cost (`margin_query_service.py:84-93`, `:137-156`). The sums come from `_flight_facts_query` (`sqlalchemy_margin_repositories.py:150-210`), which reads the channel's delivery metric as stored now (`delivered_volume.py:7-16`).
- **The totals add `FlightMargin`s and nothing else** (`margin_totals.py:36-132`): a frozen `FlightMargin` per closed flight freezes every level above it.
- **The ingestion ignores the closing.** The window is replaced delete-then-insert (`delivery_range_replacement.py:43-45`), with no history: the delivery of the moment of a past closing cannot be rebuilt. Unlinking a line deletes its delivery (`delivery-ingestion`, «A line's mapping can be removed with its delivery»).
- **A month can be closed in more than one run.** The registration accepts flights in any past month: `CampaignRegistrationService` never compares the dates with today and `Campaign.validate` only checks `start_date <= end_date` (`backend/app/domain/entities/campaign.py:94`). The closing freezes every ended flight without a row, so a flight registered in a closed month is frozen by the next closing of that month.
- **Frozen tables are append-only** through the trigger function `reject_append_only_change()` (`alembic/versions/20261026_1712_439b6b8481f8_add_the_margin_tables.py:144-155`). The migration head is `950895fa2d75`.
- **The margin modules never name the channel** (`backend/tests/domain/test_margin_model_integrity.py:19`, `:54-66`), and the frontend computes no figure (`frontend/tests/unit/features/margin/no-arithmetic.test.ts`).

## Goals / Non-Goals

**Goals:**
- A closed flight reads the same figures forever, whatever the delivery, the masters or the formulas do afterwards, and those figures equal the pending-close figures to the cent.
- The stored delivery keeps being the DSP's latest truth, and the difference between it and a closed figure is computed, shown and counted, never added.
- Every rule of the snapshot and of the warning is a pure domain function, tested without a database.

**Non-Goals:**
- Changing how a flight that is not closed is priced, or the rebate ledger of `applied_rates`.

## Decisions

### 1. Two tables beside `applied_rates`, not wider `applied_rates`

`month_closings` is the header: `id`, `period_year`, `period_month`, `closed_at`, `closed_by` (FK `users`), `as_of`, all `NOT NULL`, indexed on (`period_year`, `period_month`) and not unique (decision 4). `month_closing_batches` names its batches: (`month_closing_id`, `dsp_id`) as primary key and `ingestion_batch_id`, all `NOT NULL` with their foreign keys.

`closed_flight_snapshots` holds the frozen flight: `id`, `applied_rate_id` (FK, `UNIQUE`, `NOT NULL`), `month_closing_id` (FK, `NOT NULL`), and

- the final amounts, `Numeric(18,2) NOT NULL`: `revenue`, `contracted_revenue`, `media_cost`, `rebate`, `platform_cost`, `margin`; `gross_revenue` `Numeric(18,2)` nullable, with the check `(volume_commitment = 'target') = (gross_revenue IS NOT NULL)`: the only nullable column, because a committed flight has no gross (decided with the user);
- the delivery they were computed on, `NOT NULL`: `delivered_impressions` `BigInteger`, `delivered` `Numeric(18,4)`, and the unrounded window sums `window_media_cost`, `window_reported_revenue`, `window_buyer_spend`, `window_data_cost` `Numeric(18,6)`, the precision of `daily_deliveries`;
- the flags and the line, `NOT NULL`: `gross_differs_from_buyer_spend`, `data_cost_reported`, `delivery_metric` (check `impressions` or `ots`), `sale_cpm` (the type of `campaign_lines.sale_cpm`), `contracted_impressions` `BigInteger`, `volume_commitment` (check `committed` or `target`).

The three tables get the existing append-only trigger. `applied_rates` is not touched: it stays the rebate ledger that `opening_positions` reads, and keeps its `revenue_amount` and `rebate_base_amount`.

*Alternatives*: widening `applied_rates` (rejected by the user: it mixes the counter ledger with the report, and its target-only pair check stops making sense); storing only the delivery and recomputing the amounts on read (rejected: a later change of `calculate_flight_margin` would move closed months).

### 2. The snapshot is built in the domain from the priced flight

A value object `ClosedFlightSnapshot` (`backend/app/domain/value_objects/closed_flight.py`) holds the columns above. A pure function `snapshot_of(priced: PricedFlight) -> ClosedFlightSnapshot` copies `priced.margin` and `priced.facts`: the closing freezes exactly what the pending-close read showed, by construction, since both come from `price_flights`. The repository only maps fields to columns.

### 3. A closed flight's margin comes from its snapshot, without `calculate_flight_margin`

A pure function `margin_from_snapshot(snapshot, flight_start, flight_end) -> FlightMargin` (`backend/app/domain/services/closed_flight.py`) builds the `FlightMargin` field by field: status `CLOSED`, not provisional, `accrued_days = window_days` from the dates, `below_cost = margin < 0`, `zero_sale = sale_cpm == 0`, and everything else from the snapshot. `_margin_from_frozen` is deleted. With it goes the last caller that passes a frozen gross, so `FlightEconomics.gross_revenue` is removed afterwards (task 9.1): `calculate_flight_margin` always computes a target flight's gross from its served impressions, and the test builder of `FlightEconomics` absorbs the change. The module joins `MARGIN_MODULES` in `test_margin_model_integrity.py`, so it cannot name the channel either.

### 4. One header per closing run, and the response counts them

`MarginClosingService._close` writes, after pricing and only when at least one flight is frozen: the header, with `as_of` and the latest succeeded batch of each DSP of the frozen flights' lines (latest `finished_at`, then highest id; a DSP with none is left out), then the rates and the snapshots, all under the month's advisory lock and in the one transaction. `ClosingResult` and `ClosingResponse` add `closings`, the headers of the month after the request (decided with the user, so that a second closing of a month shows). A month is closed when it holds a header.

*Alternatives*: one header per month, reused by a later run (rejected: its `as_of` and batches would not describe the flights it adds); one header per month, refusing a later run (rejected: a late flight would stay pending close and block every later month with `previous_month_open`).

### 5. The read keeps the live sums, only for the check

`list_flights` outer-joins the snapshot and its header through `applied_rates`, and `ReadFlight.frozen` carries the `ClosedFlightSnapshot` beside the rates. The live window sums stay in the query; for a closed flight they are the current delivery the check compares, and the delivered volume is summed in the snapshot's metric, not the channel's metric now (`coalesce(snapshot.delivery_metric, channels.delivery_metric)` in the case of `delivered_in_channel_metric`), so a channel whose metric changed never compares OTS with impressions.

### 6. The check is one pure function

`check_closed_delivery(snapshot, platform_rate, current: WindowDelivery) -> ClosedDeliveryCheck` (`backend/app/domain/services/closed_flight.py`) returns the differences, the current margin, its difference and `changed`, with the rules of `finance/margin-calculation` («A closed flight is checked against its current delivery»): revenue frozen for committed and `round(current reported revenue)` for target; media cost `round(current)`; rebate the snapshot's; platform cost `round(current impressions / 1000 × frozen rate)`. Two constants of the margin model: `MARGIN_CHANGE_TOLERANCE = Decimal("1.00")` (≥, absolute) and `DELIVERED_CHANGE_TOLERANCE = Decimal("0.01")` (≥, relative to the frozen volume; a frozen zero is exceeded by any non-zero current volume). It reuses `round_amount` and `WindowDelivery`. The query service sets `FlightMargin.delivery_changed` and `FlightReport.delivery_change`. `total_flights` and `total_lines` add `delivery_changed_count` and nothing else.

### 7. Response and screen

`FlightMarginResponse` adds `delivery_changed` and `delivery_change` (`DeliveryChangeResponse`, null unless closed), `TotalsResponse` adds `delivery_changed_count`; the field descriptions state that the current margin uses the closing's rebate and rates and that only the delivery changes. The frontend adds the fields to `frontend/lib/api/margin.ts`, a «Cambió tras el cierre» tag in `Flags.tsx` and in `TotalsFlags`, and the flight's differences and current margin as the API gives them, with the same note. No arithmetic.

### 8. The migration refuses closed flights

The migration first runs `SELECT EXISTS (SELECT 1 FROM applied_rates)` and, when true, raises with a message that names the reason (closed flights without a snapshot, which this migration does not backfill) and asks to run `e2e/scripts/reset-data.sh`; nothing is created, since PostgreSQL runs the DDL in the migration's transaction. There is no production, `reset-data.sh` drops the volume before migrating, and the test database is recreated per session (`backend/tests/conftest.py:86-121`).

### 9. `closed_month_days` in the command

A pure function `days_in_closed_months(window, closed_months) -> int` counts the calendar days of a window whose (year, month) is closed; `scripts/run_ingestion.py` reads the months of the window that hold a header, after a succeeded run, like `_new_unmatched_exceptions`, and prints the count. A failed run prints no count. The ingestion service is unchanged.

### 10. Reports

As in the previous changes, the reports go to `docs/reports/`, not to `specs/<change-name>/reports/` as `openspec/config.yaml` says.

## Risks / Trade-offs

- [A flight can be registered in a closed month] → Out of scope (proposal, Non-goals). The registration accepts past dates (`campaign.py:94` checks only the order of the dates), so the month shows a `pending_close` flight among closed ones, its totals grow by it, `previous_month_open` blocks closing later months until it is closed, and a second closing adds a header, which the closing response shows in `closings`.
- [The target revenue and gross are stored twice] → `applied_rates` keeps them as the ledger of the rebate base; the read takes the snapshot. A repository test checks that both agree on every target flight a closing writes.
- [A fix to the formulas never reaches a closed month] → Intended: a closed figure is the reported one. Recomputing a closed month is reopening, a non-goal.
- [The current margin of a target flight keeps the closing's rebate even when its gross moved] → Decided with the user: the counter has already advanced by the frozen gross; the field descriptions and the screen say so.
- [A developer database with closed flights stops the migration] → The message names `e2e/scripts/reset-data.sh`.
- [`applied_rates.closed_at` and `closed_by` repeat the header] → Kept: the table is append-only and the existing tests read them.

## Migration Plan

1. One migration after `950895fa2d75`: refuse a database whose `applied_rates` has rows; create `month_closings`, `month_closing_batches` and `closed_flight_snapshots` with their checks, keys, indexes and append-only triggers. Downgrade drops the triggers and the three tables.
2. Development: `e2e/scripts/reset-data.sh` (drops the volume, migrates, seeds). Tests: nothing to do.
3. Rollback: downgrade the migration and redeploy the previous image; the snapshots are lost and the previous code recomputes closed flights from the delivery, as before.
