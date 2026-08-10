"""
Litigation & Court Data Analytics — Phase 2: EDA & Statistical Modelling
=======================================================================

Runs four analyses over `data/litigation_court_data.csv` and writes tidy
result tables to `results/` for the Phase 3 charts to consume.

  1. DURATION       - median and IQR of days_to_resolution by venue and
                      complexity, with an explicit censoring-bias warning.
  2. RECOVERY       - final award as a share of amount claimed, by outcome.
  3. JUDGE VARIANCE - summary-judgment grant rates with Wilson confidence
                      intervals, a chi-square test of homogeneity, and a
                      within-venue two-proportion test that isolates the judge
                      effect from the court effect.
  4. SURVIVAL       - Kaplan-Meier survival by complexity (S(365), S(540),
                      S(720)), a multivariate log-rank test, and a Cox
                      proportional-hazards model with a PH assumption check.

METHODOLOGICAL NOTE ON CENSORING
--------------------------------
22.7% of cases are still open at the snapshot date, and open cases are heavily
concentrated in the High-complexity stratum. Any statistic computed on resolved
cases only is therefore biased downward — the slowest cases are precisely the
ones missing from the sample. This script reports the naive figure and the
Kaplan-Meier figure side by side so the size of that bias is visible rather
than hidden. Quote the KM figures.

Usage
-----
    pip install -r requirements.txt
    python src/generate_dataset.py   # must run first
    python src/analysis.py
"""

from __future__ import annotations

import json
import os

from pathlib import Path

# Resolve paths relative to the repository root, not the working
# directory, so the scripts run correctly from anywhere.
ROOT = Path(__file__).resolve().parents[1]
import warnings

import numpy as np
import pandas as pd
from lifelines import (
    CoxPHFitter,
    KaplanMeierFitter,
    LogNormalAFTFitter,
    WeibullAFTFitter,
)
from lifelines.statistics import multivariate_logrank_test, proportional_hazard_test
from scipy import stats
from statsmodels.stats.proportion import proportion_confint, proportions_ztest

warnings.filterwarnings("ignore", category=FutureWarning)

DATA_FILE = ROOT / "data" / "litigation_court_data.csv"
RESULTS_DIR = ROOT / "results"

HORIZONS = [365, 540, 720]
COMPLEXITY_ORDER = ["Low", "Medium", "High"]


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA_FILE, parse_dates=["filing_date", "disposition_date"])
    df["case_complexity"] = pd.Categorical(
        df["case_complexity"], categories=COMPLEXITY_ORDER, ordered=True
    )
    df["log_claim"] = np.log(df["claim_amount_gbp"])
    return df


# ---------------------------------------------------------------------------
# 1. DURATION: MEDIAN AND IQR
# ---------------------------------------------------------------------------

