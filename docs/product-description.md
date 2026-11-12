# GeoQ Campaign Hub — Product Description

> Working document owned by the Product Owner. Source of truth for scope discussions until the OpenSpec change is created.
> Written in English per `CLAUDE.md` §2. Business stakeholders receive a Spanish summary separately.

## 1. Context and problem

GeoQ plans, buys and measures digital and out-of-home (OOH/DOOH) advertising campaigns on behalf of media agencies and, less frequently, direct advertisers. Campaign execution happens in third-party DSPs — Adform, Equativ and Displayce — while every other part of the process lives in spreadsheets:

| Team | Tool today | What it produces |
|---|---|---|
| Business | Excel | Commercial offer (`OF`) that must become a purchase order (`OC`) |
| Operations / AdOps | `campaigns.xlsx` on OneDrive | Campaign configuration, transcribed from the client's `OC` |
| Operations / AdOps | Manual daily Excel downloads from each DSP | Daily delivery status |
| Finance | Qlik Sense + `extraprimas 2026.xlsx` | Margins and period/agency/campaign-type roll-ups |

The chain is fragile at every hand-off: the offer is re-keyed into the configuration file, the configuration file is re-keyed against the DSP, delivery is downloaded and filtered by hand every morning, and margin depends on a rebate table maintained in a separate workbook whose values change mid-year with the reason written in a free-text comment.

### Evidence from the current files

Analysis of the two workbooks provided (September 2026 snapshot):

- `campaigns.xlsx` → `Campaigns`: 170 rows, 113 distinct campaigns, 17 distinct agencies. **The grain is campaign × calendar month**, not campaign — a campaign running February to December produces one row per month.
- `campaigns.xlsx` → `History`: 3,112 archived rows, 1,623 distinct campaigns, 71 distinct agencies, covering 2022-03 to 2026-08. This is the migration corpus.
- `campaigns.xlsx` → `Customer`: 49 rows mapping `Agencia` → `GRUPO` (holding group), plus a third column `RECLAM` whose 25 values each map to exactly one agency. The PO confirms the campaign is invoiced to the **agency**, so `RECLAM` is not the billing entity; it is carried as descriptive metadata and drives nothing.
- `campaigns.xlsx` → `Providers`: 8 rows mapping a provider to the sender address and mechanism its report arrives by — `adform` / `reports_noreply@adform.com` / attachment, `equativ` / `report@smartadserver.com` / link, plus Google Ad Manager, CM360, Sizmek, Smart, SiteScout and one human sender at `beyup.es`. Delivery reporting arrives **by email**, as attachments or as links, and is opened by hand.
- `extraprimas 2023.xlsx`, `extraprimas 2024.xlsx`, `extraprimas 2026.xlsx`: the rebate tables. **Their key schema widens year on year**, which is the single most important structural finding of this analysis:

  | Year | Key | Rows | Groups |
  |---|---|---:|---:|
  | 2023 | `GRUPO` | 17 | 17 |
  | 2024 | `GRUPO` × platform type | 80 | 21 |
  | 2025 | *(no file — inherits 2024)* | — | — |
  | 2026 | `GRUPO` × platform type × scope | 167 | 22 |

  Rebate values range from 0% to 40%. Rates genuinely move between years — `DENTSU` 30%→25%, `IPG` 35%→25%, `GRUPO HAVAS` 36%→40% — which confirms that applying the current table retroactively would have produced materially wrong historical margins.

  The tables are also **incomplete within a year**: in 2024 `IKI GROUP` has no `Directo`, `CTV` or `DOOH` rate and `IRISMEDIA` has no `CTV`; in 2026 `GROUPMWPP` has only one of its eight combinations and `IRISMEDIA` still lacks `CTV`. `IKI GROUP` is the second-largest agency by active campaign volume and `Directo` is 129 of 170 active rows, so this gap has money attached to it.

- `C.C.C. v2.qvf`: the Qlik Sense application, 41 MB. Its load script and master measures were extracted and are the basis of §5. It also reveals the Business team's offer register in a commented-out `BEYUP` block (`Estatus Agencias BEYUP.xlsx`): offer number, group, agency, client, campaign, owner, sector, geography, presentation date, acceptance date, start date, duration, net budget, and a state funnel of `OFERTA` → `GANADA`. That is the phase 3 model, already specified by an existing artefact.

- `Campaigns_all_config.qvd` (table `CAMPAÑAS1`, 2,921 rows, 41 fields) and `Campaigns_all_1.qvd` (table `ADFORM`, **8,511,412 rows**, 22 fields): the two datasets Qlik actually reads. Decoded directly from the QVD symbol tables and record data.

### There is no ETL and no API

This was the biggest open question in the previous revision, and the delivery QVD answers it plainly. Two of its fields describe how the data got there:

- `origen` — 49 distinct values, all hand-named load batches: `carga 1`, `carga 2`, `carga actual`, `carga 14/7`, `carga octopus`, `carga Clarel 14-7`, `carga equativ feb_3`, `carga equativ 8/11`, `carga dooh`.
- `file` — 1,999 distinct values, one per daily spreadsheet: `Campaigns_Fecha_Creas_viewability_13_12_2023.xlsx`, `…_14_12_2023.xlsx`, `…_15_12_2023.xlsx`, unbroken to the present.

So the "pipeline" is a Qlik script concatenating **1,999 manually downloaded Excel files**, accumulated daily since December 2023, re-loaded in ad-hoc batches named by whoever ran them. The Adform API has never been used. Nothing upstream can be reused, and nothing exists to be decommissioned — phase 1 builds the ingestion from zero, and the manual Excel path it must preserve as a fallback is, today, the only path there is.

It also sizes the problem: 8.5 M delivery rows over roughly 1,830 days is an average of ~4,600 rows a day at the line-item/creative/day grain, with peaks well above that.

### The agency reference resolves for 94% of rows

The campaign is invoiced to the agency, and the agency belongs to a holding group, which is what the rebate brackets accumulate against (§5.4). That makes `Campaign → Agency → Group` a mandatory chain: a campaign whose agency does not resolve cannot be invoiced, and a group with no rate accrues nothing. Against the 2,921 configured rows:

| | Rows | Revenue |
|---|---:|---:|
| Agency resolves to a group | 2,738 | 11,520,215 € |
| Value is a *group* typed into the agency field | 16 | 57,684 € |
| **Does not resolve at all** | **167** | **324,428 €** |

The 167 unresolved rows span 22 distinct values: `DENTSU Portugal` (45), `RELEVANT TRAFFIC` (37), `Directo` (25), 12 blanks, `Acomedios`, `MEDIACOM`, `NATEEVO`, `MEDIADIAMOND`, `Gorsky` and others. Some are real agencies missing from the master, some are a country suffix appended to an existing one, and `Directo` is a sales channel typed into an agency field. A further 44 rows worth 177,657 € resolve to a group that has no rebate rate in any year — `DIRECTO`, `DATAPLANNING`, `GORSKY`, `WIRED&LINKED`, `MANIFIESTO` — which under the PO's ruling accrues 0% (§5).

None of this is recoverable by inference, and guessing would put revenue against the wrong holding group and shift its brackets for the whole year. The agency master is therefore a **migration prerequisite**: the 22 unresolved values are reconciled by Operations before the corpus loads, and from then on the agency is a validated reference rather than free text.

### Three ingestion paths, not one

The `Providers` sheet is not a historical curiosity: email is a live intake mechanism. Confirmed by the PO for CTV, whose reports Adform does not expose through the platform and sends by email instead. So the product has to support three routes into the same delivery model, and phase 1 cannot assume the API covers everything:

