"""SCR.data load: detect new or revised files, reload them, rebuild dbt.

Two DAGs share this code:

  scr_monthly     manual, source=replay, target=replay
                  Replays real files month by month: you "publish" a month by copying its
                  CSV from data/replay/vault into data/replay/landing.

  scr_bcb_weekly  every Monday 07:00, source=bcb, target=dev
                  The Banco Central publishes SCR.data in batches a few times a year (for
                  example Jan-Jul in one release, Aug-Dec in January), not monthly. Each week
                  this DAG sends a HEAD request for the yearly ZIPs of this year and last year.
                  If neither changed, nothing is downloaded and the run ends as skipped.
                  If one changed, it is downloaded and extracted to data/bcb/landing.

Either way, a month is loaded when its file is new or its MD5 differs from the last one in
RAW.LOAD_LOG: a batch of several months loads them all; a republished month reloads only that
month; a run with nothing new does nothing. Months load one at a time; dbt runs once at the end.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

try:  # Airflow 3
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:  # older runtimes
    from airflow.exceptions import AirflowSkipException

INC = Path("/usr/local/airflow/include")
SOURCE_DIRS = {
    "replay": INC / "data" / "replay" / "landing",
    "bcb": INC / "data" / "bcb" / "landing",
}
BCB_ZIPS = INC / "data" / "bcb" / "zips"
DATABASES = {"replay": "CREDITO_REPLAY", "dev": "CREDITO"}
FILE_RE = re.compile(r"scrdata_(\d{6})\.csv$")


def _ingestion():
    """Make ingestion/ importable; imported inside tasks, never at DAG parse time."""
    path = str(INC / "ingestion")
    if path not in sys.path:
        sys.path.insert(0, path)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_bcb() -> None:
    """Refresh data/bcb/landing from the BCB site, downloading only ZIPs that changed."""
    _ingestion()
    from download_scr import extract_all, fetch_year_if_changed

    landing = SOURCE_DIRS["bcb"]
    this_year = pendulum.now("America/Sao_Paulo").year
    for year in (this_year - 1, this_year):  # last year too: Aug-Dec is published in January
        zip_path, changed = fetch_year_if_changed(year, BCB_ZIPS)
        if zip_path is None:
            continue
        already_extracted = any(landing.glob(f"scrdata_{year}??.csv"))
        if changed or not already_extracted:
            extract_all(zip_path, landing)


def available_files(source: str) -> dict[str, Path]:
    """{'YYYYMM': path} for every file the source currently offers."""
    if source == "bcb":
        sync_bcb()
    files = {}
    for p in SOURCE_DIRS[source].glob("scrdata_*.csv"):
        m = FILE_RE.search(p.name)
        if m:
            files[m.group(1)] = p
    return files


def read_load_log(database: str) -> dict[str, str]:
    """{'YYYYMM': md5} of the latest load of each month."""
    _ingestion()
    from load_snowflake_stage import connect

    con = connect(database.lower())
    try:
        rows = con.cursor().execute(
            f"""
            select ref_month, file_md5
            from {database}.raw.load_log
            qualify row_number() over (partition by ref_month order by loaded_at desc) = 1
            """
        ).fetchall()
    finally:
        con.close()
    return {r[0]: r[1] for r in rows}


def make_dag(dag_id: str, schedule: str | None, source: str, target: str, tags: list[str]):

    @dag(
        dag_id=dag_id,
        schedule=schedule,
        start_date=pendulum.datetime(2026, 1, 1, tz="America/Sao_Paulo"),
        catchup=False,
        max_active_runs=1,
        tags=["scr", "br-credit-analytics", *tags],
        params={
            "source": Param(source, enum=["replay", "bcb"]),
            "target": Param(target, enum=["replay", "dev"]),
        },
        doc_md=__doc__,
    )
    def scr_load():

        @task(retries=2, retry_delay=timedelta(minutes=10))  # the BCB site can be slow or down
        def detect() -> list[str]:
            params = get_current_context()["params"]
            files = available_files(params["source"])
            logged = read_load_log(DATABASES[params["target"]])
            todo = sorted(m for m, path in files.items() if logged.get(m) != md5(path))
            print(f"available: {sorted(files)}; to load: {todo}")
            if not todo:
                raise AirflowSkipException("No new or revised month")
            return todo

        @task(max_active_tis_per_dag=1)
        def load(month: str):
            params = get_current_context()["params"]
            ym = f"{month[:4]}-{month[4:]}"
            subprocess.run(
                [
                    sys.executable, str(INC / "ingestion" / "load_snowflake_stage.py"),
                    "--start", ym, "--end", ym,
                    "--source-dir", str(SOURCE_DIRS[params["source"]]),
                    "--database", DATABASES[params["target"]],
                    "--replace-month",
                ],
                check=True,
            )

        @task
        def dbt_build():
            params = get_current_context()["params"]
            subprocess.run(
                ["dbt", "build", "--target", params["target"]],
                cwd=INC / "dbt",
                env={**os.environ, "DBT_PROFILES_DIR": str(INC / "dbt")},
                check=True,
            )

        load.expand(month=detect()) >> dbt_build()

    return scr_load()


make_dag("scr_monthly", None, "replay", "replay", ["replay"])
make_dag("scr_bcb_weekly", "0 7 * * 1", "bcb", "dev", ["production"])
