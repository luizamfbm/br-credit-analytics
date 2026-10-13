{#
  Staging: rename to English, type every column, clean text. No business rules here.
  Grain: one row per reference month x state x institution segment x customer type
         x economic activity x customer size x modality x submodality x funding origin x rate index.
#}
with source as (

    select * from {{ source('scr', 'scr_data') }}

),

typed as (

    select
        cast(data_base as date)                          as reference_date,
        {{ clean_text('uf') }}                           as state_code,
        {{ clean_text('segmento') }}                     as institution_segment,
        {{ clean_text('cliente') }}                      as customer_type,
        {{ clean_text('cnae_ocupacao') }}                as economic_activity,
        {{ clean_text('porte') }}                        as customer_size,
        {{ clean_text('modalidade') }}                   as product_modality,
        {{ clean_text('submodalidade') }}                as product_submodality,
        {{ clean_text('origem') }}                       as funding_origin,
        {{ clean_text('indexador') }}                    as rate_index,

        -- The BCB publishes -1 when the number of operations is not disclosed.
        -- Keep it as NULL plus a flag, so nobody sums -1 by accident.
        case when numero_de_operacoes = '-1' then null
             else cast(numero_de_operacoes as integer) end as number_of_operations,
        (numero_de_operacoes = '-1')                     as is_operations_undisclosed,

        {{ br_number('a_vencer_ate_90_dias') }}           as current_up_to_90d,
        {{ br_number('a_vencer_de_91_ate_360_dias') }}    as current_91_to_360d,
        {{ br_number('a_vencer_de_361_ate_1080_dias') }}  as current_361_to_1080d,
        {{ br_number('a_vencer_de_1081_ate_1800_dias') }} as current_1081_to_1800d,
        {{ br_number('a_vencer_de_1801_ate_5400_dias') }} as current_1801_to_5400d,
        {{ br_number('a_vencer_acima_de_5400_dias') }}    as current_over_5400d,
        {{ br_number('carteira_a_vencer') }}              as current_portfolio,
        {{ br_number('vencido_de_15_ate_90_dias') }}      as overdue_15_to_90d,
        {{ br_number('vencido_acima_de_90_dias') }}       as overdue_over_90d,
        {{ br_number('carteira_vencida') }}               as overdue_portfolio,
        {{ br_number('carteira_ativa') }}                 as outstanding_portfolio,
        {{ br_number('carteira_inadimplencia') }}         as nonperforming_portfolio,
        {{ br_number('ativo_problematico') }}             as problem_assets,

        _source_file,
        _loaded_at

    from source

),

deduplicated as (

    -- If the same month is ever loaded twice, keep the most recent load.
    select *
    from typed
    qualify row_number() over (
        partition by
            reference_date, state_code, institution_segment, customer_type, economic_activity,
            customer_size, product_modality, product_submodality, funding_origin, rate_index
        order by _loaded_at desc
    ) = 1

)

select * from deduplicated
