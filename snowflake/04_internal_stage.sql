-- =====================================================================
-- 04_internal_stage.sql: alternative to 02_s3_integration.sql
-- Use when Snowflake cannot assume an IAM role in your AWS account (for example,
-- AWS free-plan accounts). Files are uploaded from your machine with
-- ingestion/load_snowflake_stage.py instead of being read from S3.
-- =====================================================================
use role accountadmin;

create stage if not exists credito.raw.scr_internal_stage
  file_format = credito.raw.scr_csv
  comment = 'Monthly SCR.data CSVs uploaded with ingestion/load_snowflake_stage.py';

-- dbt's service user loads RAW with the transformer role: it needs to write to the
-- stage, read from it, and insert into the RAW table.
grant read, write on stage credito.raw.scr_internal_stage to role transformer;
grant usage on file format credito.raw.scr_csv to role transformer;
grant insert on table credito.raw.scr_data to role transformer;
