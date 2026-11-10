"""Did the Novo Desenrola Brasil (May-Aug 2026) lower delinquency in the products it covered?

Difference in differences on marts.mart_desenrola_did (individuals only, from Jan 2025):

  A. Eligible products (credit card, overdraft, personal loans) vs control products
     (vehicle financing, real estate), program window vs before.
  B. Within eligible products: up to 5 minimum wages (could join the program) vs above
     (could not), program window vs before. Same products, so product-specific shocks
     cancel out: the stronger comparison.
  C. Pre-trend check: before the program, did the gaps already move? If they did, A and B
     are weaker, and the write-up has to say so.

Panel: one row per product group x income band x month ("cell"), rate in %. Regressions
use cell and month fixed effects, weights = outstanding balance, standard errors clustered
by cell. With 10 cells, treat the intervals as rough.

Hypothesis, written before running it: delinquency in the eligible group FALLS relative
to the comparison group during the program window (negative coefficient).

    python analysis/desenrola_did.py                          # main spec: pre-period from Jan 2025
    python analysis/desenrola_did.py --pre-start 2025-09      # robustness: stable pre-period only
    python analysis/desenrola_did.py --target dev             # Snowflake

The --pre-start robustness check was added AFTER seeing the main results (the gap jumped in
Aug 2025 and was flat from Sep 2025 to Apr 2026). Report it as robustness, next to the main
spec, never instead of it.

Writes docs/analysis/desenrola_results.json, docs/img/desenrola_gap.png and
dashboards/data/desenrola_monthly.csv (for Tableau).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402

from ai.warehouse import Warehouse  # noqa: E402

PROGRAM_START, PROGRAM_END = pd.Timestamp("2026-05-01"), pd.Timestamp("2026-08-31")


def load(target: str) -> pd.DataFrame:
    wh = Warehouse(target)
    try:
        rows = wh.query(
            "select month_date, product_group, product_role, income_band, period, "
            "outstanding_portfolio, nonperforming_portfolio from marts.mart_desenrola_did"
        )
    finally:
        wh.close()
    df = pd.DataFrame(rows, columns=["month_date", "product_group", "product_role", "income_band", "period",
                                     "outstanding", "nonperforming"])
    df["month_date"] = pd.to_datetime(df["month_date"])
    for c in ("outstanding", "nonperforming"):
        df[c] = df[c].astype(float)
    df = df[(df["income_band"] != "unknown") & (df["period"] != "post")]
    df["rate"] = 100 * df["nonperforming"] / df["outstanding"]
    df["cell"] = df["product_group"] + " | " + df["income_band"]
    df["program"] = (df["period"] == "program").astype(int)
    df["eligible"] = (df["product_role"] == "eligible").astype(int)
    df["low_income"] = (df["income_band"] == "up_to_5_mw").astype(int)
    df["t"] = (df["month_date"].dt.year - 2025) * 12 + df["month_date"].dt.month
    return df[df["outstanding"] > 0]


def did(df: pd.DataFrame, treat: str) -> dict:
    """Coefficient of treat x program with cell and month fixed effects."""
    model = smf.wls(f"rate ~ {treat}:program + C(cell) + C(month_date)", data=df, weights=df["outstanding"])
    fit = model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(df["cell"])[0]})
    name = f"{treat}:program"
    lo, hi = fit.conf_int().loc[name]
    return {"estimate_pp": round(fit.params[name], 3), "ci95_pp": [round(lo, 3), round(hi, 3)],
            "p_value": round(fit.pvalues[name], 4), "cells": int(df["cell"].nunique()),
            "months": int(df["month_date"].nunique())}


def pretrend(df: pd.DataFrame, treat: str) -> dict:
    """Before the program: did the treated group's rate already drift relative to the other?"""
    pre = df[df["program"] == 0]
    fit = smf.wls(f"rate ~ {treat}:t + C(cell) + C(month_date)", data=pre, weights=pre["outstanding"]).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(pre["cell"])[0]})
    name = f"{treat}:t"
    return {"slope_pp_per_month": round(fit.params[name], 4), "p_value": round(fit.pvalues[name], 4)}


def group_rates(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(["month_date", by], as_index=False)[["outstanding", "nonperforming"]].sum()
    g["rate"] = 100 * g["nonperforming"] / g["outstanding"]  # after aggregation, never averaged
    return g.pivot(index="month_date", columns=by, values="rate")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default="local", choices=["local", "dev"])
    p.add_argument("--pre-start", default="2025-01", help="First month of the pre-period, YYYY-MM")
    args = p.parse_args(argv)

    df = load(args.target)
    df = df[df["month_date"] >= pd.Timestamp(f"{args.pre_start}-01")]
    tag = "" if args.pre_start == "2025-01" else f"_pre_from_{args.pre_start}"
    within = df[df["eligible"] == 1]
    results = {
        "spec": "main" if not tag else f"robustness: pre-period from {args.pre_start} (chosen after seeing the main results)",
        "data": {"first_month": str(df["month_date"].min().date()), "last_month": str(df["month_date"].max().date()),
                 "program_window": [str(PROGRAM_START.date()), str(PROGRAM_END.date())]},
        "A_eligible_vs_control": {**did(df, "eligible"), "pretrend": pretrend(df, "eligible")},
        "B_low_vs_high_income_within_eligible": {**did(within, "low_income"), "pretrend": pretrend(within, "low_income")},
    }

    rates_a = group_rates(df.assign(group=df["product_role"]), "group")
    rates_b = group_rates(within.assign(group=within["income_band"]), "group")
    monthly = pd.DataFrame({
        "eligible_rate": rates_a["eligible"], "control_rate": rates_a["control"],
        "eligible_up_to_5_mw_rate": rates_b["up_to_5_mw"], "eligible_above_5_mw_rate": rates_b["above_5_mw"],
    }).round(3)
    monthly["gap_A_pp"] = (monthly["eligible_rate"] - monthly["control_rate"]).round(3)
    monthly["gap_B_pp"] = (monthly["eligible_up_to_5_mw_rate"] - monthly["eligible_above_5_mw_rate"]).round(3)

    out_json = ROOT / "docs" / "analysis" / f"desenrola_results{tag}.json"
    out_png = ROOT / "docs" / "img" / f"desenrola_gap{tag}.png"
    out_csv = ROOT / "dashboards" / "data" / f"desenrola_monthly{tag}.csv"
    for f in (out_json, out_png, out_csv):
        f.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2))
    monthly.to_csv(out_csv)

    # Each point sits in the middle of its month, so the shaded window covers exactly May to Aug.
    x = monthly.index.to_period("M").to_timestamp() + pd.Timedelta(days=14)
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
    for ax, gap, title in [
        (axes[0], "gap_A_pp", "A. Eligible minus control products (p.p.)"),
        (axes[1], "gap_B_pp", "B. Eligible products: up to 5 minimum wages minus above (p.p.)"),
    ]:
        ax.axvspan(PROGRAM_START, PROGRAM_END + pd.Timedelta(days=1), color="0.88", label="Program window (May to Aug 2026)")
        ax.plot(x, monthly[gap], color="#1F4E8C", marker="o", markersize=3)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(axis="y", color="0.9")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", frameon=False)
    fig.suptitle("Novo Desenrola Brasil: did the gaps move during the program?", x=0.02, ha="left", fontsize=13)
    fig.text(0.02, 0.01, "Delinquency rate gap, individuals only. Source: Banco Central do Brasil, SCR.data.",
             fontsize=8, color="0.4")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out_png, dpi=150)

    print(json.dumps(results, indent=2))
    print(f"\n{out_json}\n{out_png}\n{out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
