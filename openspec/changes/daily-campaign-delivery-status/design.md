## Context

See `proposal.md` — Why. This change introduces the only high-volume table in the system. The historical corpus is 8,511,412 delivery rows over roughly 1,830 days, averaging ~4,600 rows a day at the DSP's line-item and day grain, with peaks well above that. The stored model is coarser: one record per campaign line and day, with several line items summed. Everything else in the schema is in the thousands of rows.

It also introduces the first scheduled work in the product. Until now every write has been a user action inside a request.

## Goals / Non-Goals

**Goals**

- An ingestion contract that the Equativ and Displayce connectors implement in phase 2 without the ingestion service changing.
- A delivery table that still answers a period roll-up quickly at 10 M+ rows.
- Re-running an ingestion is always safe.

**Non-Goals**

- The margin calculation. Delivery is its input, not its owner.
- A general job scheduler. One nightly run and a manual trigger is the whole requirement.

## Decisions

**Idempotency is delete-then-insert per line and date range, inside one transaction.** The alternative was an upsert keyed on line and date. Rejected because a restatement can *remove* a line-item's rows, not only change their figures, and an upsert would leave the removed ones behind. A batch either lands whole or not at all.

**The reprocessing window is 7 days, applied on every nightly run.** So the nightly job ingests D-7 to D-1, not just D-1. It costs roughly seven times one day's rows — about 32,000 — which is cheap, and it means a restatement within a week is picked up without anyone noticing it happened.

**Delivery is written in batches and streamed, never held as a list of entities.** The domain entity exists for the rules that read delivery; ingestion itself writes through a bulk path. Loading 8.5 M rows as objects is how the migration runs out of memory.

**Aggregation happens in the database.** Pacing and period totals are computed with SQL aggregates over indexed columns, not by fetching rows into Python. Relationships are loaded explicitly; lazy loading across this table is how a status page becomes a timeout.

**Pacing is a pure domain function.** It takes contracted volume, period bounds, a date and delivered volume, and returns the deviation. No database, so the ±10% rule and its boundaries are unit-tested directly.

**The `line_format` from the DSP is stored but never read by a calculation.** Storing it costs a column and makes the disagreement detectable; reading it would let a value GeoQ does not control move the rebate accumulation key and shift brackets for a whole year.

**The nightly run is a container command invoked by the host scheduler**, not an in-process scheduler inside the API. It keeps long work out of the request cycle and makes a manual re-run the same code path as the scheduled one.

**One stats request per run, for every mapped line.** The Adform quota is 10 requests a minute and 500 a day, shared with the whole agency, so a run asks once for the whole window and splits the answer by line afterwards. The report is asynchronous: the request is accepted, its operation is polled at an interval of at least three seconds up to a configurable number of attempts, and the data is read only once the operation has succeeded. Any state other than running or succeeded is a failure.

**A run records its batch outside the delivery transaction.** The batch is written before the range is replaced and finished after, each in its own transaction, so a run that fails still leaves a batch with a failed outcome while the range itself rolls back whole.

**Identifiers are compared as text.** Adform reports campaign and line item identifiers as integers and mappings hold them as text; both sides are normalised to text before they are compared.

**One campaign line per external pair and DSP; several pairs may feed one line.** A pair identifies at most one campaign line, enforced by a unique constraint. Several pairs may map to the same line, and their rows for a day are summed into the single record the grain allows. Decided by the PO.

**Unattributed rows are ignored and counted, never worked.** Rows the DSP reports with no attributed line item are not exceptions: they are counted on the batch. A currency other than EUR is a batch failure, not a conversion.

**Which lines are ingested and which are watched are different sets.** A line is ingested when it has a validated mapping and its campaign's dates overlap the D-7 to D-1 window, whatever the campaign's status: a campaign that ended three days ago still needs the figures Adform restates. The missing-data flag watches only a campaign whose status is `active` and whose dates include D-1. A campaign that has not started belongs to neither set. A line without a validated mapping for the DSP is skipped and counted, not failed.

**Validating a pair through the stats API can only see delivery.** A pair is found when it appears in any row of the last 30 days; a line with no delivery in that period cannot be told apart from one that does not exist. The limitation is documented where the check is made.

**The D-7 to D-1 window prevails over a single D-1.** The proposal's earlier "D-1" wording is superseded: every nightly run replaces the whole window.

**An unmatched pair is one exception, with its retained delivery in a child table.** An `unmatched_delivery` exception is unique per type, DSP and external pair, whatever its status, and holds the first and last dates of its retained delivery. The figures live in `ingestion_exception_deliveries`, one row per exception and date (impressions, clicks, media cost to six decimals, measurable and viewable impressions), unique on exception and date. Ingesting a window again replaces the rows of its dates instead of adding to them. New delivery for a pair whose exception is already resolved is added to it and does not reopen it. A `missing_delivery` exception is unique per line and period. Every exception has `resolved_at`, `resolved_by` (a user) and an optional note.