| Route | Covers | Status |
|---|---|---|
| DSP API | Adform (68% of configured rows) | Built in phase 1; credentials available |
| Manual upload | Everything else, migration, and any API outage | Built in phase 1; today the only route that exists |
| Email intake | CTV, and whatever else the `Providers` sheet still reflects | Phase 2, on top of the manual-upload model |

Email intake is deliberately not in phase 1. It is the same ingestion contract with a different transport, so building the upload path first and adding a mail drop later costs nothing and avoids putting inbox parsing on the critical path of the first release. What phase 1 must not do is model ingestion in a way that assumes an API on the other end.

### The delivery grain

Richer than the campaign file suggests: `Campaign`, `Line Item`, `Línea`, `Banner/Adgroups`, `Banner Size`, `pantalla` (740 distinct — DOOH screens), `Impressions`, `Cost`, `Clicks`, `Measurable Impressions`, `Viewable Impressions for IAB Viewability`, `CuratorMargin`, plus a full date breakdown. Delivery covers 2023–2026 only, which bounds what history can be reported with actuals regardless of how far back the configuration goes.

### The campaign file has no lifecycle

`EstadoCampaña` holds exactly two values, `Activa` (72 rows) and `Inactiva` (2,849). There is no state machine today — no notion of an offer, an OC pending, a campaign closed or invoiced. The states proposed in §6 are new, not a migration of something existing.

`trading` confirms the DSP catalogue is wider than three: `Adform` (1,985), `Equativ` (749 + 47 as `Equative`), `Displayce` (90), `Pubmatic` (20), `DV360` (6), `Revenue`/`RevenueMaker`/`Revenue Maker`/`Pubmatic/RevenueMaker` (13 across four spellings), `Ikreate` (1), `adfomr` (2), and 8 rows with no DSP at all. Adform is 68% of configured rows, which supports the phase 1 cut.

**Neither Excel file contains a single row of actual delivery data.** Everything in them is contracted/planned. Actual impressions and media cost only exist inside the DSPs and inside the daily Excel exports that are filtered and discarded. That is the central gap this product closes.

### Data quality findings (these become migration requirements, not bugs)

1. **DSP is stored in the wrong column.** `trading` holds the DSP (`Adform` 132, `Equative` 22, `Displayce` 10, `Equativ` 3, `adfomr` 2) while the column literally named `DSP` is empty in 162 of 170 rows. The history sheet adds `Pubmatic`, `RevenueMaker`, `DV360`, `Revenue`, `Pubmatic/RevenueMaker` — so the DSP list is longer than the three named, and needs to be a maintained catalogue, not an enum.
2. **Free-text values that must be normalised.** `period` mixes `agosto`/`Agosto`/`agosto_1`; `location` has 12 variants (`Nacional`, `nacional`, `Nacional (Madrid)`, `Internacional `, `Internacional (Francia)`…) while the rebate table only recognises `Nacional` / `Internacional`. Location therefore has to be split into a **rebate-relevant scope** (national/international) and a **descriptive market**.
3. **The agency-to-group join is incomplete.** Of 17 agencies in `Campaigns`, 13 match `Customer.Agencia` and only 6 match a `GRUPO` present in the rebate table. 12 groups in `Customer` (`ADSOCY`, `ALMA MEDIA`, `MANIFIESTO`, `DIRECTO`…) have no rebate row at all. Confirmed by the PO: **a group with no rebate row means 0%**, not an error. The rate is still recorded explicitly as `0%` on the line so the margin stays auditable, and the absence is surfaced in the masters view so Finance can tell "negotiated at zero" from "never loaded".
4. **`CTV` is priced but never used.** The rebate table prices `CTV` for all 22 groups, yet `tipo_plataforma` in `Campaigns` only ever holds `Directo`, `Deal` or `DOOH`. Confirmed by the PO as a channel that starts clean: the taxonomy carries it from day one, and migration imports existing tags as they are — there is no historical CTV inventory hiding under `Directo` or `Deal` to reclassify.
5. **Dead columns.** `KPI`, `frecuencia`, `device`, `temporality`, `activo|inactivo`, `Configurada`, `Check`, `GENERA`, `cpm_especial`, `conf_impressions_*` are empty in 100% of active rows. They are not requirements; they are abandoned intentions. The new model keeps only what is used. The same applies to `providers`, a mislabelled day counter the PO has confirmed is not carried forward.
6. **Duplicated header.** `observaciones` appears twice in `History`.

## 2. Objective

A single system of record for a campaign — from commercial offer to invoiced margin — that pulls its own delivery data from the DSPs instead of asking a person to download it every morning.

Concretely, the product replaces the OneDrive workbook, the manual daily report download, and (in a later phase) the Qlik Sense financial layer, with one application whose three views are the three teams.

### Value proposition per role

| Role | Pain today | What the product gives them |
|---|---|---|
| Business | Offers live in personal spreadsheets; no visibility of whether an offer became an OC or how it performed | Offer register that converts into a campaign in one click, plus read access to the daily status of their own accounts |
| Operations / AdOps | Re-keys the OC, downloads and filters a report per DSP every morning, has no alert when a campaign under-delivers | Campaign entered once, delivery ingested automatically overnight, pacing alerts instead of manual inspection |
| Finance | Margin logic lives inside chart expressions in a Qlik app, keyed on a parsed campaign-name string, with the rebate year chosen by a hardcoded `if` | The same calculation as explicit, tested, versioned rules — rebate resolved by date, platform rate as configurable data, and an auditable month-end snapshot |

### Success metrics (to be agreed with stakeholders)

- Time from receiving an `OC` to a fully configured campaign: target under 10 minutes.
- Active campaigns with automatically ingested D-1 delivery: target 100% for Adform in phase 1.
- Manual effort on the daily status: from a per-DSP download routine to zero.
- Month-end financial close: target reduction to be baselined against the current process.

## 3. Users and roles

Four functional roles — **Business**, **Operations**, **Finance**, **Trading** — plus **Admin**. Operations has global control and Finance is the reviewer. A user may hold several roles; the current team is small enough that this is the normal case rather than the exception.

Access rules assumed for phase 1 (pending confirmation):

- Operations and Finance see all campaigns.
- Business sees all campaigns but cost and margin figures are restricted to Operations, Finance and Admin.
- Trading reads the daily delivery status only, with no cost, revenue, rebate or margin figure.
- No external access for agencies or advertisers.
- Authentication through Microsoft Entra ID, with Cognito kept as a second issuer for development and the end-to-end tests. The provider answers *who is this*; roles live only in the application database, so authorisation stays the application's own responsibility. See [Base Standards §6](./base-standards.md#6-authorization-model).

## 4. Domain model

Derived from the actual workbook and QVD structures rather than invented, and refined by every decision recorded in §8:

