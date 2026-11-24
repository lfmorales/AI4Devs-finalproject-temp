## Context

See `proposal.md` (Why). The current state that shapes the approach:

- **The ingestion is DSP-agnostic up to the client.** `DeliveryIngestionService.run` takes a `DspDeliveryClient`, a DSP id, a route, a source and an optional window (`backend/app/application/services/delivery_ingestion_service.py:60-69`); the targets are found per DSP (`sqlalchemy_ingestion_target_repository.py:24-62`), the window is replaced delete-then-insert (`delivery_range_replacement.py:28-46`), rows are combined per line and day (`delivery_combination.py:7-21`), unmatched rows become exceptions (`unmatched_delivery_recording.py:23-47`) and the catalogue is folded per pair (`catalog_observation.py`). Adform is hard-wired in three places only: `scripts/run_ingestion.py` (`_DSP_NAME` `:46`, `_adform_client` `:138-146`, one lock key `:45`), the client resolver of the API (`backend/app/presentation/dependencies/providers.py:132-141`) and the settings (`backend/app/config.py:48-49`).
- **A DSP pair is two strings.** `dsp_mappings`, `dsp_catalog_lines` and the unmatched exceptions are keyed on (`external_campaign_id`, `external_line_item_id`) per DSP, both `NOT NULL` (`models/dsp_mapping.py:15-17`, `models/dsp_catalog.py:14-16`, `models/delivery.py:90-110`).
- **The margin never reads the channel.** `tests/domain/test_margin_model_integrity.py:47-66` forbids any field of `FlightEconomics` containing `channel`, `deal` or `platform_type`, and any identifier or literal containing `deal`, `directo` or `channel` in the margin modules. Revenue is contracted volume × CPM (`flight_margin.py:45-55`); the rebate base is the same contracted revenue (`priced_flights.py:34`); a running flight pro-rates revenue and rebate (`flight_margin.py:47-50`).
- **Closing freezes rates only.** `applied_rates` holds the rebate amount and the platform rate (`models/margin.py:111-146`); a closed flight's revenue, media cost and delivery are read live and recomputed from the frozen rates (`margin_query_service.py:137-148`). The flight query that feeds both the read and the close is written twice (`sqlalchemy_margin_repositories.py:155-200` and `:224-292`).
- **Pacing flags both directions** (`pacing.py:56-62`) and the status service raises `pacing_flag` on any deviation (`campaign_status_service.py:41`).
- **What the Equativ probes established (2026-11-24, recorded in the team's probe notes, outside the repository):** `POST /async-report` answers 201 with the report's id; the execution reaches `PostProcessingSuccessful` in about 30 seconds; the preview pages with `limit` 100 (a `limit` of 10,000 answers 403) and reports `totalRows`; every value arrives as text; `day` is `YYYY-MM-DDTHH:MM:SS`; `auctionPackageDealId` is always filled, digits only, one per name; `childdealid` is 0 on every row; Equativ returns no row for a day without delivery; the total curator margin is exactly 80 % of the spend on every row; the data costs are 0; with `Etc/UTC` the totals of 2026-11-19 match the reference to 0.03 % and are identical in two reports run at different times, while `Europe/Madrid` falls 9.5 % short. The synchronous `POST /report` gives figures Equativ declares invalid.

## Goals / Non-Goals

**Goals:**
- One attribute on the line, not the channel, decides how a flight earns, how its rebate is based, whether it is pro-rated and whether over-delivery is flagged.
- Equativ enters through the same service, batches, catalogue, exceptions and linking as Adform; only the client and the command's DSP selection are new.
- What Equativ bills (spend, curator margin, data costs) is stored per line and day, exactly, and the figures of a closed target flight never move.

**Non-Goals:**
- A generic connector framework or a DSP registry: two connectors, selected by name.
- Changing anything for `committed` lines: every existing figure, test and screen of a committed line stays as it is.

## Decisions

### 1. `campaign_lines.volume_commitment`, not a rule on the channel

A `String` column, `NOT NULL`, `server_default 'committed'`, with a check limiting it to `committed` and `target`, like `channels.delivery_metric`. A domain `VolumeCommitment` enum travels through `CampaignLine`, `FlightFacts`, `FlightEconomics`, `FlightDeliveryFigures` and the status and margin rows. The name passes the guard of `test_margin_model_integrity.py`.

The request field is required on every line of `POST /api/campaigns` (BREAKING): an implicit default would make a Deal registered by an old client silently `committed`. The form proposes `target` when the chosen channel is named `Deal`, `committed` otherwise, and re-proposes when the channel changes unless the user has already touched the field; the server never derives it.

*Alternatives*: deriving it from the channel (rejected: the guard forbids it and the business decided by the nature of the buy, not by the label); two attributes, one for the volume and one for the revenue basis (rejected: every Deal sets both together, and no case needs them apart); a column `revenue_basis` (rejected: the status also needs it, for over-delivery, which has nothing to do with revenue).

### 2. The Equativ pair is (`auctionPackageDealId`, `auctionPackageDealId`)

The package id fills both strings of the pair. The catalogue keeps the package name in both name columns and no line dates. Operations writes the id once in the screen and the frontend sends it in both fields; the server refuses, with 422 `invalid_equativ_package`, a pair for a line on Equativ whose two ids differ or carry anything but digits. Nothing else in the mapping, the exceptions, the linking or the removal changes, and their uniqueness constraints already say "one package, at most one line".

*Alternatives*: making `external_line_item_id` nullable (rejected: touches three tables, two check constraints and every query on the pair for no behaviour); (package, `childDealId`) (rejected: the child is 0 on every row); a constant in the second slot (rejected: an invented value that would appear in the exception queue).

### 3. One asynchronous report per run, read through its preview

`EquativDeliveryClient` implements `DspDeliveryClient` with an injected `httpx.Client`, like `AdformDeliveryClient`, so tests drive it with a mock transport (`tests/fixtures/fake_equativ.py`). Per run: token (`POST https://oauth.smartadserverapis.com/oauth2/token`, client credentials, cached for the run), `POST /async-report` with the body of the spec and the name `adops360-<first day>-<last day>`, `GET /async-report/{id}/executions` every 30 seconds up to 15 minutes, then `GET /async-report/{id}/preview?offset=N&limit=100` until `totalRows` rows are read. The poll interval, the timeout and the page size are constructor arguments so the tests do not sleep. Errors map to the existing domain errors: transport failures to `DspUnreachableError`, 401/403 on the token to `DspAuthenticationError`, a failed execution status to `DspReportFailedError`, the 15 minutes to `DspReportTimeoutError`, any unexpected shape or count to `DspResponseFormatError`. `fetch_delivery` yields rows as the pages arrive; the service already holds no rows. The report id is returned to the service and recorded as the batch's `source_file`, the column the batch already has for "where the rows came from".

*Alternatives*: the synchronous `POST /report` (rejected by Equativ: its figures are not valid); the `downloadUrl` file (rejected: a second format to parse and a signed URL to handle, for 80 rows a night); a scheduled report with S3 or email delivery (rejected: out of scope, and it adds an AWS dependency); deleting the report after reading (left out, proposal Non-goals: keeping it is the reversible choice, and it lets Equativ review a run).

### 4. Reading a row

Values are text, so amounts are `Decimal(text)` and counts `int(text)`; nothing goes through `float`. `day` keeps its first ten characters as an ISO date. An empty or `0` package id gives `key=None`, counted as ignored like Adform's unattributed rows. `media_cost`, `measurable_impressions` and `ots` are zero; `banner_size`, `screen` and `line_format` are `None` (no channel contrast: the channel-mismatch check needs a reported format and gets none). A missing column, an empty cell or an unreadable value raises `DspResponseFormatError` naming the column, never the value. Every metric is strict: the probes returned `"0"` for zero, never an empty cell.

### 5. Four columns on `daily_deliveries` (option A)

`buyer_spend`, `reported_revenue`, `third_party_data_cost` and `audience_data_cost`, `Numeric(18,6) NOT NULL DEFAULT 0`, like `media_cost`. `DspDeliveryRow` and `DailyDelivery` gain the four `Decimal` fields with the same decimal guard as `media_cost`, and `_from_row`/`_add` sum them. One table, one grain, one replacement and one transaction keep the run all-or-nothing; the margin adds `SUM`s to the query it already runs.

*Alternatives*: a separate table at the same grain (rejected: a second replacement path that must stay in step with the first, and a second join in two queries); the raw report grain (rejected: the margin needs only line and day, and the report is kept in Equativ).

The names say what the figure is, not who reports it: `reported_revenue` is GeoQ's income as the DSP reports it. The buyer's spend is never written to `media_cost`, which would repeat Qlik's error of reading cost as revenue (`docs/product-description.md` §5.3).

### 6. The command selects the DSP; one lock per DSP; absence after 06:00 UTC

`--dsp NAME` (default `Adform`) looks the DSP up by name and picks its client from a small map `{"Adform": …, "Equativ": …}`; a name outside the map, or missing credentials, exits 3 before any batch. The advisory lock becomes `pg_try_advisory_lock(<namespace>, <dsp id>)`, the two-key form the month closing already uses, so an Adform and an Equativ run may overlap and two runs of one DSP may not. The rule "absence only from 06:00 UTC" is applied by the command to Equativ runs, from an injected clock, so a run scheduled too early still ingests and says why absence was skipped. The crontab line for Equativ (06:15 UTC) is documented in `docs/deploy.md`. At that hour the calendar day of Madrid and of UTC is the same, so the window computed in Madrid names the UTC days Equativ reports.

### 6b. An Equativ mapping is validated by the user

`DspMappingService` receives the set of DSPs whose mappings the user validates (`{"Equativ"}`, from the providers). For those it asks no client and no catalogue: it checks the pair's shape, sets `validated_at` at creation and answers the outcome `user_validated` (a new value of `IdentifierCheck` and of the response's `validation`). `last_impressions_date` still comes from the catalogue, null when the package has not been seen. The check for lines without delivery needs no change: it already evaluates every line whose validated mapping predates the flight's end and sums the flight's delivery from its first day (`sqlalchemy_ingestion_target_repository.py:78-110`), so a package that never bids, or an id written wrong, surfaces as `missing_delivery` once the flight ends. The catalogue is used to suggest packages in the screen and by the exception route.

