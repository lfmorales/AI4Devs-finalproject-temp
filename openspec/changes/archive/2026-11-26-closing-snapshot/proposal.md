## Why

Closing a month freezes only the rebate, the platform rate and, for a target flight, its revenue and its gross (`applied_rates`), while the ingestion keeps replacing the days of a closed month: the nightly D-7 to D-1 window and any `--from`/`--to` or `--date` run ignore the closing, and so does removing a line's mapping. A closed flight therefore reads its media cost, its platform cost, its delivered volumes and its two flags from the delivery as stored now, and a restatement moves a margin that Finance has already reported: in the case recorded by the design of `2026-11-25-equativ-deals`, a committed Adform line closed at 1,850.00 € goes to −450.00 € when Adform restates 28 November after the closing, with no one reopening the month. The only guard today is a provisional rule, closing a month from the 8th of the next month, which a custom range still defeats.

**Phase 2** per `docs/product-description.md` §6: it is the immutable month-end snapshot listed there.

## What Changes

- **A snapshot of every closed flight.** Closing a month stores, beside each `applied_rates` row, one `closed_flight_snapshots` row with the flight's final rounded amounts (revenue, contracted revenue, media cost, rebate, platform cost, margin and, for a target flight, its gross), the delivery they were computed on (delivered impressions, delivered volume in the metric, media cost, reported revenue, buyer's spend, data costs), the two flags, and the line's delivery metric, sale CPM, contracted volume and commitment as of closing.
- **A closed flight is read only from its snapshot.** `GET /api/margin` builds a closed flight's figures from the snapshot, without recomputing them; nothing a later ingestion, unlinking, master or formula change does can move a closed flight, its line, its campaign or the totals.
- **A closing header per closing run.** Every closing that freezes at least one flight records a `month_closings` row (the month, the time, the user, `as_of`) with the latest succeeded ingestion batch of each DSP of the flights it froze. A month is closed when it has at least one. `POST /api/margin/closings` answers `closings`, how many headers the month holds after the request, so that a second closing of a month shows. **BREAKING** for clients that compare the closing response exactly: it gains one field.
- **The delivery keeps updating, as information.** The ingestion and the unlinking stay allowed over closed months and keep superseding the stored delivery; the nightly command prints `closed_month_days`, how many days of its window fall in closed months.
- **«Cambió tras el cierre».** A closed flight whose current delivery moves its margin by 1.00 € or more, or its delivered volume by 1 % or more, carries `delivery_changed`. Every closed flight carries `delivery_change`: the differences of its delivered volume, delivered impressions, media cost and, for a target flight, reported revenue and buyer's spend, and the margin its current delivery would give with the closing's rebate and rates. It is informative only: no amount or total changes. Lines, campaigns and the totals count it, and the margin screen labels it.
- **The migration refuses a database with closed flights.** There is no production; a database whose `applied_rates` holds rows stops the migration with a message asking to run `e2e/scripts/reset-data.sh`.
- **No route is added**: `ACCESS_MATRIX` is unchanged.
- **Documentation**: `docs/product-description.md` drops the provisional rule of the 8th and records the snapshot; `docs/deploy.md`, `readme.md` and `openspec/config.yaml` follow after the implementation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `finance/rebate-accrual`: closing writes a snapshot and a header, answers how many headers the month holds, and a closed month is read only from its snapshot.
- `finance/margin-calculation`: the media cost, the platform cost, the target revenue and the two flags of a closed flight are those of its snapshot; the informative margin of the change warning.
- `finance/margin-reporting`: a closed flight reports its frozen volumes and figures, carries `delivery_changed` and `delivery_change`, every level counts it, and the screen labels it.
- `finance/platform-rate`: the platform cost of a closed flight is frozen with the rate and the impressions it was computed on.
- `delivery/delivery-ingestion`: a restatement of a closed month supersedes the stored delivery and leaves the closed margin unchanged; the command reports the days of its window in closed months.

## Impact

- Backend: the margin models and an Alembic migration (two new tables and their batch rows), the closing service and the applied-rate repository, the margin read repository and `MarginQueryService`, two new pure domain functions (the flight margin from a snapshot and the change check), `FlightMargin`, `MarginTotals` and `margin_totals.py`, the margin schemas, `scripts/run_ingestion.py`.
- API: `POST /api/margin/closings` adds `closings`; `GET /api/margin` adds `delivery_changed` and `delivery_change` on every flight and `delivery_changed_count` on every line, campaign and the totals.
- Frontend: the margin types, the flight and totals tags, with the label «Cambió tras el cierre».
- Data: no backfill; a database holding closed flights must be reset before migrating.
- Documentation: `docs/product-description.md` (with this specification), then `docs/deploy.md`, `readme.md` and `openspec/config.yaml`.

## Non-goals

- Reopening, restating or recalculating a closed month, and versioning a closed figure.
- Refusing or skipping the ingestion or the unlinking of a closed month's days.
- Filling the snapshot of months closed before this change: there is no production, and the delivery as of their closing is not kept.
- Repricing the rebate of a closed flight with its current delivery: the informative margin keeps the closing's rebate and rates.
- Refusing at registration a flight in a month already closed (a risk recorded in the design).
- A screen or a route to list the closing headers.
- E2E coverage of the change warning: it is covered by API and Vitest tests; the E2E keep checking that a closing changes no amount.