```
HoldingGroup (GRUPO)
  ├─ RebateSchedule            ← per group × channel × scope, with validFrom/validTo.
  │    │                         Optionally narrowed to a single agency, which then
  │    │                         overrides its group's schedule (§5.9)
  │    └─ RebateBracket        ← marginal tiers: threshold + rate  (§5.4)
  ├─ RebateAccrual             ← per counter × channel × year: accrued vs settled.
  │                              The counter is the group, except for an agency
  │                              carrying an exception, which accrues on its own
  │                              and is carved out of its group's (§5.4)
  └─ Agency (Agencia)          ← the entity the campaign is invoiced to
Advertiser (brand)
CommercialOffer (OF)                                            ← phase 3
  └─ PurchaseOrder (OC)
       └─ PurchaseOrderVersion ← contracted volume, sale CPM, reason and date (§5.5)
            └─ Campaign
                 └─ CampaignPeriod    ← the monthly grain that exists today
                      └─ CampaignLine ← DSP + channel + format + buy model + rate + volume
                           ├─ DspMapping    ← external campaign / line item id (§7)
                           ├─ AppliedRates  ← rebate rate and platform rate frozen at
                           │                  calculation time, with their provenance
                           └─ DailyDelivery ← impressions, clicks, media cost, measurable
                                              and viewable impressions, banner size,
                                              screen, line format — per line item and day
DspCatalogue                  ← maintained list, not an enum (§1)
IngestionBatch                ← source, route (API / upload / email), file, run log
```

Key modelling decisions:

- **The monthly period is a first-class entity.** It is how the business thinks (`period` = `agosto`), how budgets are committed, how Finance rolls up, and how the Qlik app is organised — two parallel measure sets for a closed month and a running one (§5.1). Flattening it to a date range would lose the way the team works.
- **Contracted volume and delivered volume are separate quantities.** Revenue derives from the first, platform cost from the second, pacing from the ratio, and the credit-note trigger from the gap (§5.5). Conflating them breaks the financial model.
- **The purchase order is versioned, not overwritten.** A campaign that stopped or under-delivered is billed at the lesser of contracted and served, via a revised order or a credit note. Revenue, rebate base and bracket accumulation all read the version in force.
- **The rebate is a bracket schedule, not a rate**, accumulating per holding group *and channel* over the year, attributed chronologically, and settled once in arrears. Accrual and settlement are distinct quantities the system must hold separately. The schedule is normally negotiated with the group, but **an individual agency may carry its own exception**, which overrides its group's schedule for that agency only (§5.9).
- **Applied rates are frozen on the line.** Both the rebate rate and the platform rate are stored at calculation time with the step and source year that produced them (§5.9). A financial figure that silently changes when someone edits a master table is not auditable.
- **`DspMapping` is a real foreign key**, not a parsed string. See §7 — the single highest risk in the project.
- **The channel comes from the configuration**, never from the DSP's `line_format` (§5.10), because it is the accumulation key for the rebate brackets.
- **Rates and volumes live on the line, not the campaign**, because `cpm_estandar` already varies per row (4.375, 5, 25, 31.25 observed).
- **`CuratorMargin` is not modelled as data.** It is `OC revenue − purchase cost` (§5.3), computed on demand for Equativ billing.

## 5. Economic model

Reverse-engineered from the master measures inside `C.C.C. v2.qvf`, which is the authoritative statement of how Finance actually computes today. The Qlik expressions are quoted in §5.6.

**Revenue is booked on contracted volume, not delivered volume.** This is the single most important correction the Qlik app forced on this document: `venta_oc` multiplies `target_impressions_estandar` — the volume on the purchase order — by the sale CPM. Delivered impressions never enter the revenue figure. They drive the platform cost and nothing else.

```
Revenue (closed month)  = contracted_impressions / 1000 × sale_cpm
Media cost              = actual spend reported by the DSP   (Adform's figure is all-in:
                                                              it already includes its
                                                              platform fee, so no separate
                                                              fee line is modelled)
Agency rebate           = Revenue × rebate_rate     (a % of the SALE price, booked as a cost)
Platform cost           = delivered_impressions / 1000 × platform_cpm_rate   (1.00 €, adjustable)

Margin                  = Revenue − Media cost − Agency rebate − Platform cost
Margin %                = Margin / Revenue
```

The platform cost is part of the margin. Confirmed by the PO on 2026-09-14, and it is **the point on which this product's numbers will differ most visibly from the ones Finance reads today** — see §5.2.

### 5.1 In-flight months are pro-rated by elapsed days

Qlik keeps two parallel sets of measures — `venta_oc` / `coste_extraprima` for a closed month, and `venta_mes_actual` / `coste_extraprima_mes_actual` for a month still running — and the app has two corresponding sheets, `COSTES MES CERRADO` and `COSTES MES ACTUAL`. For an in-flight month:

```
elapsed_days  = min(last_delivery_date, period_end) − period_start + 1
period_days   = period_end − period_start + 1
Revenue       = (elapsed_days / period_days) × contracted_impressions / 1000 × sale_cpm
Agency rebate = Revenue × rebate_rate          (same pro-rating applied)
```

Revenue is therefore recognised on **elapsed contract time**, not on delivery. A campaign that delivers nothing still accrues revenue in the current month. That is a deliberate revenue-recognition choice and the product must reproduce it, not "improve" it — but it also means the current-month view is an accrual, not a result, and should be labelled as such.

### 5.2 Confirmed defect: Qlik omits the platform cost from the margin

`coste_infraestructura` exists as a measure — `sum(Impressions)/1000`, with the 1 €/CPM rate hardcoded as the bare division — but the `total` measure subtracts only media cost and rebate:

```
total = venta_oc − coste_compra − coste_extraprima          ← what Qlik reports
```

The platform cost is computed, displayed on its own sheet, and then left out of the margin. With the PO's confirmation that it belongs in the margin, **the margins Finance reads today are overstated**, and the QVDs allow the amount to be stated rather than estimated.

Decoding all 8,511,412 delivery rows gives 1,906,045,002 delivered impressions for 2023–2026, so the omitted platform cost is **1,906,045 €**. Since every platform type follows the same economic model (§5.3), this covers the whole business:

| Concept | € | % of revenue |
|---|---:|---:|
| Revenue (contracted volume × CPM) | 11,902,327 | 100.0% |
| Media cost (DSP) | 2,235,517 | 18.8% |
| Agency rebate | 3,460,499 | 29.1% |
| Platform cost (1 €/CPM delivered) | 1,906,045 | 16.0% |
| **Margin as Qlik reports it** | **6,206,311** | **52.1%** |
| **Margin as defined by the PO** | **4,300,266** | **36.1%** |

**16.0 points of margin across four years.** The platform cost is 85% of the media cost — the second-largest cost line in the business after the agency rebate, and it is missing from the headline figure.

Three caveats on the numbers, none of which change the conclusion. Revenue and rebate come from the configuration QVD while cost and impressions come from the delivery QVD, and the two do not reconcile perfectly (§7), so this is an aggregate estimate rather than a closed ledger. The rebate is resolved with the ladder proposed in §5.9, not with Qlik's current logic, so 29.1% is what the rate *should* be. And the platform cost assumes a flat 1 €/CPM on every delivered impression, which is exactly what the Qlik expression does.

This is the single strongest argument for the project. A margin figure this far from its own definition cannot be fixed by editing a chart expression, because nothing records what the rule was supposed to be.

### 5.3 One economic model for every platform type

Confirmed by the PO. There is no separate model for curation: `Deal` is calculated exactly like `Directo` — revenue from the OC, media cost from the DSP, rebate on the OC sale price, platform cost on delivered impressions. Platform type determines which DSP the campaign runs on, not how it is priced:

| Platform type | DSP | Notes |
|---|---|---|
| `Directo` | Adform | |
| `Deal` | Equativ | GeoQ curates; billed to Equativ via `CuratorMargin` |
| `DOOH` | Displayce, or Adform | |
| `CTV` | *(planned)* | priced in the rebate tables, not yet used on campaigns |