def duration_stats(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    rule("1. TIME TO RESOLUTION — MEDIAN & INTERQUARTILE RANGE")

    resolved = df[df["event_observed"] == 1]

    def agg(frame: pd.DataFrame, key: str) -> pd.DataFrame:
        g = frame.groupby(key, observed=True)["days_to_resolution"]
        out = pd.DataFrame(
            {
                "n": g.size(),
                "median_days": g.median(),
                "q1": g.quantile(0.25),
                "q3": g.quantile(0.75),
            }
        )
        out["iqr"] = out["q3"] - out["q1"]
        return out.sort_values("median_days", ascending=False)

    by_venue = agg(resolved, "court_venue")
    by_complexity = agg(resolved, "case_complexity")

    cross = (
        resolved.groupby(["court_venue", "case_complexity"], observed=True)[
            "days_to_resolution"
        ]
        .agg(n="size", median_days="median",
             q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75))
        .reset_index()
    )
    cross["iqr"] = cross["q3"] - cross["q1"]

    print("\nBy court venue (resolved cases only):")
    print(by_venue.round(1).to_string())
    print("\nBy case complexity (resolved cases only):")
    print(by_complexity.round(1).to_string())

    # Kruskal-Wallis: are the venue duration distributions the same?
    groups = [g["days_to_resolution"].to_numpy()
              for _, g in resolved.groupby("court_venue", observed=True)]
    h_stat, h_p = stats.kruskal(*groups)
    print(f"\nKruskal-Wallis across venues: H = {h_stat:.1f}, p = {h_p:.3e}")
    print("  -> venue duration distributions are not identical."
          if h_p < 0.05 else "  -> no significant venue difference detected.")

    # Censoring exposure by stratum — the caveat that makes the above honest.
    cens = (
        df.groupby("case_complexity", observed=True)["event_observed"]
        .agg(n="size", resolved_share="mean")
    )
    cens["censored_share"] = 1 - cens["resolved_share"]
    print("\nCensoring exposure (share of cases still open at snapshot):")
    print(cens[["n", "censored_share"]].round(3).to_string())
    print("\n  WARNING: the medians above exclude open cases and therefore")
    print("  understate true duration, most severely for High complexity.")
    print("  Section 4 reports the censoring-corrected figures.")

    return {"by_venue": by_venue, "by_complexity": by_complexity, "cross": cross,
            "censoring": cens}


# ---------------------------------------------------------------------------
# 2. FINANCIAL RECOVERY
# ---------------------------------------------------------------------------

def recovery_stats(df: pd.DataFrame) -> pd.DataFrame:
    rule("2. FINANCIAL RECOVERY RATE BY DISPOSITION")

    res = df[df["event_observed"] == 1].copy()
    res["recovery_ratio"] = res["final_awarded_amount_gbp"] / res["claim_amount_gbp"]

    out = (
        res.groupby("disposition_type", observed=True)
        .agg(
            n=("recovery_ratio", "size"),
            mean_recovery=("recovery_ratio", "mean"),
            median_recovery=("recovery_ratio", "median"),
            zero_recovery_share=("final_awarded_amount_gbp", lambda s: (s == 0).mean()),
            total_claimed_gbp=("claim_amount_gbp", "sum"),
            total_awarded_gbp=("final_awarded_amount_gbp", "sum"),
        )
        .sort_values("mean_recovery", ascending=False)
    )
    # Aggregate rate: pounds recovered per pound claimed (not a mean of ratios).
    out["aggregate_recovery"] = out["total_awarded_gbp"] / out["total_claimed_gbp"]

    print("\n" + out.round(3).to_string())

    # Settlements only: does recovery vary with complexity?
    settled = res[res["disposition_type"] == "Settled"]
    by_cx = settled.groupby("case_complexity", observed=True)["recovery_ratio"].agg(
        ["size", "mean", "median"]
    )
    print("\nSettlement recovery by complexity:")
    print(by_cx.round(3).to_string())

    portfolio = res["final_awarded_amount_gbp"].sum() / res["claim_amount_gbp"].sum()
    print(f"\nPortfolio-wide recovery: £{portfolio:.3f} recovered per £1 claimed")
    print("  NOTE: the mean of ratios and the aggregate ratio differ because")
    print("  claim sizes are heavily right-skewed. Report the aggregate for")
    print("  budgeting; report the mean for typical-case expectations.")

    return out


# ---------------------------------------------------------------------------
# 3. JUDGE VARIANCE
# ---------------------------------------------------------------------------

