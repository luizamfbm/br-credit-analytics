"""Phase 3: LLM-written monthly summary, validated against the warehouse before publishing.

1. Build a small table of facts for the month from reporting.rpt_delinquency_monthly.
2. Ask an LLM for a short summary in JSON, with every number listed as a structured claim.
3. Recompute every claim with SQL. Publish only if all claims match.

Run locally against DuckDB (mock mode needs no API key; it includes one wrong claim on
purpose so you can see the validator block it):

    python ai/monthly_summary.py --month 2024-07 --mock
    ANTHROPIC_API_KEY=... python ai/monthly_summary.py --month 2024-07

Outputs land in ai/output/summary_<month>.json with the text, each claim and its verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

RPT = "reporting.rpt_delinquency_monthly"
DIMENSIONS = {"region", "product_group", "customer_type"}
RATE_TOLERANCE_PP = 0.05      # percentage points
BALANCE_TOLERANCE = 0.005     # 0.5 %


@dataclass
class Claim:
    metric: str                 # "nonperforming_rate_pct" or "outstanding_bn"
    month: str                  # "YYYY-MM"
    filters: dict               # e.g. {"region": "Northeast", "customer_type": "PF"}
    value: float
    verdict: str = "pending"    # ok | mismatch | unverifiable
    actual: float | None = None


def month_end_filter(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"year = {y} and month = {m}"


def compute(con, metric: str, month: str, filters: dict) -> float | None:
    if not set(filters) <= DIMENSIONS:
        return None
    where = [month_end_filter(month)] + [f"{k} = ?" for k in filters]
    params = list(filters.values())
    if metric == "nonperforming_rate_pct":
        sql = f"select 100 * sum(nonperforming_portfolio) / nullif(sum(outstanding_portfolio), 0) from {RPT} where {' and '.join(where)}"
    elif metric == "outstanding_bn":
        sql = f"select sum(outstanding_portfolio) / 1e9 from {RPT} where {' and '.join(where)}"
    else:
        return None
    row = con.execute(sql, params).fetchone()
    return None if row is None or row[0] is None else float(row[0])


def facts_for_prompt(con, month: str) -> list[dict]:
    """The only numbers the LLM is allowed to use."""
    out = [{"filters": {}, "nonperforming_rate_pct": compute(con, "nonperforming_rate_pct", month, {}),
            "outstanding_bn": compute(con, "outstanding_bn", month, {})}]
    for dim in sorted(DIMENSIONS):
        values = [r[0] for r in con.execute(f"select distinct {dim} from {RPT} where {month_end_filter(month)} order by 1").fetchall()]
        for v in values:
            f = {dim: v}
            out.append({"filters": f,
                        "nonperforming_rate_pct": round(compute(con, "nonperforming_rate_pct", month, f) or 0, 2),
                        "outstanding_bn": round(compute(con, "outstanding_bn", month, f) or 0, 1)})
    return out


PROMPT = """You write a short monthly note on the Brazilian credit portfolio for {month}.
Use ONLY the numbers in the FACTS below. Do not compute new numbers.

Return JSON only, in this shape:
{{"summary": "<3 to 4 sentences in English>",
  "claims": [{{"metric": "nonperforming_rate_pct" | "outstanding_bn", "month": "{month}",
              "filters": {{"region" | "product_group" | "customer_type": "<value>"}}, "value": <number>}}]}}
Every number in the summary must appear as one claim. Use empty filters for national totals.

FACTS:
{facts}
"""


def ask_llm(month: str, facts: list[dict]) -> dict:
    import anthropic  # pip install anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        max_tokens=1200,
        messages=[{"role": "user", "content": PROMPT.format(month=month, facts=json.dumps(facts, ensure_ascii=False))}],
    )
    text = msg.content[0].text.strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def mock_llm(month: str, facts: list[dict]) -> dict:
    """Deterministic stand-in for the LLM, with one deliberately wrong number."""
    national = facts[0]
    worst = max((f for f in facts if "region" in f["filters"]), key=lambda f: f["nonperforming_rate_pct"])
    claims = [
        {"metric": "outstanding_bn", "month": month, "filters": {}, "value": round(national["outstanding_bn"], 1)},
        {"metric": "nonperforming_rate_pct", "month": month, "filters": {}, "value": round(national["nonperforming_rate_pct"], 2)},
        {"metric": "nonperforming_rate_pct", "month": month, "filters": worst["filters"], "value": worst["nonperforming_rate_pct"]},
        {"metric": "nonperforming_rate_pct", "month": month, "filters": {"customer_type": "PF"}, "value": 1.23},  # wrong on purpose
    ]
    summary = (f"In {month}, the outstanding credit portfolio reached R$ {claims[0]['value']:,} billion, "
               f"with a nonperforming rate of {claims[1]['value']}%. The {worst['filters']['region']} region had the "
               f"highest rate, at {worst['nonperforming_rate_pct']}%. Individuals (PF) stood at 1.23%.")
    return {"summary": summary, "claims": claims}


def validate(con, claims: list[Claim]) -> list[Claim]:
    for c in claims:
        actual = compute(con, c.metric, c.month, c.filters)
        c.actual = None if actual is None else round(actual, 4)
        if actual is None:
            c.verdict = "unverifiable"
        elif c.metric == "nonperforming_rate_pct":
            c.verdict = "ok" if abs(actual - c.value) <= RATE_TOLERANCE_PP else "mismatch"
        else:
            c.verdict = "ok" if abs(actual - c.value) <= BALANCE_TOLERANCE * max(abs(actual), 1e-9) else "mismatch"
    return claims


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--db", default="data/credito.duckdb")
    p.add_argument("--mock", action="store_true", help="Use the deterministic mock instead of a real LLM")
    p.add_argument("--out-dir", default="ai/output")
    args = p.parse_args(argv)

    con = duckdb.connect(args.db, read_only=True)
    facts = facts_for_prompt(con, args.month)
    draft = mock_llm(args.month, facts) if args.mock else ask_llm(args.month, facts)
    claims = validate(con, [Claim(**{k: c[k] for k in ("metric", "month", "filters", "value")}) for c in draft["claims"]])

    publishable = bool(claims) and all(c.verdict == "ok" for c in claims)
    result = {
        "month": args.month,
        "summary": draft["summary"],
        "publishable": publishable,
        "claims": [asdict(c) for c in claims],
        "claim_accuracy": round(sum(c.verdict == "ok" for c in claims) / len(claims), 3) if claims else None,
    }
    out = Path(args.out_dir) / f"summary_{args.month}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    for c in claims:
        print(f"[{c.verdict:>12}] {c.metric} {c.filters or 'Brazil'}: claimed {c.value}, actual {c.actual}")
    print(f"\nPublishable: {publishable}  ->  {out}")
    return 0 if publishable else 2


if __name__ == "__main__":
    sys.exit(main())