**`CuratorMargin` is a billing field, not an economic one.** It is what GeoQ invoices Equativ — the mechanism by which the money arrives in a curated deal, where the buyer pays the platform rather than GeoQ — and it is gross of the agency rebate, because the rebate is settled separately with the agency in arrears (§5.4). It never enters the margin calculation. The data agrees: it is populated only on `Deal` rows, only on 34–39% of them, and its ratio to OC revenue swings between 28% and 55% year on year. No revenue basis behaves like that.

It still belongs in the model — stored per delivery row, reported, and reconciled against what Equativ actually pays — but as an operational obligation, not an input to profit.

This makes Qlik's `venta_oc_deal = sum(Cost)` and the `if tipo_plataforma = 'Deal'` short-circuit in `total_mes_actual` plainly wrong: they read the cost column as revenue, understating Deal revenue by 2.47 M€ over four years against an OC value of 3,149,770 €. Deal is 7.9 M of the 8.5 M delivery rows, so this is not a rounding error in a corner of the business.

The resulting margin is unremarkable, which is itself the confirmation: 35.6% for Deal against 36.3% for the rest.

#### `CuratorMargin` is derived, not source data

The three `CuratorMargin20XX.xlsx` reports settle this. Each is a per-campaign P&L for Deal inventory — 408 campaigns across 2024–2026 — with columns for served and contracted impressions, cost CPM and OC CPM, purchase cost, rebate rate and amount, and the curator margin itself. Checking the arithmetic row by row:

```
Curator Margin  = OC revenue − purchase cost                      404 / 408 rows
Rebate cost     = OC revenue × rebate rate                        404 / 408 rows
% Margin        = (OC revenue − purchase cost − rebate) / revenue 404 / 408 rows
```

**The curator margin is a calculation, not an input.** GeoQ already holds both of its terms, so the product computes it rather than ingesting it — and the `CuratorMargin` column in the delivery QVD becomes redundant. That also explains why it is populated on only 34–39% of Deal rows: it is a partial copy of a number that lives elsewhere.

The reports independently corroborate the rest of §5.3. Deal OC revenue across them is 3,035,373 € against the 3,149,770 € derived from the configuration QVD (96%), and purchase cost is 676,135 € against 678,920 € from the delivery QVD (100%). Two datasets built by different routes agree to within rounding, which is the strongest confirmation available that Deal revenue is the OC.

**The QVD field holds barely half the real figure:**

| Year | Reports | In the QVD | In the QVD |
|---|---:|---:|---:|
| 2024 | 646,506 | 518,512 | 80% |
| 2025 | 1,265,532 | 449,418 | 36% |
| 2026 | 447,286 | 270,640 | 61% |
| **Total** | **2,359,324** | **1,238,570** | **52%** |

Since revenue and cost reconcile but the copied result does not, nothing is missing from the business — only from the Qlik dataset. Recomputing removes the discrepancy entirely, and the reconciliation against what Equativ actually pays becomes a check on one derived number rather than an audit of millions of delivery rows.

Three things in the reports are worth carrying into the model regardless:

- **The Equativ-facing margin excludes the platform cost.** `% Margin` in these reports is `(revenue − purchase cost − rebate) / revenue`, with no 1 €/CPM line. That is defensible for a billing document, but it means GeoQ's internal margin and its Equativ-facing margin are two different numbers by construction, and the product must not present them as the same figure.
- **Six campaigns carry a negative curator margin** — purchase cost above sale price. `Asisa_jul24` (−114 €), `Cepsa_Lavado_jul24` (−191 €), `Repsol_CCRR_jul24` (−209 €) and three others. Small amounts, but the system should flag a line sold below cost rather than let it average away.
- **The reports bill the full OC even where less was served**, and the PO has ruled that this is wrong: a campaign that stopped early is invoiced at **the lesser of contracted and served**, settled either by a credit note or by a revised OC carrying the volume actually delivered. See §5.5.

### 5.4 The rebate is a tiered annual accrual, settled in arrears

This is the most structurally demanding part of the economic model, and none of it exists in the current tooling.

**It accrues per campaign but is settled once a year.** The rebate is paid to the agency in arrears, normally at year end. Every campaign accrues against that liability; the agency is paid once, against the annual total. The system has to hold both quantities and show the difference — accrued liability per agency, and what was actually settled.

**The rate is tiered, and the tiers are marginal.** Confirmed by the PO. A rate is not a single percentage but a bracket schedule per holding group and channel. **Volume accumulates per channel, not across the agency**: `Directo`, `Deal`, `DOOH` and `CTV` each run their own annual counter, so an agency's DOOH spend never helps it reach a higher `Directo` bracket. One agency can therefore sit in three different brackets at once.

**An agency exception carries its own counter.** Confirmed by the PO (2026-09-21): where an agency has a rebate schedule of its own (§5.9), its volume accrues against **that agency** and is carved out of its group's counter for that channel. The group therefore accumulates less, and its remaining agencies cross brackets later. The accumulation key is `(group, agency | null, channel, year)` — the agency slot filled only where an exception is in force, so the carve-out is per channel rather than global: an agency can run its own counter in `Directo` while still feeding its group's in `DOOH`.

Because attribution is chronological, moving an agency into or out of a counter **restates that whole year** for every agency affected on both sides. It is the same recomputation a schedule change triggers, not a separate case. For example, with brackets of 15% up to 100,000 €, 20% from 100,000 to 500,000 €, and 25% above 500,000 €, an agency with 600,000 € of annual revenue in that channel accrues:

```
  100,000 × 15%  =  15,000
  400,000 × 20%  =  80,000
  100,000 × 25%  =  25,000
                    ───────
                    120,000     effective rate 20.0%
```

Not 600,000 × 25% = 150,000. The brackets apply to the slice, exactly like income tax bands.

**A rate change restates the whole current year.** Also confirmed by the PO. When a rate or a bracket moves in May, everything accrued since January is recomputed at the new schedule. Margins for months already closed and reported will change. This is not an edge case to guard against — it is the defined behaviour, and it means the rebate engine must be able to recompute an entire agency-year on demand, and that reported margins must be versioned so the change is visible rather than silent.

Together these three facts have a consequence worth stating plainly: **campaign-level margin is provisional until the year closes.** The rate applied to a campaign in February depends on volume the agency has not yet delivered. Every margin figure outside a closed year is an estimate, and reports must present it as one.

#### Attribution is chronological

Confirmed by the PO: the year's euros are consumed in order, and each campaign is charged at the bracket its own revenue falls into. The reason is operational rather than theoretical — chronological attribution gives a true picture at any point in the year and minimises month-to-month restatement, because when an agency crosses a threshold only the campaigns from that month onward see the higher marginal rate. Months already closed keep the rate they were accrued at.

This means two different events must behave differently, and conflating them would be a bug:

| Trigger | Behaviour |
|---|---|
| **The bracket schedule changes** (renegotiation) | Restate the whole year to date at the new schedule |
| **Cumulative volume crosses a bracket** | Marginal and forward-only; prior months are untouched |

**A campaign can straddle a boundary.** If an agency stands at 90,000 € and a 30,000 € campaign arrives, 10,000 € of it falls in the 15% bracket and 20,000 € in the 20% — an effective 18.3% for that one campaign. The engine allocates at the slice, not at the campaign, so a campaign's own rate can be a blend.

This is not theoretical. Replaying the 2,884 campaign-months chronologically per group and channel against the PO's example brackets, **36 of them (1.2%) straddle a threshold**:

