# Feature Spec: Client Data Model

> Spec 01 of 15 · Slug: `client-data-model` · Status: Draft for build
> Data profiled on 2026-10-01 from `structured_data/merchant_profiles_v3.csv` and `structured_data/pos_daily_acquiring_v3.csv`. Every number in this spec comes from that profiling, not from assumption.

## 1. Purpose

This feature defines the foundation every other RM Co-pilot feature reads from. It does four things:

1. Ingests the two real data sources (merchant profiles and POS daily acquiring) into a typed, validated relational store.
2. Fixes the vocabulary for a **client** (one merchant, keyed by `merchant_id`).
3. Computes a small set of **base facts** (plain aggregates such as 30-day volume, card-type share and limit utilisation) so scoring, analytics, recommendations and both co-pilots all use identical numbers.
4. Provides a **client-scoped data access layer**, so the Merchant Co-pilot's "one client only" rule is enforced by the code that reads the data, not by a prompt.

It deliberately does **not** score, rank, suggest rates or recommend products. Those belong to Specs 02, 05 and 06. If the data model is wrong, every downstream number is wrong, so this spec comes first.

## 2. User Goal

The RM never touches this layer directly. The outcome is that every figure the RM sees (a volume, a utilisation %, a card-mix share, a "data as of" date) is correct, reproducible, and identical across the dashboard, the profile, the analytics screen and both co-pilots.

The developer should be able to run one ingest command and get a populated database with a clear data-quality report. They should be able to call one function to get a single client's full record.

## 3. Business Context

- **Workflow position.** This is the `MONITOR PORTFOLIO` input. Nothing in the Core Workflow works without a trustworthy client record.
- **Proactive intelligence.** The signals the pitch depends on (declining volume, limit pressure, idle balances, dormant terminals, onboarding gaps) are all functions of these two tables. This spec defines the base facts those signals are built from.
- **Hackathon pitch.** A live demo cannot show a wrong number. Deterministic, pre-computed base facts keep the numbers on screen identical to the numbers the co-pilot quotes.
- **Co-pilot boundary.** The system design requires the Merchant Co-pilot to be unable to answer about other clients. That is only credible if the data layer cannot return other clients' rows in that mode (FR-011).
- **Data integrity.** All data is synthetic (`synthetic_credit_score` is named as such in the source). This spec makes the labelling a requirement, not a convention (FR-014).

### What the data actually contains (profiled)

| Source | Shape | Grain / key |
|---|---|---|
| Merchant profiles | 150 rows × 19 columns, no nulls | one row per `merchant_id` (`MER2001`–`MER2150`, unique) |
| POS daily acquiring | 36,000 rows × 6 columns, no nulls | one row per `(merchant_id, date)`, 150 × 240 days, no duplicate keys, no orphans either way |

- **POS window:** 2025-12-07 to 2026-08-03 (240 consecutive days). The "as of" date for the product is **2026-08-03**, the last POS date, and not the wall-clock date (today is 2026-10-01).
- **Dormant terminals:** 128 rows (`terminal_status = Dormant`) across 10 clients. Every one has `volume = 0` and `transaction_count = 0`, and in every case the dormancy run is a **trailing run ending on 2026-08-03** (6–24 days). So these 10 clients are dormant *right now*. This is a planted, demo-able signal.
- **`card_type`** takes the values `Mass`, `Premium`, `Super Premium`. It is a **per-day label**, with exactly one value per client per day. It is not a per-transaction split. Every client has all three labels over the window.
- **Calendar months in the POS window:** Dec 2025 (from the 7th) and Aug 2026 (only 3 days) are partial. **Feb–Jul 2026 are the six complete months.**
- **Consistency of the two sources:** POS monthly volume divided by `avg_monthly_turnover_aed` ranges 0.56–1.13 (median 1.00). POS monthly volume divided by `monthly_pos_limit_aed` ranges 0.35–0.78 (median 0.60). No daily row exceeds `daily_pos_limit_aed`.