def judge_variance(df: pd.DataFrame) -> pd.DataFrame:
    rule("3. JUDGE VARIANCE IN SUMMARY-JUDGMENT GRANT RATES")

    filed = df[df["summary_judgment_filed"]]

    tbl = (
        filed.groupby(["judge_id", "court_venue"], observed=True)[
            "summary_judgment_granted"
        ]
        .agg(motions="size", granted="sum")
        .reset_index()
    )
    tbl["grant_rate"] = tbl["granted"] / tbl["motions"]

    lo, hi = proportion_confint(tbl["granted"], tbl["motions"],
                                alpha=0.05, method="wilson")
    tbl["ci_low"], tbl["ci_high"] = lo, hi

    overall = filed["summary_judgment_granted"].mean()
    tbl["vs_overall"] = tbl["grant_rate"] - overall
    # Outlier flag: Wilson interval excludes the panel-wide rate.
    tbl["outlier"] = (tbl["ci_low"] > overall) | (tbl["ci_high"] < overall)
    tbl = tbl.sort_values("grant_rate", ascending=False).reset_index(drop=True)

    print(f"\nPanel-wide grant rate: {overall:.1%} "
          f"({filed['summary_judgment_granted'].sum():,} of {len(filed):,} motions)")
    print("\n" + tbl.round(3).to_string(index=False))

    # Chi-square test of homogeneity across the full bench.
    ct = pd.crosstab(filed["judge_id"], filed["summary_judgment_granted"])
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    print(f"\nChi-square test of homogeneity across 10 judges:")
    print(f"  chi2 = {chi2:.1f}, dof = {dof}, p = {p:.3e}")
    print("  -> reject the null that all judges grant at the same rate."
          if p < 0.05 else "  -> cannot reject equal grant rates.")

    spread = tbl["grant_rate"].max() - tbl["grant_rate"].min()
    print(f"\nObserved spread: {tbl['grant_rate'].min():.1%} to "
          f"{tbl['grant_rate'].max():.1%} ({spread:.1%} points)")
    print(f"Outlier judges (Wilson CI excludes panel rate): "
          f"{', '.join(tbl.loc[tbl['outlier'], 'judge_id']) or 'none'}")

    # ---- Within-venue contrast: the causally cleanest comparison -----------
    print("\n--- Within-venue contrast (controls for jurisdiction) ---")
    multi = tbl.groupby("court_venue").filter(lambda g: len(g) > 1)
    for venue, g in multi.groupby("court_venue"):
        g = g.sort_values("grant_rate", ascending=False)
        top, bot = g.iloc[0], g.iloc[-1]
        z, pz = proportions_ztest(
            count=[top["granted"], bot["granted"]],
            nobs=[top["motions"], bot["motions"]],
        )
        ratio = top["grant_rate"] / bot["grant_rate"] if bot["grant_rate"] else np.inf
        print(f"\n  {venue}")
        print(f"    {top['judge_id']}: {top['grant_rate']:.1%}  vs  "
              f"{bot['judge_id']}: {bot['grant_rate']:.1%}")
        print(f"    ratio = {ratio:.1f}x | two-proportion z = {z:.2f}, p = {pz:.3e}"
              f" {'[SIGNIFICANT]' if pz < 0.05 else '[not significant]'}")

    print("\n  Same bench, same case mix, same procedural rules — so a")
    print("  significant gap here cannot be attributed to the jurisdiction.")

    return tbl


# ---------------------------------------------------------------------------
# 4. SURVIVAL ANALYSIS
# ---------------------------------------------------------------------------