| Group / channel | Campaign | Cumulative before → after | Effective rate |
|---|---|---:|---:|
| DENTSU / Directo | `EESS_Bolueta` | 98,104 → 100,600 | 16.2% |
| IPG / Directo | `Turismo_Andorra_ES_ene_mar_2026_Vi…` | 95,854 → 100,664 | 15.7% |
| GRUPO HAVAS / Directo | `CRF_Sobres Dorados_mar_2026` | 97,895 → 107,895 | 18.9% |
| GRUPO HAVAS / Directo | `UE_Malaga_abr_jul26_TOP` | 498,245 → 500,720 | 21.5% |
| GROUPM / Directo | `Alcampo_Pso.Direccion_may26` | 99,428 → 104,900 | 19.5% |
| IRISMEDIA / DOOH | `Promperu_Paris_may26` | 95,824 → 119,262 | 19.1% |

**Ordering within a month is sequential.** Confirmed by the PO, on the grounds that the accrual is driven by invoiced money: the total consumed by a month is the same whatever order its campaigns are processed in, so no weighting scheme is needed. That is correct — marginal brackets are order-invariant in aggregate. Any roll-up at agency, channel, month or above is unaffected by the sequence.

The one place it shows is the individual campaign. Two comparable campaigns for the same agency in the same month can carry different rates purely because one was sequenced first, and that difference is real in campaign-level reporting. It is bounded: only the 36 straddling campaign-months (1.2%) are affected at all, and only within the month they straddle. Recorded here so that a campaign-level margin comparison inside a crossing month is read as an artefact of the accrual method rather than a difference in performance.

**The cost of chronological is backdated corrections.** Because each campaign's rate depends on everything accrued before it, any change to an earlier month cascades into every later one. Adding a campaign in September that started in March re-brackets the rest of the year. The discard ruling of §7 is a live example: removing 449,913 € of never-executed revenue lowers cumulative volume for those agencies and can push later campaigns back into a cheaper bracket. The engine must therefore be able to replay an agency-year from scratch, and margins must be versioned so a restatement is visible rather than silent. The PO's argument still holds — this case is rarer than the month-to-month churn that blended attribution would cause — but it is the case that has to work correctly.

#### What the volumes look like

Against real data — annual OC revenue per holding group × channel, 2023–2026 — there are 112 group/channel/year combinations. Using the PO's example brackets:

| Bracket | Combinations |
|---|---:|
| Up to 100,000 € | 82 |
| 100,000 – 500,000 € | 24 |
| Above 500,000 € | 6 |

So roughly 30 combinations a year would sit above the first bracket, where the tiering actually changes the number. The largest, `GRUPO HAVAS / Directo / 2024` at 1,159,752 €, accrues 259,938 € under those brackets — an effective 22.4% — against 289,938 € at a flat 25%. Applied across the whole corpus the difference is 2.24 M€ versus 2.98 M€, which is the order of magnitude at stake in getting the mechanism right rather than approximating it with a single rate.

**Migration note.** None of the rate tables provided carry bracket columns — 2023, 2024 and 2026 all hold exactly one percentage per key. Tiering is therefore a forward-looking requirement, and historical rates migrate as a single bracket covering all volume. The free-text comments in the 2026 file (`"se baja desde el 35% porque no llega a volumen"`) are the manual approximation of what the bracket schedule will do automatically.

### 5.5 Revenue follows the purchase order in force, and the order can be revised

The pro-rating in §5.1 and the full-OC billing in the curator margin reports are not two competing revenue rules. Confirmed by the PO: a campaign that stopped early is invoiced at **the lesser of contracted and served**, and that reduction is made real either by a credit note or by a revised OC stating what was actually delivered. Qlik's elapsed-day pro-rating is an accrual view of an open month; the closing figure is the order in force.

**So the purchase order is a versioned entity, not a static field.** This was raised at the start of the analysis and left unanswered; it is now a confirmed requirement. Each campaign line carries an order version with its contracted volume, its sale CPM, and the reason and date of any revision. Revenue, rebate base and bracket accumulation all read the version in force.

**The scale of the adjustment is not marginal.** Across the 408 Deal campaigns of 2024–2026:

| | € |
|---|---:|
| Revenue at contracted volume | 3,035,373 |
| Revenue at served volume | 2,850,336 |
| **Difference** | **185,037 (6.1%)** |

195 campaigns — 48% of them — served less than contracted. Taking each at the lesser of the two, the aggregate adjustment is 209,781 €, and because the rebate is a percentage of the sale price, it also carries **61,920 € of rebate accrued on revenue that should not have been billed**. The largest single case, `BEYUP_Moeve_D2S_2026`, contracted 50,502 € and served 14,060 € — across its full 26 contracted days, so this is under-delivery rather than an early stop.

Two consequences for the design:

1. **An order revision is a backdated correction**, and under chronological bracket attribution (§5.4) it cascades. Revising a March order in September lowers that agency's cumulative volume and can move every later campaign of that channel into a cheaper bracket. The rebate engine must replay the agency-year, and the margin history must be versioned so the restatement is visible.
2. **The gap has to be detected, not waited for.** Today nothing compares served against contracted at close, which is why 195 campaigns carry the difference silently. Flagging *contracted versus served at period end* is a phase 1 requirement — it is the trigger for the credit note or the revised OC, and without it the correction depends on somebody remembering.

### 5.6 Source expressions

| Measure | Qlik expression (simplified) |
|---|---|
| `venta_oc` | `Sum(target_impressions_estandar) * avg(cpm_estandar) / 1000` |
| `coste_compra` | `sum(Cost)` |
| `coste_extraprima` | `venta_oc * avg(EXTRAPRIMA)` |
| `coste_infraestructura` | `sum(Impressions) / 1000` |
| `total` | `venta_oc − coste_compra − coste_extraprima` |
| `venta_mes_actual` | pro-rated by elapsed days, see §5.1 |
| `venta_oc_deal` | `sum({<line_format={'Deal'}>} Cost)` |

All of them aggregate with `avg(cpm_estandar)` and `avg(EXTRAPRIMA)` inside an `aggr(...)` over campaign × year × month × format. Averaging a rate is safe only while every row in the group carries the same rate; §5.7 is a case where it is not.

### 5.7 Confirmed defect: the scope dimension is silently averaged away

The load script keys the rebate table as `GRUPO & '_' & F2 & '_' & year` — holding group, platform type, year. **The `location` column of the 2026 table is never read.** Both the `Nacional` and `Internacional` rows therefore collapse onto the same key, and because every measure reads the rate through `avg(EXTRAPRIMA)`, Qlik returns the mean of the two.

Today this affects exactly one group, `IKI GROUP / Directo` (20% national, 15% international), which is charged 17.5% in both cases. Across its visible 2026 rows the deviation is around 600 € — small, but the mechanism is wrong rather than imprecise, and it becomes material the moment a second group is priced differently by scope.

**And the field could not be used as a key even if the script read it.** `location` holds 80 distinct free-text values across the 2,921 configured rows. Classifying them against the two buckets the rebate table recognises:

| | Rows | Share |
|---|---:|---:|
| Starts with `Nacional` (incl. `nacional`, `Nacioanal`) | 2,581 | 88.4% |
| Starts with `Internacional` | 260 | 8.9% |
| Unclassifiable | 57 | 2.0% |
| Empty | 23 | 0.8% |

