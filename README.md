# Brazil Credit Portfolio Analytics

An analytics platform built on **SCR.data**, the Banco Central do Brasil's public credit registry: the entire Brazilian financial system's loan portfolio, published every month by state, customer profile, product and lender type.

**Question it answers:** where is credit delinquency rising, for whom, and in which products?

> **What the data shows (Jul 2024 → Jul 2026):** the system's nonperforming rate rose from **3.1% to 4.8%** while the portfolio grew from R$ 6.3 to R$ 7.6 trillion. The increase is concentrated in individuals (3.8% → 5.8%) and in personal loans without payroll deduction (7.1% → 11.3%); payroll-deductible loans (*consignado*) stayed far lower (2.5% → 3.7%).
>
> *Brazilian banks adopted new accounting rules (CMN Resolution 4,966) in January 2025, so part of the change across that date may come from measurement rather than borrower behavior.*

## Architecture

```
BCB yearly ZIP ──► ingestion/download_scr.py ──► S3 (raw/scr_data/ano=YYYY/mes=MM/)
                                                   │
                                     snowflake/03_copy_into.sql (COPY INTO, idempotent)
                                                   ▼
                                     Snowflake RAW.SCR_DATA (all text, as published)
                                                   │  dbt
                         staging ──► marts (star schema) ──► reporting ──► Tableau
                                                   │
                       Airflow DAG runs it monthly (phase 2) · LLM summary validated against marts (phase 3)
```

| Layer | Schema | What lives there |
|---|---|---|
| Raw | `RAW` | Files loaded as-is, every column as text, plus source file and load time |
| Staging | `STAGING` | Renamed to English, typed, text cleaned, deduplicated (views) |
| Marts | `MARTS` | Star schema: one fact table and five dimensions |
| Reporting | `REPORTING` | Aggregated table for dashboards |
| Snapshots | `SNAPSHOTS` | SCD Type 2 history of the product grouping |

## Data model

**Fact:** `fct_credit_portfolio_monthly`, a periodic snapshot. Grain: one row per month × state × customer profile × product × funding (≈310k rows per month).

**Dimensions:** `dim_month`, `dim_state`, `dim_product`, `dim_customer_profile`, `dim_funding` (a junk dimension).

Modeling decisions are documented in [docs/modeling.md](docs/modeling.md). The two that matter most:

* **Balances are semi-additive.** Outstanding portfolio can be summed across states or products, never across months.
* **Rates are computed after aggregation.** `nonperforming_rate = sum(nonperforming) / sum(outstanding)`, never an average of rates.

## Data quality

`dbt build` runs 37 tests. Highlights:

| Test | What it protects |
|---|---|
| `assert_portfolio_reconciles` | Outstanding = current + overdue, on every row |
| `assert_buckets_sum_to_totals` | Maturity and overdue buckets add up to their totals |
| `assert_no_balance_lost_between_layers` | Monthly totals match between staging and the fact table |
| `not_null` on `dim_product.product_group` | Fails when the BCB publishes a new product the grouping seed doesn't know yet |
| `unique` on the fact's surrogate key | Enforces the declared grain |

Source quirks handled in staging: Brazilian decimal commas, a stray Windows-1252 dash character in some product names, repeated and trailing spaces, and the number of operations published as `-1` when not disclosed (kept as `NULL` plus a flag, so it is never summed by accident).

The reconciliation tests also caught a real inconsistency in the published data: one row in December 2024 whose outstanding balance does not equal current + overdue (off by R$ 3,088.53, 1 row out of 9.7 million). It is documented in [docs/modeling.md](docs/modeling.md#known-source-issues) and the test warns on isolated cases but fails if they become systematic.

## CI

Every pull request runs `dbt build` on GitHub Actions against DuckDB with a 2,000-row sample of real data (`ci/sample/`). This keeps CI free and credential-free; the production target is Snowflake.

## Run it

```bash
pip install -r requirements.txt

# Local (no cloud account): DuckDB
python ingestion/download_scr.py --start 2024-07 --end 2024-07 --no-upload
python ingestion/load_local_duckdb.py data/raw/scr_data   # or any folder with scrdata_YYYYMM.csv files
cd dbt && export DBT_PROFILES_DIR=. && dbt deps && dbt build

# Snowflake: see docs/GUIA_PT.md (setup SQL in snowflake/, then DBT_TARGET=dev)
```

## Roadmap

- [x] Ingestion to S3, Snowflake RAW, dbt staging and star schema, tests, CI
- [ ] Tableau Public dashboard
- [ ] Airflow orchestration with monthly backfill (`orchestration/`)
- [ ] LLM monthly summary with claim-level validation against the warehouse (`ai/`)

## Data source and license

Data: Banco Central do Brasil, [SCR.data](https://dadosabertos.bcb.gov.br/dataset/scr_data), licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). The CI sample in `ci/sample/` is a subset of that data under the same license.
