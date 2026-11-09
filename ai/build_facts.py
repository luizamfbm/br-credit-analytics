"""Compute every metric in the catalog for one month: the only facts the LLM receives."""

from __future__ import annotations

from datetime import date

from ai.metrics import CATALOG, compute


def build_facts(wh, month: date) -> list[dict]:
    return [
        {"metric_id": m.metric_id, "description": m.description, "unit": m.unit,
         "value": compute(m.metric_id, wh, month)}
        for m in CATALOG.values()
    ]
