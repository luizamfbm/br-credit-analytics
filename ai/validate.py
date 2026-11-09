"""Check every claim against the warehouse before anything is published.

A claim is rejected when:
  1. its metric_id is not in the catalog;
  2. its value differs from a FRESH computation of that metric (numbers: more than 0.05;
     text: a different name);
  3. its sentence contains a number that is not the claim's value (rounded to 1 decimal),
     a year, or "12" (as in "12 months"); or, for a text metric, does not contain the name;
  4. it is the rate OF a named group (top product, top state...) and the sentence does not
     name the group the warehouse says it is. Otherwise "Credit card had the highest rate,
     at 11.6%" would pass on the number alone.

The recomputation is injected (compute_fn), so tests run without a warehouse.
"""

from __future__ import annotations

import re
from typing import Callable

from ai.metrics import CATALOG

TOLERANCE = 0.05
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")


def _numbers_in(text: str) -> list[float]:
    out = []
    for raw in NUMBER.findall(text):
        n = float(raw.replace(",", "."))
        if raw.isdigit() and (1900 <= n <= 2100 or n == 12):
            continue  # a year, or "12 months"
        out.append(n)
    return out


def check(claim: dict, compute_fn: Callable[[str], object]) -> str | None:
    """None if the claim is valid, otherwise the reason it was rejected."""
    metric_id, value, text = claim.get("metric_id"), claim.get("value"), claim.get("text", "")
    if metric_id not in CATALOG:
        return f"unknown metric_id {metric_id!r}"
    truth = compute_fn(metric_id)

    if CATALOG[metric_id].unit == "text":
        if str(value).strip().lower() != str(truth).strip().lower():
            return f"value {value!r} but the warehouse says {truth!r}"
        if str(truth).lower() not in text.lower():
            return f"sentence does not name {truth!r}"
        if _numbers_in(text):
            return f"unexpected number in a text claim: {_numbers_in(text)}"
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return f"value {value!r} is not a number"
    if truth is None or abs(value - float(truth)) > TOLERANCE:
        return f"value {value} but the warehouse says {truth}"
    for n in _numbers_in(text):
        if abs(abs(n) - round(abs(float(truth)), 1)) > TOLERANCE:
            return f"sentence has {n}, but the value is {truth}"
    if CATALOG[metric_id].names:
        name = compute_fn(CATALOG[metric_id].names)
        if str(name).lower() not in text.lower():
            return f"sentence must name {name!r}, the group this value belongs to"
    return None


def validate(claims: list[dict], compute_fn: Callable[[str], object]) -> tuple[list[dict], list[dict]]:
    accepted, rejected = [], []
    for claim in claims:
        reason = check(claim, compute_fn)
        (rejected if reason else accepted).append({**claim, **({"reason": reason} if reason else {})})
    return accepted, rejected