*Alternatives*: checking against the catalogue (rejected by the business: a new Deal could not be mapped until it had delivered, and its first days would be lost to the window); creating an Equativ report per mapping (rejected: about 30 seconds inside a request, and one more report in the account per mapping).

The Equativ client is therefore needed only by the nightly command, never by the API.

### 7. The margin of a target flight

`FlightEconomics` gains `volume_commitment`, `reported_revenue`, `buyer_spend` and `data_cost` (the two data costs summed: only their presence is flagged). `calculate_flight_margin` branches once on the commitment:

- `committed`: unchanged.
- `target`: revenue `round(reported_revenue)`; gross `round(served / 1000 × CPM)`; no pro-rating of revenue or rebate; `contracted_revenue` stays the target's sale.

The rebate base is computed in `priced_flights.py` from a pure helper of `flight_margin.py` (`rebate_base(facts)`: the contracted revenue for `committed`, the gross for `target`), so the engine, the counters and the frozen positions advance by the gross without knowing why. `FlightMargin` gains `volume_commitment`, `gross_revenue`, `gross_differs_from_buyer_spend` and `data_cost_reported`; `MarginTotals` sums the gross of target flights (null when none), counts the two flags and carries the shared commitment or null, like `delivery_metric`.

The gross tolerance is a constant of the margin model, `GROSS_TOLERANCE = Decimal("0.01")`, compared on rounded amounts: `abs(gross − spend) > spend × 0.01`, or `spend == 0 and gross != 0`.

