-- Junk dimension: low-cardinality attributes of the lender and the funding.
select distinct
    {{ dbt_utils.generate_surrogate_key(['institution_segment', 'funding_origin', 'rate_index']) }} as funding_key,
    institution_segment,
    funding_origin,
    rate_index
from {{ ref('stg_scr__credit_portfolio') }}
