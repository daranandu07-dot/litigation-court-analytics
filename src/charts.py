"""
Litigation & Court Data Analytics — Phase 3: Interactive Visualisations
======================================================================

Builds four standalone, self-contained Plotly HTML files in `charts/`, each
sized and styled for <iframe> embedding in a Framer case study page.

  chart_duration.html   - box + violin of time to resolution by venue/complexity
  chart_judges.html     - summary-judgment grant rate by judge, Wilson CIs
  chart_survival.html   - Kaplan-Meier curves with 365/540/720-day horizons
  chart_financial.html  - claim vs award scatter with OLS trendlines

Every chart carries its own caveat annotation. A chart that travels away from
its source (which is exactly what embedding does) has to explain itself.

Usage
-----
    python src/generate_dataset.py
    python src/analysis.py
    python src/charts.py

Embedding
---------
    <iframe src="chart_survival.html" width="100%" height="620"
            style="border:0;" loading="lazy"></iframe>
"""

from __future__ import annotations

import os

from pathlib import Path

# Resolve paths relative to the repository root, not the working
# directory, so the scripts run correctly from anywhere.
ROOT = Path(__file__).resolve().parents[1]

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

DATA_FILE = ROOT / "data" / "litigation_court_data.csv"
RESULTS_DIR = ROOT / "results"
CHART_DIR = ROOT / "charts"

COMPLEXITY_ORDER = ["Low", "Medium", "High"]
HORIZONS = [365, 540, 720]

# ---------------------------------------------------------------------------
# THEME
# ---------------------------------------------------------------------------

INK = "#0B0F14"        # page background
PANEL = "#111820"      # plot area
TEXT = "#E6EDF3"
MUTED = "#8B98A5"
GRID = "rgba(255,255,255,0.07)"

TEAL = "#2DD4BF"
AMBER = "#FBBF24"
CORAL = "#F87171"
BLUE = "#60A5FA"
VIOLET = "#A78BFA"

COMPLEXITY_COLORS = {"Low": TEAL, "Medium": AMBER, "High": CORAL}
DISPOSITION_COLORS = {"Settled": TEAL, "Trial Judgment": VIOLET, "Dismissed": MUTED}

FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif"

TEMPLATE = go.layout.Template(
    layout=dict(
        paper_bgcolor=INK,
        plot_bgcolor=PANEL,
        font=dict(family=FONT, size=13, color=TEXT),
        title=dict(font=dict(size=19, color=TEXT), x=0.012, xanchor="left", y=0.955),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID,
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED))),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID,
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED))),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT),
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        hoverlabel=dict(bgcolor="#1C2530", font=dict(family=FONT, color=TEXT),
                        bordercolor="rgba(255,255,255,0.15)"),
        margin=dict(l=70, r=40, t=95, b=90),
    )
)
pio.templates["litops"] = TEMPLATE

CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def caption(fig: go.Figure, y: float, text: str) -> None:
    """Footnote pinned below the plot — travels with the chart when embedded.

    `y` is in paper coordinates and must be tuned per chart: axis tick labels
    and rotated categories eat into the bottom margin by different amounts.
    """
    fig.add_annotation(
        text=text, xref="paper", yref="paper", x=0, y=y,
        showarrow=False, xanchor="left", yanchor="top",
        font=dict(size=11, color=MUTED), align="left",
    )


def save(fig: go.Figure, name: str) -> str:
    os.makedirs(CHART_DIR, exist_ok=True)
    path = os.path.join(CHART_DIR, name)
    fig.update_layout(template="litops")
    fig.write_html(path, include_plotlyjs="cdn", full_html=True,
                   config=CONFIG, default_height="100%", default_width="100%")
    size_kb = os.path.getsize(path) / 1024
    print(f"  [saved] {path}  ({size_kb:.0f} KB)")
    return path


# ---------------------------------------------------------------------------
# 1. DURATION DISTRIBUTION
# ---------------------------------------------------------------------------