## 4. Scope

### In Scope

- Project data folder convention and configuration for the source CSV location.
- SQLAlchemy models and a SQLite database (Postgres-compatible: no SQLite-only types or functions in model code).
- An idempotent ingest pipeline: CSV → validate → load → compute base facts → data-quality report.
- Base-fact computation (Section 7.3).
- A client-scoped repository/service layer with a hard single-client mode.
- Read-only FastAPI endpoints exposing the base record (FR-012).
- Matching TypeScript types for the frontend.
- Automated tests for validation, windowing and scope isolation.

### Out of Scope

- Opportunity/risk scoring, ranking, flags and one-line reasons (Spec 02).
- Any screen layout beyond the data-status indicator (Specs 02–04, 11).
- Rate, lending and NTB logic (Specs 05–06).
- Any LLM call or retrieval-context assembly (Specs 08–09, 12). This spec only guarantees the scoped data they will read.
- Authentication, RM login or multi-tenant permissions.
- Live bank integrations, real-time/streaming POS, or editing client data through the UI.
- Individual transactions, individual cards or per-terminal data. None of these exist in the sources.

## 5. Functional Requirements

### FR-001 — Source location and configuration
- **Input:** environment variables `MERCHANT_CSV_PATH` and `POS_CSV_PATH`. Defaults point at `structured_data/merchant_profiles_v3.csv` and `structured_data/pos_daily_acquiring_v3.csv`. `DATABASE_URL` defaults to a local SQLite file, `backend/rm_copilot.db`.
- **Behavior:** source CSVs are treated as read-only. The ingest never writes to `structured_data/`.
- **Failure:** a missing or unreadable file aborts ingest with a message naming the path. The existing database is left untouched.

### FR-002 — Structural validation (abort-level)
- **Check:** each file's header must contain every required column from Section 7.1 and 7.2. Extra columns are kept in a log warning and ignored. Missing columns abort the ingest.
- **Failure:** abort with a list of the missing columns. No partial load.

### FR-003 — Row validation and quarantine
Rows failing a rule below are **quarantined** (excluded from the load and listed in the data-quality report with file, row number, field and reason). The ingest continues. The rules:

**Merchant rows**
- `merchant_id` matches `^MER\d{4}$` and is unique (a duplicate quarantines every row after the first).
- `rm_id` matches `^RM\d{3}$`. `branch_id` matches `^BR\d{3}$`.
- `risk_segment` is one of `Low | Medium | High`.
- `vat_registered` is boolean (`True`/`False`).
- `relationship_start_date` is a valid ISO date.
- `account_balance_aed`, `avg_monthly_turnover_aed`, `monthly_pos_limit_aed` and `daily_pos_limit_aed` are numbers ≥ 0.
- `num_pos_terminals` is an integer ≥ 1.
- `synthetic_credit_score` is an integer in 300–900 (observed range is 354–899).

**POS rows**
- `merchant_id` exists in the loaded merchants. An orphan row is quarantined.
- `date` is a valid ISO date. `(merchant_id, date)` is unique.
- `terminal_status` is one of `Active | Dormant`. `card_type` is one of `Mass | Premium | Super Premium`.
- `daily_acquiring_volume_aed` ≥ 0 and `transaction_count` ≥ 0 (integer).
- If `terminal_status = Dormant`, volume and count must both be 0. This holds for all 128 current dormant rows.

A merchant with zero valid POS rows is still loaded and flagged `has_pos_data = false`. Downstream specs must handle this (Section 8 states).

### FR-004 — Soft consistency checks (warn-level, never quarantine)
These are logged in the data-quality report because they reflect real quirks in the data. They must **not** be "fixed" silently.

