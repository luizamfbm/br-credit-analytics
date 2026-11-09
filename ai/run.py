"""Monthly LLM summary, validated against the warehouse before it is published.

    python -m ai.run                     # local DuckDB, latest month
    python -m ai.run --target dev        # Snowflake
    python -m ai.run --dry-run           # print the facts only, no LLM call
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ai.build_facts import build_facts
from ai.metrics import compute, latest_month
from ai.publish import TooFewClaims, publish
from ai.validate import validate
from ai.warehouse import Warehouse
from ai.write_summary import DEFAULT_MODEL, write_summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default=os.getenv("DBT_TARGET", "local"), choices=["local", "dev", "replay"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    wh = Warehouse(args.target)
    try:
        month = latest_month(wh)
        facts = build_facts(wh, month)
        print(f"Month: {month:%Y-%m}\n" + json.dumps(facts, indent=2, default=str, ensure_ascii=False))
        if args.dry_run:
            return 0

        model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
        claims = write_summary(facts, month, model=model)
        # Fresh queries, not the facts sent to the model: the check is independent.
        accepted, rejected = validate(claims, lambda metric_id: compute(metric_id, wh, month))
        for c in rejected:
            print(f"REJECTED: {c['text']}  ->  {c['reason']}")
        path = publish(month, accepted, rejected, model)
        print(f"\n{len(accepted)} accepted, {len(rejected)} rejected -> {path}")
        return 0
    except TooFewClaims as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        wh.close()


if __name__ == "__main__":
    sys.exit(main())
