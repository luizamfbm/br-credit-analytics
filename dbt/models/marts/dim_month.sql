-- One row per reference month.
select distinct
    {{ dbt_utils.generate_surrogate_key(['reference_date']) }} as month_key,
    reference_date                                             as month_date,
    extract(year from reference_date)                          as year,
    extract(quarter from reference_date)                       as quarter,
    extract(month from reference_date)                         as month
from {{ ref('stg_scr__credit_portfolio') }}
