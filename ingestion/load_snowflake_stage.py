"""Load monthly SCR.data CSVs into Snowflake RAW through an internal stage.

Alternative to the S3 external stage (snowflake/02_s3_integration.sql) for accounts
where Snowflake cannot assume an IAM role, such as AWS free-plan accounts.
The raw files still land in S3 with ingestion/download_scr.py; this script copies the
same local files into Snowflake.

Flow: PUT each file to @credito.raw.scr_internal_stage/ano=YYYY/mes=MM/ (gzip-compressed
by Snowflake on upload), then one COPY INTO credito.raw.scr_data.

Run once snowflake/04_internal_stage.sql has been executed:

    set -a; source .env; set +a
    python ingestion/load_snowflake_stage.py --start 2024-01 --end 2026-07 --source-dir ~/Downloads

Safe to re-run: PUT skips files already in the stage and COPY skips files already loaded.
Authenticates as the DBT_SVC service user with the same key pair dbt uses.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from download_scr import find_local, month_range  # same folder

STAGE = "@credito.raw.scr_internal_stage"

COPY_SQL = f"""
copy into credito.raw.scr_data
from (
  select
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
    metadata$filename,
    metadata$start_scan_time
  from {STAGE}
)
pattern = '.*scrdata_[0-9]{{6}}[.]csv[.]gz'
on_error = 'abort_statement'
"""


def connect():
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
        database=os.getenv("SNOWFLAKE_DATABASE", "CREDITO"),
        schema="RAW",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", required=True, help="First month, YYYY-MM")
    p.add_argument("--end", required=True, help="Last month, YYYY-MM")
    p.add_argument("--source-dir", required=True, help="Folder with scrdata_YYYYMM.csv files (searched recursively)")
    args = p.parse_args(argv)

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

    con = connect()
    cur = con.cursor()
    try:
        for month, path in files:
            target = f"{STAGE}/ano={month.year}/mes={month.month:02d}/"
            row = cur.execute(f"put 'file://{path.resolve()}' {target} auto_compress=true overwrite=false").fetchone()
            print(f"{month:%Y-%m}: {row[6].lower()}")  # status column: UPLOADED or SKIPPED

        print("\nCOPY INTO credito.raw.scr_data ...")
        results = cur.execute(COPY_SQL).fetchall()
        # One row per file (file, status, rows_parsed, rows_loaded, ...), or a single
        # status row when there was nothing new to load.
        if results and len(results[0]) > 3:
            for r in results:
                print(f"  {r[0]}: {r[1]}, {r[3]:,} rows")
        else:
            print("  no new files: everything in the stage was already loaded")

        total = cur.execute(
            "select count(*), count(distinct _source_file) from credito.raw.scr_data"
        ).fetchone()
        print(f"\nRAW now has {total[0]:,} rows from {total[1]} files")
    finally:
        cur.close()
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
