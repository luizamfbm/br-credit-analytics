"""Export the reporting layer to a CSV that Tableau Public can read.

Tableau Public cannot connect to a warehouse, so the dashboard reads this extract.
Credentials stay out of the published workbook.

    python dashboards/export_reporting.py                       # local DuckDB (default)
    set -a; source .env; set +a
    python dashboards/export_reporting.py --target dev          # Snowflake, CREDITO
    python dashboards/export_reporting.py --target replay       # Snowflake, CREDITO_REPLAY

Writes dashboards/data/reporting_monthly.csv and prints the row count and the latest
reference month, so the dashboard's "data as of" label can be checked.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "reporting.rpt_delinquency_monthly"


def rows_from_duckdb():
    import duckdb

    path = os.getenv("DUCKDB_PATH", str(ROOT / "data" / "credito.duckdb"))
    con = duckdb.connect(path, read_only=True)
    try:
        cur = con.execute(f"select * from {TABLE} order by 1")
        yield [c[0].lower() for c in cur.description]
        while batch := cur.fetchmany(10_000):
            yield from batch
    finally:
        con.close()


def rows_from_snowflake(database: str):
    sys.path.insert(0, str(ROOT / "ingestion"))
    from load_snowflake_stage import connect  # same key pair as dbt

    db = database.lower()
    con = connect(db)
    cur = con.cursor()
    try:
        cur.execute(f"select * from {db}.{TABLE} order by 1")
        yield [c[0].lower() for c in cur.description]
        for batch in iter(lambda: cur.fetchmany(10_000), []):
            yield from batch
    finally:
        cur.close()
        con.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default="local", choices=["local", "dev", "replay"])
    p.add_argument("--out", default=str(ROOT / "dashboards" / "data" / "reporting_monthly.csv"))
    args = p.parse_args(argv)

    if args.target == "local":
        source = rows_from_duckdb()
    else:
        database = "CREDITO_REPLAY" if args.target == "replay" else os.getenv("SNOWFLAKE_DATABASE", "CREDITO")
        source = rows_from_snowflake(database)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = next(source)
    month_idx = columns.index("month_date") if "month_date" in columns else None
    rows, latest = 0, None
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in source:
            writer.writerow(row)
            rows += 1
            if month_idx is not None and (latest is None or row[month_idx] > latest):
                latest = row[month_idx]

    print(f"{rows:,} rows -> {out}")
    print("columns:", ", ".join(columns))
    if latest is not None:
        print(f"latest month_date: {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
