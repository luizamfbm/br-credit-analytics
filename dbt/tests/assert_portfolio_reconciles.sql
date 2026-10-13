-- Outstanding portfolio must equal current + overdue on every row (tolerance: 1 cent).
-- Returns the rows that break the rule; the test passes when it returns nothing.
--
-- The BCB files themselves contain isolated rows that break this rule (see
-- docs/modeling.md, "Known source issues"). A handful of rows is a source quirk to
-- report, not a pipeline bug, so it warns; more than 10 rows means something
-- systematic changed (a parsing or format problem) and it fails the build.
{{ config(warn_if='>0', error_if='>10') }}

select
    portfolio_row_key,
    outstanding_portfolio,
    current_portfolio,
    overdue_portfolio
from {{ ref('fct_credit_portfolio_monthly') }}
where abs(outstanding_portfolio - (current_portfolio + overdue_portfolio)) > 0.01