The unclassifiable 57 are values like `UK`, `FRANCIA`, `Francia`, `Portugal`, `Marruecos`, `Rotterdam`, `Montreal (Canada)`, `España_Italia`, `Madrid`, `Sevilla`, `Alcobendas`, `Levante`, `Galicia(CP)`, and one that is a sentence: `IP Galicia + CP Familia en Asturias, León, Palencia y Zamora`. Several of them are unambiguously international campaigns filed under a bare city or country name.

So the scope dimension the 2026 rebate table prices on **does not reliably exist in the data**. The fix is not to parse this field harder: scope becomes an explicit, validated attribute of the campaign line, and the descriptive market text moves to a separate free-text field where it belongs. The new implementation resolves scope explicitly (§5.9) instead of averaging.

The platform rate is configurable at three levels, most specific winning: system default (1.00 €/CPM) → per agency or campaign type → per campaign line. Every override is stored with author and timestamp, because it moves the margin. Today no such rate exists as data at all — the `1` is a hardcoded division in a chart expression.

Both rebate rate and platform rate are **stored on the campaign line at the moment of calculation**, not looked up at read time. A financial figure that changes when someone edits a master table is not auditable.

An agency group with no rebate row is treated as **0%**, confirmed by the PO. The zero is written to the line as an explicit rate so the calculation remains traceable, and the masters view distinguishes a group negotiated at zero from a group whose rate was never loaded.

### 5.8 Worked example

A real closed-month row (`IPROSPECT / BM`, 726,202 contracted impressions at 5.00 € CPM, `Directo`/`Nacional`, DENTSU group → 25%). Media cost and delivered impressions are placeholders, since both only exist in Adform:

| Concept | Amount |
|---|---:|
| Revenue — contracted volume × CPM | 3,631.01 € |
| Media cost (DSP) | 1,200.00 € |
| Agency rebate (25% of revenue) | 907.75 € |
| Platform cost (700,000 delivered × 1 €/CPM) | 700.00 € |
| Margin as Qlik reports it today | 1,523.26 € (42.0%) |
| **Margin as defined by the PO** | **823.26 € (22.7%)** |

19.3 points of margin on this campaign, 16.0 points across the whole 2023–2026 history (§5.2).

### 5.9 Rebate rate resolution

The three yearly tables use three different key schemas (§1) and none of them is complete. They are normalised on import into one table keyed by `group × platform type × scope`, with `valid_from` / `valid_to` and an optional `agency` narrowing, and the rate for a given campaign line is resolved by walking this ladder until a value is found:

**The agency exception comes first.** Confirmed by the PO (2026-09-21): the rebate is normally negotiated with the holding group, but an individual agency inside that group may carry its own schedule, and where one exists it overrides the group's. None of the three tables contains agency-level rows — all three are keyed on `GRUPO` — so every migrated rate loads as a group schedule and exceptions are created in the application from then on.

1. Exact match on `agency + platform type + scope`, in the table in force on the delivery date.
2. Same table, `agency + platform type`, any scope.
3. Same table, `agency` alone.
4. `group + platform type + scope` — the normal case, and the key schema of the 2026 table.
5. Same table, `group + platform type`, any scope — this is how 2023 and 2024 rows, which have no scope dimension, apply to both national and international campaigns.
6. Same table, `group` alone — this is how 2023 rows, which have no platform dimension, apply to every platform type.
7. The most recent earlier table, restarting at step 1. This implements the PO's carry-forward rule: **a year with no table inherits the previous year's rates**, so 2025 (1,042 rows, the largest single year in the corpus) is priced with the 2024 table. The same step also covers combinations missing from an otherwise present table, such as `IKI GROUP / Directo` in 2024.

   The Qlik script already does exactly this for 2025, and hardcodes it: it loads `extraprimas 2024.xlsx` under the literal year label `'2025'`. What it does *not* do is generalise — the year is chosen by `if(date_imp >= '1/1/2026', '2026', '2025')`, a two-way branch that prices every delivery before 2026, including 2022 and 2023, with the 2024 table. The 2023 table is not loaded at all. Replacing that branch with a proper `valid_from`/`valid_to` lookup is a correctness fix, not a refactor.
8. **0%**, recorded explicitly with its reason.

Every resolution records which step produced the rate, which source year it came from, and **whether it came from an agency exception or from the group schedule**. A rate obtained at step 7 or 8 is an inherited or defaulted figure, not a negotiated one, and reports must be able to distinguish the two — otherwise nobody can tell a genuine 0% rebate from a hole in the data. The agency flag matters for the same reason: a 25% negotiated with one agency and a 25% inherited from its group are the same number with different authority behind it.

**An exception moves the accrual counter too, not just the rate.** An agency resolved at steps 1–3 accrues against its own counter and is carved out of its group's for that channel (§5.4). Resolution and accumulation therefore stay in step: the schedule that priced the line is the counter the line accrues against.

### 5.10 The channel is authoritative from the configuration, never from the DSP

Two fields carry the same `Deal` value and Qlik uses them interchangeably: `tipo_plataforma`, typed by Operations from the purchase order, and `line_format`, arriving in the DSP delivery report. `venta_oc_deal` filters on `line_format`; `total_mes_actual` branches on `tipo_plataforma`.

Confirmed by the PO: **`tipo_plataforma` is authoritative**. The DSP's `line_format` can be produced by configuration GeoQ does not control, so it must not influence any calculation.

This matters more under the tiered rebate than it did before. The channel is the accumulation key for the brackets (§5.4), so a campaign attributed to the wrong channel does not merely mislabel itself — its revenue accrues against the wrong annual counter and shifts the bracket of every later campaign that agency runs in both channels. A single misclassification propagates forward through the year.

`line_format` is still ingested and stored, as a contrast value. Where it disagrees with the configured channel the row is flagged for review, never silently reclassified — the same treatment as any other unmatched key (§7).

## 6. Scope

### Phase 1 — MVP, Adform only

1. **Masters**: holding group / agency / billing entity, advertiser, DSP catalogue, sales rep, sector, campaign type, format, platform type. Seeded by importing `campaigns.xlsx` and `extraprimas 2026.xlsx`.
2. **Campaign registration from an OC**: campaign header, monthly periods, and lines with DSP, buy model, contracted volume and sale CPM. `OF` and `OC` references captured as first-class fields (populated in 122 and 101 of 170 current rows respectively).
3. **Adform mapping and ingestion**: external id per line, validated against the Adform API on save; nightly D-1 ingestion of impressions, clicks and spend per line and day; rolling 7-day reprocessing window because DSPs restate figures; per-run execution log.
4. **Manual fallback**: upload of the same Excel export used today, through the same mapping. Non-negotiable, and now known to be more than a safety net: this manual path is the *only* ingestion that exists today (§1), so it is also the migration route for the 8.5 M historical delivery rows and the bridge for every DSP that phase 1 does not connect. Each upload records its source file and batch, replacing the hand-typed `origen` labels with something traceable.
5. **Daily status**: active campaigns with delivered vs. contracted volume, pacing against expected-to-date, days remaining, and flags for *active campaign with no data received* and *pacing deviation beyond ±10%*.
6. **Margin and roll-ups**: per-campaign economics as specified in §5 — closed-month and running-month variants, rebate resolved by date, platform rate as configurable data — aggregated by period, agency, advertiser and campaign type, with Excel/CSV export. Runs alongside Qlik Sense; it does not replace it yet.

   **Acceptance is explained divergence from Qlik, not parity.** Parity is no longer the target: §5.2 establishes that the new margin will be roughly 16 points lower than the one Finance reads today, and Deal revenue will more than quadruple, by design. So phase 1 recomputes a set of closed months, reconciles line by line against the app, and requires every difference to land in one of two buckets — a known, quantified defect (§5.2 platform cost, §5.7 scope averaging, §5.9 rebate year selection) or a bug in the new implementation. Nothing is waved through as "close enough".

   This makes the rollout a communications problem as much as a technical one. Margins will appear to fall sharply the day the new figures are published, and the reason must be documented and socialised with Finance and Business **before** they see it, not after.
