"""Load monthly SCR.data CSVs into Snowflake RAW through an internal stage.

Alternative to the S3 external stage (snowflake/02_s3_integration.sql) for accounts
where Snowflake cannot assume an IAM role, such as AWS free-plan accounts.
The raw files still land in S3 with ingestion/download_scr.py; this script copies the
same local files into Snowflake.

Flow: PUT each file to @<db>.raw.scr_internal_stage/ano=YYYY/mes=MM/ (gzip-compressed
by Snowflake on upload), then COPY INTO <db>.raw.scr_data.

Run once snowflake/04_internal_stage.sql has been executed:

    set -a; source .env; set +a
    python ingestion/load_snowflake_stage.py --start 2024-01 --end 2026-07 --source-dir ~/Downloads

Default mode is safe to re-run: PUT skips files already in the stage and COPY skips
files already loaded.

Options used by the Airflow DAG and the replay environment:

    --database NAME     load into another database (default: $SNOWFLAKE_DATABASE or CREDITO)
    --replace-month     reload each month idempotently: upload the file again, then in ONE
                        transaction delete that month's rows, COPY it with FORCE = TRUE and
                        record the file's MD5 and row count in <db>.raw.load_log.
                        FORCE is needed because COPY remembers which files it already loaded,
                        so a revised file with the same name would otherwise be skipped.
                        If anything fails, the transaction rolls back and RAW is unchanged.

    python ingestion/load_snowflake_stage.py --start 2026-02 --end 2026-02 \\
        --source-dir data/replay/landing --database CREDITO_REPLAY --replace-month

Authenticates as the DBT_SVC service user with the same key pair dbt uses.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from download_scr import find_local, month_range  # same folder

ALL_FILES_PATTERN = ".*scrdata_[0-9]{6}[.]csv[.]gz"


def stage(db: str) -> str:
    return f"@{db}.raw.scr_internal_stage"


def copy_sql(db: str, pattern: str, force: bool = False) -> str:
    return f"""
copy into {db}.raw.scr_data
from (
  select
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
    metadata$filename,
    metadata$start_scan_time
  from {stage(db)}
)
pattern = '{pattern}'
on_error = 'abort_statement'
{"force = true" if force else ""}
"""


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(database: str):
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).expanduser()
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.getenv("SNOWFLAKE_USER", "DBT_SVC"),
        private_key=private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        role=os.getenv("SNOWFLAKE_ROLE", "TRANSFORMER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "CREDITO_WH"),
        database=database,
        schema="RAW",
    )


def load_new_files(cur, db: str, files) -> None:
    """Original behaviour: upload what is missing, COPY what was never loaded."""
    for month, path in files:
        target = f"{stage(db)}/ano={month.year}/mes={month.month:02d}/"
        row = cur.execute(f"put 'file://{path.resolve()}' {target} auto_compress=true overwrite=false").fetchone()
        print(f"{month:%Y-%m}: {row[6].lower()}")  # status column: UPLOADED or SKIPPED

    print(f"\nCOPY INTO {db}.raw.scr_data ...")
    results = cur.execute(copy_sql(db, ALL_FILES_PATTERN)).fetchall()
    # One row per file (file, status, rows_parsed, rows_loaded, ...), or a single
    # status row when there was nothing new to load.
    if results and len(results[0]) > 3:
        for r in results:
            print(f"  {r[0]}: {r[1]}, {r[3]:,} rows")
    else:
        print("  no new files: everything in the stage was already loaded")


def replace_month(cur, db: str, month, path: Path) -> None:
    """Reload one month idempotently, in one transaction, and log it."""
    name = f"scrdata_{month:%Y%m}.csv.gz"
    folder = f"ano={month.year}/mes={month.month:02d}/"
    md5 = file_md5(path)

    # PUT is a file upload, not DML, so it runs before the transaction.
    cur.execute(f"put 'file://{path.resolve()}' {stage(db)}/{folder} auto_compress=true overwrite=true")

    cur.execute("begin")
    try:
        deleted = cur.execute(
            f"delete from {db}.raw.scr_data where _source_file like %s", (f"%{name}",)
        ).fetchone()[0]
        pattern = f".*{folder}scrdata_{month:%Y%m}[.]csv[.]gz"
        results = cur.execute(copy_sql(db, pattern, force=True)).fetchall()
        loaded = sum(r[3] for r in results if len(r) > 3)
        if loaded == 0:
            raise RuntimeError(f"{month:%Y-%m}: COPY loaded 0 rows from {name}")
        cur.execute(
            f"insert into {db}.raw.load_log (ref_month, file_md5, row_count) values (%s, %s, %s)",
            (f"{month:%Y%m}", md5, loaded),
        )
        cur.execute("commit")
    except Exception:
        cur.execute("rollback")
        print(f"{month:%Y-%m}: failed, rolled back; RAW unchanged", file=sys.stderr)
        raise
    print(f"{month:%Y-%m}: replaced ({deleted:,} rows removed, {loaded:,} loaded, md5 {md5[:8]})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", required=True, help="First month, YYYY-MM")
    p.add_argument("--end", required=True, help="Last month, YYYY-MM")
    p.add_argument("--source-dir", required=True, help="Folder with scrdata_YYYYMM.csv files (searched recursively)")
    p.add_argument("--database", help="Target database (default: $SNOWFLAKE_DATABASE or CREDITO)")
    p.add_argument("--replace-month", action="store_true",
                   help="Delete and reload each month in one transaction, and record it in raw.load_log")
    args = p.parse_args(argv)

    db = (args.database or os.getenv("SNOWFLAKE_DATABASE", "CREDITO")).lower()
    source_dir = Path(args.source_dir).expanduser()
    files = []
    for month in month_range(args.start, args.end):
        path = find_local(source_dir, month)
        if path is None:
            print(f"{month:%Y-%m}: file not found under {source_dir}", file=sys.stderr)
            continue
        files.append((month, path))
    if not files:
        print("Nothing to load", file=sys.stderr)
        return 1

    con = connect(db)
    cur = con.cursor()
    try:
        if args.replace_month:
            for month, path in files:
                replace_month(cur, db, month, path)
        else:
            load_new_files(cur, db, files)

        total = cur.execute(
            f"select count(*), count(distinct _source_file) from {db}.raw.scr_data"
        ).fetchone()
        print(f"\n{db.upper()}.RAW now has {total[0]:,} rows from {total[1]} files")
    finally:
        cur.close()
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
