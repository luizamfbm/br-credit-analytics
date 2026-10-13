-- =====================================================================
-- 01_setup.sql: run once in a Snowflake worksheet (as ACCOUNTADMIN on a trial)
-- Creates the warehouse, database, schemas, a role for dbt and the RAW table.
-- =====================================================================
use role accountadmin;

-- Compute: smallest size, suspends after 60s idle so the trial credits last.
create warehouse if not exists credito_wh
  warehouse_size = 'XSMALL'
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true;

-- Storage: one database, one schema per layer.
create database if not exists credito;
create schema if not exists credito.raw;        -- files as published (all VARCHAR)
create schema if not exists credito.seeds;      -- reference CSVs managed by dbt
create schema if not exists credito.staging;    -- cleaned and typed (views)
create schema if not exists credito.marts;      -- star schema
create schema if not exists credito.reporting;  -- tables for dashboards
create schema if not exists credito.snapshots;  -- SCD Type 2 history

-- Role used by dbt: can read RAW and build everything else.
create role if not exists transformer;
grant usage on warehouse credito_wh to role transformer;
grant usage on database credito to role transformer;
grant usage, create table, create view on all schemas in database credito to role transformer;
grant select on future tables in schema credito.raw to role transformer;
-- Replace <YOUR_USER> with your Snowflake login name.
grant role transformer to user <YOUR_USER>;

-- Service user for dbt and Airflow: no password, key-pair authentication only.
-- Replace <PUBLIC_KEY> with the content of dbt_svc_key.pub without the BEGIN/END lines.
create user if not exists dbt_svc
  type = service
  default_role = transformer
  default_warehouse = credito_wh
  rsa_public_key = '<PUBLIC_KEY>';
grant role transformer to user dbt_svc;

-- The RAW table mirrors the CSV exactly: every column is text.
-- Typing happens in dbt staging, so a bad value never breaks the load.
create table if not exists credito.raw.scr_data (
  data_base varchar, uf varchar, segmento varchar, cliente varchar, cnae_ocupacao varchar,
  porte varchar, modalidade varchar, submodalidade varchar, origem varchar, indexador varchar,
  numero_de_operacoes varchar,
  a_vencer_ate_90_dias varchar, a_vencer_de_91_ate_360_dias varchar, a_vencer_de_361_ate_1080_dias varchar,
  a_vencer_de_1081_ate_1800_dias varchar, a_vencer_de_1801_ate_5400_dias varchar, a_vencer_acima_de_5400_dias varchar,
  carteira_a_vencer varchar, vencido_de_15_ate_90_dias varchar, vencido_acima_de_90_dias varchar,
  carteira_vencida varchar, carteira_ativa varchar, carteira_inadimplencia varchar, ativo_problematico varchar,
  _source_file varchar,
  _loaded_at timestamp_ltz
);
grant select on table credito.raw.scr_data to role transformer;

-- File format matching the BCB files: ';' separator, quoted fields, header line, UTF-8.
create file format if not exists credito.raw.scr_csv
  type = csv
  field_delimiter = ';'
  field_optionally_enclosed_by = '"'
  skip_header = 1
  encoding = 'UTF8';