7. **History migration**: 2023-01-01 onwards — 2,921 configured campaign-months across 2023–2026 — loaded read-only and reportable alongside current campaigns. Confirmed as a phase 1 requirement, not a later nice-to-have, because Finance needs year-on-year comparison from launch.

   **The corpus starts on 2023-01-01.** Confirmed by the PO: 2022 is discarded, not migrated. It is 160 rows and 103 campaigns between 2022-03-28 and 2022-12-29, worth 1,010,990 € of contracted revenue, concentrated in HAVAS (86 rows) and T2O (25). There is no 2022 rebate table and the carry-forward rule has no earlier year to draw from, so any margin for that year would have been invented — and with brackets now in the model (§5.4), even a recovered flat rate would only approximate it.

   The cut-off costs nothing in continuity: the configuration QVD that Qlik actually reads already contains only 2023–2026, so 2022 has been outside the live system for some time. Discarding it aligns the new corpus with the one in use rather than reaching further back than the current tooling does.

   One consequence the team should expect regardless: historical rows carry only contracted volumes, never actual delivery (§1). Historical margin is therefore a *planned* margin and must be labelled as such in every report, or Finance will unknowingly compare it against the actual margins the system starts producing from phase 1 onwards.

### Phase 2

Equativ and Displayce connectors (the Adform connector defines the contract); immutable month-end snapshot; email/Teams alerting; rebate-rate versioning UI for Finance.

### Phase 3

Commercial offer management for Business, rate card master, and automatic `OF` → `OC` → campaign conversion with margin-threshold approval. The offer model does not need inventing: `Estatus Agencias BEYUP.xlsx`, wired into an earlier version of the Qlik app, already defines the fields and the `OFERTA` → `GANADA` funnel (§1).

### Phase 4

Retirement of Qlik Sense: native financial dashboards, roll-ups by sales rep and sector, ERP/invoicing integration.

### Explicitly out of scope

- Campaign creation or trafficking in the DSPs (excluded by the PO).
- Reconciliation against the advertiser's own ad server (CM360, Sizmek).
- Make-goods, under-delivery compensation, invoicing and ERP posting.
- Any external portal for agencies or advertisers.
- Multi-tenant operation — this is an internal GeoQ system.
- Multi-currency. Everything is EUR and billed from Spain today (§8). Amounts are stored with an explicit currency so the assumption is visible, but no conversion, rate table or conversion-date rule is built — despite campaigns running in France, Portugal, the UK, Italy, Mexico, Colombia, Canada and Morocco.
- GeoQ's proprietary audience data as an analytical source; the product consumes DSP delivery only.

## 7. Principal risk

**Name matching between GeoQ and the DSP** — and the Qlik app confirms this is not a hypothetical risk but the current production mechanism.

The join key between configuration and delivery is `campaign_month_year_tipo_plataforma`, a single string, and the load script extracts the platform type from it positionally: `SubField(campaign_month_year_tipo_plataforma, '*', 6)` — the sixth `*`-delimited token. **The entire financial model therefore hangs on a naming convention encoded in a delimited string**, with no referential integrity of any kind. The script also carries hardcoded patches around it: a special case for names starting with `Octopus`, and two campaigns excluded by literal name (`ADSERVER_REDIRECTS`, `DIA_PWEEKS_AO_2026_PW10`).

Rename a campaign, insert a token, or drop a separator, and a campaign silently stops contributing to revenue — no error, just a smaller number.

**The QVDs let this be measured rather than argued.** Comparing the key sets on both sides:

| | Keys | Share |
|---|---:|---:|
| Configured campaign-months | 2,711 | |
| Delivery campaign-months | 2,620 | |
| Delivery with **no configuration** | 87 | 3.3% of delivery |
| Configured with **no delivery at all** | 178 | 6.6% of configuration |

Restricting to periods that have already ended — so that future 2026 campaigns are not counted as missing — **136 finished campaign-months worth 449,913 € of contracted revenue have zero delivery rows**, against 11.34 M€ of contracted revenue for 2023–2026.

**Cross-referencing the largest of them against the orphans on the other side identifies the dominant cause: granularity mismatch in the campaign name.** The two sides describe the same campaign at different levels of detail, so neither finds the other:

| Configured, no delivery | Delivered, no configuration |
|---|---|
| `CCVV_Montreal_sep_2025_mupi`, `…_billboard` (31,593 € + 31,004 €) | `CCVV_Montreal_sep_2025` — one key, no format suffix |
| `Telefonica_ESIM_2a_JUN_AGO26_VIDEO_ESP` × 2 months (22,290 €) | 23 orphan keys: `…_OOH_ESP_VIOOH`, `…_OOH_ESP_Perion`, `…_OOH_DE_Viooh`, `…_VIDEO_AR`, `…_OOH_LATAM` |
| `Promperu_Londres_May26`, `…_Paris_jun26`, `…_Lyon_jun26`, `…_Madrid_Jun26`, `…_Barcelona_Jun26` (82,700 €) | `Promperu_FOTOS_MAD_ROBERTO`, `Promperu_WOW_may_sept26_Londres` |

GeoQ splits a campaign by format or city in the configuration; the DSP reports it as one line, or split a different way. The campaign delivered perfectly well — the string simply does not match.

The exception is instructive: `Repsol_EESS_PlanazoX2_abr_2025_DTS (no válido)` (25,052 €) has no orphan counterpart. Its name says what it is — a cancelled order left in the configuration file, inflating contracted revenue and, since the rebate is a percentage of that revenue (§5), accruing a rebate the agency was never owed.

**The DSP field predicts the failure.** Grouping unmatched rows by the `trading` value shows that misspellings are near-perfect predictors of an orphan row:

| DSP value | Rows | No delivery | |
|---|---:|---:|---:|
| `Adform` | 1,985 | 86 | 4% |
| `Equativ` | 749 | 40 | 5% |
| `Displayce` | 90 | 15 | 17% |
| `Equative` *(typo)* | 47 | 20 | 43% |
| `Pubmatic` | 20 | 12 | 60% |
| `adfomr`, `RevenueMaker`, `Pubmatic/RevenueMaker`, `Ikreate` *(variants)* | 8 | 8 | 100% |

Every row whose DSP is misspelled is also a row whose campaign name failed to match. Careless entry in one free-text field travels with careless entry in the other — which is the argument for validated references over typed strings, made by the data rather than by assertion.

Making this distinction visible is, on its own, a strong justification for phase 1: today a mismatched name and an undelivered campaign look identical, and one of them is a commercial problem while the other is a typo.

**PO ruling (2026-09-15): these campaign-months did not execute and are discarded.** That becomes a migration rule — the 136 rows are excluded from the corpus rather than imported and flagged. Two consequences follow, and both are requirements rather than observations.

*The rebate accrued on them has to be reversed.* Because the rebate is a percentage of the OC sale price (§5), 449,913 € of contracted revenue that never executed carried **111,572 € of accrued rebate** — 24.8% on average — spread across the agency groups that would have been paid it at year end:

