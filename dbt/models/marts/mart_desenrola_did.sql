{{ config(materialized = 'table') }}

{#
  Input for the Novo Desenrola Brasil analysis (difference in differences).

  The families track ran from 4 May to 31 Aug 2026, for individuals earning up to five
  minimum wages, covering credit card, overdraft and personal loan (CDC) debts that were
  91 days to 2 years overdue (Ministerio da Fazenda).

  Grain: one row per month x product group x income band, individuals (PF) only, from
  Jan 2025 on, so the comparison does not cross the Jan 2025 accounting change
  (CMN Resolution 4,966).

  - eligible products: Credit card, Overdraft and revolving, Personal loans
  - control products:  Vehicle financing, Real estate. Payroll loans and rural credit are
    left out: other measures in the same package (FGTS-backed credit, Desenrola Rural)
    could have moved them.
  - income_band: up_to_5_mw (includes "no income"), above_5_mw, unknown

  Balances only: rates are computed after aggregation, in the analysis.
#}

with base as (

    select
        f.month_date,
        p.product_group,
        c.customer_size,
        f.outstanding_portfolio,
        f.nonperforming_portfolio,
        f.overdue_over_90d
    from {{ ref('fct_credit_portfolio_monthly') }} f
    join {{ ref('dim_product') }} p on p.product_key = f.product_key
    join {{ ref('dim_customer_profile') }} c on c.customer_profile_key = f.customer_profile_key
    where c.customer_type = 'PF'
      and f.month_date >= cast('2025-01-31' as date)
      and p.product_group in (
          'Credit card', 'Overdraft and revolving', 'Personal loans',
          'Vehicle financing', 'Real estate'
      )

)

select
    month_date,
    product_group,
    case
        when product_group in ('Credit card', 'Overdraft and revolving', 'Personal loans') then 'eligible'
        else 'control'
    end                                                       as product_role,
    case
        when customer_size like 'Indispon%' then 'unknown'
        when customer_size like 'Mais de 5 a%'
          or customer_size like 'Mais de 10%'
          or customer_size like 'Acima%' then 'above_5_mw'
        else 'up_to_5_mw'
    end                                                       as income_band,
    case
        when month_date < cast('2026-05-01' as date) then 'pre'
        when month_date <= cast('2026-08-31' as date) then 'program'
        else 'post'
    end                                                       as period,
    sum(outstanding_portfolio)                                as outstanding_portfolio,
    sum(nonperforming_portfolio)                              as nonperforming_portfolio,
    sum(overdue_over_90d)                                     as overdue_over_90d
from base
group by 1, 2, 3, 4, 5
