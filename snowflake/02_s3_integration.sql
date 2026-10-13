-- =====================================================================
-- 02_s3_integration.sql: connect Snowflake to your S3 bucket (run once)
-- Replace <AWS_ACCOUNT_ID> and <BUCKET> before running.
-- Full walkthrough in docs/GUIA_PT.md, step 4.
-- =====================================================================
use role accountadmin;

create storage integration if not exists s3_scr_int
  type = external_stage
  storage_provider = 'S3'
  enabled = true
  storage_aws_role_arn = 'arn:aws:iam::<AWS_ACCOUNT_ID>:role/snowflake-scr-read'
  storage_allowed_locations = ('s3://<BUCKET>/raw/scr_data/');

-- Copy STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID from this output
-- into aws/trust_policy.json, then update the IAM role's trust relationship.
desc integration s3_scr_int;

create stage if not exists credito.raw.scr_stage
  url = 's3://<BUCKET>/raw/scr_data/'
  storage_integration = s3_scr_int
  file_format = credito.raw.scr_csv;

grant usage on integration s3_scr_int to role transformer;
grant usage on stage credito.raw.scr_stage to role transformer;

-- Should list the files you uploaded with ingestion/download_scr.py
list @credito.raw.scr_stage;
