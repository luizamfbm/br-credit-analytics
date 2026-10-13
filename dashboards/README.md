# Dashboard

Tableau Public cannot connect to Snowflake, so the dashboard reads a CSV export of `reporting.rpt_delinquency_monthly`.

## Export

**From Snowflake** (worksheet → run → download results as CSV):

```sql
select * from credito.reporting.rpt_delinquency_monthly order by month_date, state_code;
```

**From local DuckDB:**

```bash
python -c "import duckdb; duckdb.connect('data/credito.duckdb', read_only=True).sql('select * from reporting.rpt_delinquency_monthly').write_csv('dashboards/rpt_delinquency_monthly.csv')"
```

## Views

1. Map: nonperforming rate by state, latest month.
2. Line: nonperforming rate per product group over time.
3. Bars: PF vs PJ, outstanding and nonperforming.

In Tableau, recompute the rate as `SUM([Nonperforming Portfolio]) / SUM([Outstanding Portfolio])`. Do not average the `nonperforming_rate` column.

Link: _add the Tableau Public URL here_
