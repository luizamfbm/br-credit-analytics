"""Monthly SCR.data load: detect new or revised files, reload them, rebuild dbt.

Params
  source  replay -> reads include/data/replay/landing (you "publish" a month by copying
                    its CSV from data/replay/vault into data/replay/landing)
          bcb    -> Banco Central do Brasil site (not implemented yet; needed only when
                    the next real release comes out)
  target  replay -> database CREDITO_REPLAY, dbt target "replay"
          dev    -> database CREDITO, dbt target "dev"

A month is loaded when its file is new or its MD5 differs from the last one recorded in
RAW.LOAD_LOG, so re-running with nothing new is a no-op (the run ends as skipped), and a
revised file reloads only that month. Months load one at a time; dbt runs once at the end.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

try:  # Airflow 3
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:  # older runtimes
    from airflow.exceptions import AirflowSkipException

INC = Path("/usr/local/airflow/include")
LANDING = INC / "data" / "replay" / "landing"
DATABASES = {"replay": "CREDITO_REPLAY", "dev": "CREDITO"}
FILE_RE = re.compile(r"scrdata_(\d{6})\.csv$")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def available_files(source: str) -> dict[str, Path]:
    """{'YYYYMM': path} for every file the source currently offers."""
    if source == "bcb":
        raise NotImplementedError("bcb source: implement when the next real release is out")
    files = {}
    for p in LANDING.glob("scrdata_*.csv"):
        m = FILE_RE.search(p.name)
        if m:
            files[m.group(1)] = p
    return files


def read_load_log(database: str) -> dict[str, str]:
    """{'YYYYMM': md5} of the latest load of each month."""
    sys.path.insert(0, str(INC / "ingestion"))
    from load_snowflake_stage import connect  # imported here, not at DAG parse time

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


@dag(
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="America/Sao_Paulo"),
    catchup=False,
    tags=["scr", "br-credit-analytics"],
    params={
        "source": Param("replay", enum=["replay", "bcb"]),
        "target": Param("replay", enum=["replay", "dev"]),
    },
    doc_md=__doc__,
)
def scr_monthly():

    @task
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
                "--source-dir", str(LANDING),
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


scr_monthly()
