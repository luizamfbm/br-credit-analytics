# Dashboard

**[Brazil Credit Delinquency on Tableau Public](https://public.tableau.com/app/profile/lu.za.b.a.morte/viz/BrazilCreditDelinquency/Dashboard12)**

Tableau Public cannot connect to a warehouse, so the dashboard reads a CSV export of `reporting.rpt_delinquency_monthly`. No credentials go into the published workbook.

## Export

```bash
python dashboards/export_reporting.py                 # local DuckDB (default)
python dashboards/export_reporting.py --target dev    # Snowflake (source .env first)
```

The file lands in `dashboards/data/reporting_monthly.csv` (ignored by git) and the script prints the latest `month_date`, to check the dashboard's "data as of" label.

## Views

1. Map: nonperforming rate by state, latest month.
2. Line: nonperforming rate per product group over time, with a reference line at January 2025 (CMN Resolution 4,966 accounting change).
3. Bars: individuals (PF) vs companies (PJ).

The rate is a calculated field, `SUM([Nonperforming Portfolio]) / SUM([Outstanding Portfolio])`, so it stays correct at any filter. Never average the `nonperforming_rate` column.

## Refresh

When the BCB publishes a new batch (the weekly watcher opens a `bcb-release` issue): load it, run `dbt build`, export again, then in Tableau Public replace the data source with the new CSV and republish.