def chart_duration(df: pd.DataFrame) -> None:
    res = df[df["event_observed"] == 1].copy()

    order = (res.groupby("court_venue")["days_to_resolution"]
                .median().sort_values(ascending=False).index.tolist())

    fig = px.box(
        res, x="court_venue", y="days_to_resolution", color="case_complexity",
        category_orders={"court_venue": order, "case_complexity": COMPLEXITY_ORDER},
        color_discrete_map=COMPLEXITY_COLORS, points=False,
        labels={"court_venue": "", "days_to_resolution": "Days to resolution",
                "case_complexity": "Complexity"},
    )
    # NOTE: do not set an explicit trace `width` here. It overrides the
    # group offset that boxmode="group" applies, which silently stacks the
    # three complexity boxes on top of each other at the same x position.
    fig.update_traces(
        marker=dict(line=dict(width=0)), line=dict(width=1.6),
        hovertemplate="<b>%{x}</b><br>Median %{median:.0f} d<br>"
                      "IQR %{q1:.0f}–%{q3:.0f} d<extra></extra>",
    )

    # One-year reference line — the horizon most clients actually care about.
    fig.add_hline(y=365, line_dash="dot", line_color=MUTED, line_width=1,
                  annotation_text="1 year", annotation_position="top left",
                  annotation_font=dict(color=MUTED, size=11))

    fig.update_layout(
        title="Time to Resolution by Court and Case Complexity<br>"
              f"<span style='font-size:13px;color:{MUTED}'>"
              "Resolved cases only · box = IQR, line = median</span>",
        yaxis=dict(title="Days to resolution", rangemode="tozero"),
        boxmode="group", boxgap=0.28, boxgroupgap=0.12, height=690,
        margin=dict(l=70, r=40, t=95, b=205),
    )
    fig.update_xaxes(tickangle=-20)

    caption(fig, -0.33,
            "Open cases are excluded, so these medians understate true duration — "
            "most severely for High complexity (45.6% still open at snapshot).<br>"
            "See the survival chart for censoring-corrected figures. "
            "Synthetic data; illustrative of method, not of any real court.")
    save(fig, "chart_duration.html")


# ---------------------------------------------------------------------------
# 2. JUDGE VARIANCE
# ---------------------------------------------------------------------------

def chart_judges(judges: pd.DataFrame, panel_rate: float) -> None:
    d = judges.sort_values("grant_rate").copy()
    d["label"] = d["judge_id"] + "  ·  " + d["court_venue"].str.replace(
        "US District Court — ", "", regex=False)

    colors = [CORAL if o else BLUE for o in d["outlier"]]

    fig = go.Figure(
        go.Bar(
            x=d["grant_rate"], y=d["label"], orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            error_x=dict(
                type="data", symmetric=False,
                array=(d["ci_high"] - d["grant_rate"]),
                arrayminus=(d["grant_rate"] - d["ci_low"]),
                color="rgba(255,255,255,0.45)", thickness=1.3, width=4,
            ),
            customdata=np.stack([d["motions"], d["granted"],
                                 d["ci_low"], d["ci_high"]], axis=-1),
            hovertemplate="<b>%{y}</b><br>Grant rate %{x:.1%}<br>"
                          "95% CI %{customdata[2]:.1%}–%{customdata[3]:.1%}<br>"
                          "%{customdata[1]:.0f} of %{customdata[0]:.0f} motions"
                          "<extra></extra>",
        )
    )

    fig.add_vline(x=panel_rate, line_dash="dash", line_color=AMBER, line_width=1.4,
                  annotation_text=f"Panel rate {panel_rate:.1%}",
                  annotation_position="top",
                  annotation_font=dict(color=AMBER, size=11))

    fig.update_layout(
        title="Summary Judgment Grant Rate by Judge<br>"
              f"<span style='font-size:13px;color:{MUTED}'>"
              "Bars in coral are statistical outliers · whiskers = 95% Wilson CI"
              "</span>",
        xaxis=dict(title="Share of filed motions granted", tickformat=".0%",
                   range=[0, 0.60]),
        yaxis=dict(title=""), height=660, showlegend=False,
        margin=dict(l=310, r=60, t=110, b=145),
    )

    # Call out the within-venue contrast: same bench, opposite postures.
    # Anchored to the right of JUD-01's bar so it cannot collide with the
    # panel-rate annotation at the top of the plot.
    fig.add_annotation(
        x=d.loc[d["judge_id"] == "JUD-01", "ci_high"].iloc[0],
        y="JUD-01  ·  London Commercial Court",
        text="<b>5.3x JUD-02's grant rate</b><br>on the same bench "
             "(p ≈ 8×10⁻²⁰)",
        showarrow=True, arrowhead=0, arrowcolor=CORAL, arrowwidth=1.2,
        ax=-26, ay=62, xanchor="right",
        font=dict(color=CORAL, size=11.5), align="right",
    )

    caption(fig, -0.235,
            "χ² test of homogeneity across the bench: χ² = 131.9, df = 9, "
            "p ≈ 5×10⁻²⁴ — grant rates are not uniform.<br>"
            "Judges sit in a single venue, so within-venue pairs isolate the "
            "judge effect from the jurisdiction. Synthetic data.")
    save(fig, "chart_judges.html")