| Holding group | Revenue withdrawn | Rebate reversed |
|---|---:|---:|
| GRUPO HAVAS | 138,055 | 53,387 |
| GROUPM | 53,308 | 18,658 |
| IRISMEDIA | 89,062 | 13,359 |
| IPG | 43,113 | 13,283 |
| DENTSU | 30,977 | 8,289 |
| Others | 95,398 | 4,596 |
| **Total** | **449,913** | **111,572** |

Whether any of it was actually settled is a question for Finance, but the migration must not carry the accrual forward silently.

*The delivery on the other side does not disappear with them.* The orphan keys belonging to these same campaign families still hold real delivery — 13.7 M impressions and 27,623 € of media cost, of which Telefónica alone is 12.7 M impressions and 27,621 €. Discarding the configuration rows removes the revenue but leaves that cost unattributed. Either it belongs to a campaign that does exist under a different name, or it is delivery GeoQ paid for against no order at all. The product has to surface both sides of the mismatch, not just the side that shows up as missing revenue.

This is the general requirement: **an unmatched key is an exception to be worked, on either side of the join.** Delivery with no campaign is as much a finding as a campaign with no delivery, and today neither is visible.

**In aggregate, delivery matches contract.** Aggregating both QVDs by year:

| Year | Contracted impressions | Delivered | Ratio |
|---|---:|---:|---:|
| 2023 | 166,002,265 | 161,432,904 | 97% |
| 2024 | 596,548,224 | 589,905,966 | 99% |
| 2025 | 694,722,621 | 704,491,453 | 101% |
| 2026 *(partly in flight)* | 489,457,725 | 450,214,679 | 92% |
| **Total** | **1,946,730,835** | **1,906,045,002** | **98%** |

There is no systemic under-delivery to explain, which makes the 126 empty campaign-months below stand out more sharply rather than less: the aggregate is healthy precisely because most campaigns deliver what they sold, so the ones contributing nothing are anomalies, not the tail of a broad shortfall.

The 87 orphans on the other side are cost without revenue. They skew international and DOOH — `Telefonica_ESIM_2a_JUN_AGO26_OOH_LATAM`, `…_VIDEO_UK`, `Orange_Fútbol_audio_ene_feb_2024` with an `Audio` format that exists in no configuration — which suggests the gap widens exactly where the taxonomy is least settled.

Mitigation: replace the parsed string with a real foreign key. Require the Adform id on the line at registration time (roughly 30 seconds per line), validate it against the API immediately, and treat *active line with no mapping* as a blocking status rather than a warning. Fuzzy name matching is offered only as a suggestion during data entry, never as the binding link. Exclusions and special cases become flagged data, not script literals.

Secondary risk: ingestion currently depends on report emails for some providers (`Providers` sheet), a mechanism that will not survive into the new system.

## 8. Open questions

Ordered by how much they move the numbers.


*None outstanding.* New ones will appear as the OpenSpec change is written — this section is the place for them.

### Resolved

- **The purchase order prevails over the commercial offer.** Where the two disagree — volume, CPM — the campaign is created from the `OC` and the deviation against the offer is recorded as informational. It does not block registration; the offer remains the commercial antecedent. *(PO, 2026-09-21)*
- **An active campaign is flagged `no data received` as soon as D-1 is missing**, checked after the nightly ingestion. The tighter threshold is deliberate: a DSP running late produces a flag that clears itself the next night, whereas a wider window hides a real outage for a day. *(PO, 2026-09-21)*
- An agency carrying a rebate exception accrues volume on its own counter and is carved out of its group's, per channel. The accumulation key is `(group, agency | null, channel, year)`. *(PO, 2026-09-21)*
- The rebate is normally negotiated with the holding group, but an individual agency within a group may carry its own exception, which overrides the group's schedule for that agency only. No such rows exist in the 2023, 2024 or 2026 tables, so exceptions are created in the application rather than migrated. *(PO, 2026-09-21)*
- Authentication is Microsoft Entra ID, with Cognito kept for development and the end-to-end tests. Roles stay in the application database. *(PO, 2026-11-12; supersedes the 2026-09-21 decision that chose Cognito)*
- Operations has global control and sees the margin; Finance is the reviewer and no longer writes rebate schedules or platform rates. Trading is a new role that reads the delivery status only. *(PO, 2026-11-12)*

- The 136 finished campaign-months with no delivery did not execute and are discarded on migration; their 111,572 € of accrued rebate is reversed. *(PO, 2026-09-15)*
- A rate change restates the whole current year; a volume-driven bracket crossing is marginal and forward-only. *(PO, 2026-09-17)*
- A campaign that stopped or under-delivered is invoiced at the lesser of contracted and served, via credit note or revised OC. The purchase order is therefore versioned. *(PO, 2026-09-17)*
- `CuratorMargin` = OC revenue − purchase cost, verified on 404 of 408 campaigns in the 2024–2026 reports. It is computed, not ingested. *(Evidence: `CuratorMargin2024/2025/2026.xlsx`, 2026-09-17)*
- Everything is EUR and billed from Spain **for now**. No currency conversion is built, but amounts carry an explicit currency so that adding one later is not a migration. *(PO, 2026-09-21)*
- The campaign is invoiced to the agency, which belongs to a holding group. `RECLAM` is not the billing entity. *(PO, 2026-09-21)*
- The channel comes from `tipo_plataforma` in the configuration. The DSP's `line_format` is contrast data only and never feeds a calculation. *(PO, 2026-09-17)*
- Bracket volume accumulates per channel; each channel has its own annual counter. *(PO, 2026-09-17)*
- Tiered rebate is attributed chronologically, not blended across the year; sequential order within a month is sufficient, since the monthly total is order-invariant. *(PO, 2026-09-17)*
- The rebate is tiered with marginal brackets per holding group and channel. *(PO, 2026-09-17)*
- The platform cost is part of the margin: `margin = (revenue − media cost − rebate − platform cost) / revenue`. Qlik omits it today, overstating margin by 16.0 points over 2023–2026. *(PO, 2026-09-14)*
- Every platform type uses the same economic model. `Deal` is priced like `Directo`; `CuratorMargin` only exists to bill Equativ and never enters the margin. *(PO, 2026-09-15)*
- The rebate is always a percentage of the OC sale price, for Deal as for everything else. *(PO, 2026-09-15)*
- Platform type maps to DSP: `Directo` → Adform, `Deal` → Equativ, `DOOH` → Displayce or Adform. `CuratorMargin` is the Deal revenue line, invoiced to Equativ, and exists only for Deal rows. *(PO, 2026-09-15; confirmed against all 8.5 M delivery rows.)*
- Historical rebate tables provided for 2023, 2024 and 2026; a year with no table inherits the previous year's rates. *(PO, 2026-09-14)*
- Adform's reported cost is all-in and already includes its platform fee — no separate fee line. *(PO, 2026-09-14)*
- An agency group with no rebate row is 0%, not a blocking error. *(PO, 2026-09-14)*
- The `providers` column is dropped, not migrated. *(PO, 2026-09-14)*
- CTV is a channel in its own right, starts clean from now on with no retroactive re-tagging, and its reports arrive by email rather than through the Adform platform. *(PO, 2026-09-14, extended 2026-09-17)*
- History is migrated from 2023-01-01. 2022 is discarded: no rebate table exists for it and the live system already excludes it. *(PO, 2026-09-14, amended 2026-09-17)*
- There is no upstream ETL and no DSP API in use: delivery is 1,999 manually downloaded spreadsheets concatenated by the Qlik load script. *(Evidence: `origen` and `file` fields in `Campaigns_all_1.qvd`.)*
