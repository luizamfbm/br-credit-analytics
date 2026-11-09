"""Closed catalog of metrics the summary is allowed to cite.

Each metric is computed from reporting.rpt_delinquency_monthly with the rate always taken
AFTER aggregation: sum(nonperforming) / sum(outstanding). Rates are in percent, changes in
percentage points (p.p.), both rounded to 2 decimals. Text metrics hold a name.

The LLM never computes anything: it can only cite a metric_id from this catalog, and the
validator recomputes that metric with a fresh query before anything is published.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Callable

TABLE = "reporting.rpt_delinquency_monthly"
RATE = "round(100.0 * sum(nonperforming_portfolio) / nullif(sum(outstanding_portfolio), 0), 2)"


def same_month_last_year(m: date) -> date:
    y = m.year - 1
    return date(y, m.month, calendar.monthrange(y, m.month)[1])


def lit(d: date) -> str:
    """A date literal that DuckDB and Snowflake both accept. Dates come from our own queries."""
    return f"date '{d.isoformat()}'"


def latest_month(wh) -> date:
    (value,) = wh.query(f"select max(month_date) from {TABLE}")[0]
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


@dataclass(frozen=True)
class Metric:
    metric_id: str
    description: str
    unit: str  # "%", "p.p." or "text"
    compute: Callable  # (wh, month) -> float | str
    names: str | None = None  # text metric whose value the sentence must name (a rate OF something)


def _scalar(wh, sql):
    value = wh.query(sql)[0][0]
    return float(value) if value is not None else None


def _rate(wh, m, where="1 = 1"):
    return _scalar(wh, f"select {RATE} from {TABLE} where month_date = {lit(m)} and {where}")


def _ranked(wh, column, m):
    """(name, rate) of the group with the highest rate in month m."""
    row = wh.query(
        f"select {column}, {RATE} as rate from {TABLE} where month_date = {lit(m)} "
        f"group by 1 order by rate desc, 1 limit 1"
    )[0]
    return row[0], float(row[1])


def _fastest_rising_product(wh, m):
    """(name, change in p.p.) of the product group whose rate rose most in 12 months."""
    prev = same_month_last_year(m)
    row = wh.query(
        f"""
        with now as (
            select product_group, {RATE} as rate from {TABLE} where month_date = {lit(m)} group by 1
        ), before as (
            select product_group, {RATE} as rate from {TABLE} where month_date = {lit(prev)} group by 1
        )
        select now.product_group, round(now.rate - before.rate, 2) as change_pp
        from now join before using (product_group)
        order by change_pp desc, 1 limit 1
        """
    )[0]
    return row[0], float(row[1])


def _change(wh, m, where="1 = 1"):
    now, before = _rate(wh, m, where), _rate(wh, same_month_last_year(m), where)
    return round(now - before, 2)


CATALOG: dict[str, Metric] = {
    m.metric_id: m
    for m in [
        Metric("rate_total", "Delinquency rate of the whole system in the month", "%",
               lambda wh, m: _rate(wh, m)),
        Metric("rate_individuals", "Delinquency rate of individuals (PF)", "%",
               lambda wh, m: _rate(wh, m, "customer_type = 'PF'")),
        Metric("rate_companies", "Delinquency rate of companies (PJ)", "%",
               lambda wh, m: _rate(wh, m, "customer_type = 'PJ'")),
        Metric("change_12m_total_pp", "Change in the system rate vs the same month last year", "p.p.",
               lambda wh, m: _change(wh, m)),
        Metric("change_12m_individuals_pp", "Change in the individuals rate vs the same month last year", "p.p.",
               lambda wh, m: _change(wh, m, "customer_type = 'PF'")),
        Metric("change_12m_companies_pp", "Change in the companies rate vs the same month last year", "p.p.",
               lambda wh, m: _change(wh, m, "customer_type = 'PJ'")),
        Metric("top_product", "Product group with the highest rate", "text",
               lambda wh, m: _ranked(wh, "product_group", m)[0]),
        Metric("top_product_rate", "Rate of the product group with the highest rate", "%",
               lambda wh, m: _ranked(wh, "product_group", m)[1], names="top_product"),
        Metric("fastest_rising_product", "Product group whose rate rose the most in 12 months", "text",
               lambda wh, m: _fastest_rising_product(wh, m)[0]),
        Metric("fastest_rising_product_change_pp", "How much that product group's rate rose in 12 months", "p.p.",
               lambda wh, m: _fastest_rising_product(wh, m)[1], names="fastest_rising_product"),
        Metric("top_state", "State with the highest rate", "text",
               lambda wh, m: _ranked(wh, "state_name", m)[0]),
        Metric("top_state_rate", "Rate of the state with the highest rate", "%",
               lambda wh, m: _ranked(wh, "state_name", m)[1], names="top_state"),
    ]
}


def compute(metric_id: str, wh, month: date):
    return CATALOG[metric_id].compute(wh, month)
