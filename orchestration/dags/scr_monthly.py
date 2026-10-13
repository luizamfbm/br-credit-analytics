"""Phase 2: monthly orchestration with Apache Airflow (tested layout: Astro CLI project).

Flow: pick month -> download + upload to S3 -> COPY INTO Snowflake RAW -> dbt build

* The month comes from the run's data interval, not from datetime.now(), so backfills work:
  triggering the DAG for an old interval reloads that old month.
* The BCB publishes a month about 30 days after it closes. The DAG runs on the 5th of each
  month and loads the month two months back (e.g. the run on 5 Oct loads August).
* If the file is not published yet, the ingestion task fails and retries every 6 hours.

Requires the Airflow connection `snowflake_default`, the AWS credentials for S3 and the
environment variables in .env.example. See docs/GUIA_PT.md, Fase 2.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

try:  # Airflow 3
    from airflow.sdk import dag, task
except ImportError:  # Airflow 2
    from airflow.decorators import dag, task

from airflow.operators.bash import BashOperator

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # repo root inside the Airflow image
DBT_DIR = PROJECT_ROOT / "dbt"
COPY_SQL = PROJECT_ROOT / "snowflake" / "03_copy_into.sql"


def first_of_month_minus(dt: datetime, months: int) -> str:
    y, m = dt.year, dt.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


@dag(
    dag_id="scr_monthly",
    schedule="0 9 5 * *",  # 09:00 UTC on the 5th of every month
    start_date=datetime(2024, 3, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 3, "retry_delay": timedelta(hours=6)},
    tags=["scr", "credit", "portfolio"],
)
def scr_monthly():

    @task
    def target_month(data_interval_end=None, params=None) -> str:
        """Month to load: a manual run can pass {"month": "2025-06"}; otherwise two months back."""
        if params and params.get("month"):
            return params["month"]
        return first_of_month_minus(data_interval_end, 2)

    @task
    def ingest(month: str) -> str:
        sys.path.insert(0, str(PROJECT_ROOT))
        from ingestion.download_scr import main as download_main

        download_main(["--start", month, "--end", month, "--data-dir", "/tmp/scr"])
        return month

    @task
    def copy_into_snowflake(month: str) -> int:
        from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

        hook = SnowflakeHook(snowflake_conn_id="snowflake_default")
        statements = [s.strip() for s in COPY_SQL.read_text().split(";") if s.strip() and not s.strip().startswith("--")]
        hook.run(statements)
        rows = hook.get_first(
            "select count(*) from credito.raw.scr_data where _source_file ilike %(f)s",
            parameters={"f": f"%scrdata_{month.replace('-', '')}.csv"},
        )[0]
        if rows == 0:
            raise ValueError(f"No rows loaded for {month}")
        return rows

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {DBT_DIR} && dbt deps && dbt build --target dev",
        env={"DBT_PROFILES_DIR": str(DBT_DIR)},
        append_env=True,
    )

    month = target_month()
    copy_into_snowflake(ingest(month)) >> dbt_build


scr_monthly()
