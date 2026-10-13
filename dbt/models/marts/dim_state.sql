-- One row per Brazilian state, with name and region from the uf_region seed.
with states as (
    select distinct state_code from {{ ref('stg_scr__credit_portfolio') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['s.state_code']) }} as state_key,
    s.state_code,
    r.state_name,
    r.region
from states s
left join {{ ref('uf_region') }} r on r.state_code = s.state_code
