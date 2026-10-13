{{
  config(
    materialized = 'incremental',
    unique_key = 'portfolio_row_key',
    on_schema_change = 'fail'
  )
}}

{#
  Periodic snapshot fact table.
  Grain: one row per month x state x customer profile x product x funding.
  Balances are semi-additive: sum across any dimension except month.
  Incremental: each run only processes months newer than the latest one already loaded.
#}

with stg as (

    select * from {{ ref('stg_scr__credit_portfolio') }}
    {% if is_incremental() %}
    where reference_date > (select max(month_date) from {{ this }})
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
    problem_assets

from stg
