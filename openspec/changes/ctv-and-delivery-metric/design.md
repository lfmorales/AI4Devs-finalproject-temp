## Context

See `proposal.md` (Why). The current state that shapes the approach:

- `channels` holds only `id` and `name` (`backend/app/infrastructure/persistence/models/masters.py:39`). The channel name is the rebate counter key (`backend/app/domain/services/rebate_engine.py:18`) and the schedule match (`backend/app/domain/services/rebate_ladder.py:35`). No migration seeds channels: development and tests load `Digital`, `OOH`, `DOOH` (`backend/scripts/seed_dev_data.py:76`, `backend/tests/fixtures/master_data.py:71-72`), a fresh deployment loads `deploy/masters.example.json` through `scripts/load_masters.py`, which only creates and never modifies (`load_masters.py:1-10`, `docs/deploy.md:120`), and the margin demo adds `DEMO Channel`.
- The Adform client asks for five metrics (`backend/app/infrastructure/dsp/adform_delivery_client.py:46`) and fails the run on any value it cannot read (`:223-224`). Rows are combined per line and day by `delivery_combination.py`; an unmatched row is worked when it has impressions or cost (`unmatched_delivery_recording.py:23-25`).
- The delivered volume is `SUM(daily_deliveries.impressions)` in four places: the daily status (`sqlalchemy_campaign_status_repository.py:26`), the margin read and the month close (`sqlalchemy_margin_repositories.py:161`, `:231`) and the missing-delivery check (`sqlalchemy_ingestion_target_repository.py:80-102`). Pacing takes integers (`pacing.py:31-52`); the platform cost reads `delivered_impressions` (`flight_margin.py:52`); the margin totals sum integers (`margin_totals.py:13-62`).
- No seed, fixture or E2E registers a campaign whose lines have different channels; the only tests with a second channel use a channel that does not exist (`test_campaign_registration_flights.py:184`, `test_campaign_registration_service.py:154`, `test_campaign_repository_flights.py:130`).

## Goals / Non-Goals

**Goals:**
- One place that says which unit a channel is counted in, read by every query that sums delivery.
- The impressions figure keeps one meaning everywhere, so the platform cost and every existing consumer of `delivered_impressions` are untouched.
- Exact arithmetic for OTS from the Adform cell to the API string.

**Non-Goals:**
- A generic metric framework: only `impressions` and `ots` exist, and the set is closed.
- Changing the meaning of any stored figure other than the contracted volume of DOOH lines, of which there are none today.

## Decisions

### 1. The catalogue is fixed in the seeds, not by a migration

The four channels are written by `seed_dev_data.py`, `tests/fixtures/master_data.py` and `deploy/masters.example.json` in the order `Directo`, `Deal`, `DOOH`, `CTV`, so that in a fresh test database `channel_id=1` is `Directo` and `DOOH` keeps id 3. `OOH` and `Digital` are removed with no data migration: no real database holds them. An existing development database keeps its old rows until it is reset, because the seed only inserts. The fictitious CTV schedule is a second schedule of the seed's `Default Holding Group` with `channel_id` = CTV and no agency or scope; it does not overlap the existing any-channel schedule under the exclusion constraint (`models/margin.py:47`), because the channel is part of the key.

*Alternative*: an Alembic data migration that inserts the four channels. Rejected: channels have always been data loaded per deployment, and a migration would collide with names already loaded from a masters file.

`DEMO Channel` stays. It is created only by `scripts/seed_margin_demo.py` (`:96`), in the development and E2E databases, as a stand-in for real channels in the invented campaigns; the E2E form helper picks it on purpose (`e2e/support/campaign-form.ts:26`). The API helper takes the first channel by name (`e2e/support/campaigns.ts:47`, ordered at `masters.py:88`): today that is `DEMO Channel`, but with the four channels it becomes `CTV` under both the C and the `en_US` collations, which would move the E2E campaigns onto the CTV rebate schedule of the seed. Task 15.1 makes that helper prefer the `DEMO` channel like the form helper, so the E2E keep their channel. The catalogue of four is what the seeds, the fixtures and the masters file define; channels named `DEMO …` are an exception of the demonstration data, counted in impressions by default, and no real deployment has them. Removing it would rewrite the margin and exceptions demos and every E2E that chooses a channel, for no change in behaviour. The DOOH demo campaign of task 15 uses the real `DOOH` channel, not a demo one, because its point is the `ots` metric.

### 2. `channels.delivery_metric` is a column, not a rule on the name

A `String` column, `NOT NULL`, `server_default 'impressions'`, with a check constraint limiting it to `impressions` and `ots`. Every query that sums delivery joins the line's channel and sums `CASE WHEN channels.delivery_metric = 'ots' THEN daily_deliveries.ots ELSE daily_deliveries.impressions END`, in the database, next to the unchanged `SUM(impressions)`.

