"""Export the reporting layer to a CSV that Tableau Public can read.

Tableau Public cannot connect to Snowflake, so the dashboard reads this extract.
Credentials stay out of the published workbook.

    set -a; source .env; set +a
    python dashboards/export_reporting.py                 # CREDITO (default)
    python dashboards/export_reporting.py --database CREDITO_REPLAY

Writes dashboards/data/reporting_monthly.csv and prints the columns, row count and
latest reference month, so the dashboard's "data as of" label can be checked.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingestion"))
from load_snowflake_stage import connect  # noqa: E402  same key pair as dbt

TABLE = "reporting.rpt_delinquency_monthly"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database", default=os.getenv("SNOWFLAKE_DATABASE", "CREDITO"))
    p.add_argument("--out", default=str(ROOT / "dashboards" / "data" / "reporting_monthly.csv"))
    args = p.parse_args(argv)

    db = args.database.lower()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    con = connect(db)
    cur = con.cursor()
    try:
        cur.execute(f"select * from {db}.{TABLE} order by 1")
        columns = [c[0].lower() for c in cur.description]
        rows = 0
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            for batch in iter(lambda: cur.fetchmany(10_000), []):
                writer.writerows(batch)
                rows += len(batch)
    finally:
        cur.close()
        con.close()

    print(f"{rows:,} rows -> {out}")
    print("columns:", ", ".join(columns))
    date_cols = [c for c in columns if "month" in c or "date" in c]
    if date_cols:
        latest = max(r[date_cols[0]] for r in csv.DictReader(open(out, encoding="utf-8")))
        print(f"latest {date_cols[0]}: {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
