-- =====================================================================
-- 03_copy_into.sql: load new monthly files from S3 into RAW
-- Safe to re-run: Snowflake remembers which files it already loaded and skips them.
-- To reload a month that changed, delete its rows first and add FORCE = TRUE.
-- =====================================================================
use warehouse credito_wh;

copy into credito.raw.scr_data
from (
  select
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
    metadata$filename,
    metadata$start_scan_time
  from @credito.raw.scr_stage
)
pattern = '.*scrdata_[0-9]{6}[.]csv'
on_error = 'abort_statement';

-- Quick audit: rows per file
select _source_file, count(*) as rows_loaded, max(_loaded_at) as loaded_at
from credito.raw.scr_data
group by 1
order by 1;