*Alternatives*: a constant `{"DOOH": "ots"}` in code, rejected because the name is data, the margin demo uses `DEMO Channel` and a renamed channel would silently change unit; a PostgreSQL enum, rejected in favour of a string with a check like `platform_rate_settings.level` (`models/margin.py:87`), which a later migration can widen without altering a type.

### 3. How the metric is set on a channel that already exists

`load_masters` cannot update, so four options were weighed:

| Option | Fresh deployment | Database that already has `DOOH` | Cost |
|---|---|---|---|
| A. Migration sets `ots` on the row named `DOOH` | Does nothing: migrations run before the masters load, so the row does not exist yet | Fixed | One `UPDATE` |
| B. `load_masters` accepts `delivery_metric` when it creates | Fixed | Does nothing | One optional key |
| C. `load_masters` also updates existing channels | Fixed | Fixed | Breaks its contract that nothing existing is modified |
| D. A route or a script to change it | Fixed | Fixed | A new route and an `ACCESS_MATRIX` entry, excluded by this change |

**Chosen: A + B, and `load_masters` refuses a disagreement.** The migration that adds the column runs `UPDATE channels SET delivery_metric = 'ots' WHERE name = 'DOOH'`; a fresh deployment gets `ots` from `{"name": "DOOH", "delivery_metric": "ots"}` in the masters file. A file that names an existing channel with a different metric is rejected as invalid by `--check` and by the load, reported as `channels[i]`, writing nothing, so a wrong file never passes silently. Changing the metric of a channel that already has lines would change the unit of its history, so it is deliberately not offered; if it is ever needed it is an operator `UPDATE`, documented in `docs/deploy.md`.

### 4. One metric per campaign is a registration rule in the application layer

`CampaignRegistrationService` already validates each line's master references (`campaign_registration_service.py:137-147`). After that loop it compares the delivery metrics of the lines' channels and raises a new domain error, `MixedDeliveryMetricsError`, mapped in `presentation/errors.py` to 422 `mixed_delivery_metrics` like `line_dates_outside_campaign`. Because it runs after the reference loop, an unknown channel is still reported for itself (today a 400 from the `ValueError`). The master repository's `Channel` gains `delivery_metric`, and the in-memory registration fixture returns it. The flight preview takes one line and is unaffected. With this rule a line and a campaign have exactly one metric; `total_lines` still returns `None` for the metric if the lines ever disagreed, as a defensive fallback that the rule makes unreachable.

### 5. Reading OTS and completions from Adform

`_METRICS` gains `ots` and `videoCompletionRate`, so `_REQUIRED_COLUMNS` already makes a missing column a format error naming it. For these two metrics only, an empty cell (`None`, `""`, `"-"`) is zero, matching the connector of the trading desk; any other unreadable value still raises `DspResponseFormatError`. The five existing metrics keep their strict reading.

Both cells are read as `Decimal(str(value))` and rounded with `quantize(..., rounding=ROUND_HALF_EVEN)`; `round()` is never applied, and no value is ever converted to `float`. The report is already parsed with `parse_float=Decimal` (`adform_delivery_client.py:169`), but `str()` first makes the reading independent of whether the cell arrives as a `Decimal`, an `int`, a text or, in a test double, a `float` (whose shortest `str` is the decimal that was written, `"0.575"`, not its binary expansion).

- OTS: `Decimal(str(ots)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)`.
- Completions: `int((Decimal(str(rate)) * impressions).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))`, per row, before combination.
- Why not `round()` on a float: `round(0.575 * 100)` is 57 because the float product is 57.49999…, while the decimal product is exactly 57.5 and rounds half to even to 58; `round(100.00035, 4)` is 100.0003, while the decimal rounds to 100.0004. The spec carries both cases as a scenario, and the tests of task 3.1 assert them.
- Half to even differs from the half-up rounding of money only on exact halves; completions and OTS are not money.
- OTS are never derived from impressions. The connector falls back to impressions when the column is absent; here an absent column fails the run instead.

### 6. Storage and combination

`daily_deliveries` gains `ots Numeric(18,4) NOT NULL DEFAULT 0` and `video_completions BigInteger NOT NULL DEFAULT 0` in one migration. `DspDeliveryRow` and `DailyDelivery` gain `ots: Decimal` and `video_completions: int`; `_from_row` and `_add` sum them. No rate is ever held in a value object, so an averaged rate cannot be stored by mistake. The retained delivery of an unmatched exception does not gain them (proposal, Non-goals): it is never moved into the delivery table (`exception_linking_service.py:32`), and the next window brings the OTS in through the new mapping.