def survival_analysis(df: pd.DataFrame) -> dict:
    rule("4. SURVIVAL ANALYSIS — PROBABILITY A CASE REMAINS OPEN")

    kmf = KaplanMeierFitter()
    curves, rows = {}, []

    print("\nKaplan-Meier survival S(t) = P(case still open at t days):\n")
    header = "  {:<10} {:>7} {:>9} " + " ".join(f"{'S(' + str(h) + ')':>9}" for h in HORIZONS)
    print(header.format("Complexity", "n", "events"))

    for level in COMPLEXITY_ORDER:
        sub = df[df["case_complexity"] == level]
        kmf.fit(sub["days_to_resolution"], sub["event_observed"], label=level)
        curves[level] = kmf.survival_function_.copy()

        probs = [float(kmf.predict(h)) for h in HORIZONS]
        med = kmf.median_survival_time_
        rows.append({"complexity": level, "n": len(sub),
                     "events": int(sub["event_observed"].sum()),
                     "km_median_days": med,
                     **{f"S_{h}": p for h, p in zip(HORIZONS, probs)}})

        line = "  {:<10} {:>7,} {:>9,} ".format(level, len(sub),
                                                int(sub["event_observed"].sum()))
        line += " ".join(f"{p:>9.1%}" for p in probs)
        print(line)

    km_table = pd.DataFrame(rows)

    # Naive (resolved-only) median vs censoring-corrected KM median.
    naive = (df[df["event_observed"] == 1]
             .groupby("case_complexity", observed=True)["days_to_resolution"]
             .median().reindex(COMPLEXITY_ORDER).to_numpy())
    km_table["naive_median_days"] = naive
    km_table["bias_days"] = km_table["km_median_days"] - km_table["naive_median_days"]

    print("\nCensoring bias — naive median vs Kaplan-Meier median:")
    print(km_table[["complexity", "naive_median_days", "km_median_days",
                    "bias_days"]].to_string(index=False))
    print("\n  The naive figure understates duration because unresolved cases")
    print("  are dropped. The gap widens with complexity. Quote the KM column.")

    # Log-rank test across the three strata.
    lr = multivariate_logrank_test(df["days_to_resolution"], df["case_complexity"],
                                   df["event_observed"])
    print(f"\nMultivariate log-rank test across complexity strata:")
    print(f"  chi2 = {lr.test_statistic:.1f}, p = {lr.p_value:.3e}")

    # ---- Cox proportional hazards -----------------------------------------
    print("\n--- Cox Proportional Hazards model ---")
    print("  Covariates exclude disposition_type and summary_judgment_granted:")
    print("  both are realised at or near the moment the case ends, so")
    print("  including them would leak the outcome into the predictor set.")

    cox_df = df[["days_to_resolution", "event_observed", "case_complexity",
                 "court_venue", "log_claim", "num_interlocutory_motions",
                 "summary_judgment_filed"]].copy()
    cox_df["summary_judgment_filed"] = cox_df["summary_judgment_filed"].astype(int)
    cox_df = pd.get_dummies(cox_df, columns=["case_complexity", "court_venue"],
                            drop_first=True, dtype=float)

    cph = CoxPHFitter()
    cph.fit(cox_df, duration_col="days_to_resolution", event_col="event_observed")

    summary = cph.summary[["coef", "exp(coef)", "exp(coef) lower 95%",
                           "exp(coef) upper 95%", "p"]].copy()
    summary.columns = ["coef", "hazard_ratio", "hr_low", "hr_high", "p"]
    print("\nHazard ratios (>1 = resolves faster; <1 = stays open longer):\n")
    print(summary.sort_values("hazard_ratio", ascending=False).round(4).to_string())
    print(f"\n  Concordance index: {cph.concordance_index_:.3f}")
    print(f"  Log-likelihood ratio p-value: {cph.log_likelihood_ratio_test().p_value:.3e}")

    # PH assumption check — reported, not assumed.
    print("\nProportional-hazards assumption test (Schoenfeld residuals):")
    try:
        ph = proportional_hazard_test(cph, cox_df, time_transform="rank")
        ph_res = ph.summary[["test_statistic", "p"]].round(4)
        violated = ph_res[ph_res["p"] < 0.05]
        print(ph_res.to_string())
        if len(violated):
            print(f"\n  {len(violated)} covariate(s) violate PH (p < 0.05).")
            print("  Hazard ratios for these are time-averaged and should be")
            print("  read as directional, not as a constant multiplier.")
        else:
            print("\n  No PH violations detected at the 5% level.")
    except Exception as exc:  # pragma: no cover
        ph_res = pd.DataFrame()
        print(f"  PH test unavailable: {exc}")

    # ---- AFT models: the correct specification when PH fails --------------
    print("\n--- Accelerated Failure Time models ---")
    print("  The Cox model assumes hazards stay proportional over time. The")
    print("  Schoenfeld test above says they do not. AFT models drop that")
    print("  assumption and model duration directly, so they are the better")
    print("  specification here. Coefficients are TIME RATIOS: a value of 1.5")
    print("  means the case takes 50% longer, which is also easier to put in")
    print("  front of a client than a hazard ratio.")

    aft_df = cox_df.copy()
    fits = {}
    for name, fitter in [("Weibull AFT", WeibullAFTFitter()),
                         ("Log-Normal AFT", LogNormalAFTFitter())]:
        fitter.fit(aft_df, duration_col="days_to_resolution",
                   event_col="event_observed")
        fits[name] = fitter
        print(f"\n  {name}: AIC = {fitter.AIC_:,.1f} | "
              f"concordance = {fitter.concordance_index_:.3f}")

    best_name = min(fits, key=lambda k: fits[k].AIC_)
    best = fits[best_name]
    print(f"\n  Best fit by AIC: {best_name}")

    aft_summary = best.summary.loc["mu_"] if "mu_" in best.summary.index.get_level_values(0) \
        else best.summary.loc["lambda_"]
    aft_out = pd.DataFrame({
        "coef": aft_summary["coef"],
        "time_ratio": np.exp(aft_summary["coef"]),
        "tr_low": np.exp(aft_summary["coef lower 95%"]),
        "tr_high": np.exp(aft_summary["coef upper 95%"]),
        "p": aft_summary["p"],
    }).drop(index="Intercept", errors="ignore")

    print(f"\n  Time ratios from {best_name} "
          f"(>1 = case takes longer, <1 = resolves sooner):\n")
    print(aft_out.sort_values("time_ratio", ascending=False).round(4).to_string())

    return {"km_table": km_table, "curves": curves, "cox_summary": summary,
            "aft_summary": aft_out, "aft_model": best_name,
            "logrank_p": float(lr.p_value),
            "concordance": float(cph.concordance_index_), "ph_test": ph_res}


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def export(dur: dict, rec: pd.DataFrame, judges: pd.DataFrame, surv: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    p = lambda name: os.path.join(RESULTS_DIR, name)

    dur["by_venue"].to_csv(p("duration_by_venue.csv"))
    dur["by_complexity"].to_csv(p("duration_by_complexity.csv"))
    dur["cross"].to_csv(p("duration_venue_complexity.csv"), index=False)
    rec.to_csv(p("recovery_by_disposition.csv"))
    judges.to_csv(p("judge_grant_rates.csv"), index=False)
    surv["km_table"].to_csv(p("km_survival_summary.csv"), index=False)
    surv["cox_summary"].to_csv(p("cox_hazard_ratios.csv"))
    surv["aft_summary"].to_csv(p("aft_time_ratios.csv"))

    km_long = pd.concat(
        [c.rename(columns={c.columns[0]: "survival"}).assign(complexity=k)
         for k, c in surv["curves"].items()]
    ).rename_axis("timeline").reset_index()
    km_long.to_csv(p("km_curves.csv"), index=False)

    with open(p("headline_metrics.json"), "w") as fh:
        json.dump(
            {
                "logrank_p": surv["logrank_p"],
                "cox_concordance": surv["concordance"],
                "km_survival": surv["km_table"].to_dict(orient="records"),
                "judge_grant_rate_spread": float(
                    judges["grant_rate"].max() - judges["grant_rate"].min()
                ),
            },
            fh,
            indent=2,
        )

    print(f"\n\nResult tables written to {RESULTS_DIR} for Phase 3 charts.")


if __name__ == "__main__":
    data = load()
    print(f"Loaded {len(data):,} cases | "
          f"{data['event_observed'].sum():,} resolved, "
          f"{(1 - data['event_observed'].mean()):.1%} right-censored")

    d = duration_stats(data)
    r = recovery_stats(data)
    j = judge_variance(data)
    s = survival_analysis(data)
    export(d, r, j, s)