*Alternative*: a second margin function for target flights (rejected: two functions to keep consistent for rounding, flags and provisional state).

### 8. One flight query, then the new sums

The two copies of the flight query in `sqlalchemy_margin_repositories.py` are first merged into one builder (a refactor with no behaviour change, its own task), then the commitment and the sums of `reported_revenue`, `buyer_spend` and the data costs inside the window are added once.

### 9. Closing freezes the revenue and the base of target flights, and waits for the last day

`applied_rates` gains `revenue_amount` and `rebate_base_amount`, `Numeric(24,12)` nullable, with a check that both are null or both set; `save` fills them for target flights. `MarginQueryService._margin_from_frozen` passes the frozen revenue and base to the margin instead of the live sums. Media cost and platform cost keep their current behaviour (live delivery, frozen platform rate): freezing them is the immutable month-end snapshot of phase 2.

The block: `MarginClosingService` asks a new repository method for the DSPs of the month's target flights that have no succeeded batch whose window contains the month's last day; any answer raises `MonthDeliveryNotLoadedError(year, month, dsp_name)`, mapped to 409 `month_delivery_not_loaded`, inside the same transaction and before anything is written. The check runs after `previous_month_open`, so the earliest blocker is reported first.

*Alternative*: freezing every flight's revenue (rejected: a committed flight's revenue is the contract, which does not move).

### 10. Pacing flag by commitment

`calculate_pacing` stays pure and unchanged. A new pure function `pacing_flag(pacing, commitment)` in `pacing.py` returns `pacing.is_deviating` for `committed` and `pacing.status is UNDER_DELIVERING` for `target`; the status service uses it.

### 11. Screens

The campaign form adds the commitment selector per line («Compromiso» / «Objetivo»). `StatusTable` labels the contracted column of a target row «Objetivo». `MarginTree` and `Figures` say «Venta objetivo» for a target line or flight, add a «Bruto» column, and show «Bruto distinto del gasto» and «Coste de datos» as tags like «Margen negativo». The closing button maps `month_delivery_not_loaded` to a Spanish message naming the month and the DSP. No arithmetic in the frontend: every figure is the API's.

### 12. Seeds and E2E