### 7. Delivered volume next to delivered impressions

The value objects that carry a flight's delivery (`FlightDeliveryFigures`, `FlightFacts`, `FlightEconomics`, `FlightMargin`, `MarginTotals`, `WindowDelivery`) gain `delivery_metric` and `delivered: Decimal` and keep `delivered_impressions: int`. `calculate_pacing` takes the delivered volume as `Decimal`; `Fraction(Decimal)` is exact, so the ten percent boundary stays exact with OTS decimals. The ratio of the daily status is `delivered / contracted`. `flight_margin.py:52` keeps reading `delivered_impressions`: the platform cost stays on impressions for every channel.

### 8. `contracted_impressions` is in the channel's unit and is not renamed

`campaign_lines.contracted_impressions`, `campaign_line_periods.contracted_impressions`, the request field of the registration and the response fields keep their names. Their meaning becomes "contracted volume in the line's delivery metric": OTS for a DOOH line. The same applies to the pacing's `expected_impressions`. Renaming would touch the registration contract, the stored schema, the frontend form and every test for a unit that only DOOH changes; the `delivery_metric` beside them tells the reader the unit. `delivered_impressions` is the only field that is always impressions.

### 9. Totals and serialisation

`total_flights` and `total_lines` sum `delivered` exactly and carry the shared metric. The grand total of `GET /margin` is built in `MarginQueryService`: when its campaigns have more than one metric, its `delivery_metric`, `contracted_impressions` and `delivered` are `None`, and `delivered_impressions` and every amount are summed as today. `contracted_impressions` of the totals becomes `int | None` in the schema and in `frontend/lib/api/margin.ts`.

`delivered` is serialised as a decimal string with exactly four decimals, in both responses, for the same reason amounts are strings: a JSON number would pass OTS through a binary float. `delivery_ratio`, `expected_impressions` and `deviation` stay floats as today.

### 10. Screens

`StatusTable` and the margin legend (`frontend/features/margin/messages.ts:92`) read `delivery_metric` and say «OTS» or «impresiones»; the legend reads `delivered` instead of `delivered_impressions`. A level whose metric is null shows no «Entregado X de Y» legend. OTS are formatted from the string with the Spanish grouping and their decimals as received, with trailing zeros trimmed, never recomputed. The campaign form maps `mixed_delivery_metrics` to a message of its own.

### 11. E2E

`seed_margin_demo.py` adds one DOOH demo campaign whose invented days carry OTS with decimals and fewer impressions than OTS. The E2E checks that its status row says «OTS» with the seeded volume, that its margin legend says «Entregado … de … OTS», and that the existing `DEMO Channel` rows still say «impresiones». E2E data comes from `e2e/scripts/reset-data.sh`, which already runs the margin demo.

### 12. Reports

As in the previous changes, the reports go to `docs/reports/`, not to `specs/<change-name>/reports/` as `openspec/config.yaml` says.

## Risks / Trade-offs

- [A DOOH pair that plays with zero impressions and OTS above zero gets no `last_impressions_date`, so the mapping response warns that it is idle] → The catalogue keeps meaning impressions (delivery-ingestion delta). Adform plays carry impressions in DOOH; if the warning shows up on real DOOH pairs, add a `last_ots_date` in a later change.
- [Half to even rounding of completions differs from the half-up rounding used for money] → Only on exact halves, and completions are not money; the rule is stated in the spec with a worked example.
- [`contracted_impressions` holds OTS for DOOH under an impressions name] → `delivery_metric` sits next to it in every response, and the design records it; a rename is left for a change that needs it.
- [The totals' `contracted_impressions` becomes nullable] → The frontend type changes in the same task as the screen, and the totals legend is hidden when null.
- [A development database keeps `OOH` and `Digital` rows after pulling this change] → `e2e/scripts/reset-data.sh` or a fresh volume; nothing reads them.
- [Adform may report OTS equal to impressions on non-DOOH lines] → Stored but never read for those channels; the delivery metric decides.

## Migration Plan

1. Migration 1 (task group 5, storage): add `daily_deliveries.ots` and `daily_deliveries.video_completions`, both `NOT NULL DEFAULT 0`. Downgrade drops both; the stored OTS of the last days can be reloaded with the custom-range ingestion.
2. Migration 2 (task group 7, the channel's delivery metric): add `channels.delivery_metric` with its default and check, then set `ots` on the row named `DOOH`. Downgrade drops the column.
3. Deploy: `alembic upgrade head`, then, on a fresh database, `load_masters` with the four channels and `DOOH` as `ots`.
4. Rollback: downgrade both migrations and redeploy the previous image; the previous code ignores the columns, so a code rollback alone is also safe.