# ---------------------------------------------------------------------------
# 3. SURVIVAL CURVES
# ---------------------------------------------------------------------------

def chart_survival(curves: pd.DataFrame, km: pd.DataFrame) -> None:
    fig = go.Figure()

    for level in COMPLEXITY_ORDER:
        sub = curves[curves["complexity"] == level].sort_values("timeline")
        fig.add_trace(go.Scatter(
            x=sub["timeline"], y=sub["survival"], mode="lines", name=level,
            line=dict(color=COMPLEXITY_COLORS[level], width=2.6, shape="hv"),
            hovertemplate=f"<b>{level} complexity</b><br>Day %{{x:.0f}}<br>"
                          "P(still open) %{y:.1%}<extra></extra>",
        ))

    for h in HORIZONS:
        fig.add_vline(x=h, line_dash="dot", line_color="rgba(255,255,255,0.22)",
                      line_width=1)
        fig.add_annotation(x=h, y=1.03, yref="y", text=f"{h}d", showarrow=False,
                           font=dict(color=MUTED, size=10.5))

    # Label two-year survival for each stratum, offset off the curve so the
    # text does not sit on top of the line it describes.
    for _, row in km.iterrows():
        fig.add_annotation(
            x=720, y=row["S_720"], text=f"<b>{row['S_720']:.0%} at 720d</b>",
            showarrow=False, xanchor="left", yanchor="bottom",
            xshift=8, yshift=7,
            font=dict(color=COMPLEXITY_COLORS[row["complexity"]], size=12),
        )

    fig.update_layout(
        title="Probability a Case Remains Open (Kaplan-Meier)<br>"
              f"<span style='font-size:13px;color:{MUTED}'>"
              "Censoring-corrected · includes the 22.7% of cases still live at "
              "snapshot</span>",
        xaxis=dict(title="Days since filing", range=[0, 1100]),
        yaxis=dict(title="P(case still open)", tickformat=".0%",
                   range=[0, 1.08]),
        height=665, hovermode="x unified",
        margin=dict(l=75, r=45, t=95, b=145),
    )

    caption(fig, -0.22,
            "Median time to resolution: Low 270d · Medium 451d · High 782d. "
            "Log-rank across strata χ² = 2,180, p &lt; 0.001.<br>"
            "The High-complexity median is 147 days later than a naive "
            "resolved-cases-only median suggests. Synthetic data.")
    save(fig, "chart_survival.html")


# ---------------------------------------------------------------------------
# 4. FINANCIAL SCATTER
# ---------------------------------------------------------------------------