`seed_dev_data.py` and the test fixtures already hold the `Equativ` DSP and the `Deal` channel. `seed_margin_demo.py` adds a Deal demo campaign with one target line on Equativ, a validated Equativ mapping and invented daily deliveries (the four amounts included) such that a closed month reproduces the worked example and a running month delivers above its target. E2E never calls Equativ: the client is covered by the fake transport. The E2E campaign helpers send `volume_commitment` (`e2e/support/campaigns.ts`, `campaign-form.ts`).

### 13. Credentials, and no test reaches Equativ

`EQUATIV_CLIENT_ID` and `EQUATIV_CLIENT_SECRET` live only in `.env`: the developer's local `.env`, ignored by git, and the production `.env` on the instance with restricted permissions (`chmod 600`), which is where the production secrets are kept (`docs/base-standards.md` §4 and §7; Secrets Manager is out of scope for the MVP). They are never in the repository, a ticket, a report or a log: `.env.example` names them with placeholder values only, the compose files never name them, and the frontend container never receives them (`docker-compose.yml:64`). In the settings they are optional, like Adform's (`app/config.py:48-49`), so the development compose and the API start without them; only `run_ingestion --dsp Equativ` requires them, and exits 3 when they are missing.

An autouse fixture in `backend/tests/conftest.py` makes every test fail at once if it opens a real HTTP request to a host ending in `eqtv.io` or `smartadserverapis.com`: it wraps `httpx.HTTPTransport.handle_request` and `httpx.AsyncHTTPTransport.handle_async_request` and raises for those hosts. Tests of the Equativ client use `httpx.MockTransport` (`tests/fixtures/fake_equativ.py`), which never reaches the wrapped transports. Microsoft is kept away differently today: the tests replace the key provider (`tests/api/test_token_issuers_wiring.py:55`), and no fixture aborts a request to Microsoft; extending the fixture to Microsoft's hosts is left to a change of its own. The only call to the real Equativ API in this change is the manual run of task 18.6.

### 14. Reports

As in the previous changes, the reports go to `docs/reports/`, not to `specs/<change-name>/reports/` as `openspec/config.yaml` says.

## Risks / Trade-offs

- [The preview may cap the rows it returns for a long range] → The run compares the rows read with `totalRows` and fails rather than store a partial window; a 7-day window is about 80 rows and the 23-day probe returned all 238.
- [An Equativ date is a UTC day while Adform's is a Madrid day] → Decided by the business (Equativ bills in UTC); recorded in the time-zone requirement and in `docs/product-description.md`. A Deal and a Directo line are never added within one day of one campaign total.
- [Equativ returns no row for a day without delivery, so a Deal campaign that delivered nothing yesterday raises «no data received»] → That is the flag's meaning; the pacing flag of a target line only fires below target, so no double warning for over-delivery.
- [The company currency of the Equativ account is assumed EUR] → The probe's totals match the reference stated in euros; amounts carry no currency column today, as for Adform's cost. A non-EUR account would need the `…Euro` metrics; recorded as an assumption in `docs/deploy.md`.
- [One report is left in the Equativ account per run] → Named `adops360-<window>` so it is recognisable; deleting them, if Equativ asks, is a change of its own.
- [A `target` line on Adform would earn zero, because Adform reports no revenue] → Not restricted by this change (proposal, Non-goals); the form only proposes `target` for `Deal`.
- [Restated platform cost of a closed target flight] → Platform cost still reads live delivery, as for every flight today; the revenue and the rebate base do not move.
- [`POST /api/campaigns` becomes stricter] → The frontend form, the E2E helpers and every API test change in the same task as the schema.

## Migration Plan

1. Migration 1 (line attribute): add `campaign_lines.volume_commitment` with its default and check; existing rows read `committed`. Downgrade drops it.
2. Migration 2 (delivery amounts): add the four columns to `daily_deliveries`, `NOT NULL DEFAULT 0`. Downgrade drops them.
3. Migration 3 (closing): add `applied_rates.revenue_amount` and `rebate_base_amount` with their pair check. Downgrade drops them.
4. Deploy: set `EQUATIV_CLIENT_ID` and `EQUATIV_CLIENT_SECRET` in `.env`, `alembic upgrade head`, add the crontab line `15 6 * * * … python -m scripts.run_ingestion --dsp Equativ`, run one `--dsp Equativ --from <first day of the running Deal lines> --to <D-1>` to load their history, then map the packages from the exception queue.
5. Rollback: downgrade the three migrations and redeploy the previous image; no Deal line was closed with frozen revenue before this change, so nothing is lost.

## Open Questions

- Whether `measurable_impressions` should come from an Equativ metric; no screen or figure reads it today, so zero is safe until one does.