**Resolving only marks.** It reprocesses nothing: retained delivery stays readable in the child table and never moves into `daily_deliveries`.

**`channel_mismatch` is defined but not generated.** Neither the statistics API nor the manual upload carries `line_format`, so there is nothing to compare. The type exists so the exception queue does not change shape when a source supplies it.

**Unmatched rows of zeros are ignored, not worked.** The statistics API returns rows with no impressions for active campaigns (152 of 279 rows over two days on a real account), so treating each as an exception would bury the real ones. An unmatched row with impressions and media cost both zero is counted on the batch in `zero_unmatched_row_count`; only unmatched delivery with impressions or cost different from zero becomes an exception.

**Absence is judged once a period has ended.** A line is absent from a period when it has no row in it or its impressions sum to zero, evaluated when the period's last day is on or before D-1. The check is a service method, not wired to a scheduler yet.

**Absence is evaluated only for mapped lines, inside the window, after the mapping.** A `missing_delivery` exception is considered only for a line with a validated DSP mapping, for a period whose last day falls between D-7 and D-1, and only if the mapping was validated on or before that last day, so a period older than the mapping is never flagged. A line without a validated mapping could never have received delivery, and that case is already reported as a skipped line. The campaign's own status is not part of the rule: a campaign that ended inside the window is exactly the one whose last period is evaluated.

**Pacing, the status view and absence are three separate things.** Pacing is a pure function of contracted volume, period bounds, a date and delivered volume. It does not know which periods are shown, so a finished period with nothing delivered reports under-delivery. The status endpoint decides what is listed, and leaves out finished periods and campaigns that have not started. Delivery that never arrived in a finished period is the absence exception's job.

**The exception queue exposes what was retained, not its cost.** An exception shows its first and last dates, its number of days, and the total impressions and clicks it retains. The retained media cost is stored but not returned by any endpoint until the finance restriction of the status API exists, because cost figures are restricted to `finance` and the queue is open to `operations`.

**The two flags are different questions.** The missing-data flag asks whether the latest delivery predates D-1, and a row of zero impressions counts as data received. A campaign that keeps sending rows of zeros is stalled, which the pacing deviation flag covers.

**A batch counts rows read.** `row_count` is the number of rows read from the DSP; rows without an attributed line item are counted in `ignored_row_count` and unmatched rows of zeros in `zero_unmatched_row_count`. The states are `running`, `succeeded` and `failed`.

## Risks / Trade-offs

- **The delivery table grows without bound and the migration adds 8.5 M rows at once.** → Index the columns joins and filters use — the mapping, the campaign period, the delivery date — from the first migration. Partitioning by date is the escape hatch if roll-ups degrade; deliberately not built now, because the access pattern is period-scoped and an index covers it until volumes are known in production.
- **Adform restates figures beyond 7 days.** → The window is a configuration value, and a manual re-run over an arbitrary range uses the same idempotent path.
- **An unmatched-key flood on the first migration run** could bury real exceptions: 87 orphan delivery keys and 178 configured months with none are already known. → The migration reconciles against the known list rather than generating exceptions one by one, and the 136 campaign-months ruled as never executed are excluded from the corpus rather than imported and flagged.
- **A D-1 flag is noisy when the DSP runs late.** → Accepted deliberately by the PO: the flag clears itself on the next successful ingestion, whereas a wider window hides a real outage for a day. A stalled campaign that still sends rows is not this flag's job; the pacing deviation flag covers it.
- **The nightly run failing silently** would leave the status stale while looking healthy. → Every run writes a batch record with its outcome, and the status view reads the last successful run, so a stale page is visibly stale.

## Migration Plan

1. The initial migration creates identity, master data, the campaign tree, purchase orders and DSP mappings.
2. `add delivery ingestion tables` creates `daily_deliveries`, `ingestion_batches` and `ingestion_exceptions` with their indexes.
3. `widen media cost to six decimals` changes `daily_deliveries.media_cost` to `Numeric(18,6)`.
4. `add ignored row count to ingestion batches` adds `ignored_row_count`.
5. `make dsp mapping external pair unique per dsp` replaces the lookup index on `dsp_mappings` with a unique constraint.
6. The exceptions migration renames the exception types, adds the DSP, external pair, period, first and last dates and resolution columns, creates `ingestion_exception_deliveries`, and adds `zero_unmatched_row_count` to the batches.
7. The Adform connector runs against a bounded recent range first and is reconciled by hand before the schedule is enabled.
8. The historical corpus loads through the upload route in date-ordered batches, each recorded with its source file.
9. Rollback runs the migrations downward in reverse order. The unique constraint on `dsp_mappings` is restored to the original lookup index by its own migration's downgrade, so dropping only the delivery tables would leave it behind. Dropping the delivery tables does not touch the campaign tree, which nothing in them references the other way.

## Open Questions

- Whether the ingestion window should widen beyond 7 days for specific DSPs once their restatement behaviour is observed. It is a configuration value either way and does not change the schema or the task breakdown.