def chart_financial(df: pd.DataFrame) -> None:
    """Claim vs award.

    Both axes are logarithmic. Claim values span two orders of magnitude and
    awards span more, so a linear y-axis compresses roughly 90% of the cases
    into an unreadable band along the baseline.

    A log y-axis cannot show £0, and zero-recovery cases are a third of the
    resolved docket — dropping them silently would overstate recovery. They get
    their own strip below the main panel instead, so they stay visible and
    countable without distorting the scale.
    """
    res = df[df["event_observed"] == 1].copy()
    res["recovery_ratio"] = res["final_awarded_amount_gbp"] / res["claim_amount_gbp"]

    paid = res[res["final_awarded_amount_gbp"] > 0]
    zero = res[res["final_awarded_amount_gbp"] == 0]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.84, 0.16], vertical_spacing=0.045,
    )

    hover = ("<b>%{customdata[0]}</b> · %{customdata[2]} complexity<br>"
             "Claimed £%{x:,.0f}<br>Awarded £%{y:,.0f}<br>"
             "Recovery %{customdata[1]:.1%}<extra></extra>")

    for disp in ["Settled", "Trial Judgment"]:
        sub = paid[paid["disposition_type"] == disp]
        fig.add_trace(go.Scattergl(
            x=sub["claim_amount_gbp"], y=sub["final_awarded_amount_gbp"],
            mode="markers", name=disp,
            marker=dict(size=5, opacity=0.5, line=dict(width=0),
                        color=DISPOSITION_COLORS[disp]),
            customdata=np.stack([sub["case_id"], sub["recovery_ratio"],
                                 sub["case_complexity"]], axis=-1),
            hovertemplate=hover,
        ), row=1, col=1)

        # Fit in log-log space: the relationship is multiplicative, so a
        # power-law fit is the right functional form. The exponent tells you
        # whether recovery scales proportionally with claim size (b = 1) or
        # decays as claims get larger (b < 1).
        lx, ly = np.log10(sub["claim_amount_gbp"]), np.log10(
            sub["final_awarded_amount_gbp"])
        b, a = np.polyfit(lx, ly, 1)
        r2 = np.corrcoef(lx, ly)[0, 1] ** 2
        xs = np.logspace(lx.min(), lx.max(), 120)
        fig.add_trace(go.Scatter(
            x=xs, y=10 ** a * xs ** b, mode="lines", showlegend=False,
            line=dict(color=DISPOSITION_COLORS[disp], width=2.8),
            hovertemplate=f"<b>{disp} power-law fit</b><br>"
                          f"exponent = {b:.3f}<br>R² = {r2:.3f}<extra></extra>",
        ), row=1, col=1)

    # Full-recovery reference. Plotted across many points, not two: a straight
    # y = x line drawn from two endpoints renders as a chord in log space and
    # sits in the wrong place.
    lo, hi = res["claim_amount_gbp"].min(), res["claim_amount_gbp"].max()
    ref = np.logspace(np.log10(lo), np.log10(hi), 120)
    fig.add_trace(go.Scatter(
        x=ref, y=ref, mode="lines", name="100% recovery",
        line=dict(color="rgba(255,255,255,0.30)", width=1.2, dash="dash"),
        hoverinfo="skip",
    ), row=1, col=1)

    # Zero-recovery strip, jittered vertically for density.
    jitter = np.random.default_rng(7).uniform(-1, 1, len(zero))
    for disp, colour in [("Dismissed", MUTED), ("Trial Judgment", VIOLET)]:
        m = (zero["disposition_type"] == disp).to_numpy()
        if not m.any():
            continue
        fig.add_trace(go.Scattergl(
            x=zero.loc[m, "claim_amount_gbp"], y=jitter[m], mode="markers",
            name=f"{disp} — £0 recovered", legendgroup=f"zero-{disp}",
            marker=dict(size=4.5, opacity=0.45, line=dict(width=0), color=colour),
            customdata=np.stack([zero.loc[m, "case_id"],
                                 zero.loc[m, "case_complexity"]], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]} complexity"
                          "<br>Claimed £%{x:,.0f}<br>Recovered £0<extra></extra>",
        ), row=2, col=1)

    fig.update_xaxes(type="log", tickprefix="£", row=1, col=1)
    fig.update_xaxes(type="log", tickprefix="£", row=2, col=1,
                     title_text="Amount claimed (£, log scale)")
    fig.update_yaxes(type="log", tickprefix="£", row=1, col=1,
                     title_text="Final award (£, log scale)")
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False,
                     range=[-2.6, 2.6], row=2, col=1,
                     title_text="£0", title_font=dict(color=MUTED, size=12))

    fig.add_annotation(
        text=f"<b>{len(zero):,} total-loss cases</b> "
             f"({len(zero) / len(res):.0%} of resolved docket)",
        xref="paper", yref="paper", x=0.995, y=0.135, showarrow=False,
        xanchor="right", font=dict(color=MUTED, size=11),
    )

    fig.update_layout(
        title="Claim Value vs Final Award by Disposition<br>"
              f"<span style='font-size:13px;color:{MUTED}'>"
              "Resolved cases · log-log scale · power-law fit per disposition · "
              "dashed line = full recovery</span>",
        height=680, margin=dict(l=85, r=45, t=110, b=125),
        legend=dict(orientation="h", yanchor="bottom", y=1.015,
                    xanchor="right", x=1),
    )

    caption(fig, -0.20,
            "Zero-recovery cases cannot be shown on a log axis, so they sit in "
            "the strip below rather than being dropped: every dismissal and 36% "
            "of trial judgments recover nothing.<br>"
            "Portfolio-wide recovery is £0.269 per £1 claimed — the aggregate "
            "ratio, not the mean of per-case ratios. Synthetic data.")
    save(fig, "chart_financial.html")


