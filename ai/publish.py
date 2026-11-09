"""Write the validated summary to docs/summaries/YYYY-MM.md and log the rejected claims."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_ACCEPTED = 3


class TooFewClaims(Exception):
    pass


def publish(month: date, accepted: list[dict], rejected: list[dict], model: str) -> Path:
    log_dir = ROOT / "ai" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (log_dir / f"{month:%Y-%m}_{stamp}.json").write_text(
        json.dumps({"month": f"{month:%Y-%m}", "model": model, "accepted": accepted, "rejected": rejected},
                   indent=2, default=str))

    if len(accepted) < MIN_ACCEPTED:
        raise TooFewClaims(f"only {len(accepted)} claims passed validation; nothing published")

    out = ROOT / "docs" / "summaries" / f"{month:%Y-%m}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- {c['text']}" for c in accepted)
    out.write_text(
        f"# Credit delinquency in Brazil, {month:%B %Y}\n\n{body}\n\n"
        f"---\n*Written by an LLM ({model}) from the warehouse's metric catalog. "
        f"{len(accepted)} claims validated against the warehouse, {len(rejected)} rejected. "
        f"Source: Banco Central do Brasil, SCR.data.*\n")
    return out
