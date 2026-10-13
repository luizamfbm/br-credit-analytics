# Modeling decisions

## Grain

The source publishes one row per combination of:

`reference month × state × institution segment × customer type × economic activity × customer size × modality × submodality × funding origin × rate index`

This combination is unique in the source (checked in staging with `unique_combination_of_columns`), so the fact table keeps the source grain with no aggregation. Keeping the finest grain means any report can be built by rolling up, never by guessing.

## Fact type

`fct_credit_portfolio_monthly` is a **periodic snapshot**: it records the state of the portfolio at the end of each month. It is not a transaction fact (no individual loans) and not an accumulating snapshot (no loan lifecycle).

## Dimensions

| Dimension | Natural key | Notes |
|---|---|---|
| `dim_month` | reference date | Year, quarter, month |
| `dim_state` | state code | Name and region come from the `uf_region` seed |
| `dim_product` | modality + submodality | Submodality alone is not unique ("Financiamento de projeto" exists under four modalities). `product_group` comes from the `product_grouping` seed |
| `dim_customer_profile` | customer type + size + economic activity | Size means income band for individuals (PF) and company size for companies (PJ) |
| `dim_funding` | institution segment + funding origin + rate index | Junk dimension: three low-cardinality flags that would clutter the fact table |

Surrogate keys are MD5 hashes of the natural keys (`dbt_utils.generate_surrogate_key`), so the fact can compute them without joining to the dimensions.

## Bus matrix

| Fact | Month | State | Customer profile | Product | Funding |
|---|:-:|:-:|:-:|:-:|:-:|
| `fct_credit_portfolio_monthly` | ✓ | ✓ | ✓ | ✓ | ✓ |

## Measures

| Measure | Additivity | Why |
|---|---|---|
| Balances (`outstanding_portfolio`, `current_*`, `overdue_*`, `nonperforming_portfolio`, `problem_assets`) | **Semi-additive** | They are end-of-month stocks. Sum across states or products; across months, take the value of a month or an average, never a sum |
| `number_of_operations` | Additive within a month, but **partially missing** | Published as `-1` when not disclosed (about a quarter of rows). Stored as `NULL` with `is_operations_undisclosed` |
| `nonperforming_rate` | **Non-additive** | Computed after aggregation as sum(nonperforming) / sum(outstanding) |

## Definitions (from the BCB methodology)

* **Outstanding portfolio (carteira ativa):** current + overdue balance.
* **Nonperforming portfolio (carteira de inadimplência):** total balance of operations with at least one installment more than 90 days overdue. It includes the not-yet-due installments of those operations, so it is larger than `overdue_over_90d`.
* **Problem assets (ativo problemático):** operations overdue more than 90 days or with signs they won't be fully paid. The criteria changed in January 2025, so compare this measure across that date with care.

## Incremental strategy

The fact table only processes months newer than the latest month already loaded. Months are published whole and never partially, so a month-level high-water mark is enough. If the BCB revises a past month, run `dbt build --full-refresh -s fct_credit_portfolio_monthly`.

## Slowly changing dimensions

The business product grouping is edited by hand in a seed. `snap_product_grouping` keeps its history as SCD Type 2 (`dbt_valid_from`, `dbt_valid_to`), so a report from last year can be rebuilt with last year's grouping.

## Known source issues

The data is kept exactly as the BCB publishes it; issues are reported by tests, not patched.

| Month | Row | Issue | How it is handled |
|---|---|---|---|
| Dec 2024 | PR · Fintech · PF · payroll-deductible personal loans · 1 to 2 minimum wages · fixed rate (line 197,652 of `scrdata_202412.csv`) | `carteira_ativa` is R$ 345,414.46, but current + overdue add up to R$ 348,502.99 (difference of R$ 3,088.53). It is the only row out of 9.7 million that breaks the rule | `assert_portfolio_reconciles` warns on up to 10 such rows and fails above that |
