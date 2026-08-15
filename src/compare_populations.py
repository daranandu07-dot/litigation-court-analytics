"""
Litigation & Court Data Analytics — population comparison
=========================================================

Compares the commercial disputes docket against the general civil claims
cohort, using the same survival methodology on both.

The question this answers
-------------------------
"How long does a civil claim take?"

It has no single answer, and the reason is not that some courts are faster
than others. It is that the two populations are made of different things.

Roughly six in seven County Court claims are never defended. They end
administratively — a default judgment, or the defendant simply pays — without
a judge exercising any discretion. Commercial disputes are the opposite: every
one is defended, by represented parties, over years.

So a national median duration is not a slow version of a commercial median. It
is a statistic about a different activity that happens to share a name. Any
figure quoted across both is a composition artefact.

Usage
-----
    python src/compare_populations.py

Outputs
-------
    results/population_comparison.csv
    charts/chart_populations.html
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from lifelines import KaplanMeierFitter

COMMERCIAL_FILE = ROOT / "data" / "litigation_court_data.csv"
GENERAL_FILE = ROOT / "data" / "general_civil_claims.csv"
RESULTS_DIR = ROOT / "results"
CHART_DIR = ROOT / "charts"

# Dispositions in which a judge decided a contested question at a hearing.
ADJUDICATED = {"Trial Judgment"}

# Dispositions requiring no judicial determination at all: a default judgment
# is entered administratively on the papers once the CPR 10.3 period expires,
# and a claim paid or discontinued never troubles a judge in the first place.
# Nothing in the commercial docket falls into this category by construction —
# every case there is defended.
ADMINISTRATIVE = {"Default Judgment", "Paid or discontinued"}


def km_summary(df: pd.DataFrame, label: str) -> dict:
    kmf = KaplanMeierFitter()
    kmf.fit(df["days_to_resolution"], df["event_observed"], label=label)

    resolved = df[df["event_observed"] == 1]

    return {
        "population": label,
        "n": len(df),
        "resolved": int(df["event_observed"].sum()),
        "censored_share": float(1 - df["event_observed"].mean()),
        "naive_median_days": float(resolved["days_to_resolution"].median()),
        "km_median_days": float(kmf.median_survival_time_),
        "tried_share": float(resolved["disposition_type"].isin(ADJUDICATED).mean()),
        "administrative_share": float(
            resolved["disposition_type"].isin(ADMINISTRATIVE).mean()
        ),
        "curve": kmf.survival_function_,
    }


def build_chart(rows: list[dict]) -> None:
    os.makedirs(CHART_DIR, exist_ok=True)
    fig = go.Figure()

    palette = {
        "Commercial disputes": "#1f4e79",
        "General civil claims": "#c0504d",
        "General civil — defended only": "#e8a33d",
    }

    for r in rows:
        curve = r["curve"]
        fig.add_trace(go.Scatter(
            x=curve.index, y=curve.iloc[:, 0] * 100,
            mode="lines", name=r["population"],
            line=dict(width=2.5, color=palette.get(r["population"])),
            hovertemplate="%{x:.0f} days<br>%{y:.1f}% still open<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text="<b>Two civil populations, same methodology</b><br>"
                 "<sup>Probability a claim is still open, by days since issue</sup>",
            x=0.02, xanchor="left",
        ),
        xaxis=dict(title="Days since claim issued", range=[0, 1100]),
        yaxis=dict(title="Still open (%)", range=[0, 100], ticksuffix="%"),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, x=0),
        margin=dict(t=90, b=140, l=70, r=40),
        height=620,
    )

    fig.add_annotation(
        text=("Synthetic data. The general civil cohort is calibrated to Ministry of Justice<br>"
              "Civil Justice Statistics Quarterly (Jan–Mar 2026); the commercial docket is a<br>"
              "deliberately unrepresentative tail. The gap between the two red lines is the<br>"
              "whole point: it is composition, not court speed."),
        xref="paper", yref="paper", x=0, y=-0.40,
        showarrow=False, xanchor="left", yanchor="top",
        font=dict(size=11, color="#666"), align="left",
    )

    path = CHART_DIR / "chart_populations.html"
    fig.write_html(path, include_plotlyjs="cdn", full_html=True,
                   default_height="100%", default_width="100%",
                   div_id="chart-chart_populations")
    print(f"  [saved] {path}")


def main() -> None:
    commercial = pd.read_csv(COMMERCIAL_FILE)
    general = pd.read_csv(GENERAL_FILE)

    rows = [
        km_summary(commercial, "Commercial disputes"),
        km_summary(general, "General civil claims"),
        km_summary(general[general["defended"]], "General civil — defended only"),
    ]

    table = pd.DataFrame([{k: v for k, v in r.items() if k != "curve"} for r in rows])

    print("\n" + "=" * 78)
    print("POPULATION COMPARISON")
    print("=" * 78 + "\n")
    print(table.round(3).to_string(index=False))

    comm, gen, gen_def = rows[0], rows[1], rows[2]
    ratio = comm["km_median_days"] / gen["km_median_days"]
    comp_ratio = gen_def["km_median_days"] / gen["km_median_days"]

    print(f"""
Reading of the above
--------------------
1. A commercial dispute runs {ratio:.0f}x longer than a typical civil claim
   ({comm['km_median_days']:.0f} days against {gen['km_median_days']:.0f}).

2. That comparison is close to meaningless. The general cohort is dominated by
   claims nobody defends. Restrict it to DEFENDED claims only and the median
   rises to {gen_def['km_median_days']:.0f} days — {comp_ratio:.0f}x the
   all-claims figure, from the same courts under the same rules. Most of the
   apparent gap is COMPOSITION, not speed.

3. {gen['administrative_share']:.1%} of resolved general civil claims required
   no judicial determination at all — a default judgment entered on the papers,
   or a claim paid or discontinued. In the commercial docket that figure is
   {comm['administrative_share']:.1%}, by construction: every case is defended.
   This is the cleanest separation between the two populations.

4. Worth noting against intuition: BOTH populations rarely reach trial.
   {gen['tried_share']:.1%} of general claims and {comm['tried_share']:.1%} of
   commercial ones ended in a trial judgment. Commercial disputes are not
   meaningfully more likely to be adjudicated — they are more likely to be
   fought at length and then settled anyway.

The practical consequence: a national average duration cannot be quoted to a
commercial client, and a commercial average cannot be quoted as a statistic
about the civil justice system. They describe different activities that happen
to share a name.
""")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = RESULTS_DIR / "population_comparison.csv"
    table.to_csv(out, index=False)
    print(f"Written → {out}")

    build_chart(rows)


if __name__ == "__main__":
    main()
