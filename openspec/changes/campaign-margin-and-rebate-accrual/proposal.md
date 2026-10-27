## Why

The margin logic lives inside chart expressions in a Qlik Sense application, keyed on a parsed campaign-name string, with the rebate year chosen by a hardcoded two-way `if`. Nothing records what the rule was supposed to be, which is why the app computes the platform cost on its own sheet and then leaves it out of the margin — overstating the figure Finance reads by **16.0 points across 2023–2026**, or 1,906,045 € of cost that never reaches the headline number.

The rebate is worse: it is stored as one flat percentage per key in a spreadsheet whose key schema widens every year and whose mid-year changes are recorded by inventing a new row and writing the reason in a free-text comment. The tiered accrual the business actually negotiates does not exist anywhere in the tooling.

This change makes the calculation explicit, tested and versioned.

**Phase 1** per `docs/product-description.md` §6.

## What Changes

- **The unit of calculation is the flight.** A flight is one campaign line in one calendar month (`campaign_line_periods`, with `flight_start`, `flight_end` and `contracted_impressions`). The margin of a line is the sum of its flights and the margin of a campaign is the sum of its lines. A flight never crosses a calendar month, so it never crosses a year.
- **The margin is computed from explicit rules**: revenue on contracted volume, less media cost, less agency rebate, **less platform cost**. The platform cost is part of the margin, which is the point on which this product's numbers will differ most visibly from the ones Finance reads today.
- **Revenue is recognised on contracted volume, never on delivered.** Revenue is the flight's contracted volume times the line's sale CPM; it does not depend on the purchase order version, which may be absent. Delivered volume drives the platform cost and nothing else.
- **Media cost is the Adform `Cost` column summed over the flight's window.** It already includes Adform's additional costs; no other media cost exists.
- **A running flight is pro-rated by elapsed contract days of its own window** and presented as a provisional accrual, explicitly labelled, not as a result. It writes nothing and does not advance the rebate counter.
- **The rebate becomes a bracket schedule with marginal tiers**, resolved by date through an eight-step ladder (the reference date is `flight_start`), accumulating per holding group and channel over the year of `flight_start`, applied chronologically.
- **An agency may carry an exception** that replaces its group's schedule for that agency. Carving the agency out of the group's counter is **deferred** and documented as a limitation.
- **Rates are frozen per closed flight** in `applied_rates`, an append-only table with one row per closed flight. A finance-only closing endpoint, `POST /margin/closings`, resolves and freezes the rates of the flights that ended in a given month, idempotently. Editing a master afterwards does not move a closed month.
- **The platform rate becomes data**, configurable at line, agency, campaign-type and system level, every override stamped with its author and time. The system value is 1.00 €/CPM, held as data and never as a constant in code.
- **Every monetary amount of a flight is rounded to 2 decimals, half up, before it is subtracted**; totals are the exact sum of their flights' rounded amounts.
- **Roll-ups by period, agency, advertiser and campaign type**, restricted to the `finance` role.

### Cut of this change

The first cut implements the closed-month and running-month margin, the ladder, marginal brackets with the chronological counter, the platform rate, freezing at closing, and the finance-only API and views. The following are **deferred** with their reason in `tasks.md`: accrued/settled storage (1.3), scope-mean and carry-forward tests (3.5, 3.6, and therefore ladder step 7), the agency carve-out and every restatement or replay mechanism (4.4–4.10), export (6.6), `CuratorMargin` (6.9), the roll-up view (7.4), the masters zero-versus-unloaded view (7.7) and the data migration and reconciliation (8.1, 8.3–8.5).

## Capabilities

### New Capabilities

- `finance/margin-calculation`: the per-flight economics — revenue, media cost, rebate, platform cost and margin — in closed and running form, summed up to line and campaign.
- `finance/rebate-schedule`: bracket schedules with temporal validity, the resolution ladder, and the agency exception that replaces a group's schedule.
- `finance/rebate-accrual`: the annual counter per group and channel, chronological bracket attribution and the freezing of the rate at closing.
- `finance/platform-rate`: the infrastructure rate as configurable, audited data resolved most-specific-first.
- `finance/margin-reporting`: roll-ups and the provisional labelling that keeps an estimate from being read as a result.

### Modified Capabilities

- `campaign/campaign-registration`: a line may carry a sale CPM of 0.00 when its contracted impressions are above zero, and never a negative one (delta in this change).

### Dependencies

- `register-campaign-from-purchase-order`: **archived** on 2026-10-18; its requirements live in `openspec/specs/campaign/campaign-registration/spec.md`. It supplies the campaign, its lines, scope, channel, sale CPM and the agency-to-group chain.
- `daily-campaign-delivery-status`: **not archived**. It introduces the flight model (`campaign_lines` hanging from the campaign with their own dates, and `campaign_line_periods` as flights) and supplies delivered impressions and media cost in `daily_deliveries`.
- **Known stale text in the main registration spec.** `openspec/specs/campaign/campaign-registration/spec.md` still says that volume and price "live on the line" and that a campaign "expands into one period per calendar month". Both are superseded by the flight model of `daily-campaign-delivery-status`. This change does not modify that spec; the correction belongs to the change of `daily-campaign-delivery-status` (story 2), which must carry the delta before it is archived.

## Impact

- **Database**: `rebate_schedules` with temporal validity and a nullable agency for exceptions, `rebate_brackets`, `platform_rate_settings`, and `applied_rates` (one append-only row per closed flight, foreign key to `campaign_line_periods`). `rebate_accruals` (accrued versus settled) is deferred.
- **Backend**: the whole economic model in the domain layer, testable without a database; the resolution ladder; the chronological counter; roll-up queries aggregated in the database joining deliveries to flights by date range; `finance`-only routers, including `POST /margin/closings`.
- **Frontend**: the margin view restricted to `finance`, with provisional figures labelled and below-cost flights flagged.
- **Migration**: loading the rebate spreadsheets is deferred (8.1).

## Non-goals

- **The bracket thresholds themselves.** The ladder is built; the negotiated values are pending and load as single brackets until supplied.
- **Immutable month-end snapshots and a rate-versioning interface for Finance.** Phase 2. Deliberately recalculating a closed month, restating the year after a schedule change and replaying a counter chronologically are likewise deferred.
- **Retiring Qlik Sense.** Phase 4. This runs alongside it, and acceptance is explained divergence, not parity.
- **Invoicing, ERP posting and credit notes.** Excluded by the PO.
- **Multi-currency.** Everything is EUR; amounts carry an explicit currency so adding conversion later is not a migration.
- **`CuratorMargin` as stored data.** It is `OC revenue − purchase cost`, computed on demand for Equativ billing, and never enters the margin. Its implementation is deferred.
