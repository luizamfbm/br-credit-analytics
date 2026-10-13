"""Download monthly SCR.data files from the Banco Central do Brasil and land them in S3.

Source: https://dadosabertos.bcb.gov.br/dataset/scr_data (license: ODbL)
The BCB publishes one ZIP per year with one CSV per month inside.

Examples
--------
# Download Jan/2024 to Dec/2025, save locally and upload to S3
python ingestion/download_scr.py --start 2024-01 --end 2025-12 --bucket my-bucket

# Only save locally (no AWS needed), e.g. to test with DuckDB
python ingestion/download_scr.py --start 2024-07 --end 2024-07 --no-upload

# Already downloaded and unzipped the yearly files yourself? Point to that folder.
# Files named scrdata_YYYYMM.csv are found anywhere under it and uploaded as they are.
python ingestion/download_scr.py --start 2024-01 --end 2026-07 --source-dir ~/Downloads

Design notes
------------
* Idempotent: a month always goes to the same S3 key, so re-running overwrites it.
* Raw files are stored exactly as published (no parsing, no re-encoding).
* Every file is logged with row count and MD5 so loads can be audited.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://www.bcb.gov.br/pda/desig/scrdata_{year}.zip"
DEFAULT_PREFIX = "raw/scr_data"
MONTH_IN_NAME = re.compile(r"(\d{6})")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("download_scr")


def month_range(start: str, end: str) -> list[date]:
    """Inclusive list of first-of-month dates between two YYYY-MM strings."""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def download_year_zip(year: int, cache_dir: Path) -> Path:
    """Stream the yearly ZIP to disk once; reuse it if already downloaded."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"scrdata_{year}.zip"
    if target.exists() and target.stat().st_size > 0:
        log.info("Using cached %s", target)
        return target
    url = BASE_URL.format(year=year)
    log.info("Downloading %s", url)
    tmp = target.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.rename(target)
    return target


def extract_month(zip_path: Path, month: date, out_dir: Path) -> Path | None:
    """Extract the CSV for one month from the yearly ZIP. Returns None if not published yet."""
    wanted = f"{month.year}{month.month:02d}"
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        match = [n for n in members if MONTH_IN_NAME.search(Path(n).name) and MONTH_IN_NAME.search(Path(n).name).group(1) == wanted]
        if not match:
            log.warning("Month %s not found in %s (members: %s)", wanted, zip_path.name, members[:3])
            return None
        dest_dir = out_dir / f"ano={month.year}" / f"mes={month.month:02d}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"scrdata_{wanted}.csv"
        with zf.open(match[0]) as src, open(dest, "wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                dst.write(chunk)
    return dest


def find_local(source_dir: Path, month: date) -> Path | None:
    """Find an already-extracted scrdata_YYYYMM.csv anywhere under source_dir."""
    hits = sorted(source_dir.rglob(f"scrdata_{month.year}{month.month:02d}.csv"))
    return hits[0] if hits else None


def describe(path: Path) -> tuple[int, str]:
    """Row count (excluding header) and MD5 of a file."""
    md5 = hashlib.md5()
    lines = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            md5.update(chunk)
            lines += chunk.count(b"\n")
    return max(lines - 1, 0), md5.hexdigest()


def upload(path: Path, bucket: str, prefix: str, month: date) -> str:
    import boto3  # imported here so --no-upload works without AWS installed

    key = f"{prefix}/ano={month.year}/mes={month.month:02d}/{path.name}"
    boto3.client("s3").upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", required=True, help="First month, YYYY-MM")
    p.add_argument("--end", required=True, help="Last month, YYYY-MM")
    p.add_argument("--bucket", default=os.getenv("SCR_BUCKET"), help="S3 bucket (or set SCR_BUCKET)")
    p.add_argument("--prefix", default=DEFAULT_PREFIX)
    p.add_argument("--data-dir", default="data", help="Local folder for the zip cache and extracted CSVs")
    p.add_argument("--no-upload", action="store_true", help="Only save locally")
    p.add_argument("--source-dir", help="Use CSVs already extracted under this folder instead of downloading")
    args = p.parse_args(argv)

    if not args.no_upload and not args.bucket:
        p.error("--bucket (or SCR_BUCKET) is required unless --no-upload is set")

    data_dir = Path(args.data_dir)
    months = month_range(args.start, args.end)
    missing = []
    source_dir = Path(args.source_dir).expanduser() if args.source_dir else None
    for month in months:
        if source_dir:
            csv_path = find_local(source_dir, month)
        else:
            zip_path = download_year_zip(month.year, data_dir / "zips")
            csv_path = extract_month(zip_path, month, data_dir / "raw" / "scr_data")
        if csv_path is None:
            missing.append(month.strftime("%Y-%m"))
            continue
        rows, digest = describe(csv_path)
        msg = f"{month:%Y-%m}: {rows:,} rows, md5={digest}, local={csv_path}"
        if not args.no_upload:
            msg += f", s3={upload(csv_path, args.bucket, args.prefix, month)}"
        log.info(msg)

    if missing:
        log.warning("Not available yet: %s", ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
