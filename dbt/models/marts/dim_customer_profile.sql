-- One row per borrower profile: PF/PJ, size (income band or company size) and occupation / economic activity.
select distinct
    {{ dbt_utils.generate_surrogate_key(['customer_type', 'customer_size', 'economic_activity']) }} as customer_profile_key,
    customer_type,
    customer_size,
    economic_activity
from {{ ref('stg_scr__credit_portfolio') }}