| Check | Observed today |
|---|---|
| Client has POS rows dated before `relationship_start_date` | **14 clients** have `relationship_start_date` after 2025-12-07 (the POS window start) yet have POS data from day 1 |
| Two clients share a `business_name` | `Johnson Technologies` (MER2077, MER2091), `Hardy Style Co` (MER2108, MER2131) |
| `daily_pos_limit_aed × 30` differs from `monthly_pos_limit_aed` | ratio ranges 1.88–3.09; the two limits are independent and must not be derived from each other |
| `risk_segment` not monotonic with `synthetic_credit_score` | `Low` spans 354–897, `High` spans 387–813 |
| Any POS daily volume exceeds `daily_pos_limit_aed` | 0 rows today |
| Source row count differs from the previous ingest | none yet |

### FR-005 — Persistence and idempotency
- **Behavior:** the ingest runs inside a single transaction and replaces the previous contents (truncate-and-load, or load to staging and swap). Running it twice on the same files produces identical tables and identical base facts.
- **Failure:** any exception rolls back. The previously loaded data remains queryable.
- **Output:** a record in `ingest_run` (timestamp, source file names, SHA-256 of each file, row counts loaded/quarantined, warnings count, status).

### FR-006 — Time anchoring
- `as_of_date = max(pos_daily.date)` for the loaded data, stored in `ingest_run` and returned by the API.
- Nothing in the backend may call the wall clock (`date.today()`, `now()`) to decide what "recent" means. All windows are relative to `as_of_date`. Rationale: the data ends 2026-08-03 and a demo run in October must still show "last 30 days" correctly.
- Windows (all inclusive, calendar-day based):
  - `t30` = `as_of_date − 29` to `as_of_date` (currently 2026-07-05 → 2026-08-03).
  - `p30` (prior 30) = `as_of_date − 59` to `as_of_date − 30` (currently 2026-06-05 → 2026-07-04).
  - `m6` = the six most recent **complete calendar months** ending before the `as_of_date` month if that month is incomplete (currently Feb–Jul 2026). A month is complete when the data covers every day of it.

### FR-007 — Base facts per client
After load, compute and persist one `client_fact` row per client (field definitions in Section 7.3). Rules:
- All facts are pure aggregates or ratios of sourced fields. No thresholds, no labels such as "declining" or "at risk" (those are Spec 02).
- A ratio with a zero or missing denominator is stored as `NULL`, never `0` and never `inf`.
- Money is rounded to 2 decimals and ratios to 4 decimals at persistence. Percentages are not stored (the UI formats them).

### FR-008 — Monthly volume series
Persist one `client_monthly_volume` row per client per calendar month present in the POS data (9 months: Dec 2025–Aug 2026), with an `is_complete` flag. The 6-month chart in Spec 04 reads the six rows where `is_complete = true` and takes the latest six. The partial months must never be shown as if they were full months.

