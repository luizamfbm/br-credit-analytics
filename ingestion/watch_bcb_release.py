"""Open a GitHub issue when the Central Bank publishes a new SCR.data batch.

Runs weekly on GitHub Actions (see .github/workflows/bcb_release_watch.yml), so it works
with no computer on. It only sends HEAD requests: nothing is downloaded. Each yearly ZIP
version is identified by its ETag (or Last-Modified). One issue per version, labelled
`bcb-release`; a version that already has an issue, open or closed, is skipped.

The BCB publishes in batches (for example Jan-Jul in one release, Aug-Dec in January),
so the previous year's file is checked too.

    GH_TOKEN=... python ingestion/watch_bcb_release.py            # needs the gh CLI
    python ingestion/watch_bcb_release.py --dry-run               # print only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date

from download_scr import BASE_URL, remote_signature  # same folder

LABEL = "bcb-release"


def release_id(year: int, sig: dict) -> str:
    raw = sig.get("ETag") or sig.get("Last-Modified") or sig.get("Content-Length", "unknown")
    return f"scrdata-{year}-" + re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-")


def known_ids() -> set[str]:
    out = subprocess.run(
        ["gh", "issue", "list", "--label", LABEL, "--state", "all", "--limit", "500", "--json", "body"],
        check=True, capture_output=True, text=True).stdout
    return {m for issue in json.loads(out) for m in re.findall(r"release-id: (\S+)", issue["body"])}


def issue_body(year: int, sig: dict, rid: str) -> str:
    return f"""The Central Bank published a new version of `scrdata_{year}.zip`.

| | |
| --- | --- |
| File | {BASE_URL.format(year=year)} |
| Last-Modified | {sig.get('Last-Modified', 'not sent')} |
| Size | {sig.get('Content-Length', 'not sent')} bytes |

**To load it locally (DuckDB):**

```bash
rm -f data/zips/scrdata_{year}.zip   # drop the cached old version
python ingestion/download_scr.py --start {year}-01 --end {year}-12 --no-upload
python ingestion/load_local_duckdb.py data/raw/scr_data
cd dbt && DBT_TARGET=local dbt build && cd ..
python -m ai.run --target local
```

The load is idempotent: months already loaded are replaced, not duplicated, and the
incremental fact reprocesses only the months whose files changed.

release-id: {rid}
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    today = date.today()
    found = []
    for year in (today.year - 1, today.year):
        sig = remote_signature(year)
        if sig is None:
            print(f"{year}: not published")
            continue
        rid = release_id(year, sig)
        print(f"{year}: {sig} -> {rid}")
        found.append((year, sig, rid))

    if args.dry_run:
        return 0

    subprocess.run(["gh", "label", "create", LABEL, "--color", "1F4E8C",
                    "--description", "New Central Bank SCR.data release", "--force"], check=True)
    seen = known_ids()
    for year, sig, rid in found:
        if rid in seen:
            print(f"{year}: already reported")
            continue
        title = f"New SCR.data release: {year} file updated ({sig.get('Last-Modified', 'date not sent')})"
        subprocess.run(["gh", "issue", "create", "--title", title, "--label", LABEL,
                        "--body", issue_body(year, sig, rid)], check=True)
        print(f"{year}: issue opened")
    return 0


if __name__ == "__main__":
    sys.exit(main())
