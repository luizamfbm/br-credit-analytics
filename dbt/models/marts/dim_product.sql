-- One row per credit product (modality + submodality).
-- product_group comes from the product_grouping seed; a NULL means a new submodality
-- appeared in the source and the seed needs updating (the not_null test will fail).
with products as (
    select distinct product_modality, product_submodality
    from {{ ref('stg_scr__credit_portfolio') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['p.product_modality', 'p.product_submodality']) }} as product_key,
    p.product_modality,
    p.product_submodality,
    g.product_group
from products p
left join {{ ref('product_grouping') }} g
    on  g.product_modality = p.product_modality
    and g.product_submodality = p.product_submodality