### FR-009 — Card-type mix
Persist `client_card_mix` rows per client × window (`t30`, `m6`) × `card_type`:
- `volume_aed`, `volume_share` (of that window's total, `NULL` if the window total is 0), `active_days`, `day_share`.
- Because `card_type` is a per-day label, "card mix" means *the share of the client's volume (or days) that fell on days labelled Mass / Premium / Super Premium*. It is not a transaction-level split, and UI copy must not claim otherwise (see Open Question 3).
- Dormant days have 0 volume and are excluded from `active_days` and `day_share`.

### FR-010 — Dormancy facts
For each client compute `dormant_days_t30`, `is_dormant_now` (the status on `as_of_date` is `Dormant`) and `dormant_streak_days` (consecutive trailing dormant days ending at `as_of_date`, 0 if active on `as_of_date`). Today: 10 clients are `is_dormant_now`, with streaks of 6–24 days.

### FR-011 — Client-scoped data access (hard boundary)
Implement a repository layer with exactly two access modes:

- **`PortfolioReader`** can list and filter all clients and read their facts.
- **`ClientReader(merchant_id)`** is constructed with one id and every method on it filters on that id inside the query. It exposes **no** method that accepts a different `merchant_id` or returns a list of clients.

Rules:
- The Merchant Co-pilot (Spec 09) must obtain its context only through a `ClientReader`. A request for an unknown `merchant_id` raises `ClientNotFound`. It must not fall back to a fuzzy match or to the portfolio reader.
- Unit tests prove that a `ClientReader("MER2001")` can never return a row where `merchant_id != "MER2001"`, including via any filter, join or sort argument (tests must try to pass hostile arguments).

### FR-012 — Read-only API
| Endpoint | Returns |
|---|---|
| `GET /api/clients` | Unranked list: id, business name, industry, city, `package`, `risk_segment`, `rm_id`, `is_dormant_now`. Supports `q` (name/id substring, case-insensitive), `industry`, `city`, `rm_id`, `limit`, `offset`. |
| `GET /api/clients/{merchant_id}` | Full profile (7.1) + base facts (7.3). 404 with `{"code":"client_not_found"}` for an unknown id. |
| `GET /api/clients/{merchant_id}/daily?from&to` | Daily POS rows (7.2) inside the window. Default is `t30`. Maximum span is 240 days. |
| `GET /api/clients/{merchant_id}/monthly` | `client_monthly_volume` rows (FR-008). |
| `GET /api/clients/{merchant_id}/card-mix?window=t30\|m6` | `client_card_mix` rows (FR-009). |
| `GET /api/data/status` | `as_of_date`, window dates, row counts, quarantined count, warnings, last ingest time, `synthetic: true`. |

Responses use `snake_case` JSON, ISO dates and plain numbers (AED, no currency symbol in the payload). Ranking and sorting beyond the default (`business_name`, then `merchant_id`) belong to Spec 02.

### FR-013 — Frontend types
Provide TypeScript interfaces mirroring the API payloads (`Client`, `ClientFacts`, `PosDay`, `MonthlyVolume`, `CardMix`, `DataStatus`) in one shared module. Nullable facts are typed `number | null` so the UI is forced to handle them.

### FR-014 — Synthetic-data labelling
- `GET /api/data/status` always returns `synthetic: true` and a `disclaimer` string. The text is fixed by this spec: "Synthetic demonstration data. Not real customer, bureau or compliance data."
- The API field for the score is exposed as `synthetic_credit_score` (never `credit_score` or `bureau_score`). UI copy labels it "Synthetic score".
- The data layer contains no real bank product names, fee schedules or rate cards. If Specs 05–06 need any, they must cite a real public source (Open Question 2).

### FR-015 — Data-quality report
Ingest writes `data_quality_report.json` (and prints a summary): counts, quarantined rows with reasons, and every FR-004 warning with the affected ids. A clean run on the current files is expected to show **0 quarantined rows** and **4 warning types** (the 14-client pre-relationship POS, the 2 duplicate names, the limit-ratio spread, the score/segment non-monotonicity). If the count differs, the ingest is not considered correct.

## 6. User Flow

The RM never sees this layer. The developer flow and the flow of data to the RM are:

```text
Developer sets MERCHANT_CSV_PATH / POS_CSV_PATH / DATABASE_URL
      ↓
Runs ingest command
      ↓
Structural check (FR-002) ── fail ──► abort, DB unchanged
      ↓
Row validation (FR-003) ── bad rows ──► quarantined + reported
      ↓
Load in one transaction (FR-005)
      ↓
Compute as_of_date, windows, base facts, monthly, card mix, dormancy (FR-006…010)
      ↓
Write ingest_run + data_quality_report.json (FR-015)
      ↓
Backend starts ──► GET /api/data/status shows as_of 2026-08-03, synthetic: true
      ↓
RM opens dashboard (Spec 02)  ◄── reads PortfolioReader / client_fact
      ↓
RM opens a client / merchant co-pilot ◄── reads ClientReader(merchant_id) only
```

## 7. Data Requirements

### 7.1 Source: `merchant_profiles_v3.csv` → table `client`

Primary key `merchant_id`. All columns are **sourced** (not derived).

| Column | Type | Observed domain / notes |
|---|---|---|
| `merchant_id` | text PK | `MER2001`–`MER2150` |
| `business_name` | text | 148 distinct of 150; **not unique, never use as a key** |
| `industry` | text | 16 values (e.g. Grocery & Supermarket 14, Construction & Contracting 15, Jewelry & Watches 5) |
| `mcc_code` | text | stored as given (`"MCC 5411"`); maps 1:1 to `industry` in this data. Also store `mcc_numeric` (int, e.g. 5411) as a parsed convenience column |
| `business_type` | text | 6 values: LLC 34, Branch of Foreign Company 29, Free Zone Establishment (FZE) 29, Sole Establishment 22, Free Zone Company (FZCO) 18, Civil Company 18 |
| `license_authority` | text | 9 values (Dubai DED, DMCC Free Zone, Sharjah DED, …) |
| `vat_registered` | bool | True 119 / False 31 |
| `package` | text | 7 values: Prime 39, Preferred 39, Connect 29, Prestige 19, Proprietor 13, Platinum 9, Emirati Business 2. This is the only segment-like field (see Open Question 4) |
| `relationship_start_date` | date | 2020-10-19 → 2026-06-08 |
| `rm_id` | text | 25 RMs (RM001–RM025), 3–13 clients each |
| `branch_id` | text | 8 branches. **All 25 RMs span more than one branch**, so `rm_id` is not nested inside `branch_id` |
| `account_balance_aed` | numeric(14,2) | 745.34 → 2,053,840.37 (median ≈ 47.3k) |
| `avg_monthly_turnover_aed` | numeric(14,2) | 3,402.57 → 3,500,000; heavy clustering at round values (200k ×36, 50k ×24, 500k ×18) |
| `synthetic_credit_score` | int | 354 → 899 |
| `num_pos_terminals` | int | 1 (96), 2 (31), 3 (17), 4 (6) |
| `risk_segment` | text | Low 91, Medium 48, High 11 |
| `city` | text | Dubai 65, Sharjah 40, Ras Al Khaimah 18, Ajman 16, Abu Dhabi 11 |
| `monthly_pos_limit_aed` | numeric(14,2) | 5,585.10 → 6,239,913.42 |
| `daily_pos_limit_aed` | numeric(14,2) | 457.37 → 503,545.97 |

Additional columns on `client` set by the ingest: `has_pos_data` (bool), `ingest_run_id` (FK).

**Not present in the source (must not be invented):** card number, a client-level card type, per-card limits, existing products held, current MDR/pricing rate, RM names, branch names, contact details, loan/credit-facility records. See Open Questions 1, 2 and 4.

### 7.2 Source: `pos_daily_acquiring_v3.csv` → table `pos_daily`

Composite PK `(merchant_id, date)`, FK to `client`. Indexed on `(merchant_id, date)`.

| Column | Type | Observed domain / notes |
|---|---|---|
| `merchant_id` | text FK | 150 distinct, 240 rows each |
| `date` | date | 2025-12-07 → 2026-08-03, contiguous |
| `daily_acquiring_volume_aed` | numeric(14,2) | 0.00 → 274,140.91; median ≈ 4,493.55 |
| `transaction_count` | int | 0 → 2,580; median 4 |
| `terminal_status` | text | `Active` 35,872 / `Dormant` 128 |
| `card_type` | text | `Mass` 17,194 / `Premium` 11,571 / `Super Premium` 7,235 (per-day label) |

Notes: `terminal_status` is a daily status for the client's POS estate as a whole, not per terminal. Dormant rows always have volume 0 and count 0.

### 7.3 Derived: `client_fact` (one row per client, **computed**)

Every field here is derived. None come from the source files. The primary key is `merchant_id`, and the table carries `as_of_date`.

| Field | Definition |
|---|---|
| `volume_t30`, `volume_p30` | Σ `daily_acquiring_volume_aed` over `t30` / `p30` |
| `volume_change_t30_vs_p30` | `(volume_t30 − volume_p30) / volume_p30`, `NULL` if `volume_p30 = 0` |
| `txn_t30`, `txn_p30` | Σ `transaction_count` |
| `avg_ticket_t30` | `volume_t30 / txn_t30` (`NULL` if 0 txns) |
| `active_days_t30`, `dormant_days_t30` | counts by `terminal_status` in `t30` |
| `is_dormant_now`, `dormant_streak_days` | FR-010 |
| `peak_daily_volume_t30` | max daily volume in `t30` |
| `daily_limit_utilisation_t30` | `peak_daily_volume_t30 / daily_pos_limit_aed` |
| `monthly_limit_utilisation_t30` | `volume_t30 / monthly_pos_limit_aed` (t30 is a 30-day proxy for a month) |
| `volume_to_turnover_t30` | `volume_t30 / avg_monthly_turnover_aed` |
| `balance_to_turnover` | `account_balance_aed / avg_monthly_turnover_aed` (idle-balance signal input) |
| `tenure_months` | whole months from `relationship_start_date` to `as_of_date`, floored at 0 |
| `premium_share_t30` | `volume_share` of `Premium` + `Super Premium` in `t30` (convenience; full detail in `client_card_mix`) |
| `has_pos_data` | copied from `client` for convenience |

Companion derived tables: `client_monthly_volume(merchant_id, month, volume_aed, txn_count, active_days, dormant_days, is_complete)` and `client_card_mix(merchant_id, window, card_type, volume_aed, volume_share, active_days, day_share)`.

Bookkeeping tables: `ingest_run` (FR-005) and `ingest_issue` (quarantine and warning rows).

### 7.4 Read / write matrix

| Component | Reads | Writes |
|---|---|---|
| Ingest (this spec) | both CSVs | all tables above |
| API / services (this spec, then Specs 02–10) | all tables | nothing (Spec 10 will add its own accept-log table) |
| Co-pilots (Specs 08, 09) | via `PortfolioReader` / `ClientReader` only | nothing |

### 7.5 Synthetic vs real

- **Synthetic (safe as illustrative):** all of the above, in full.
- **Real / must not be invented:** product names, fees and rates. None exist in this spec's data. See FR-014.

## 8. UI Requirements

This spec ships no new screen. It sets the data contracts and states that later screens must honour, plus one shared element.

**Shared element: Data-status chip** (used in the app header in Spec 11 and on every screen)
- Content: "Data as of 3 Aug 2026 · Synthetic". Built from `GET /api/data/status`.
- Style: Industry `.tag` (square-cornered, hairline, steel-blue tonal ramp). No second accent. Warnings use the system's existing status treatment, not a new color.
- Click: opens a small blueprint card (`.card.blueprint` with corner registration marks) with the disclaimer, ingest time, row counts and warning count.

**States every consuming screen must handle (defined here so they are consistent):**

| State | Source condition | Required behavior |
|---|---|---|
| Loading | request in flight | skeleton rows in `.table` / empty `.card.blueprint`, no spinner-only screens |
| Empty database | `/api/data/status` reports 0 clients | full-card empty state: "No client data loaded" with the ingest command shown in a mono block |
| Client not found | 404 `client_not_found` | inline error card with a `.btn-secondary` back to dashboard |
| No POS data | `has_pos_data = false` | show profile fields; every POS-derived value renders "No POS data" and not `0` |
| Null fact | any `client_fact` field `NULL` | render an en dash with tooltip "Not enough data", never `0%` or `NaN` |
| Dormant client | `is_dormant_now` | show a "Dormant · N days" `.tag`. Volume shows `0`, which is a real value here. |
| Partial month | `is_complete = false` | excluded from the 6-month chart. If shown anywhere, labelled "partial". |
| API error | 5xx / network | `.card.blueprint` error with retry `.btn-secondary` |

Lucide icons at 1.5 stroke (e.g. `database`, `shield-alert` for the data chip).

## 9. Dependencies

- **Prior specs:** none. This is the first spec. `.claudespecs/` did not exist before this file.
- **Existing implementation:** none. The project currently contains only `structured_data/` (the two CSVs), `.claude/` command templates and an empty `venv/` (pip only; **pandas, SQLAlchemy and FastAPI are not installed yet**). There is no frontend, backend, database, scoring logic, co-pilot or styling code to reuse.
- **Referenced documents that do not exist yet:** `.claude/system_design.md` and `.claude/wireframe.md` are command templates, not completed design docs, and both refer to a `spec.md` that is not in the repo. This spec therefore stands on the product context given in the `create_spec` command. No Project Architecture spec exists. This spec assumes a conventional layout (`backend/`, `frontend/`, `scripts/`) and does not create it.
- **Specs that depend on this one:** all of 02–15. In particular: 02 (reads `client_fact`), 04 (monthly + card mix), 05/06 (profile + facts), 08/09 (readers), 12 (grounding uses these tables as the only truth).
- **Install needed to build:** `pandas`, `sqlalchemy`, `fastapi`, `uvicorn`, `pydantic`, `pytest` in the project venv.

## 10. Open Questions

1. **Missing fields the wireframe expects.** The Client Profile wireframe shows *card no., card type, card limits* and *existing products*. None of these are in the data. Proposed handling: replace them with what exists (`package`, POS limits, `num_pos_terminals`, `account_balance_aed`) and drop "existing products" entirely, so the NTB engine (Spec 06) cannot know what a client already holds. Alternatively, add a third small file or a documented synthetic rule for products held. **Needs a product decision before Spec 03 and Spec 06.**
2. **No current pricing rate in the data.** Spec 05 promises "current → suggested rate", but there is no MDR or fee field. Options: (a) a configurable assumed rate card keyed by `package` or `card_type` (must be labelled illustrative, and any real product names or rates must come from a cited public source), or (b) compute only an *effective rate* if a fee/revenue column is supplied later. **Needs a decision before Spec 05.**
3. **Meaning of "card mix".** `card_type` is a per-day label, so the mix is by day/volume share, not by transaction. Confirm that this is acceptable for the "Card Mix & Volume" screen and that the UI copy can say "share of volume on Premium days".
4. **Segment definition.** Is `package` the "segment" in the wireframe's Profile & Behavior card, or should segment be derived (for example from turnover bands)? Proposed default: show `package` and call it "Package".
5. **Portfolio scope.** The 150 clients belong to 25 RMs (all spanning multiple branches). Is the "portfolio" the full book (default, simplest for the demo), or should there be an RM selector that filters by `rm_id`? This spec supports both (`rm_id` filter). The choice affects Specs 02, 08 and 11.
6. **POS before relationship start.** 14 clients show POS activity before their `relationship_start_date`. Treat as a data quirk (current approach, warn only), or as an onboarding-gap signal for Spec 02? Do not interpret it until decided.
7. **Limit-pressure headroom.** Average monthly POS volume reaches at most 78% of `monthly_pos_limit_aed` across the whole window. Peak-day utilisation has not been profiled. Spec 02 needs to calibrate the "limit pressure" threshold against the real distribution of `daily_limit_utilisation_t30` before choosing a cutoff, or the signal may flag nobody.
8. **Data location naming.** Product docs refer to `data/`, but the files live in `structured_data/`. Proposed: keep them where they are and configure via env vars (FR-001). Rename only if you prefer.
9. **Refresh model.** Is a single static load sufficient for the hackathon (current assumption), or should the demo support dropping in a new CSV pair and re-ingesting from the UI? The latter is out of scope here unless requested.