# ---------------------------------------------------------------------------

def build_index(names: list[str]) -> None:
    """Contact sheet for previewing all four charts locally before embedding."""
    cards = "\n".join(
        f'  <section><iframe src="{n}" loading="lazy"></iframe></section>'
        for n in names
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Litigation Analytics — Chart Preview</title>
<style>
  body {{ margin:0; padding:32px; background:{INK}; color:{TEXT};
         font-family:{FONT}; }}
  h1 {{ font-size:20px; font-weight:600; margin:0 0 4px; }}
  p  {{ color:{MUTED}; font-size:13px; margin:0 0 28px; }}
  section {{ margin-bottom:28px; border:1px solid rgba(255,255,255,0.08);
             border-radius:10px; overflow:hidden; }}
  iframe {{ width:100%; height:640px; border:0; display:block; }}
</style></head><body>
<h1>Litigation &amp; Court Data Analytics</h1>
<p>Local preview of the four embeddable charts. Synthetic data.</p>
{cards}
</body></html>"""
    path = os.path.join(CHART_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [saved] {path}")


if __name__ == "__main__":
    df = pd.read_csv(DATA_FILE, parse_dates=["filing_date", "disposition_date"])
    judges = pd.read_csv(os.path.join(RESULTS_DIR, "judge_grant_rates.csv"))
    curves = pd.read_csv(os.path.join(RESULTS_DIR, "km_curves.csv"))
    km = pd.read_csv(os.path.join(RESULTS_DIR, "km_survival_summary.csv"))

    panel_rate = (df.loc[df["summary_judgment_filed"], "summary_judgment_granted"]
                    .mean())

    print("Building charts...")
    chart_duration(df)
    chart_judges(judges, panel_rate)
    chart_survival(curves, km)
    chart_financial(df)
    build_index(["chart_duration.html", "chart_judges.html",
                 "chart_survival.html", "chart_financial.html"])
    print(f"\nDone. Open {CHART_DIR}/index.html to preview all four.")
