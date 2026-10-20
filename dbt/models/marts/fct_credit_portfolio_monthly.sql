{{
  config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'month_date',
    on_schema_change = 'fail'
  )
}}

{#
  Periodic snapshot fact table.
  Grain: one row per month x state x customer profile x product x funding.
  Balances are semi-additive: sum across any dimension except month.

  Incremental by month: each run reprocesses every month whose raw rows were loaded
  after the last build of this table. That covers new months AND revised months
  (the Central Bank can republish a month; the loader reloads it in RAW with a new
  load time). delete+insert on month_date replaces the whole month, so rows that
  disappear in a revision are removed too, not left behind as a merge would.
#}

with changed_months as (

    {% if is_incremental() %}
    select reference_date
    from {{ ref('stg_scr__credit_portfolio') }}
    group by reference_date
    having max(_loaded_at) > (
        select coalesce(max(_loaded_at), cast('1900-01-01' as timestamp)) from {{ this }}
    )
    {% else %}
    select 1 as reference_date where 1 = 0
    {% endif %}

),

stg as (

    select * from {{ ref('stg_scr__credit_portfolio') }}
    {% if is_incremental() %}
    where reference_date in (select reference_date from changed_months)
    {% endif %}

)

select
    {{ dbt_utils.generate_surrogate_key([
        'reference_date', 'state_code', 'institution_segment', 'customer_type', 'economic_activity',
        'customer_size', 'product_modality', 'product_submodality', 'funding_origin', 'rate_index'
    ]) }}                                                                                                   as portfolio_row_key,
    {{ dbt_utils.generate_surrogate_key(['reference_date']) }}                                             as month_key,
    {{ dbt_utils.generate_surrogate_key(['state_code']) }}                                                 as state_key,
    {{ dbt_utils.generate_surrogate_key(['customer_type', 'customer_size', 'economic_activity']) }}        as customer_profile_key,
    {{ dbt_utils.generate_surrogate_key(['product_modality', 'product_submodality']) }}                    as product_key,
    {{ dbt_utils.generate_surrogate_key(['institution_segment', 'funding_origin', 'rate_index']) }}        as funding_key,
    reference_date                                                                                          as month_date,

    number_of_operations,
    is_operations_undisclosed,
    current_up_to_90d,
    current_91_to_360d,
    current_361_to_1080d,
    current_1081_to_1800d,
    current_1801_to_5400d,
    current_over_5400d,
    current_portfolio,
    overdue_15_to_90d,
    overdue_over_90d,
    overdue_portfolio,
    outstanding_portfolio,
    nonperforming_portfolio,
    problem_assets,

    _loaded_at

from stg
